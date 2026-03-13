import re
import unreal


LOG_PREFIX = "[GetNextShotNumber]"


def _sanitize_show_name(show_name):
    return "".join(ch for ch in str(show_name or "") if ch.isalnum())


def _sanitize_sequence_name(sequence_name):
    cleaned = "".join(ch for ch in str(sequence_name or "") if ch.isalnum() or ch == "_")
    return cleaned.upper()


def _parse_shot_name(asset_name):
    """Parse names like SEQ_000_0050 (supports underscores in SEQ by splitting from right)."""
    parts = asset_name.rsplit("_", 2)
    if len(parts) != 3:
        return None

    shot_sequence, shot_block, shot_number_token = parts
    if not shot_sequence:
        return None
    if not re.fullmatch(r"\d{3}", shot_block):
        return None
    if not re.fullmatch(r"\d+", shot_number_token):
        return None

    return {
        "shot_name": asset_name,
        "shot_sequence": shot_sequence,
        "shot_number": int(shot_number_token),
    }


def run(show_name, sequence_name):
    sanitized_show_name = _sanitize_show_name(show_name)
    sanitized_sequence_name = _sanitize_sequence_name(sequence_name)

    if not sanitized_show_name:
        unreal.log_error(f"{LOG_PREFIX} Invalid show_name after sanitizing: '{show_name}'")
        return 0

    if not sanitized_sequence_name:
        unreal.log_error(f"{LOG_PREFIX} Invalid sequence_name after sanitizing: '{sequence_name}'")
        return 0

    target_folder = f"/Game/_{sanitized_show_name}/Sequences/{sanitized_sequence_name}"

    if not unreal.EditorAssetLibrary.does_directory_exist(target_folder):
        unreal.log_error(f"{LOG_PREFIX} Target folder does not exist: {target_folder}")
        return 0

    asset_paths = unreal.EditorAssetLibrary.list_assets(target_folder, recursive=False, include_folder=False)

    if not any("_sequenceholder" in path.lower() for path in asset_paths):
        unreal.log_error(f"{LOG_PREFIX} Target folder is missing required '_sequenceholder': {target_folder}")
        return 0

    highest_shot_number = None

    for asset_path in asset_paths:
        asset_name = asset_path.rsplit("/", 1)[-1]

        parsed = _parse_shot_name(asset_name)
        if not parsed:
            continue

        if parsed["shot_sequence"].upper() != sanitized_sequence_name:
            continue

        asset_obj = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not asset_obj:
            continue

        if not isinstance(asset_obj, unreal.LevelSequence):
            continue

        shot_number = parsed["shot_number"]
        if highest_shot_number is None or shot_number > highest_shot_number:
            highest_shot_number = shot_number

    if highest_shot_number is None:
        next_shot_number = 50
        unreal.log(f"{LOG_PREFIX} No valid shots found in {target_folder}. Returning {next_shot_number}.")
        return next_shot_number

    next_shot_number = highest_shot_number + 50
    if next_shot_number % 50 != 0:
        next_shot_number = ((next_shot_number + 49) // 50) * 50

    unreal.log(
        f"{LOG_PREFIX} Highest shot: {highest_shot_number} | Next shot number: {next_shot_number} | Folder: {target_folder}"
    )
    return int(next_shot_number)
