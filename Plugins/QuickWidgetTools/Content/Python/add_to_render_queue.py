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

    asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()
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

        graph_asset_data = None
        try:
            graph_asset_data = asset_registry.get_asset_by_object_path(unreal.Name(object_path))
        except Exception:
            graph_asset_data = None

        registry_class_name = ""
        if graph_asset_data and graph_asset_data.is_valid():
            try:
                registry_class_name = str(graph_asset_data.asset_class_path.asset_name)
            except Exception:
                registry_class_name = ""

        graph_asset = unreal.load_asset(object_path)
        if not graph_asset:
            continue

        loaded_class_name = ""
        try:
            loaded_class_name = graph_asset.get_class().get_name()
        except Exception:
            loaded_class_name = ""

        class_name_candidates = {registry_class_name, loaded_class_name}
        normalized_class_names = {class_name for class_name in class_name_candidates if class_name}

        class_hierarchy_names = set()
        try:
            class_obj = graph_asset.get_class()
        except Exception:
            class_obj = None

        while class_obj:
            try:
                class_name = class_obj.get_name()
            except Exception:
                class_name = ""
            if class_name:
                class_hierarchy_names.add(class_name)
            try:
                class_obj = class_obj.get_super_class()
            except Exception:
                break

        detected_class_names = normalized_class_names.union(class_hierarchy_names)
        expected_class_names = {
            "MovieGraphConfig",
            "MovieGraphConfigBase",
        }
        is_expected_graph_class = any(class_name in expected_class_names for class_name in detected_class_names)
        detected_primary_class = loaded_class_name or registry_class_name or "Unknown"

        _log(
            f"Matched graph asset candidate: path='{object_path}', "
            f"registry_class='{registry_class_name}', loaded_class='{loaded_class_name}'."
        )
        _log(
            f"Detected graph asset class for '{object_path}': primary='{detected_primary_class}', "
            f"all={sorted(detected_class_names)}"
        )

        if not is_expected_graph_class:
            _log_warning(
                f"Asset name matched '{movie_render_graph}' but class did not match expected Movie Render Graph classes "
                f"(registry='{registry_class_name}', loaded='{loaded_class_name}'). Skipping."
            )
            continue

        _log(
            f"Selected Movie Render Graph asset: {object_path} "
            f"(registry_class='{registry_class_name}', loaded_class='{loaded_class_name}')."
        )
        return graph_asset

    return None


def _switch_job_to_movie_render_graph_mode(job):
    _log("Attempting to switch queue job to Movie Render Graph configuration mode.")

    def _is_mrg_mode_enabled():
        probes = [
            ("job property", job, "use_graph_configuration"),
            ("job property", job, "use_movie_graph"),
            ("job property", job, "is_graph_configuration"),
        ]

        get_configuration_method = getattr(job, "get_configuration", None)
        configuration_obj = None
        if callable(get_configuration_method):
            try:
                configuration_obj = get_configuration_method()
            except Exception:
                configuration_obj = None

        if configuration_obj:
            probes.extend([
                ("configuration property", configuration_obj, "use_graph_configuration"),
                ("configuration property", configuration_obj, "use_movie_graph"),
            ])

        for source, target, prop_name in probes:
            try:
                value = target.get_editor_property(prop_name)
            except Exception:
                continue
            if bool(value):
                _log(f"MRG mode verification passed via {source} '{prop_name}'={value}.")
                return True

        return False

    method_candidates = [
        ("job method", job, "set_use_graph_configuration", [True]),
        ("job method", job, "set_use_movie_graph", [True]),
        ("job method", job, "enable_graph_configuration", []),
        ("job method", job, "switch_to_graph_configuration", []),
    ]
    for source, target, method_name, args in method_candidates:
        _log(f"Trying {source} '{method_name}()' to enable MRG mode.")
        method = getattr(target, method_name, None)
        if not callable(method):
            continue
        try:
            method(*args)
            if _is_mrg_mode_enabled():
                _log(f"Movie Render Graph mode switch succeeded via {source} '{method_name}()'.")
                return True
            _log_warning(f"{source} '{method_name}()' was called but MRG mode could not be verified.")
        except Exception:
            continue

    property_candidates = [
        ("job property", "use_graph_configuration", True),
        ("job property", "use_movie_graph", True),
        ("job property", "is_graph_configuration", True),
        ("job property", "configuration_mode", "GRAPH"),
    ]
    for source, prop_name, value in property_candidates:
        _log(f"Trying {source} '{prop_name}' to enable MRG mode.")
        try:
            job.set_editor_property(prop_name, value)
            if _is_mrg_mode_enabled():
                _log(f"Movie Render Graph mode switch succeeded via {source} '{prop_name}'.")
                return True
            _log_warning(f"{source} '{prop_name}' was set but MRG mode could not be verified.")
        except Exception:
            continue

    get_configuration_method = getattr(job, "get_configuration", None)
    if callable(get_configuration_method):
        _log("Trying configuration object methods/properties to enable MRG mode.")
        try:
            configuration_obj = get_configuration_method()
        except Exception:
            configuration_obj = None

        if configuration_obj:
            configuration_method_candidates = [
                ("configuration method", "set_use_graph_configuration", [True]),
                ("configuration method", "set_use_movie_graph", [True]),
                ("configuration method", "switch_to_graph_configuration", []),
            ]
            for source, method_name, args in configuration_method_candidates:
                _log(f"Trying {source} '{method_name}()' to enable MRG mode.")
                method = getattr(configuration_obj, method_name, None)
                if not callable(method):
                    continue
                try:
                    method(*args)
                    if _is_mrg_mode_enabled():
                        _log(f"Movie Render Graph mode switch succeeded via {source} '{method_name}()'.")
                        return True
                    _log_warning(f"{source} '{method_name}()' was called but MRG mode could not be verified.")
                except Exception:
                    continue

            configuration_property_candidates = [
                ("configuration property", "use_graph_configuration", True),
                ("configuration property", "use_movie_graph", True),
            ]
            for source, prop_name, value in configuration_property_candidates:
                _log(f"Trying {source} '{prop_name}' to enable MRG mode.")
                try:
                    configuration_obj.set_editor_property(prop_name, value)
                    if _is_mrg_mode_enabled():
                        _log(f"Movie Render Graph mode switch succeeded via {source} '{prop_name}'.")
                        return True
                    _log_warning(f"{source} '{prop_name}' was set but MRG mode could not be verified.")
                except Exception:
                    continue

    _log_error("Unable to switch queue job to Movie Render Graph configuration mode.")
    return False


def _remove_job_from_queue(queue, job, shot_name, reason):
    if not queue or not job:
        return

    _log_warning(f"Removing queue job for '{shot_name}' after skip reason: {reason}")

    for method_name in ("delete_job", "remove_job"):
        method = getattr(queue, method_name, None)
        if not callable(method):
            continue
        try:
            method(job)
            _log(f"Removed queue job for '{shot_name}' using queue method '{method_name}()'.")
            return
        except Exception:
            continue

    _log_warning(
        f"Unable to remove queue job for '{shot_name}' (no supported queue delete/remove method)."
    )


def _assign_movie_render_graph_to_job(job, graph_asset):
    graph_asset_path = ""
    try:
        graph_asset_path = graph_asset.get_path_name()
    except Exception:
        graph_asset_path = str(graph_asset)

    def _is_graph_assignment_verified(target_obj, target_label):
        for getter_name in ("get_graph_preset", "get_graph_config"):
            getter = getattr(target_obj, getter_name, None)
            if not callable(getter):
                continue
            try:
                assigned_asset = getter()
            except Exception:
                continue
            if assigned_asset == graph_asset:
                _log(
                    f"Movie Render Graph assignment verified on {target_label} "
                    f"via method '{getter_name}()'."
                )
                return True
            try:
                assigned_path = assigned_asset.get_path_name() if assigned_asset else "None"
            except Exception:
                assigned_path = str(assigned_asset)
            _log(
                f"Verification probe on {target_label} via '{getter_name}()' "
                f"returned '{assigned_path}'."
            )

        for prop_name in ("graph_preset", "graph_config", "movie_graph_config", "movie_render_graph", "graph"):
            try:
                assigned_asset = target_obj.get_editor_property(prop_name)
            except Exception:
                continue
            if assigned_asset == graph_asset:
                _log(
                    f"Movie Render Graph assignment verified on {target_label} "
                    f"via property '{prop_name}'."
                )
                return True
            try:
                assigned_path = assigned_asset.get_path_name() if assigned_asset else "None"
            except Exception:
                assigned_path = str(assigned_asset)
            _log(
                f"Verification probe on {target_label} via property '{prop_name}' "
                f"returned '{assigned_path}'."
            )

        return False

    for setter_name in ("set_graph_preset", "set_graph_config"):
        _log(f"Trying graph assignment via job method '{setter_name}()'.")
        setter = getattr(job, setter_name, None)
        if callable(setter):
            try:
                setter(graph_asset)
                if _is_graph_assignment_verified(job, "job"):
                    _log(
                        f"Successfully assigned Movie Render Graph '{graph_asset_path}' "
                        f"using job method '{setter_name}()'."
                    )
                    return True
                _log_warning(
                    f"Job method '{setter_name}()' executed but assignment could not be verified."
                )
            except Exception:
                continue

    get_configuration_method = getattr(job, "get_configuration", None)
    if callable(get_configuration_method):
        try:
            configuration_obj = get_configuration_method()
        except Exception:
            configuration_obj = None

        if configuration_obj:
            for setter_name in ("set_graph_preset", "set_graph_config"):
                _log(f"Trying graph assignment via configuration method '{setter_name}()'.")
                setter = getattr(configuration_obj, setter_name, None)
                if callable(setter):
                    try:
                        setter(graph_asset)
                        if _is_graph_assignment_verified(configuration_obj, "configuration"):
                            _log(
                                f"Successfully assigned Movie Render Graph '{graph_asset_path}' "
                                f"using configuration method '{setter_name}()'."
                            )
                            return True
                        _log_warning(
                            f"Configuration method '{setter_name}()' executed but assignment could not be verified."
                        )
                    except Exception:
                        continue

    _log("Falling back to editor property graph assignment (undocumented path).")
    graph_property_candidates = [
        "graph_preset",
        "graph_config",
        "movie_graph_config",
        "movie_render_graph",
        "graph",
    ]
    for prop_name in graph_property_candidates:
        _log(f"Trying graph assignment via job property '{prop_name}' (fallback).")
        try:
            job.set_editor_property(prop_name, graph_asset)
            if _is_graph_assignment_verified(job, "job"):
                _log(
                    f"Successfully assigned Movie Render Graph '{graph_asset_path}' "
                    f"using job property '{prop_name}' (fallback)."
                )
                return True
            _log_warning(
                f"Job property '{prop_name}' was set but assignment could not be verified."
            )
        except Exception:
            continue

    if callable(get_configuration_method):
        try:
            configuration_obj = get_configuration_method()
        except Exception:
            configuration_obj = None

        if configuration_obj:
            for prop_name in ("graph_preset", "graph_config", "movie_graph_config", "movie_render_graph", "graph"):
                _log(f"Trying graph assignment via configuration property '{prop_name}' (fallback).")
                try:
                    configuration_obj.set_editor_property(prop_name, graph_asset)
                    if _is_graph_assignment_verified(configuration_obj, "configuration"):
                        _log(
                            f"Successfully assigned Movie Render Graph '{graph_asset_path}' "
                            f"using configuration property '{prop_name}' (fallback)."
                        )
                        return True
                    _log_warning(
                        f"Configuration property '{prop_name}' was set but assignment could not be verified."
                    )
                except Exception:
                    continue

    _log_error("Unable to assign Movie Render Graph to queue job (no supported property/method found).")
    return False


def _set_job_sequence_and_map(job, level_sequence_object_path, map_object_path):
    _log(f"Attempting sequence assignment from object path: {level_sequence_object_path}")
    _log(f"Attempting map assignment from object path: {map_object_path}")

    sequence_soft_path = unreal.SoftObjectPath(level_sequence_object_path)
    map_soft_path = unreal.SoftObjectPath(map_object_path)

    sequence_assigned = False
    map_assigned = False
    sequence_property_name = ""
    map_property_name = ""

    for prop_name in ("sequence", "sequence_path"):
        try:
            job.set_editor_property(prop_name, sequence_soft_path)
            sequence_assigned = True
            sequence_property_name = prop_name
            _log(
                f"Assigned sequence object path '{level_sequence_object_path}' "
                f"using job property '{prop_name}'."
            )
            break
        except Exception:
            continue

    for prop_name in ("map", "map_path"):
        try:
            job.set_editor_property(prop_name, map_soft_path)
            map_assigned = True
            map_property_name = prop_name
            _log(
                f"Assigned map object path '{map_object_path}' "
                f"using job property '{prop_name}'."
            )
            break
        except Exception:
            continue

    if sequence_assigned and map_assigned:
        _log(
            f"Sequence/map assignment succeeded (sequence_prop='{sequence_property_name}', "
            f"map_prop='{map_property_name}', sequence='{level_sequence_object_path}', map='{map_object_path}')."
        )
    else:
        _log_warning(
            f"Sequence/map assignment failed (sequence_assigned={sequence_assigned}, map_assigned={map_assigned}, "
            f"sequence_prop='{sequence_property_name}', map_prop='{map_property_name}', "
            f"sequence='{level_sequence_object_path}', map='{map_object_path}')."
        )

    return sequence_assigned and map_assigned


def _format_summary_string(result):
    summary = (
        f"success={1 if result.get('success') else 0};"
        f"jobs_added={result.get('jobs_added', 0)};"
        f"jobs_skipped={result.get('jobs_skipped', 0)};"
        f"missing_shots={','.join(result.get('missing_shots', []))};"
        f"missing_data_assets={','.join(result.get('missing_data_assets', []))};"
        f"missing_levels={','.join(result.get('missing_levels', []))};"
        f"movie_render_graph={result.get('movie_render_graph_name', '')}"
    )
    _log(f"Returned summary string: {summary}")
    return summary


def _build_result_summary(success, jobs_added, jobs_skipped, missing_shots, missing_data_assets, missing_levels, movie_render_graph_name):
    summary = (
        f"success={1 if success else 0};"
        f"jobs_added={jobs_added};"
        f"jobs_skipped={jobs_skipped};"
        f"missing_shots={','.join(missing_shots)};"
        f"missing_data_assets={','.join(missing_data_assets)};"
        f"missing_levels={','.join(missing_levels)};"
        f"movie_render_graph={movie_render_graph_name}"
    )
    _log(f"Returned summary string: {summary}")
    return summary


def run(shot_name_array, is_active_array, is_hero_array, movie_render_graph):
    movie_render_graph_name = str(movie_render_graph or "").strip()
    jobs_added = 0
    jobs_skipped = 0
    missing_shots = []
    missing_data_assets = []
    missing_levels = []
    result = {
        "success": False,
        "jobs_added": jobs_added,
        "jobs_skipped": jobs_skipped,
        "missing_shots": missing_shots,
        "missing_data_assets": missing_data_assets,
        "missing_levels": missing_levels,
        "movie_render_graph_name": movie_render_graph_name,
    }

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
        return _format_summary_string(result)

    if len(shot_names) != len(active_values) or len(shot_names) != len(hero_values):
        _log_error("Array length mismatch: shot_name_array, is_active_array, and is_hero_array must match.")
        return _format_summary_string(result)

    graph_asset = _find_movie_render_graph_asset(movie_render_graph)
    if not graph_asset:
        _log_error(
            f"Movie Render Graph '{movie_render_graph}' was not found under '{MRG_SETTINGS_FOLDER}'."
        )
        return _format_summary_string(result)

    queue_subsystem = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    if not queue_subsystem:
        _log_error("Unable to resolve MoviePipelineQueueSubsystem.")
        return _format_summary_string(result)

    queue = queue_subsystem.get_queue()
    if not queue:
        _log_error("Unable to access Movie Render Queue.")
        return _format_summary_string(result)

    seen_shot_names = set()

    for idx, raw_shot_name in enumerate(shot_names):
        shot_name = _sanitize_shot_name(raw_shot_name)
        is_active = int(active_values[idx]) if isinstance(active_values[idx], (int, bool)) else 0

        _log(f"Processing shot index {idx}: raw='{raw_shot_name}', sanitized='{shot_name}', active={is_active}")

        if not _is_shot_name_valid(shot_name):
            _log_warning(f"Skipping malformed shot name at index {idx}: '{raw_shot_name}'")
            jobs_skipped += 1
            continue

        if is_active != 1:
            _log(f"Skipping inactive shot '{shot_name}' (is_active={is_active}).")
            jobs_skipped += 1
            continue

        if shot_name in seen_shot_names:
            _log_warning(f"Skipping duplicate active shot '{shot_name}'.")
            jobs_skipped += 1
            continue
        seen_shot_names.add(shot_name)

        level_sequence_object_path = _find_level_sequence_asset_path(shot_name)
        if not level_sequence_object_path:
            _log_warning(f"Shot sequence not found for '{shot_name}'.")
            missing_shots.append(shot_name)
            jobs_skipped += 1
            continue

        data_asset_object_path = _build_shot_data_asset_object_path(level_sequence_object_path, shot_name)
        shot_data_asset = _load_shot_data_asset(data_asset_object_path)
        if not shot_data_asset:
            _log_warning(f"Shot data asset not found for '{shot_name}': {data_asset_object_path}")
            missing_data_assets.append(shot_name)
            jobs_skipped += 1
            continue

        associated_level_object_path = _extract_associated_level_object_path(shot_data_asset)
        if not associated_level_object_path:
            _log_warning(f"AssociatedLevel is missing/invalid for '{shot_name}'.")
            missing_levels.append(shot_name)
            jobs_skipped += 1
            continue

        job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
        if not job:
            _log_error(f"Failed to allocate queue job for shot '{shot_name}'.")
            jobs_skipped += 1
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
            _remove_job_from_queue(queue, job, shot_name, "sequence/map assignment failed")
            jobs_skipped += 1
            continue

        if not _switch_job_to_movie_render_graph_mode(job):
            _log_error(f"Skipping shot '{shot_name}' because MRG mode switch failed.")
            _remove_job_from_queue(queue, job, shot_name, "MRG mode switch failed")
            jobs_skipped += 1
            continue

        if not _assign_movie_render_graph_to_job(job, graph_asset):
            _remove_job_from_queue(queue, job, shot_name, "MRG asset assignment failed")
            jobs_skipped += 1
            continue

        jobs_added += 1
        _log(
            f"Added queue job for '{shot_name}' "
            f"(Sequence='{level_sequence_object_path}', Map='{associated_level_object_path}')."
        )

    success = jobs_added > 0
    result["success"] = success
    result["jobs_added"] = jobs_added
    result["jobs_skipped"] = jobs_skipped
    _log(
        "Summary: success={0}, jobs_added={1}, jobs_skipped={2}, missing_shots={3}, "
        "missing_data_assets={4}, missing_levels={5}, movie_render_graph='{6}'".format(
            success,
            jobs_added,
            jobs_skipped,
            missing_shots,
            missing_data_assets,
            missing_levels,
            movie_render_graph_name,
        )
    )

    return _format_summary_string(result)
