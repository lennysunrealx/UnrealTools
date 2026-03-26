import re
import unreal


LOG_PREFIX = "[SetFrameRange]"


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} {message}")


def _sanitize_show_name(value):
    if value is None:
        return ""
    return "".join(ch for ch in str(value) if ch.isalnum())


def _sanitize_sequence_or_shot_name(value):
    if value is None:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", str(value))
    return cleaned.upper()


def _is_valid_frame_number(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _set_sequence_playback_range(sequence, start_frame, end_frame):
    try:
        sequence.set_playback_start(start_frame)
        sequence.set_playback_end(end_frame)
        return True
    except Exception:
        return False


def _get_tracks(sequence):
    if hasattr(sequence, "get_tracks"):
        try:
            return sequence.get_tracks()
        except Exception:
            pass

    if hasattr(sequence, "get_master_tracks"):
        try:
            return sequence.get_master_tracks()
        except Exception:
            pass

    return []


def _get_track_sections(track):
    if hasattr(track, "get_sections"):
        try:
            return track.get_sections()
        except Exception:
            pass

    if hasattr(unreal, "MovieSceneTrackExtensions"):
        try:
            return unreal.MovieSceneTrackExtensions.get_sections(track)
        except Exception:
            pass

    return []


def _get_subsequence_reference(section):
    if hasattr(section, "get_sequence"):
        try:
            return section.get_sequence()
        except Exception:
            pass

    if hasattr(section, "get_sub_sequence"):
        try:
            return section.get_sub_sequence()
        except Exception:
            pass

    try:
        return section.get_editor_property("sub_sequence")
    except Exception:
        return None


def _set_section_range(section, start_frame, end_frame):
    if hasattr(section, "set_range"):
        try:
            section.set_range(start_frame, end_frame)
            return True
        except Exception:
            pass

    had_start = False
    had_end = False

    if hasattr(section, "set_start_frame"):
        try:
            section.set_start_frame(start_frame)
            had_start = True
        except Exception:
            pass

    if hasattr(section, "set_end_frame"):
        try:
            section.set_end_frame(end_frame)
            had_end = True
        except Exception:
            pass

    if hasattr(section, "set_start_frame_bounded"):
        try:
            section.set_start_frame_bounded(False)
        except Exception:
            pass

    if hasattr(section, "set_end_frame_bounded"):
        try:
            section.set_end_frame_bounded(False)
        except Exception:
            pass

    return had_start and had_end


def _to_package_path(asset_path):
    if not asset_path:
        return ""
    return str(asset_path).split(".", 1)[0]


def _get_asset_name(asset_or_path):
    if not asset_or_path:
        return ""

    if hasattr(asset_or_path, "get_name"):
        try:
            return str(asset_or_path.get_name())
        except Exception:
            pass

    package_path = _to_package_path(asset_or_path)
    if not package_path:
        return ""

    return package_path.rsplit("/", 1)[-1]


def _print_failed_sequence_names(failed_names):
    if not failed_names:
        return
    unique_names = list(dict.fromkeys(name for name in failed_names if name))
    if not unique_names:
        return
    _log(f"Failed child sequences: {', '.join(unique_names)}")


def _list_assets(folder_path):
    try:
        return unreal.EditorAssetLibrary.list_assets(folder_path, recursive=False, include_folder=False)
    except TypeError:
        try:
            return unreal.EditorAssetLibrary.list_assets(folder_path, False, False)
        except Exception:
            return []
    except Exception:
        return []


def _load_level_sequence(asset_path, required=True):
    if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        if required:
            _log_error(f"Required asset does not exist: {asset_path}")
        else:
            _log(f"Asset is not present and will be skipped: {asset_path}")
        return None

    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not asset:
        _log_error(f"Failed to load asset: {asset_path}")
        return None

    if not isinstance(asset, unreal.LevelSequence):
        _log_error(f"Asset is not a Level Sequence: {asset_path}")
        return None

    return asset


def _save_asset(asset, asset_path):
    save_ok = unreal.EditorAssetLibrary.save_loaded_asset(asset)
    _log(f"Save result: asset={asset_path}, success={save_ok}")
    return save_ok


def _sync_master_subsequence_sections(master_sequence, subsequences_folder, start_frame, end_frame):
    updated_count = 0
    failed_names = []
    subsequence_prefix = f"{subsequences_folder}/"

    for track in _get_tracks(master_sequence):
        if not isinstance(track, unreal.MovieSceneSubTrack):
            continue

        for section in _get_track_sections(track):
            sub_sequence = _get_subsequence_reference(section)
            if not sub_sequence:
                continue

            try:
                reference_path = _to_package_path(sub_sequence.get_path_name())
            except Exception:
                reference_path = ""

            if not reference_path.startswith(subsequence_prefix):
                continue

            if _set_section_range(section, start_frame, end_frame):
                updated_count += 1
                _log(
                    "Updated master subsequence section range: "
                    f"reference={reference_path}, start={start_frame}, end={end_frame}"
                )
            else:
                child_name = _get_asset_name(reference_path)
                if child_name:
                    failed_names.append(child_name)
                _log_error(
                    "Failed master subsequence section range update: "
                    f"reference={reference_path}"
                )

    return updated_count, failed_names


def _sync_render_pass_sections(render_pass_sequence, master_sequence_path, start_frame, end_frame):
    updated_count = 0
    failed = False

    for track in _get_tracks(render_pass_sequence):
        if not isinstance(track, unreal.MovieSceneSubTrack):
            continue

        for section in _get_track_sections(track):
            sub_sequence = _get_subsequence_reference(section)
            if not sub_sequence:
                continue

            try:
                reference_path = _to_package_path(sub_sequence.get_path_name())
            except Exception:
                reference_path = ""

            if reference_path != master_sequence_path:
                continue

            if _set_section_range(section, start_frame, end_frame):
                updated_count += 1
                _log(
                    "Updated render pass section range: "
                    f"render_pass={render_pass_sequence.get_path_name()}, reference={reference_path}, "
                    f"start={start_frame}, end={end_frame}"
                )
            else:
                failed = True
                _log_error(
                    "Failed render pass section range update: "
                    f"render_pass={render_pass_sequence.get_path_name()}, reference={reference_path}"
                )

    return updated_count, failed


def run(show_name, sequence_name, shot_name, start_frame, end_frame):
    """Update a shot frame range for master, subsequences, and render passes."""
    _log(
        "Inputs received: "
        f"show_name={show_name}, sequence_name={sequence_name}, shot_name={shot_name}, "
        f"start_frame={start_frame}, end_frame={end_frame}"
    )

    raw_show_name = "" if show_name is None else str(show_name)
    raw_sequence_name = "" if sequence_name is None else str(sequence_name)
    raw_shot_name = "" if shot_name is None else str(shot_name)

    sanitized_show_name = _sanitize_show_name(show_name)
    sanitized_sequence_name = _sanitize_sequence_or_shot_name(sequence_name)
    sanitized_shot_name = _sanitize_sequence_or_shot_name(shot_name)

    _log(
        "Sanitized values: "
        f"show_name={sanitized_show_name}, sequence_name={sanitized_sequence_name}, shot_name={sanitized_shot_name}"
    )

    if not sanitized_show_name or sanitized_show_name != raw_show_name:
        _log_error("Validation failed: show_name must contain letters/numbers only.")
        _log("Final return value: False")
        return False

    if not sanitized_sequence_name or sanitized_sequence_name != raw_sequence_name.upper():
        _log_error("Validation failed: sequence_name must contain uppercase letters/numbers/underscores only.")
        _log("Final return value: False")
        return False

    if not sanitized_shot_name or sanitized_shot_name != raw_shot_name.upper():
        _log_error("Validation failed: shot_name must contain uppercase letters/numbers/underscores only.")
        _log("Final return value: False")
        return False

    if not _is_valid_frame_number(start_frame) or not _is_valid_frame_number(end_frame):
        _log_error("Validation failed: start_frame and end_frame must both be ints and not bools.")
        _log("Final return value: False")
        return False

    if end_frame < start_frame:
        _log_error("Validation failed: end_frame cannot be less than start_frame.")
        _log("Final return value: False")
        return False

    sequence_folder = f"/Game/_{sanitized_show_name}/Sequences/{sanitized_sequence_name}"
    sequence_holder_path = f"{sequence_folder}/_sequenceholder"
    master_sequence_path = f"{sequence_folder}/{sanitized_shot_name}"
    shot_folder = f"{sequence_folder}/{sanitized_shot_name}"
    subsequences_folder = f"{shot_folder}/SubSequences"
    render_passes_folder = f"{shot_folder}/RenderPasses"

    _log(f"Resolved path - sequence folder: {sequence_folder}")
    _log(f"Resolved path - required _sequenceholder asset: {sequence_holder_path}")
    _log(f"Resolved path - master sequence asset: {master_sequence_path}")
    _log(f"Resolved path - shot folder: {shot_folder}")
    _log(f"Resolved path - subsequences folder: {subsequences_folder}")
    _log(f"Resolved path - render passes folder: {render_passes_folder}")

    if not unreal.EditorAssetLibrary.does_directory_exist(sequence_folder):
        _log_error(f"Failure reason: sequence folder does not exist: {sequence_folder}")
        _log("Final return value: False")
        return False

    if not unreal.EditorAssetLibrary.does_asset_exist(sequence_holder_path):
        _log_error(f"Failure reason: required _sequenceholder is missing: {sequence_holder_path}")
        _log("Final return value: False")
        return False

    master_sequence = _load_level_sequence(master_sequence_path, required=True)
    _log(f"Master sequence found: {bool(master_sequence)}")
    if not master_sequence:
        _log_error(f"Failure reason: could not load valid master Level Sequence: {master_sequence_path}")
        _log("Final return value: False")
        return False

    if not _set_sequence_playback_range(master_sequence, start_frame, end_frame):
        _log_error(f"Failure reason: unable to set playback range on master sequence: {master_sequence_path}")
        _log("Final return value: False")
        return False

    _log(f"Updated master playback range: asset={master_sequence_path}, start={start_frame}, end={end_frame}")

    modified_subsequences = []
    modified_render_passes = []
    failed_child_names = []

    if unreal.EditorAssetLibrary.does_directory_exist(subsequences_folder):
        for asset_path in _list_assets(subsequences_folder):
            _log(f"Subsequence asset found: {asset_path}")
            sequence_asset = _load_level_sequence(asset_path, required=False)
            if not sequence_asset:
                child_name = _get_asset_name(asset_path)
                if child_name:
                    failed_child_names.append(child_name)
                continue

            if not _set_sequence_playback_range(sequence_asset, start_frame, end_frame):
                _log_error(f"Failure reason: unable to set playback range for subsequence: {asset_path}")
                child_name = _get_asset_name(sequence_asset)
                if child_name:
                    failed_child_names.append(child_name)
                continue

            _log(f"Updated subsequence playback range: {asset_path}")
            modified_subsequences.append((asset_path, sequence_asset))
    else:
        _log(f"SubSequences folder does not exist; continuing: {subsequences_folder}")

    if unreal.EditorAssetLibrary.does_directory_exist(render_passes_folder):
        for asset_path in _list_assets(render_passes_folder):
            _log(f"Render pass asset found: {asset_path}")
            sequence_asset = _load_level_sequence(asset_path, required=False)
            if not sequence_asset:
                child_name = _get_asset_name(asset_path)
                if child_name:
                    failed_child_names.append(child_name)
                continue

            if not _set_sequence_playback_range(sequence_asset, start_frame, end_frame):
                _log_error(f"Failure reason: unable to set playback range for render pass: {asset_path}")
                child_name = _get_asset_name(sequence_asset)
                if child_name:
                    failed_child_names.append(child_name)
                continue

            _log(f"Updated render pass playback range: {asset_path}")
            modified_render_passes.append((asset_path, sequence_asset))
    else:
        _log(f"RenderPasses folder does not exist; continuing: {render_passes_folder}")

    _, failed_master_sync_names = _sync_master_subsequence_sections(
        master_sequence=master_sequence,
        subsequences_folder=subsequences_folder,
        start_frame=start_frame,
        end_frame=end_frame,
    )
    failed_child_names.extend(failed_master_sync_names)

    for _, render_pass_sequence in modified_render_passes:
        _, render_pass_sync_failed = _sync_render_pass_sections(
            render_pass_sequence=render_pass_sequence,
            master_sequence_path=master_sequence_path,
            start_frame=start_frame,
            end_frame=end_frame,
        )
        if render_pass_sync_failed:
            child_name = _get_asset_name(render_pass_sequence)
            if child_name:
                failed_child_names.append(child_name)

    for asset_path, sequence_asset in modified_subsequences:
        if not _save_asset(sequence_asset, asset_path):
            _log_error(f"Failed to save subsequence: {asset_path}")
            child_name = _get_asset_name(sequence_asset)
            if child_name:
                failed_child_names.append(child_name)

    for asset_path, sequence_asset in modified_render_passes:
        if not _save_asset(sequence_asset, asset_path):
            _log_error(f"Failed to save render pass: {asset_path}")
            child_name = _get_asset_name(sequence_asset)
            if child_name:
                failed_child_names.append(child_name)

    if not _save_asset(master_sequence, master_sequence_path):
        _log_error(f"Failure reason: failed to save master sequence: {master_sequence_path}")
        _print_failed_sequence_names(failed_child_names)
        _log("Final return value: False")
        return False

    _print_failed_sequence_names(failed_child_names)
    _log("Final return value: True")
    return True
