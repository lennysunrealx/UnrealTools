import re
import unreal


LOG_PREFIX = "[AddToRenderQueue]"
MRG_SETTINGS_FOLDER = "/QuickWidgetTools/Misc/MRGSettings"
SHOT_NAME_PATTERN = re.compile(r"^([A-Za-z0-9]+)_(\d{3})_(\d{4,})$")


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_warning(message):
    unreal.log_warning(f"{LOG_PREFIX} Warning: {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} Error: {message}")


def _sanitize_shot_name(value):
    if value is None:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", str(value))
    return cleaned.upper()


def _is_shot_name_valid(shot_name):
    return bool(SHOT_NAME_PATTERN.fullmatch(shot_name))


def _derive_sequence_prefix(shot_name):
    match = SHOT_NAME_PATTERN.fullmatch(shot_name)
    if not match:
        return ""
    return match.group(1).upper()


def _normalize_asset_object_path(path_or_object_path):
    if not path_or_object_path:
        return ""

    text = str(path_or_object_path).strip()
    if not text:
        return ""

    if text.startswith("SoftObjectPath(") and text.endswith(")"):
        text = text[len("SoftObjectPath("):-1].strip().strip("\"'")

    if text.startswith("/Game/") or text.startswith("/QuickWidgetTools/"):
        return text

    return ""


def _asset_object_path_from_package_path(package_path):
    if not package_path:
        return ""
    asset_name = package_path.rsplit("/", 1)[-1]
    return f"{package_path}.{asset_name}"


def _list_valid_show_folders():
    editor_asset_lib = unreal.EditorAssetLibrary
    root_assets = editor_asset_lib.list_assets("/Game", recursive=False, include_folder=True)

    show_folders = []
    for entry in root_assets:
        if not entry.startswith("/Game/_"):
            continue

        if "." in entry:
            continue

        marker_asset_path = f"{entry}/_showholder"
        if editor_asset_lib.does_asset_exist(marker_asset_path):
            show_folders.append(entry)

    return show_folders


def _find_level_sequence_asset_path(shot_name):
    sequence_prefix = _derive_sequence_prefix(shot_name)
    if not sequence_prefix:
        return ""

    editor_asset_lib = unreal.EditorAssetLibrary
    for show_folder in _list_valid_show_folders():
        package_path = f"{show_folder}/Sequences/{sequence_prefix}/{shot_name}"
        object_path = _asset_object_path_from_package_path(package_path)

        if not editor_asset_lib.does_asset_exist(object_path):
            continue

        loaded = unreal.load_asset(object_path)
        if not loaded:
            continue

        if not isinstance(loaded, unreal.LevelSequence):
            _log_warning(
                f"Found '{object_path}' but it is not a LevelSequence (type={loaded.get_class().get_name()})."
            )
            continue

        _log(f"Resolved shot sequence for '{shot_name}': {object_path}")
        return object_path

    return ""


def _build_shot_data_asset_object_path(level_sequence_object_path, shot_name):
    package_path = level_sequence_object_path.split(".", 1)[0]
    data_asset_name = f"{shot_name}_Data"
    return f"{package_path}/{data_asset_name}.{data_asset_name}"


def _load_shot_data_asset(data_asset_object_path):
    if not unreal.EditorAssetLibrary.does_asset_exist(data_asset_object_path):
        return None
    return unreal.load_asset(data_asset_object_path)


def _extract_associated_level_object_path(shot_data_asset):
    property_candidates = [
        "AssociatedLevel",
        "associated_level",
        "Level",
        "LevelAssociation",
        "AssociatedLevelStored",
    ]

    for property_name in property_candidates:
        try:
            value = shot_data_asset.get_editor_property(property_name)
        except Exception:
            continue

        object_path = _coerce_to_object_path(value)
        if object_path:
            _log(f"Resolved AssociatedLevel via property '{property_name}': {object_path}")
            return object_path

    return ""


def _coerce_to_object_path(value):
    if value is None:
        return ""

    if isinstance(value, str):
        return _normalize_asset_object_path(value)

    for getter_name in ("get_asset_path_name", "get_path_name", "to_string"):
        getter = getattr(value, getter_name, None)
        if callable(getter):
            try:
                raw = getter()
            except Exception:
                continue
            normalized = _normalize_asset_object_path(raw)
            if normalized:
                return normalized

    try:
        as_text = str(value)
    except Exception:
        return ""

    return _normalize_asset_object_path(as_text)


def _find_movie_render_graph_asset(movie_render_graph):
    editor_asset_lib = unreal.EditorAssetLibrary
    if not editor_asset_lib.does_directory_exist(MRG_SETTINGS_FOLDER):
        _log_error(f"Movie Render Graph folder not found: {MRG_SETTINGS_FOLDER}")
        return None

    candidates = editor_asset_lib.list_assets(
        MRG_SETTINGS_FOLDER,
        recursive=True,
        include_folder=False,
    )

    for object_path in candidates:
        leaf = object_path.rsplit("/", 1)[-1]
        asset_name = leaf.split(".", 1)[0]
        if asset_name != movie_render_graph:
            continue

        graph_asset = unreal.load_asset(object_path)
        if graph_asset:
            _log(f"Selected Movie Render Graph asset: {object_path}")
            return graph_asset

    return None


def _assign_movie_render_graph_to_job(job, graph_asset):
    graph_property_candidates = [
        "graph_preset",
        "graph_config",
        "movie_graph_config",
        "movie_render_graph",
        "graph",
    ]

    for prop_name in graph_property_candidates:
        try:
            job.set_editor_property(prop_name, graph_asset)
            _log(f"Assigned Movie Render Graph using job property '{prop_name}'.")
            return True
        except Exception:
            continue

    for setter_name in ("set_graph_preset", "set_graph_config", "set_movie_graph_config"):
        setter = getattr(job, setter_name, None)
        if callable(setter):
            try:
                setter(graph_asset)
                _log(f"Assigned Movie Render Graph using job method '{setter_name}()'.")
                return True
            except Exception:
                continue

    _log_error("Unable to assign Movie Render Graph to queue job (no supported property/method found).")
    return False


def _set_job_sequence_and_map(job, level_sequence_object_path, map_object_path):
    sequence_soft_path = unreal.SoftObjectPath(level_sequence_object_path)
    map_soft_path = unreal.SoftObjectPath(map_object_path)

    sequence_assigned = False
    map_assigned = False

    for prop_name in ("sequence", "sequence_path"):
        try:
            job.set_editor_property(prop_name, sequence_soft_path)
            sequence_assigned = True
            break
        except Exception:
            continue

    for prop_name in ("map", "map_path"):
        try:
            job.set_editor_property(prop_name, map_soft_path)
            map_assigned = True
            break
        except Exception:
            continue

    return sequence_assigned and map_assigned


def _new_result(movie_render_graph_name):
    return {
        "success": False,
        "jobs_added": 0,
        "jobs_skipped": 0,
        "missing_shots": [],
        "missing_data_assets": [],
        "missing_levels": [],
        "movie_render_graph": movie_render_graph_name,
    }


def run(shot_name_array, is_active_array, is_hero_array, movie_render_graph):
    result = _new_result(str(movie_render_graph or ""))

    shot_names = [str(v) for v in list(shot_name_array or [])]
    active_values = list(is_active_array or [])
    hero_values = list(is_hero_array or [])
    movie_render_graph = str(movie_render_graph or "").strip()

    _log(
        "Input counts - shots: {0}, active flags: {1}, hero flags: {2}".format(
            len(shot_names),
            len(active_values),
            len(hero_values),
        )
    )

    if not movie_render_graph:
        _log_error("movie_render_graph is empty.")
        return result

    if len(shot_names) != len(active_values) or len(shot_names) != len(hero_values):
        _log_error("Array length mismatch: shot_name_array, is_active_array, and is_hero_array must match.")
        return result

    graph_asset = _find_movie_render_graph_asset(movie_render_graph)
    if not graph_asset:
        _log_error(
            f"Movie Render Graph '{movie_render_graph}' was not found under '{MRG_SETTINGS_FOLDER}'."
        )
        return result

    queue_subsystem = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    if not queue_subsystem:
        _log_error("Unable to resolve MoviePipelineQueueSubsystem.")
        return result

    queue = queue_subsystem.get_queue()
    if not queue:
        _log_error("Unable to access Movie Render Queue.")
        return result

    for idx, raw_shot_name in enumerate(shot_names):
        shot_name = _sanitize_shot_name(raw_shot_name)
        is_active = int(active_values[idx]) if isinstance(active_values[idx], (int, bool)) else 0

        _log(f"Processing shot index {idx}: raw='{raw_shot_name}', sanitized='{shot_name}', active={is_active}")

        if not _is_shot_name_valid(shot_name):
            _log_warning(f"Skipping malformed shot name at index {idx}: '{raw_shot_name}'")
            result["jobs_skipped"] += 1
            continue

        if is_active != 1:
            _log(f"Skipping inactive shot '{shot_name}' (is_active={is_active}).")
            result["jobs_skipped"] += 1
            continue

        level_sequence_object_path = _find_level_sequence_asset_path(shot_name)
        if not level_sequence_object_path:
            _log_warning(f"Shot sequence not found for '{shot_name}'.")
            result["missing_shots"].append(shot_name)
            result["jobs_skipped"] += 1
            continue

        data_asset_object_path = _build_shot_data_asset_object_path(level_sequence_object_path, shot_name)
        shot_data_asset = _load_shot_data_asset(data_asset_object_path)
        if not shot_data_asset:
            _log_warning(f"Shot data asset not found for '{shot_name}': {data_asset_object_path}")
            result["missing_data_assets"].append(shot_name)
            result["jobs_skipped"] += 1
            continue

        associated_level_object_path = _extract_associated_level_object_path(shot_data_asset)
        if not associated_level_object_path:
            _log_warning(f"AssociatedLevel is missing/invalid for '{shot_name}'.")
            result["missing_levels"].append(shot_name)
            result["jobs_skipped"] += 1
            continue

        job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
        if not job:
            _log_error(f"Failed to allocate queue job for shot '{shot_name}'.")
            result["jobs_skipped"] += 1
            continue

        try:
            job.set_editor_property("job_name", shot_name)
        except Exception:
            pass

        if not _set_job_sequence_and_map(job, level_sequence_object_path, associated_level_object_path):
            _log_warning(
                f"Failed to assign sequence/map for shot '{shot_name}'. "
                f"Sequence='{level_sequence_object_path}', Map='{associated_level_object_path}'"
            )
            result["jobs_skipped"] += 1
            continue

        if not _assign_movie_render_graph_to_job(job, graph_asset):
            result["jobs_skipped"] += 1
            continue

        result["jobs_added"] += 1
        _log(
            f"Added queue job for '{shot_name}' "
            f"(Sequence='{level_sequence_object_path}', Map='{associated_level_object_path}')."
        )

    result["success"] = result["jobs_added"] > 0
    _log(
        "Summary: success={0}, jobs_added={1}, jobs_skipped={2}, missing_shots={3}, "
        "missing_data_assets={4}, missing_levels={5}, movie_render_graph='{6}'".format(
            result["success"],
            result["jobs_added"],
            result["jobs_skipped"],
            result["missing_shots"],
            result["missing_data_assets"],
            result["missing_levels"],
            result["movie_render_graph"],
        )
    )

    return result
