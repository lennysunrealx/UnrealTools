import re
import unreal


LOG_PREFIX = "[CreateCoreSubSequences]"
SUBSEQUENCE_SUFFIXES = ["ANM", "CAM", "ENV", "FX", "LGT", "LVL"]


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} {message}")


def _sanitize_show_name(value):
    if value is None:
        return ""
    return "".join(ch for ch in str(value) if ch.isalnum())


def _sanitize_shot_name(value):
    if value is None:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", str(value))
    return cleaned.upper()


def _is_valid_frame_number(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _ensure_folder(path):
    if unreal.EditorAssetLibrary.does_directory_exist(path):
        return True
    if unreal.EditorAssetLibrary.make_directory(path):
        _log(f"Created folder: {path}")
        return True
    _log_error(f"Failed to create folder: {path}")
    return False


def _set_subsequence_reference(section, sequence_asset):
    if hasattr(section, "set_sequence"):
        section.set_sequence(sequence_asset)
        return True

    if hasattr(section, "set_sub_sequence"):
        section.set_sub_sequence(sequence_asset)
        return True

    try:
        section.set_editor_property("sub_sequence", sequence_asset)
        return True
    except Exception:
        return False


def _get_subsequence_reference(section):
    if hasattr(section, "get_sequence"):
        return section.get_sequence()

    if hasattr(section, "get_sub_sequence"):
        return section.get_sub_sequence()

    try:
        return section.get_editor_property("sub_sequence")
    except Exception:
        return None


def _set_section_range(section, start_frame, end_frame):
    if hasattr(section, "set_range"):
        section.set_range(start_frame, end_frame)
        return True

    range_applied = False

    if hasattr(section, "set_start_frame"):
        section.set_start_frame(start_frame)
        range_applied = True

    if hasattr(section, "set_end_frame"):
        section.set_end_frame(end_frame)
        range_applied = True

    if hasattr(section, "set_start_frame_bounded"):
        section.set_start_frame_bounded(False)

    if hasattr(section, "set_end_frame_bounded"):
        section.set_end_frame_bounded(False)

    return range_applied


def _get_sequence_tracks(sequence):
    if hasattr(sequence, "get_tracks"):
        return sequence.get_tracks()

    if hasattr(sequence, "get_master_tracks"):
        return sequence.get_master_tracks()

    _log_error("Unable to inspect sequence tracks: sequence has neither get_tracks() nor get_master_tracks().")
    return []


def _add_subsequence_track(sequence):
    if hasattr(sequence, "add_track"):
        return sequence.add_track(unreal.MovieSceneSubTrack)

    if hasattr(sequence, "add_master_track"):
        return sequence.add_master_track(unreal.MovieSceneSubTrack)

    _log_error("Unable to create subsequence track: sequence has neither add_track() nor add_master_track().")
    return None


def _get_track_sections(track):
    if hasattr(track, "get_sections"):
        return track.get_sections()

    if hasattr(unreal, "MovieSceneTrackExtensions") and hasattr(unreal.MovieSceneTrackExtensions, "get_sections"):
        return unreal.MovieSceneTrackExtensions.get_sections(track)

    _log_error("Unable to inspect track sections: track has no get_sections() and MovieSceneTrackExtensions.get_sections() is unavailable.")
    return []


def _build_existing_subsequence_path_set(master_sequence):
    existing_paths = set()
    for track in _get_sequence_tracks(master_sequence):
        if not isinstance(track, unreal.MovieSceneSubTrack):
            continue
        for section in _get_track_sections(track):
            sub_sequence = _get_subsequence_reference(section)
            if not sub_sequence:
                continue
            existing_paths.add(sub_sequence.get_path_name())
    return existing_paths


def run(show_name, shot_name, start_frame, end_frame):
    """
    Create core shot subsequences and add them to the shot master sequence.

    Returns:
        list[str]: Asset paths for core subsequences (created or existing), or [] on failure.
    """
    sub_sequences = []

    sanitized_show_name = _sanitize_show_name(show_name)
    sanitized_shot_name = _sanitize_shot_name(shot_name)

    if not sanitized_show_name:
        _log_error("Sanitized show_name is empty.")
        return sub_sequences

    if not sanitized_shot_name:
        _log_error("Sanitized shot_name is empty.")
        return sub_sequences

    if not _is_valid_frame_number(start_frame) or not _is_valid_frame_number(end_frame):
        _log_error("start_frame and end_frame must both be integers.")
        return sub_sequences

    if end_frame < start_frame:
        _log_error("end_frame cannot be less than start_frame.")
        return sub_sequences

    sequence_folder_name = sanitized_shot_name.split("_", 1)[0]
    if not sequence_folder_name:
        _log_error("Derived sequence folder name is empty.")
        return sub_sequences

    base_sequence_folder = f"/Game/_{sanitized_show_name}/Sequences/{sequence_folder_name}"
    sequence_holder_path = f"{base_sequence_folder}/_sequenceholder"
    master_sequence_path = f"{base_sequence_folder}/{sanitized_shot_name}"

    if not unreal.EditorAssetLibrary.does_directory_exist(base_sequence_folder):
        _log_error(f"Sequence folder does not exist: {base_sequence_folder}")
        return sub_sequences

    if not unreal.EditorAssetLibrary.does_asset_exist(sequence_holder_path):
        _log_error(
            f"Sequence folder does not contain required '_sequenceholder': {sequence_holder_path}"
        )
        return sub_sequences

    if not unreal.EditorAssetLibrary.does_asset_exist(master_sequence_path):
        _log_error(f"Master shot Level Sequence does not exist: {master_sequence_path}")
        return sub_sequences

    master_sequence = unreal.EditorAssetLibrary.load_asset(master_sequence_path)
    if not master_sequence or not isinstance(master_sequence, unreal.LevelSequence):
        _log_error(f"Master sequence is invalid or not a Level Sequence: {master_sequence_path}")
        return sub_sequences

    shot_folder = master_sequence_path
    shot_subsequence_folder = f"{shot_folder}/SubSequences"

    if not _ensure_folder(shot_folder):
        return sub_sequences

    if not _ensure_folder(shot_subsequence_folder):
        return sub_sequences

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory = unreal.LevelSequenceFactoryNew()

    subsequence_assets = []

    for suffix in SUBSEQUENCE_SUFFIXES:
        asset_name = f"{sanitized_shot_name}_{suffix}"
        asset_path = f"{shot_subsequence_folder}/{asset_name}"

        if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            loaded_subsequence = unreal.EditorAssetLibrary.load_asset(asset_path)
            if not loaded_subsequence or not isinstance(loaded_subsequence, unreal.LevelSequence):
                _log_error(f"Existing asset is invalid or not a Level Sequence: {asset_path}")
                return []
            _log(f"Reusing existing subsequence: {asset_path}")
        else:
            _log(f"Creating subsequence: {asset_path}")
            loaded_subsequence = asset_tools.create_asset(
                asset_name=asset_name,
                package_path=shot_subsequence_folder,
                asset_class=unreal.LevelSequence,
                factory=factory,
            )
            if not loaded_subsequence:
                _log_error(f"Failed to create subsequence asset: {asset_path}")
                return []

        loaded_subsequence.set_playback_start(start_frame)
        loaded_subsequence.set_playback_end(end_frame)

        if not unreal.EditorAssetLibrary.save_loaded_asset(loaded_subsequence):
            _log_error(f"Failed to save subsequence: {asset_path}")
            return []

        sub_sequences.append(asset_path)
        subsequence_assets.append((asset_path, loaded_subsequence))

    existing_references = _build_existing_subsequence_path_set(master_sequence)

    modified_master = False

    for asset_path, subsequence_asset in subsequence_assets:
        if asset_path in existing_references:
            _log(f"Subsequence already referenced in master, skipping track creation: {asset_path}")
            continue

        track = _add_subsequence_track(master_sequence)
        if not track:
            _log_error(f"Failed to create subsequence track for: {asset_path}")
            return []

        section = track.add_section()
        if not section:
            _log_error(f"Failed to create subsequence section for: {asset_path}")
            return []

        if not _set_subsequence_reference(section, subsequence_asset):
            _log_error(f"Failed to assign subsequence asset to section: {asset_path}")
            return []

        if _set_section_range(section, start_frame, end_frame):
            _log(f"Set section range {start_frame}-{end_frame} for: {asset_path}")
        else:
            _log(f"Section range API not available; skipped explicit range set for: {asset_path}")

        existing_references.add(asset_path)
        modified_master = True
        _log(f"Added subsequence to master sequence: {asset_path}")

    if modified_master:
        if not unreal.EditorAssetLibrary.save_loaded_asset(master_sequence):
            _log_error(f"Failed to save master sequence: {master_sequence_path}")
            return []
        _log(f"Saved master sequence: {master_sequence_path}")
    else:
        _log(f"No master sequence changes required: {master_sequence_path}")

    return sub_sequences
