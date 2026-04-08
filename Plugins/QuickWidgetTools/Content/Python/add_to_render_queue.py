import importlib
import os
import re

import unreal


LOG_PREFIX = "[AddToRenderQueue]"
MRG_SETTINGS_FOLDER = "/QuickWidgetTools/Misc/MRGSettings"
SHOT_NAME_PATTERN = re.compile(r"^([A-Za-z0-9]+)_(\d{3})_(\d{4,})$")
EXPECTED_GRAPH_CLASS_NAMES = {"MovieGraphConfig", "MovieGraphConfigBase"}
EXPECTED_SHOT_DATA_CLASS_HINTS = {
    "BP_ShotDataAsset",
    "BP_ShotDataAsset_C",
    "PrimaryDataAsset",
    "DataAsset",
}
ASSOCIATED_LEVEL_PROPERTY_CANDIDATES = [
    "AssociatedLevel",
    "associated_level",
    "Level",
    "LevelAssociation",
    "AssociatedLevelStored",
]
OUTPUT_VARIABLE_NAME = "OutputDirectory"
FILE_NAME_VARIABLE_NAME = "FileNameFormat"
RENDER_CONTEXT_SEGMENTS = ["lite", "unreal", "_output"]
VERSION_PATTERN_TEMPLATE = r"^{prefix}_v(\d{{3}})$"
DEFAULT_VERSION_NUMBER = 1


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_warning(message):
    unreal.log_warning(f"{LOG_PREFIX} Warning: {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} Error: {message}")


def _clean_package_path(path_text):
    text = str(path_text or "").strip()
    if not text:
        return ""

    text = text.replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")

    if len(text) > 1:
        text = text.rstrip("/")

    return text


def _join_package_path(*parts):
    cleaned_parts = []
    for part in parts:
        text = _clean_package_path(part)
        if not text:
            continue
        if cleaned_parts:
            text = text.lstrip("/")
        cleaned_parts.append(text)

    if not cleaned_parts:
        return ""

    return _clean_package_path("/".join(cleaned_parts))


def _normalize_asset_object_path(path_or_object_path):
    text = str(path_or_object_path or "").strip()
    if not text:
        return ""

    if text.startswith("SoftObjectPath(") and text.endswith(")"):
        text = text[len("SoftObjectPath("):-1].strip().strip("\"'")

    text = text.replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")

    if text.startswith("/Game/") or text.startswith("/QuickWidgetTools/"):
        return text

    return ""


def _asset_object_path_from_package_path(package_path):
    package_path = _clean_package_path(package_path)
    if not package_path:
        return ""

    asset_name = package_path.rsplit("/", 1)[-1]
    return f"{package_path}.{asset_name}"


def _sanitize_shot_name(value):
    if value is None:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", str(value))
    return cleaned.upper()


def _sanitize_graph_name(value):
    if value is None:
        return ""
    return re.sub(r"[^A-Za-z0-9_]", "", str(value)).strip()


def _is_shot_name_valid(shot_name):
    return bool(SHOT_NAME_PATTERN.fullmatch(shot_name))


def _derive_sequence_prefix(shot_name):
    match = SHOT_NAME_PATTERN.fullmatch(shot_name)
    if not match:
        return ""
    return match.group(1).upper()


def _coerce_to_bool_flag(value):
    if isinstance(value, bool):
        return value
    try:
        return int(value) != 0
    except Exception:
        return False


def _coerce_to_object_path(value):
    if value is None:
        return ""

    if isinstance(value, str):
        return _normalize_asset_object_path(value)

    if isinstance(value, unreal.SoftObjectPath):
        return _normalize_asset_object_path(value.to_string())

    for getter_name in ("get_asset_path_name", "get_path_name", "to_string"):
        getter = getattr(value, getter_name, None)
        if callable(getter):
            try:
                raw_value = getter()
            except Exception:
                continue
            object_path = _normalize_asset_object_path(raw_value)
            if object_path:
                return object_path

    try:
        as_text = str(value)
    except Exception:
        return ""

    return _normalize_asset_object_path(as_text)


def _new_result(movie_render_graph_name):
    return {
        "success": True,
        "jobs_added": 0,
        "jobs_skipped": 0,
        "jobs_output_configured": 0,
        "missing_shots": [],
        "missing_data_assets": [],
        "missing_levels": [],
        "invalid_shots": [],
        "duplicate_active_shots": [],
        "output_config_failures": [],
        "movie_render_graph": str(movie_render_graph_name or ""),
        "message": "",
    }


def _finalize_result(result, success=None, message=None):
    if success is not None:
        result["success"] = bool(success)
    if message is not None:
        result["message"] = str(message)
    return result


def _format_summary_string(result):
    def _join(values):
        return ",".join(str(value) for value in values) if values else ""

    return (
        f"success={1 if result.get('success') else 0};"
        f"jobs_added={int(result.get('jobs_added', 0))};"
        f"jobs_skipped={int(result.get('jobs_skipped', 0))};"
        f"jobs_output_configured={int(result.get('jobs_output_configured', 0))};"
        f"missing_shots={_join(result.get('missing_shots', []))};"
        f"missing_data_assets={_join(result.get('missing_data_assets', []))};"
        f"missing_levels={_join(result.get('missing_levels', []))};"
        f"invalid_shots={_join(result.get('invalid_shots', []))};"
        f"duplicate_active_shots={_join(result.get('duplicate_active_shots', []))};"
        f"output_config_failures={_join(result.get('output_config_failures', []))};"
        f"movie_render_graph={result.get('movie_render_graph', '')};"
        f"message={result.get('message', '')}"
    )


def _get_asset_class_names(asset_object):
    class_names = set()
    try:
        class_object = asset_object.get_class()
    except Exception:
        class_object = None

    while class_object:
        try:
            class_name = class_object.get_name()
        except Exception:
            class_name = ""
        if class_name:
            class_names.add(class_name)
            if class_name.endswith("_C"):
                class_names.add(class_name[:-2])
        try:
            class_object = class_object.get_super_class()
        except Exception:
            break

    return class_names


def _list_valid_show_folders():
    editor_asset_lib = unreal.EditorAssetLibrary
    root_assets = editor_asset_lib.list_assets("/Game", recursive=False, include_folder=True)

    show_folders = []
    for entry in root_assets:
        entry = _clean_package_path(entry)
        if not entry.startswith("/Game/_"):
            continue
        if "." in entry:
            continue

        marker_asset_path = _join_package_path(entry, "_showholder")
        if editor_asset_lib.does_asset_exist(marker_asset_path):
            show_folders.append(entry)

    show_folders.sort()
    return show_folders


def _find_level_sequence_asset_path(shot_name):
    sequence_prefix = _derive_sequence_prefix(shot_name)
    if not sequence_prefix:
        return ""

    editor_asset_lib = unreal.EditorAssetLibrary

    for show_folder in _list_valid_show_folders():
        package_path = _join_package_path(show_folder, "Sequences", sequence_prefix, shot_name)
        object_path = _asset_object_path_from_package_path(package_path)

        _log(f"Checking shot package path: {package_path}")
        _log(f"Checking shot object path: {object_path}")

        if not editor_asset_lib.does_asset_exist(object_path):
            continue

        loaded_asset = unreal.load_asset(object_path)
        if not loaded_asset:
            continue

        if not isinstance(loaded_asset, unreal.LevelSequence):
            try:
                loaded_class_name = loaded_asset.get_class().get_name()
            except Exception:
                loaded_class_name = "Unknown"
            _log_warning(
                f"Found '{object_path}' but it is not a LevelSequence (type={loaded_class_name})."
            )
            continue

        _log(f"Resolved shot sequence for '{shot_name}': {object_path}")
        return object_path

    return ""


def _build_shot_data_asset_candidate_paths(level_sequence_object_path, shot_name):
    sequence_package_path = _clean_package_path(str(level_sequence_object_path).split(".", 1)[0])
    data_asset_name = f"{shot_name}_Data"

    direct_package_path = _join_package_path(sequence_package_path, data_asset_name)
    direct_object_path = _asset_object_path_from_package_path(direct_package_path)

    nested_shot_folder_path = _join_package_path(sequence_package_path, shot_name)
    nested_package_path = _join_package_path(nested_shot_folder_path, data_asset_name)
    nested_object_path = _asset_object_path_from_package_path(nested_package_path)

    return [direct_object_path, nested_object_path]


def _load_shot_data_asset_for_shot(level_sequence_object_path, shot_name):
    editor_asset_lib = unreal.EditorAssetLibrary
    candidate_paths = _build_shot_data_asset_candidate_paths(level_sequence_object_path, shot_name)

    for candidate_path in candidate_paths:
        if not candidate_path:
            continue

        _log(f"Checking shot data asset path: {candidate_path}")

        if not editor_asset_lib.does_asset_exist(candidate_path):
            continue

        asset = unreal.load_asset(candidate_path)
        if not asset:
            _log_warning(f"Shot data asset exists but failed to load: {candidate_path}")
            continue

        class_names = _get_asset_class_names(asset)
        _log(
            f"Resolved shot data asset for '{shot_name}': {candidate_path} "
            f"(classes={sorted(class_names)})"
        )

        if EXPECTED_SHOT_DATA_CLASS_HINTS and not any(
            hint in class_names for hint in EXPECTED_SHOT_DATA_CLASS_HINTS
        ):
            _log_warning(
                f"Loaded shot data asset for '{shot_name}' but class looked unusual: {sorted(class_names)}"
            )

        return asset, candidate_path

    return None, candidate_paths[0] if candidate_paths else ""


def _extract_associated_level_object_path(shot_data_asset):
    for property_name in ASSOCIATED_LEVEL_PROPERTY_CANDIDATES:
        try:
            value = shot_data_asset.get_editor_property(property_name)
        except Exception:
            continue

        object_path = _coerce_to_object_path(value)
        if object_path:
            _log(f"Resolved AssociatedLevel via property '{property_name}': {object_path}")
            return object_path

        _log(f"Property '{property_name}' exists but did not contain a usable object path: {value}")

    try:
        all_properties = shot_data_asset.get_editor_property_names()
        _log_warning(
            "AssociatedLevel not found. Available properties: "
            + str(sorted(str(p) for p in all_properties))
        )
    except Exception:
        pass

    return ""


def _find_movie_render_graph_asset(movie_render_graph_name):
    requested_name = str(movie_render_graph_name or "").strip()
    if not requested_name:
        _log_error("Movie Render Graph name was empty.")
        return None

    editor_asset_lib = unreal.EditorAssetLibrary
    if not editor_asset_lib.does_directory_exist(MRG_SETTINGS_FOLDER):
        _log_error(f"Movie Render Graph folder not found: {MRG_SETTINGS_FOLDER}")
        return None

    asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()
    candidates = editor_asset_lib.list_assets(MRG_SETTINGS_FOLDER, recursive=True, include_folder=False)

    for object_path in candidates:
        leaf_name = object_path.rsplit("/", 1)[-1]
        asset_name = leaf_name.split(".", 1)[0]
        if asset_name != requested_name:
            continue

        registry_class_name = ""
        try:
            asset_data = asset_registry.get_asset_by_object_path(unreal.Name(object_path))
        except Exception:
            asset_data = None

        if asset_data and asset_data.is_valid():
            try:
                registry_class_name = str(asset_data.asset_class_path.asset_name)
            except Exception:
                registry_class_name = ""

        graph_asset = unreal.load_asset(object_path)
        if not graph_asset:
            continue

        try:
            loaded_class_name = graph_asset.get_class().get_name()
        except Exception:
            loaded_class_name = ""

        class_names = _get_asset_class_names(graph_asset)
        if registry_class_name:
            class_names.add(registry_class_name)
        if loaded_class_name:
            class_names.add(loaded_class_name)

        _log(
            f"Matched graph asset candidate: path='{object_path}', "
            f"registry_class='{registry_class_name}', loaded_class='{loaded_class_name}', "
            f"all_classes={sorted(class_names)}"
        )

        if not any(class_name in EXPECTED_GRAPH_CLASS_NAMES for class_name in class_names):
            _log_warning(
                f"Asset name matched '{requested_name}' but class did not match expected Movie Render Graph classes."
            )
            continue

        _log(f"Resolved Movie Render Graph asset '{requested_name}' -> {object_path}")
        return graph_asset

    _log_error(f"Could not find Movie Render Graph asset named '{requested_name}' in {MRG_SETTINGS_FOLDER}")
    return None


def _remove_job_from_queue(queue_subsystem, job):
    if not queue_subsystem or not job:
        return

    removal_candidates = [
        (queue_subsystem.get_queue(), "delete_job"),
        (queue_subsystem.get_queue(), "remove_job"),
        (queue_subsystem, "delete_job"),
        (queue_subsystem, "remove_job"),
    ]

    for target, method_name in removal_candidates:
        if not target:
            continue
        method = getattr(target, method_name, None)
        if not callable(method):
            continue
        try:
            method(job)
            _log(f"Removed partially-configured queue job via {type(target).__name__}.{method_name}().")
            return
        except Exception:
            continue

    _log_warning("Could not remove partially-configured queue job with available removal methods.")


def _assign_job_name(job, shot_name):
    job_name = str(shot_name or "").strip()
    if not job_name:
        _log_warning("Skipping queue job name assignment because shot name was blank.")
        return False

    property_candidates = [
        "job_name",
        "sequence_name",
        "name",
    ]

    for property_name in property_candidates:
        try:
            job.set_editor_property(property_name, job_name)
            try:
                current_value = job.get_editor_property(property_name)
            except Exception:
                current_value = job_name

            _log(f"Assigned queue job name via property '{property_name}': {current_value}")
            return True
        except Exception:
            continue

    setter = getattr(job, "set_job_name", None)
    if callable(setter):
        try:
            setter(job_name)
            _log(f"Assigned queue job name via set_job_name(): {job_name}")
            return True
        except Exception:
            pass

    _log_warning(f"Could not assign queue job name for shot '{job_name}' with available job properties.")
    return False


def _assign_job_sequence_and_map(job, sequence_object_path, map_object_path):
    try:
        sequence_soft_path = unreal.SoftObjectPath(sequence_object_path)
        job.set_editor_property("sequence", sequence_soft_path)
        _log(f"Assigned queue job sequence SoftObjectPath: {sequence_object_path}")
    except Exception as exc:
        _log_error(f"Failed to assign sequence on queue job: {exc}")
        return False

    try:
        map_soft_path = unreal.SoftObjectPath(map_object_path)
        job.set_editor_property("map", map_soft_path)
        _log(f"Assigned queue job map SoftObjectPath: {map_object_path}")
    except Exception as exc:
        _log_error(f"Failed to assign map on queue job: {exc}")
        return False

    return True


def _verify_graph_assignment(job, graph_asset):
    graph_asset_path = ""
    try:
        graph_asset_path = graph_asset.get_path_name()
    except Exception:
        graph_asset_path = ""

    verification_notes = []

    for getter_name in ("get_graph_preset", "get_graph_config"):
        getter = getattr(job, getter_name, None)
        if not callable(getter):
            continue
        try:
            value = getter()
            value_path = _coerce_to_object_path(value)
        except Exception as exc:
            verification_notes.append(f"{getter_name}=error:{exc}")
            continue

        verification_notes.append(f"{getter_name}={value_path or 'empty'}")
        if graph_asset_path and value_path == graph_asset_path:
            _log(f"Verified Movie Render Graph assignment via {getter_name}().")
            return True

    checker = getattr(job, "is_using_graph_configuration", None)
    if callable(checker):
        try:
            is_using_graph = bool(checker())
            verification_notes.append(f"is_using_graph_configuration={is_using_graph}")
            if is_using_graph:
                _log("Verified queue job reports graph configuration mode enabled.")
                return True
        except Exception as exc:
            verification_notes.append(f"is_using_graph_configuration=error:{exc}")

    _log_warning(
        "Movie Render Graph verification did not conclusively confirm assignment: "
        + "; ".join(verification_notes)
    )
    return False


def _assign_movie_render_graph_to_job(job, graph_asset):
    assignment_attempts = [
        ("set_graph_preset", (graph_asset, True)),
        ("set_graph_config", (graph_asset,)),
    ]

    for method_name, method_args in assignment_attempts:
        method = getattr(job, method_name, None)
        if not callable(method):
            continue
        try:
            method(*method_args)
            _log(f"Assigned Movie Render Graph via documented job method {method_name}().")
            if _verify_graph_assignment(job, graph_asset):
                return True
        except Exception as exc:
            _log_warning(f"Failed documented graph assignment via {method_name}(): {exc}")

    fallback_property_names = [
        "graph_preset",
        "graph_config",
        "movie_graph_config",
        "movie_render_graph",
        "graph",
    ]

    for property_name in fallback_property_names:
        try:
            job.set_editor_property(property_name, graph_asset)
            _log_warning(f"Assigned Movie Render Graph via undocumented fallback property '{property_name}'.")
            if _verify_graph_assignment(job, graph_asset):
                return True
        except Exception:
            continue

    _log_error("Failed to assign Movie Render Graph to queue job.")
    return False


def _load_saved_output_root():
    try:
        import get_outputFolder

        importlib.reload(get_outputFolder)
        output_root = str(get_outputFolder.run() or "").strip()
        if output_root:
            normalized = os.path.normpath(output_root)
            _log(f"Loaded output root from get_outputFolder: {normalized}")
            return normalized
    except Exception as exc:
        _log_error(f"Failed to load output root from get_outputFolder: {exc}")

    return ""


def _find_next_render_version_number(output_parent_directory, stem_prefix):
    normalized_parent = os.path.normpath(str(output_parent_directory or "").strip())
    if not normalized_parent:
        return DEFAULT_VERSION_NUMBER

    pattern = re.compile(VERSION_PATTERN_TEMPLATE.format(prefix=re.escape(stem_prefix)))
    highest_version = 0

    try:
        entries = os.listdir(normalized_parent)
    except FileNotFoundError:
        _log(f"Output parent folder does not exist yet. Starting version at v{DEFAULT_VERSION_NUMBER:03d}: {normalized_parent}")
        return DEFAULT_VERSION_NUMBER
    except Exception as exc:
        _log_warning(f"Could not inspect output parent folder '{normalized_parent}' for existing versions: {exc}")
        return DEFAULT_VERSION_NUMBER

    for entry_name in entries:
        entry_path = os.path.join(normalized_parent, entry_name)
        if not os.path.isdir(entry_path):
            continue

        match = pattern.fullmatch(str(entry_name))
        if not match:
            continue

        try:
            version_number = int(match.group(1))
        except Exception:
            continue

        if version_number > highest_version:
            highest_version = version_number

    next_version_number = highest_version + 1 if highest_version > 0 else DEFAULT_VERSION_NUMBER
    _log(
        f"Resolved next render version for prefix '{stem_prefix}' under '{normalized_parent}': "
        f"v{next_version_number:03d}"
    )
    return next_version_number



def _build_render_output_data(output_root, shot_name, movie_render_graph_name):
    if not output_root:
        raise ValueError("Output root folder was empty.")

    sequence_name = _derive_sequence_prefix(shot_name)
    if not sequence_name:
        raise ValueError(f"Could not derive sequence name from shot '{shot_name}'.")

    graph_name = _sanitize_graph_name(movie_render_graph_name)
    if not graph_name:
        raise ValueError("Movie Render Graph name was empty after sanitization.")

    stem_prefix = f"{shot_name}_{graph_name}"
    output_parent_directory = os.path.join(
        output_root,
        sequence_name,
        shot_name,
        *RENDER_CONTEXT_SEGMENTS,
    )
    output_parent_directory = os.path.normpath(output_parent_directory)

    version_number = _find_next_render_version_number(output_parent_directory, stem_prefix)
    version_text = f"v{version_number:03d}"
    base_stem = f"{stem_prefix}_{version_text}"
    output_directory = os.path.join(output_parent_directory, base_stem)
    output_directory = os.path.normpath(output_directory)

    return {
        "sequence_name": sequence_name,
        "base_stem": base_stem,
        "output_directory": output_directory,
        "output_parent_directory": output_parent_directory,
        "version_text": version_text,
        "file_name_format": f"{base_stem}.{{frame_number}}",
    }


def _get_graph_variables(graph_asset):
    getters = [
        "get_variables",
        "get_all_variables",
    ]

    for getter_name in getters:
        getter = getattr(graph_asset, getter_name, None)
        if not callable(getter):
            continue
        try:
            variables = list(getter() or [])
            if variables:
                _log(f"Discovered {len(variables)} graph variables via {getter_name}().")
            else:
                _log_warning(f"Graph variable query {getter_name}() returned no variables.")
            return variables
        except Exception as exc:
            _log_warning(f"Graph variable query {getter_name}() failed: {exc}")

    return []


def _get_graph_variable_name(variable):
    for getter_name in ("get_member_name", "get_variable_name", "get_name"):
        getter = getattr(variable, getter_name, None)
        if not callable(getter):
            continue
        try:
            value = getter()
        except Exception:
            continue
        if value is None:
            continue
        text = str(value)
        if text:
            return text
    return ""


def _find_graph_variable_by_name(graph_asset, variable_name):
    requested = str(variable_name or "").strip()
    if not requested:
        return None

    for variable in _get_graph_variables(graph_asset):
        discovered_name = _get_graph_variable_name(variable)
        if discovered_name == requested:
            _log(f"Resolved graph variable '{requested}'.")
            return variable

    _log_warning(f"Could not find graph variable named '{requested}'.")
    return None


def _set_variable_enable_state(container, variable, enabled=True):
    for method_name in ("set_variable_assignment_enable_state", "set_value_enable_state"):
        method = getattr(container, method_name, None)
        if not callable(method):
            continue
        try:
            method(variable, enabled)
            return True
        except Exception:
            continue
    return False


def _apply_job_output_overrides(job, graph_asset, output_directory, file_name_format):
    get_overrides = getattr(job, "get_or_create_variable_overrides", None)
    if not callable(get_overrides):
        _log_error("Queue job does not expose get_or_create_variable_overrides().")
        return False

    try:
        override_container = get_overrides(graph_asset)
    except Exception as exc:
        _log_error(f"Failed to get graph variable override container: {exc}")
        return False

    if not override_container:
        _log_error("Graph variable override container was empty.")
        return False

    updater = getattr(override_container, "update_graph_variable_overrides", None)
    if callable(updater):
        try:
            updater()
        except Exception as exc:
            _log_warning(f"update_graph_variable_overrides() failed: {exc}")

    output_variable = _find_graph_variable_by_name(graph_asset, OUTPUT_VARIABLE_NAME)
    file_name_variable = _find_graph_variable_by_name(graph_asset, FILE_NAME_VARIABLE_NAME)

    if not output_variable or not file_name_variable:
        _log_error(
            f"Required graph variables were missing. Needed '{OUTPUT_VARIABLE_NAME}' and '{FILE_NAME_VARIABLE_NAME}'."
        )
        return False

    _set_variable_enable_state(override_container, output_variable, True)
    _set_variable_enable_state(override_container, file_name_variable, True)

    output_serialized = unreal.DirectoryPath(output_directory).export_text()

    try:
        override_container.set_value_serialized_string(output_variable, output_serialized)
        _log(f"Set {OUTPUT_VARIABLE_NAME} override to: {output_directory}")
    except Exception as exc:
        _log_error(f"Failed to set {OUTPUT_VARIABLE_NAME} override: {exc}")
        return False

    file_name_set = False
    try:
        override_container.set_value_string(file_name_variable, file_name_format)
        file_name_set = True
    except Exception as exc:
        _log_warning(f"set_value_string() failed for {FILE_NAME_VARIABLE_NAME}: {exc}")

    if not file_name_set:
        try:
            override_container.set_value_serialized_string(file_name_variable, file_name_format)
            file_name_set = True
        except Exception as exc:
            _log_error(f"Failed to set {FILE_NAME_VARIABLE_NAME} override: {exc}")
            return False

    _log(f"Set {FILE_NAME_VARIABLE_NAME} override to: {file_name_format}")
    return True


def run(shot_name_array, is_active_array, is_hero_array, movie_render_graph):
    del is_hero_array

    result = _new_result(movie_render_graph)

    try:
        shot_names = list(shot_name_array or [])
    except Exception:
        shot_names = []

    try:
        active_flags = list(is_active_array or [])
    except Exception:
        active_flags = []

    if not shot_names:
        return _format_summary_string(
            _finalize_result(result, success=False, message="No shot names were provided.")
        )

    if len(active_flags) < len(shot_names):
        active_flags.extend([0] * (len(shot_names) - len(active_flags)))

    queue_subsystem = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    if not queue_subsystem:
        return _format_summary_string(
            _finalize_result(result, success=False, message="Could not get MoviePipelineQueueSubsystem.")
        )

    queue = queue_subsystem.get_queue()
    if not queue:
        return _format_summary_string(
            _finalize_result(result, success=False, message="Could not get Movie Render Queue.")
        )

    executor_job_class = getattr(unreal, "MoviePipelineExecutorJob", None)
    if not executor_job_class:
        return _format_summary_string(
            _finalize_result(result, success=False, message="MoviePipelineExecutorJob class was unavailable.")
        )

    graph_asset = _find_movie_render_graph_asset(movie_render_graph)
    if not graph_asset:
        return _format_summary_string(
            _finalize_result(
                result,
                success=False,
                message=f"Movie Render Graph '{movie_render_graph}' could not be resolved.",
            )
        )

    output_root = _load_saved_output_root()
    if not output_root:
        return _format_summary_string(
            _finalize_result(
                result,
                success=False,
                message="Output root folder was empty. Save an output folder before submitting jobs.",
            )
        )

    seen_active_shots = set()

    for index, raw_shot_name in enumerate(shot_names):
        shot_name = _sanitize_shot_name(raw_shot_name)
        is_active = _coerce_to_bool_flag(active_flags[index] if index < len(active_flags) else 0)

        if not shot_name:
            result["jobs_skipped"] += 1
            result["invalid_shots"].append(str(raw_shot_name))
            _log_warning(f"Skipping blank or invalid shot name at index {index}: {raw_shot_name}")
            continue

        if not _is_shot_name_valid(shot_name):
            result["jobs_skipped"] += 1
            result["invalid_shots"].append(shot_name)
            _log_warning(f"Skipping shot '{shot_name}' because it does not match expected naming pattern.")
            continue

        if not is_active:
            result["jobs_skipped"] += 1
            _log(f"Skipping inactive shot '{shot_name}'.")
            continue

        if shot_name in seen_active_shots:
            result["jobs_skipped"] += 1
            result["duplicate_active_shots"].append(shot_name)
            _log_warning(f"Skipping duplicate active shot '{shot_name}'.")
            continue

        seen_active_shots.add(shot_name)

        level_sequence_object_path = _find_level_sequence_asset_path(shot_name)
        if not level_sequence_object_path:
            result["jobs_skipped"] += 1
            result["missing_shots"].append(shot_name)
            _log_warning(f"Could not find Level Sequence for shot '{shot_name}'.")
            continue

        shot_data_asset, shot_data_asset_object_path = _load_shot_data_asset_for_shot(level_sequence_object_path, shot_name)
        if not shot_data_asset:
            result["jobs_skipped"] += 1
            result["missing_data_assets"].append(shot_name)
            _log_warning(
                f"Could not find shot data asset for '{shot_name}'. Last checked preferred path '{shot_data_asset_object_path}'."
            )
            continue

        associated_level_object_path = _extract_associated_level_object_path(shot_data_asset)
        if not associated_level_object_path:
            result["jobs_skipped"] += 1
            result["missing_levels"].append(shot_name)
            _log_warning(f"Could not resolve AssociatedLevel for shot '{shot_name}'.")
            continue

        try:
            render_output_data = _build_render_output_data(output_root, shot_name, movie_render_graph)
            _log(
                f"Render output for '{shot_name}': directory='{render_output_data['output_directory']}', "
                f"file_name_format='{render_output_data['file_name_format']}'"
            )
        except Exception as exc:
            result["jobs_skipped"] += 1
            result["output_config_failures"].append(shot_name)
            _log_error(f"Failed to build render output data for shot '{shot_name}': {exc}")
            continue

        try:
            job = queue.allocate_new_job(executor_job_class)
            _log(f"Allocated queue job for shot '{shot_name}'.")
        except Exception as exc:
            result["jobs_skipped"] += 1
            _log_error(f"Failed to allocate queue job for shot '{shot_name}': {exc}")
            continue

        job_is_valid = True

        _assign_job_name(job, shot_name)

        if not _assign_job_sequence_and_map(job, level_sequence_object_path, associated_level_object_path):
            job_is_valid = False

        if job_is_valid and not _assign_movie_render_graph_to_job(job, graph_asset):
            job_is_valid = False

        if job_is_valid and not _apply_job_output_overrides(
            job,
            graph_asset,
            render_output_data["output_directory"],
            render_output_data["file_name_format"],
        ):
            result["output_config_failures"].append(shot_name)
            job_is_valid = False

        if not job_is_valid:
            result["jobs_skipped"] += 1
            _remove_job_from_queue(queue_subsystem, job)
            continue

        result["jobs_added"] += 1
        result["jobs_output_configured"] += 1
        _log(f"Successfully added shot '{shot_name}' to Movie Render Queue.")

    success = (
        result["jobs_added"] > 0
        and not result["missing_shots"]
        and not result["missing_levels"]
        and not result["output_config_failures"]
    )
    if result["jobs_added"] == 0:
        message = "No jobs were added to the Movie Render Queue."
    else:
        message = (
            f"Added {result['jobs_added']} job(s) to the Movie Render Queue. "
            f"Configured output overrides on {result['jobs_output_configured']} job(s)."
        )

    return _format_summary_string(_finalize_result(result, success=success, message=message))
