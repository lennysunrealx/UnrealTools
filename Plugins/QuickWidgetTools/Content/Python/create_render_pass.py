import re
import unreal


LOG_PREFIX = "[CreateRenderPass]"


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


def _add_subsequence_track(sequence):
    if hasattr(sequence, "add_track"):
        try:
            return sequence.add_track(unreal.MovieSceneSubTrack)
        except Exception:
            pass

    if hasattr(sequence, "add_master_track"):
        try:
            return sequence.add_master_track(unreal.MovieSceneSubTrack)
        except Exception:
            pass

    return None


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


def _set_subsequence_reference(section, sequence_asset):
    if hasattr(section, "set_sequence"):
        try:
            section.set_sequence(sequence_asset)
            return True
        except Exception:
            pass

    if hasattr(section, "set_sub_sequence"):
        try:
            section.set_sub_sequence(sequence_asset)
            return True
        except Exception:
            pass

    try:
        section.set_editor_property("sub_sequence", sequence_asset)
        return True
    except Exception:
        return False


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

    return had_start and had_end


def _build_referenced_subsequence_paths(sequence):
    referenced_paths = set()

    for track in _get_tracks(sequence):
        if not isinstance(track, unreal.MovieSceneSubTrack):
            continue

        for section in _get_track_sections(track):
            sub_seq = _get_subsequence_reference(section)
            if not sub_seq:
                continue

            try:
                path = sub_seq.get_path_name()
            except Exception:
                path = ""

            if path:
                referenced_paths.add(path)

    return referenced_paths


def _create_folder_if_missing(folder_path):
    if unreal.EditorAssetLibrary.does_directory_exist(folder_path):
        return True
    return unreal.EditorAssetLibrary.make_directory(folder_path)


def run(show_name, shot_name):
    """
    Create or update a beauty render pass Level Sequence for a shot.

    Returns:
        str: beauty sequence asset path on success, or "" on failure.
    """
    sanitized_show_name = _sanitize_show_name(show_name)
    sanitized_shot_name = _sanitize_shot_name(shot_name)

    if not sanitized_show_name:
        _log_error("Sanitized show_name is empty.")
        return ""

    if not sanitized_shot_name:
        _log_error("Sanitized shot_name is empty.")
        return ""

    sanitized_sequence_name = sanitized_shot_name.split("_", 1)[0]
    if not sanitized_sequence_name:
        _log_error("Derived sequence name is empty.")
        return ""

    sequence_folder = f"/Game/_{sanitized_show_name}/Sequences/{sanitized_sequence_name}"
    sequence_holder = f"{sequence_folder}/_sequenceholder"
    master_sequence_path = f"{sequence_folder}/{sanitized_shot_name}"

    if not unreal.EditorAssetLibrary.does_directory_exist(sequence_folder):
        _log_error(f"Sequence folder does not exist: {sequence_folder}")
        return ""

    if not unreal.EditorAssetLibrary.does_asset_exist(sequence_holder):
        _log_error(f"Missing _sequenceholder in sequence folder: {sequence_holder}")
        return ""

    if not unreal.EditorAssetLibrary.does_asset_exist(master_sequence_path):
        _log_error(f"Master sequence does not exist: {master_sequence_path}")
        return ""

    master_sequence = unreal.EditorAssetLibrary.load_asset(master_sequence_path)
    if not master_sequence or not isinstance(master_sequence, unreal.LevelSequence):
        _log_error(f"Master sequence is not a Level Sequence: {master_sequence_path}")
        return ""

    start_frame = master_sequence.get_playback_start()
    end_frame = master_sequence.get_playback_end()

    shot_subfolder = f"{sequence_folder}/{sanitized_shot_name}"
    render_pass_folder = f"{shot_subfolder}/RenderPasses"

    if not _create_folder_if_missing(shot_subfolder):
        _log_error(f"Failed to create or access shot subfolder: {shot_subfolder}")
        return ""

    if not _create_folder_if_missing(render_pass_folder):
        _log_error(f"Failed to create or access RenderPasses folder: {render_pass_folder}")
        return ""

    beauty_asset_name = f"{sanitized_shot_name}_beauty"
    beauty_asset_path = f"{render_pass_folder}/{beauty_asset_name}"

    if unreal.EditorAssetLibrary.does_asset_exist(beauty_asset_path):
        beauty_sequence = unreal.EditorAssetLibrary.load_asset(beauty_asset_path)
        if not beauty_sequence or not isinstance(beauty_sequence, unreal.LevelSequence):
            _log_error(f"Existing beauty asset is not a Level Sequence: {beauty_asset_path}")
            return ""
        _log(f"Using existing beauty sequence: {beauty_asset_path}")
    else:
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        factory = unreal.LevelSequenceFactoryNew()
        beauty_sequence = asset_tools.create_asset(
            asset_name=beauty_asset_name,
            package_path=render_pass_folder,
            asset_class=unreal.LevelSequence,
            factory=factory,
        )
        if not beauty_sequence:
            _log_error(f"Failed to create beauty sequence: {beauty_asset_path}")
            return ""
        _log(f"Created beauty sequence: {beauty_asset_path}")

    beauty_sequence.set_playback_start(start_frame)
    beauty_sequence.set_playback_end(end_frame)

    master_path = master_sequence.get_path_name()
    existing_refs = _build_referenced_subsequence_paths(beauty_sequence)

    if master_path in existing_refs:
        _log("Master sequence already referenced in beauty sequence; skipping duplicate section creation.")
    else:
        sub_track = _add_subsequence_track(beauty_sequence)
        if not sub_track:
            _log_error("Failed to add subsequence track to beauty sequence.")
            return ""

        section = sub_track.add_section()
        if not section:
            _log_error("Failed to add subsequence section to subsequence track.")
            return ""

        if not _set_subsequence_reference(section, master_sequence):
            _log_error("Failed to set subsequence reference to master sequence.")
            return ""

        if not _set_section_range(section, start_frame, end_frame):
            _log("Unable to set section range using current API variant; continuing.")

        _log("Added master sequence as subsequence in beauty sequence.")

    if not unreal.EditorAssetLibrary.save_loaded_asset(beauty_sequence):
        _log_error(f"Failed to save beauty sequence: {beauty_asset_path}")
        return ""

    _log(f"Render pass setup complete: {beauty_asset_path}")
    return beauty_asset_path
