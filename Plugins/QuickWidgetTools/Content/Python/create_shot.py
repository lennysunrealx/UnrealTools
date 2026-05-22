import re
import unreal


LOG_PREFIX = "[CreateShot]"


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


def run(show_name, shot_name, start_frame, end_frame):
    """
    Create a Level Sequence for the given shot and set playback frame range.

    Returns:
        str: The created (or existing) asset path on success, or "" on failure.
    """
    sanitized_show_name = _sanitize_show_name(show_name)
    sanitized_shot_name = _sanitize_shot_name(shot_name)

    if not sanitized_show_name:
        _log_error("Sanitized show_name is empty.")
        return ""

    if not sanitized_shot_name:
        _log_error("Sanitized shot_name is empty.")
        return ""

    if not _is_valid_frame_number(start_frame) or not _is_valid_frame_number(end_frame):
        _log_error("start_frame and end_frame must both be integers.")
        return ""

    if end_frame < start_frame:
        _log_error("end_frame cannot be less than start_frame.")
        return ""

    sanitized_sequence_name = sanitized_shot_name.split("_", 1)[0]
    if not sanitized_sequence_name:
        _log_error("Derived sequence folder name is empty.")
        return ""

    target_folder = f"/Game/_{sanitized_show_name}/Sequences/{sanitized_sequence_name}"
    sequence_holder_path = f"{target_folder}/_sequenceholder"
    final_asset_path = f"{target_folder}/{sanitized_shot_name}"

    editor_asset_lib = unreal.EditorAssetLibrary

    if not editor_asset_lib.does_directory_exist(target_folder):
        _log_error(f"Target sequence folder does not exist: {target_folder}")
        return ""

    if not editor_asset_lib.does_asset_exist(sequence_holder_path):
        _log_error(
            f"Target sequence folder is missing required asset '_sequenceholder': {sequence_holder_path}"
        )
        return ""

    if editor_asset_lib.does_asset_exist(final_asset_path):
        _log(f"Shot asset already exists, skipping creation: {final_asset_path}")
        return final_asset_path

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory = unreal.LevelSequenceFactoryNew()

    _log(f"Creating Level Sequence: {final_asset_path}")
    created_asset = asset_tools.create_asset(
        asset_name=sanitized_shot_name,
        package_path=target_folder,
        asset_class=unreal.LevelSequence,
        factory=factory,
    )

    if not created_asset:
        _log_error("Failed to create Level Sequence asset.")
        return ""

    loaded_asset = editor_asset_lib.load_asset(final_asset_path)
    if not loaded_asset or not isinstance(loaded_asset, unreal.LevelSequence):
        _log_error(f"Created asset is invalid or not a Level Sequence: {final_asset_path}")
        return ""

    loaded_asset.set_playback_start(start_frame)
    loaded_asset.set_playback_end(end_frame)

    if not editor_asset_lib.save_loaded_asset(loaded_asset):
        _log_error(f"Failed to save created Level Sequence: {final_asset_path}")
        return ""

    _log(f"Created shot sequence successfully: {final_asset_path}")
    return final_asset_path
