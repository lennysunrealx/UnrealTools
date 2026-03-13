import re
import unreal

LOG_PREFIX = "[GetNextShotNumber]"


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} {message}")


def _sanitize_show_name(show_name):
    return "".join(ch for ch in str(show_name or "") if ch.isalnum())


def _sanitize_sequence_name(sequence_name):
    cleaned = "".join(ch for ch in str(sequence_name or "") if ch.isalnum() or ch == "_")
    return cleaned.upper()


def _extract_asset_name(asset_path):
    """
    Convert an Unreal asset path like:
        /Game/_Marathon/Sequences/ABC/ABC_000_0050.ABC_000_0050
    into:
        ABC_000_0050
    """
    leaf = asset_path.rsplit("/", 1)[-1]
    return leaf.split(".", 1)[0]


def _parse_shot_name(asset_name):
    """
    Parse names like:
        SEQ_000_0050

    Returns:
        {
            "shot_name": "SEQ_000_0050",
            "shot_sequence": "SEQ",
            "shot_number": 50,
        }
    """
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


def _round_up_to_next_multiple_of_50(value):
    if value % 50 == 0:
        return value
    return ((value + 49) // 50) * 50


def run(show_name, sequence_name):
    sanitized_show_name = _sanitize_show_name(show_name)
    sanitized_sequence_name = _sanitize_sequence_name(sequence_name)

    _log(f"Input show_name: '{show_name}'")
    _log(f"Input sequence_name: '{sequence_name}'")
    _log(f"Sanitized show_name: '{sanitized_show_name}'")
    _log(f"Sanitized sequence_name: '{sanitized_sequence_name}'")

    if not sanitized_show_name:
        _log_error(f"Invalid show_name after sanitizing: '{show_name}'")
        return 0

    if not sanitized_sequence_name:
        _log_error(f"Invalid sequence_name after sanitizing: '{sequence_name}'")
        return 0

    target_folder = f"/Game/_{sanitized_show_name}/Sequences/{sanitized_sequence_name}"
    _log(f"Target folder: {target_folder}")

    editor_asset_lib = unreal.EditorAssetLibrary

    if not editor_asset_lib.does_directory_exist(target_folder):
        _log_error(f"Target folder does not exist: {target_folder}")
        return 0

    sequence_holder_path = f"{target_folder}/_sequenceholder"
    if not editor_asset_lib.does_asset_exist(sequence_holder_path):
        _log_error(f"Target folder is missing required '_sequenceholder': {sequence_holder_path}")
        return 0

    asset_paths = editor_asset_lib.list_assets(
        target_folder,
        recursive=False,
        include_folder=False
    )

    _log(f"Found {len(asset_paths)} asset(s) in folder.")

    highest_shot_number = None

    for asset_path in asset_paths:
        asset_name = _extract_asset_name(asset_path)
        _log(f"Inspecting asset: path='{asset_path}' name='{asset_name}'")

        if asset_name == "_sequenceholder":
            continue

        parsed = _parse_shot_name(asset_name)
        if not parsed:
            _log(f"Skipping non-shot asset name: {asset_name}")
            continue

        if parsed["shot_sequence"].upper() != sanitized_sequence_name:
            _log(
                f"Skipping asset with non-matching sequence prefix: "
                f"{asset_name} (parsed sequence='{parsed['shot_sequence']}')"
            )
            continue

        asset_obj = editor_asset_lib.load_asset(asset_path)
        if not asset_obj:
            _log(f"Could not load asset: {asset_path}")
            continue

        if not isinstance(asset_obj, unreal.LevelSequence):
            _log(f"Skipping non-LevelSequence asset: {asset_name}")
            continue

        shot_number = parsed["shot_number"]
        _log(f"Valid shot found: {asset_name} -> shot_number={shot_number}")

        if highest_shot_number is None or shot_number > highest_shot_number:
            highest_shot_number = shot_number

    if highest_shot_number is None:
        next_shot_number = 50
        _log(f"No valid shots found in {target_folder}. Returning {next_shot_number}.")
        return next_shot_number

    next_shot_number = highest_shot_number + 50
    next_shot_number = _round_up_to_next_multiple_of_50(next_shot_number)

    _log(
        f"Highest shot: {highest_shot_number} | "
        f"Next shot number: {next_shot_number} | "
        f"Folder: {target_folder}"
    )

    return int(next_shot_number)
