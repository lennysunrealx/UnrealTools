import re
import unreal


LOG_PREFIX = "[GatherAllShotsAndFrameRanges]"

_START_FRAME_PROPERTY_NAME = "StartFrame"
_END_FRAME_PROPERTY_NAME = "EndFrame"

_LEVEL_PROPERTY_NAMES = [
    "AssociatedLevelPathString",
    "AssociatedLevel",
    "Level",
    "LevelAssociation",
    "AssociatedLevelStored",
]


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_warning(message):
    unreal.log_warning(f"{LOG_PREFIX} Warning: {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} Error: {message}")


def _sanitize_show_name(show_name):
    return "".join(ch for ch in str(show_name or "") if ch.isalnum())


def _sanitize_selected_sequence(selected_sequence):
    cleaned = "".join(ch for ch in str(selected_sequence or "") if ch.isalnum() or ch == "_")
    return cleaned.upper()


def _extract_asset_name(asset_path):
    leaf = str(asset_path).rstrip("/").rsplit("/", 1)[-1]
    return leaf.split(".", 1)[0]


def _parse_shot_name(asset_name):
    match = re.fullmatch(r"([A-Za-z0-9]+)_(\d{3})_(\d{4,})", asset_name)
    if not match:
        return None

    return {
        "sequence_prefix": match.group(1),
        "shot_number": int(match.group(3)),
    }


def _join_game_path(*parts):
    cleaned_parts = []

    for part in parts:
        text = str(part or "").strip().replace("\\", "/")
        while "//" in text:
            text = text.replace("//", "/")
        text = text.strip("/")

        if not text:
            continue

        cleaned_parts.append(text)

    if not cleaned_parts:
        return ""

    if cleaned_parts[0] == "Game":
        return "/" + "/".join(cleaned_parts)

    if cleaned_parts[0].startswith("Game"):
        return "/" + "/".join(cleaned_parts)

    if str(parts[0] or "").strip().startswith("/"):
        return "/" + "/".join(cleaned_parts)

    return "/".join(cleaned_parts)


def _build_shot_folder_path(target_folder, shot_name):
    return _join_game_path(target_folder, shot_name)


def _build_expected_data_asset_path(shot_folder_path, shot_name):
    data_asset_name = f"{shot_name}_Data"
    package_path = _join_game_path(shot_folder_path, data_asset_name)
    return f"{package_path}.{data_asset_name}"


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


def _coerce_level_value_to_text(level_value):
    if level_value is None:
        return ""

    if isinstance(level_value, str):
        return level_value

    for getter_name in ("get_asset_path_name", "get_path_name", "to_string"):
        getter = getattr(level_value, getter_name, None)
        if not callable(getter):
            continue

        try:
            raw_value = getter()
        except Exception:
            continue

        if raw_value:
            return str(raw_value)

    try:
        return str(level_value)
    except Exception:
        return ""


def _normalize_level_object_path(level_value):
    text = _coerce_level_value_to_text(level_value)
    text = str(text or "").strip().strip("\"'")

    if not text or text in ("None", "null"):
        return ""

    if text.startswith("SoftObjectPath(") and text.endswith(")"):
        text = text[len("SoftObjectPath("):-1].strip().strip("\"'")

    text = text.replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")

    if text.endswith(".umap"):
        text = text[:-5]

    # If this is a package path like:
    # /Game/_Nightfall/Assets/LVL_NightForest/LVL_NightForest_v001
    # convert it to an object path:
    # /Game/_Nightfall/Assets/LVL_NightForest/LVL_NightForest_v001.LVL_NightForest_v001
    if text.startswith("/Game/") and "." not in text:
        asset_name = text.rstrip("/").rsplit("/", 1)[-1]
        text = f"{text}.{asset_name}"

    return text


def _read_int_property(asset, property_name, shot_name):
    try:
        raw_value = asset.get_editor_property(property_name)
    except Exception as exc:
        _log_error(
            f"Shot data asset for '{shot_name}' does not expose {property_name}: {exc}"
        )
        return None

    if isinstance(raw_value, bool):
        _log_error(
            f"Shot data asset property {property_name} for '{shot_name}' is bool, expected int."
        )
        return None

    try:
        return int(raw_value)
    except Exception as exc:
        _log_error(
            f"Shot data asset property {property_name} for '{shot_name}' could not be converted to int. "
            f"Value={raw_value!r}, Error={exc}"
        )
        return None


def _read_level_object_path(shot_data_asset, shot_name):
    for property_name in _LEVEL_PROPERTY_NAMES:
        try:
            raw_value = shot_data_asset.get_editor_property(property_name)
        except Exception:
            continue

        object_path = _normalize_level_object_path(raw_value)
        if object_path:
            _log(f"Read level association using property '{property_name}': {object_path}")
            return object_path

    _log(f"Level association is unset or invalid for '{shot_name}'.")
    return ""


def _get_cached_shot_data(target_folder, shot_name):
    shot_folder_path = _build_shot_folder_path(target_folder, shot_name)
    shot_data_asset = _load_data_asset_for_shot(shot_folder_path, shot_name)

    if not shot_data_asset:
        return None

    start_frame = _read_int_property(
        shot_data_asset,
        _START_FRAME_PROPERTY_NAME,
        shot_name,
    )
    if start_frame is None:
        return None

    end_frame = _read_int_property(
        shot_data_asset,
        _END_FRAME_PROPERTY_NAME,
        shot_name,
    )
    if end_frame is None:
        return None

    level_object_path = _read_level_object_path(shot_data_asset, shot_name)

    return {
        "start_frame": start_frame,
        "end_frame": end_frame,
        "level_path": level_object_path,
    }


def _empty_result():
    return [], [], [], [], 0


def run(show_name, selected_sequence):
    shot_names = []
    start_frames = []
    end_frames = []
    level_paths = []
    has_any_shots = 0

    sanitized_show_name = _sanitize_show_name(show_name)
    sanitized_selected_sequence = _sanitize_selected_sequence(selected_sequence)

    _log(f"Input show_name: '{show_name}'")
    _log(f"Input selected_sequence: '{selected_sequence}'")
    _log(f"Sanitized show_name: '{sanitized_show_name}'")
    _log(f"Sanitized selected_sequence: '{sanitized_selected_sequence}'")

    if not sanitized_show_name:
        _log_error(f"Invalid show_name after sanitizing: '{show_name}'")
        return _empty_result()

    if not sanitized_selected_sequence:
        _log_error(f"Invalid selected_sequence after sanitizing: '{selected_sequence}'")
        return _empty_result()

    target_folder = _join_game_path(
        "/Game",
        f"_{sanitized_show_name}",
        "Sequences",
        sanitized_selected_sequence,
    )
    _log(f"Target folder: {target_folder}")

    editor_asset_lib = unreal.EditorAssetLibrary

    if not editor_asset_lib.does_directory_exist(target_folder):
        _log_error(f"Target folder does not exist: {target_folder}")
        return _empty_result()

    sequenceholder_path = _join_game_path(target_folder, "_sequenceholder")
    if not editor_asset_lib.does_asset_exist(sequenceholder_path):
        _log_error(f"Missing required '_sequenceholder' in folder: {sequenceholder_path}")
        return _empty_result()

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

        # Keep the LevelSequence validation, but do not read frame range from it.
        # Frame range now comes from BP_ShotDataAsset StartFrame / EndFrame.
        asset_obj = editor_asset_lib.load_asset(asset_path)
        if not asset_obj:
            _log_warning(f"Could not load asset: {asset_path}")
            continue

        if not isinstance(asset_obj, unreal.LevelSequence):
            _log(f"Skipping non-Level Sequence asset: {asset_name}")
            continue

        cached_data = _get_cached_shot_data(target_folder, asset_name)
        if cached_data is None:
            continue

        valid_rows.append(
            (
                parsed["shot_number"],
                asset_name,
                cached_data["start_frame"],
                cached_data["end_frame"],
                cached_data["level_path"],
            )
        )

    if not valid_rows:
        _log(f"No valid shot Level Sequences found in {target_folder}")
        return _empty_result()

    valid_rows.sort(key=lambda row: row[0])

    for _, asset_name, start_frame, end_frame, level_path in valid_rows:
        shot_names.append(asset_name)
        start_frames.append(start_frame)
        end_frames.append(end_frame)
        level_paths.append(level_path)

    has_any_shots = 1

    _log(f"Returning {len(shot_names)} shot(s) from {target_folder}")
    return shot_names, start_frames, end_frames, level_paths, has_any_shots
