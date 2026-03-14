import re
import unreal

LOG_PREFIX = "[GatherAllShotsAndFrameRanges]"


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} {message}")


def _sanitize_show_name(show_name):
    return "".join(ch for ch in str(show_name or "") if ch.isalnum())


def _sanitize_selected_sequence(selected_sequence):
    cleaned = "".join(ch for ch in str(selected_sequence or "") if ch.isalnum() or ch == "_")
    return cleaned.upper()


def _extract_asset_name(asset_path):
    leaf = asset_path.rsplit("/", 1)[-1]
    return leaf.split(".", 1)[0]


def _parse_shot_name(asset_name):
    match = re.fullmatch(r"([A-Za-z0-9]+)_(\d{3})_(\d{4,})", asset_name)
    if not match:
        return None

    return {
        "sequence_prefix": match.group(1),
        "shot_number": int(match.group(3)),
    }


def run(show_name, selected_sequence):
    shot_names = []
    start_frames = []
    end_frames = []

    sanitized_show_name = _sanitize_show_name(show_name)
    sanitized_selected_sequence = _sanitize_selected_sequence(selected_sequence)

    _log(f"Input show_name: '{show_name}'")
    _log(f"Input selected_sequence: '{selected_sequence}'")
    _log(f"Sanitized show_name: '{sanitized_show_name}'")
    _log(f"Sanitized selected_sequence: '{sanitized_selected_sequence}'")

    if not sanitized_show_name:
        _log_error(f"Invalid show_name after sanitizing: '{show_name}'")
        return [], [], []

    if not sanitized_selected_sequence:
        _log_error(f"Invalid selected_sequence after sanitizing: '{selected_sequence}'")
        return [], [], []

    target_folder = f"/Game/_{sanitized_show_name}/Sequences/{sanitized_selected_sequence}"
    _log(f"Target folder: {target_folder}")

    editor_asset_lib = unreal.EditorAssetLibrary

    if not editor_asset_lib.does_directory_exist(target_folder):
        _log_error(f"Target folder does not exist: {target_folder}")
        return [], [], []

    sequenceholder_path = f"{target_folder}/_sequenceholder"
    if not editor_asset_lib.does_asset_exist(sequenceholder_path):
        _log_error(f"Missing required '_sequenceholder' in folder: {sequenceholder_path}")
        return [], [], []

    asset_paths = editor_asset_lib.list_assets(
        target_folder,
        recursive=False,
        include_folder=False,
    )
    _log(f"Found {len(asset_paths)} direct asset(s) in target folder.")

    valid_rows = []

    for asset_path in asset_paths:
        asset_name = _extract_asset_name(asset_path)

        if asset_name == "_sequenceholder":
            continue

        parsed = _parse_shot_name(asset_name)
        if not parsed:
            _log(f"Skipping asset with non-shot naming pattern: {asset_name}")
            continue

        if parsed["sequence_prefix"].upper() != sanitized_selected_sequence:
            _log(
                "Skipping shot with mismatched sequence prefix: "
                f"{asset_name} (prefix='{parsed['sequence_prefix']}')"
            )
            continue

        asset_obj = editor_asset_lib.load_asset(asset_path)
        if not asset_obj:
            _log(f"Could not load asset: {asset_path}")
            continue

        if not isinstance(asset_obj, unreal.LevelSequence):
            _log(f"Skipping non-Level Sequence asset: {asset_name}")
            continue

        playback_start = int(asset_obj.get_playback_start())
        playback_end = int(asset_obj.get_playback_end())

        valid_rows.append((parsed["shot_number"], asset_name, playback_start, playback_end))

    if not valid_rows:
        _log(f"No valid shot Level Sequences found in {target_folder}")
        return [], [], []

    valid_rows.sort(key=lambda row: row[0])

    for _, asset_name, playback_start, playback_end in valid_rows:
        shot_names.append(asset_name)
        start_frames.append(playback_start)
        end_frames.append(playback_end)

    _log(f"Returning {len(shot_names)} shot(s) from {target_folder}")
    return shot_names, start_frames, end_frames
