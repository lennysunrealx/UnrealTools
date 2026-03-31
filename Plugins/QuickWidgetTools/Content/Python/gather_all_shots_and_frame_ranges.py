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


def _build_shot_folder_path(target_folder, shot_name):
    return f"{target_folder}/{shot_name}"


def _build_expected_data_asset_path(shot_folder_path, shot_name):
    data_asset_name = f"{shot_name}_Data"
    return f"{shot_folder_path}/{data_asset_name}.{data_asset_name}"


def _load_data_asset_for_shot(shot_folder_path, shot_name):
    editor_asset_lib = unreal.EditorAssetLibrary
    expected_data_asset_path = _build_expected_data_asset_path(shot_folder_path, shot_name)

    if editor_asset_lib.does_asset_exist(expected_data_asset_path):
        loaded = unreal.load_asset(expected_data_asset_path)
        if loaded:
            _log(f"Loaded expected shot data asset for '{shot_name}': {expected_data_asset_path}")
            return loaded
        _log_error(f"Failed to load expected shot data asset for '{shot_name}': {expected_data_asset_path}")

    return _find_fallback_data_asset_in_shot_folder(shot_folder_path, shot_name)


def _find_fallback_data_asset_in_shot_folder(shot_folder_path, shot_name):
    editor_asset_lib = unreal.EditorAssetLibrary

    if not editor_asset_lib.does_directory_exist(shot_folder_path):
        _log(f"Shot folder does not exist for '{shot_name}': {shot_folder_path}")
        return None

    asset_paths = editor_asset_lib.list_assets(
        shot_folder_path,
        recursive=False,
        include_folder=False,
    )

    if not asset_paths:
        _log(f"No assets in shot folder for fallback data asset lookup: {shot_folder_path}")
        return None

    preferred_name = f"{shot_name}_Data"
    fallback_candidate_path = None

    for asset_path in asset_paths:
        asset_name = _extract_asset_name(asset_path)
        if asset_name == preferred_name:
            fallback_candidate_path = asset_path
            break

        if asset_name.endswith("_Data") and fallback_candidate_path is None:
            fallback_candidate_path = asset_path

    if not fallback_candidate_path:
        _log(f"No fallback shot data asset candidates found in folder: {shot_folder_path}")
        return None

    loaded = unreal.load_asset(fallback_candidate_path)
    if not loaded:
        _log_error(f"Failed to load fallback shot data asset: {fallback_candidate_path}")
        return None

    _log(f"Loaded fallback shot data asset for '{shot_name}': {fallback_candidate_path}")
    return loaded


def _get_level_property_value(shot_data_asset):
    property_names = [
        "AssociatedLevel",
        "Level",
        "LevelAssociation",
        "AssociatedLevelStored",
    ]

    for property_name in property_names:
        try:
            value = shot_data_asset.get_editor_property(property_name)
            _log(f"Read level association using property '{property_name}'.")
            return value
        except Exception:
            continue

    _log("Shot data asset does not expose a supported level association property.")
    return None


def _convert_level_value_to_asset_path(level_value):
    def _clean_candidate(candidate):
        if not isinstance(candidate, str):
            return ""
        cleaned = candidate.strip()
        if not cleaned or cleaned in ("None", "null"):
            return ""
        if cleaned.startswith("SoftObjectPath(") and cleaned.endswith(")"):
            cleaned = cleaned[len("SoftObjectPath(") : -1].strip().strip("\"'")
        return cleaned

    if level_value is None:
        return ""

    if isinstance(level_value, str):
        return _clean_candidate(level_value)

    for getter_name in ("get_asset_path_name", "get_path_name"):
        getter = getattr(level_value, getter_name, None)
        if callable(getter):
            try:
                raw_path = getter()
                cleaned = _clean_candidate(raw_path)
                if cleaned:
                    return cleaned
            except Exception:
                pass

    try:
        as_text = _clean_candidate(str(level_value))
    except Exception:
        as_text = ""

    if as_text:
        return as_text

    return ""


def _get_level_path_for_shot(target_folder, shot_name):
    shot_folder_path = _build_shot_folder_path(target_folder, shot_name)
    shot_data_asset = _load_data_asset_for_shot(shot_folder_path, shot_name)
    if not shot_data_asset:
        return ""

    level_value = _get_level_property_value(shot_data_asset)
    if level_value is None:
        return ""

    level_path = _convert_level_value_to_asset_path(level_value)
    if not level_path:
        _log(f"Level association is unset or invalid for '{shot_name}'.")
        return ""

    return level_path


def run(show_name, selected_sequence):
    shot_names = []
    start_frames = []
    end_frames = []
    level_paths = []

    sanitized_show_name = _sanitize_show_name(show_name)
    sanitized_selected_sequence = _sanitize_selected_sequence(selected_sequence)

    _log(f"Input show_name: '{show_name}'")
    _log(f"Input selected_sequence: '{selected_sequence}'")
    _log(f"Sanitized show_name: '{sanitized_show_name}'")
    _log(f"Sanitized selected_sequence: '{sanitized_selected_sequence}'")

    if not sanitized_show_name:
        _log_error(f"Invalid show_name after sanitizing: '{show_name}'")
        return [], [], [], []

    if not sanitized_selected_sequence:
        _log_error(f"Invalid selected_sequence after sanitizing: '{selected_sequence}'")
        return [], [], [], []

    target_folder = f"/Game/_{sanitized_show_name}/Sequences/{sanitized_selected_sequence}"
    _log(f"Target folder: {target_folder}")

    editor_asset_lib = unreal.EditorAssetLibrary

    if not editor_asset_lib.does_directory_exist(target_folder):
        _log_error(f"Target folder does not exist: {target_folder}")
        return [], [], [], []

    sequenceholder_path = f"{target_folder}/_sequenceholder"
    if not editor_asset_lib.does_asset_exist(sequenceholder_path):
        _log_error(f"Missing required '_sequenceholder' in folder: {sequenceholder_path}")
        return [], [], [], []

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

        level_path = _get_level_path_for_shot(target_folder, asset_name)

        valid_rows.append(
            (parsed["shot_number"], asset_name, playback_start, playback_end, level_path)
        )

    if not valid_rows:
        _log(f"No valid shot Level Sequences found in {target_folder}")
        return [], [], [], []

    valid_rows.sort(key=lambda row: row[0])

    for _, asset_name, playback_start, playback_end, level_path in valid_rows:
        shot_names.append(asset_name)
        start_frames.append(playback_start)
        end_frames.append(playback_end)
        level_paths.append(level_path)

    _log(f"Returning {len(shot_names)} shot(s) from {target_folder}")
    return shot_names, start_frames, end_frames, level_paths
