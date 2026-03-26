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
            _log(f"Asset does not exist (skipped): {asset_path}")
        return None

    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not asset:
        _log_error(f"Failed to load asset: {asset_path}")
        return None

    if not isinstance(asset, unreal.LevelSequence):
        _log_error(f"Asset is not a Level Sequence: {asset_path}")
        return None

    return asset


def _save_asset(asset, label):
    if unreal.EditorAssetLibrary.save_loaded_asset(asset):
        _log(f"Save success: {label}")
        return True
    _log_error(f"Save failed: {label}")
    return False


def _sync_master_subsequence_sections(master_sequence, subsequences_folder, start_frame, end_frame):
    updated_count = 0
    prefix = f"{subsequences_folder}/"

    for track in _get_tracks(master_sequence):
        if not isinstance(track, unreal.MovieSceneSubTrack):
            continue

        for section in _get_track_sections(track):
            sub_sequence = _get_subsequence_reference(section)
            if not sub_sequence:
                continue

            try:
                referenced_path = _to_package_path(sub_sequence.get_path_name())
            except Exception:
                referenced_path = ""

            if not referenced_path.startswith(prefix):
                continue

            if _set_section_range(section, start_frame, end_frame):
                updated_count += 1
                _log(
                    "Updated master subsequence section range: "
                    f"reference={referenced_path}, start={start_frame}, end={end_frame}"
                )
            else:
                _log(
                    "Unable to update master subsequence section range with available API: "
                    f"reference={referenced_path}"
                )

    return updated_count


def _sync_render_pass_sections(render_pass_sequence, master_sequence_path, start_frame, end_frame):
    updated_count = 0

    for track in _get_tracks(render_pass_sequence):
        if not isinstance(track, unreal.MovieSceneSubTrack):
            continue

        for section in _get_track_sections(track):
            sub_sequence = _get_subsequence_reference(section)
            if not sub_sequence:
                continue

            try:
                referenced_path = _to_package_path(sub_sequence.get_path_name())
            except Exception:
                referenced_path = ""

            if referenced_path != master_sequence_path:
                continue

            if _set_section_range(section, start_frame, end_frame):
                updated_count += 1
                _log(
                    "Updated render pass section range: "
                    f"render_pass={render_pass_sequence.get_path_name()}, start={start_frame}, end={end_frame}"
                )
            else:
                _log(
                    "Unable to update render pass section range with available API: "
                    f"render_pass={render_pass_sequence.get_path_name()}"
                )

    return updated_count


def run(show_name, sequence_name, shot_name, start_frame, end_frame):
    """Set frame range across a shot package and synchronize nested subsequence sections."""
    _log(
        "Inputs received: "
        f"show_name={show_name}, sequence_name={sequence_name}, shot_name={shot_name}, "
        f"start_frame={start_frame}, end_frame={end_frame}"
    )

    sanitized_show_name = _sanitize_show_name(show_name)
    sanitized_sequence_name = _sanitize_sequence_or_shot_name(sequence_name)
    sanitized_shot_name = _sanitize_sequence_or_shot_name(shot_name)

    _log(
        "Sanitized values: "
        f"show_name={sanitized_show_name}, sequence_name={sanitized_sequence_name}, shot_name={sanitized_shot_name}"
    )

    if not sanitized_show_name:
        _log_error("Validation failed: sanitized show_name is empty.")
        _log("Final return value: False")
        return False

    if not sanitized_sequence_name:
        _log_error("Validation failed: sanitized sequence_name is empty.")
        _log("Final return value: False")
        return False

    if not sanitized_shot_name:
        _log_error("Validation failed: sanitized shot_name is empty.")
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
    sequence_holder = f"{sequence_folder}/_sequenceholder"
    master_sequence_path = f"{sequence_folder}/{sanitized_shot_name}"
    shot_folder = master_sequence_path
    subsequences_folder = f"{shot_folder}/SubSequences"
    render_passes_folder = f"{shot_folder}/RenderPasses"

    _log(f"Resolved path - sequence folder: {sequence_folder}")
    _log(f"Resolved path - required _sequenceholder: {sequence_holder}")
    _log(f"Resolved path - master sequence asset: {master_sequence_path}")
    _log(f"Resolved path - shot folder: {shot_folder}")
    _log(f"Resolved path - subsequences folder: {subsequences_folder}")
    _log(f"Resolved path - render passes folder: {render_passes_folder}")

    if not unreal.EditorAssetLibrary.does_directory_exist(sequence_folder):
        _log_error(f"Failure reason: sequence folder does not exist: {sequence_folder}")
        _log("Final return value: False")
        return False

    if not unreal.EditorAssetLibrary.does_asset_exist(sequence_holder):
        _log_error(f"Failure reason: required _sequenceholder is missing: {sequence_holder}")
        _log("Final return value: False")
        return False

    master_sequence = _load_level_sequence(master_sequence_path, required=True)
    _log(f"Master sequence found: {bool(master_sequence)}")
    if not master_sequence:
        _log_error(f"Failure reason: could not load valid master Level Sequence: {master_sequence_path}")
        _log("Final return value: False")
        return False

    if not _set_sequence_playback_range(master_sequence, start_frame, end_frame):
        _log_error("Failure reason: unable to set playback range on master sequence.")
        _log("Final return value: False")
        return False

    _log(
        "Updated master playback range: "
        f"asset={master_sequence_path}, start={start_frame}, end={end_frame}"
    )

    modified_sequences = []

    if unreal.EditorAssetLibrary.does_directory_exist(subsequences_folder):
        for asset_path in _list_assets(subsequences_folder):
            _log(f"Subsequence asset found: {asset_path}")
            subsequence = _load_level_sequence(asset_path, required=False)
            if not subsequence:
                continue

            if not _set_sequence_playback_range(subsequence, start_frame, end_frame):
                _log_error(f"Failure reason: unable to set playback range for subsequence: {asset_path}")
                _log("Final return value: False")
                return False

            _log(f"Updated subsequence playback range: {asset_path}")
            modified_sequences.append((asset_path, subsequence))
    else:
        _log(f"SubSequences folder does not exist, continuing: {subsequences_folder}")

    render_pass_sequences = []

    if unreal.EditorAssetLibrary.does_directory_exist(render_passes_folder):
        for asset_path in _list_assets(render_passes_folder):
            _log(f"Render pass asset found: {asset_path}")
            render_pass = _load_level_sequence(asset_path, required=False)
            if not render_pass:
                continue

            if not _set_sequence_playback_range(render_pass, start_frame, end_frame):
                _log_error(f"Failure reason: unable to set playback range for render pass: {asset_path}")
                _log("Final return value: False")
                return False

            _log(f"Updated render pass playback range: {asset_path}")
            render_pass_sequences.append((asset_path, render_pass))
    else:
        _log(f"RenderPasses folder does not exist, continuing: {render_passes_folder}")

    _sync_master_subsequence_sections(
        master_sequence=master_sequence,
        subsequences_folder=subsequences_folder,
        start_frame=start_frame,
        end_frame=end_frame,
    )

    for _, render_pass_sequence in render_pass_sequences:
        _sync_render_pass_sections(
            render_pass_sequence=render_pass_sequence,
            master_sequence_path=master_sequence_path,
            start_frame=start_frame,
            end_frame=end_frame,
        )

    for asset_path, subsequence in modified_sequences:
        if not _save_asset(subsequence, asset_path):
            _log_error(f"Failure reason: failed to save subsequence: {asset_path}")
            _log("Final return value: False")
            return False

    for asset_path, render_pass in render_pass_sequences:
        if not _save_asset(render_pass, asset_path):
            _log_error(f"Failure reason: failed to save render pass: {asset_path}")
            _log("Final return value: False")
            return False

    if not _save_asset(master_sequence, master_sequence_path):
        _log_error(f"Failure reason: failed to save master sequence: {master_sequence_path}")
        _log("Final return value: False")
        return False

    _log("Final return value: True")
    return True
