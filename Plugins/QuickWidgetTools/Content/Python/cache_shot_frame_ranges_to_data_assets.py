import re
import unreal


LOG_PREFIX = "[CacheShotFrameRanges]"

SHOT_NAME_PATTERN = re.compile(r"^([A-Za-z0-9]+)_(\d{3})_(\d{4,})$")


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_warning(message):
    unreal.log_warning(f"{LOG_PREFIX} Warning: {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} Error: {message}")


def _clean_game_path(path):
    text = str(path or "").strip().replace("\\", "/")

    while "//" in text:
        text = text.replace("//", "/")

    if len(text) > 1:
        text = text.rstrip("/")

    return text


def _join_game_path(*parts):
    cleaned_parts = []

    for part in parts:
        text = _clean_game_path(part)
        if not text:
            continue

        if cleaned_parts:
            text = text.lstrip("/")

        cleaned_parts.append(text)

    if not cleaned_parts:
        return ""

    return _clean_game_path("/".join(cleaned_parts))


def _is_safe_unreal_path(path):
    text = str(path or "")
    if not text:
        return False

    if "\\" in text:
        return False

    if "//" in text:
        return False

    if not text.startswith("/Game/"):
        return False

    return True


def _extract_asset_name(asset_path):
    leaf = str(asset_path).rstrip("/").rsplit("/", 1)[-1]
    return leaf.split(".", 1)[0]


def _sanitize_show_name(show_name):
    cleaned = "".join(ch for ch in str(show_name or "").strip().strip("/") if ch.isalnum())

    if cleaned.startswith("_"):
        cleaned = cleaned[1:]

    return cleaned


def _sanitize_sequence_name(sequence_name):
    return "".join(
        ch for ch in str(sequence_name or "").strip().strip("/") if ch.isalnum() or ch == "_"
    ).upper()


def _find_current_show_name():
    asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()
    sub_paths = asset_registry.get_sub_paths("/Game", recurse=False)

    candidate_folders = sorted(
        _clean_game_path(path)
        for path in sub_paths
        if path.split("/")[-1].startswith("_")
    )

    _log(f"Found {len(candidate_folders)} underscore-prefixed top-level folder(s).")

    for folder_path in candidate_folders:
        folder_name = folder_path.rsplit("/", 1)[-1]
        showholder_asset_path = _join_game_path(folder_path, "_showholder")

        if unreal.EditorAssetLibrary.does_asset_exist(showholder_asset_path):
            show_name = folder_name[1:] if folder_name.startswith("_") else folder_name
            _log(f"Current show resolved: {show_name}")
            return show_name

        _log(f"Skipping show candidate missing _showholder: {folder_path}")

    _log_error("Could not find current show folder with _showholder.")
    return ""


def _get_sequence_folders(show_name, sequence_filter=""):
    sequences_root = _join_game_path("/Game", f"_{show_name}", "Sequences")

    if not _is_safe_unreal_path(sequences_root):
        _log_error(f"Unsafe sequences root path: {sequences_root}")
        return []

    if not unreal.EditorAssetLibrary.does_directory_exist(sequences_root):
        _log_error(f"Sequences folder does not exist: {sequences_root}")
        return []

    children = unreal.EditorAssetLibrary.list_assets(
        sequences_root,
        recursive=False,
        include_folder=True,
    )

    sequence_folders = []
    clean_sequence_filter = _sanitize_sequence_name(sequence_filter)

    for child_path in children:
        child_path = _clean_game_path(child_path)

        if not unreal.EditorAssetLibrary.does_directory_exist(child_path):
            continue

        sequence_name = child_path.rsplit("/", 1)[-1]
        sequence_name_clean = _sanitize_sequence_name(sequence_name)

        if clean_sequence_filter and sequence_name_clean != clean_sequence_filter:
            continue

        sequenceholder_path = _join_game_path(child_path, "_sequenceholder")

        if not _is_safe_unreal_path(sequenceholder_path):
            _log_warning(f"Skipping unsafe sequenceholder path: {sequenceholder_path}")
            continue

        if not unreal.EditorAssetLibrary.does_asset_exist(sequenceholder_path):
            _log(f"Skipping folder missing _sequenceholder: {child_path}")
            continue

        sequence_folders.append((sequence_name_clean, child_path))

    sequence_folders.sort(key=lambda row: row[0])
    return sequence_folders


def _is_master_shot_sequence_asset(asset_path, sequence_name):
    asset_path = _clean_game_path(asset_path)
    asset_name = _extract_asset_name(asset_path)

    if asset_name == "_sequenceholder":
        return False

    match = SHOT_NAME_PATTERN.fullmatch(asset_name)
    if not match:
        return False

    shot_sequence_prefix = match.group(1).upper()
    if shot_sequence_prefix != str(sequence_name or "").upper():
        return False

    if not _is_safe_unreal_path(asset_path):
        _log_warning(f"Skipping unsafe master sequence path: {asset_path}")
        return False

    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not asset:
        _log_warning(f"Could not load asset: {asset_path}")
        return False

    if not isinstance(asset, unreal.LevelSequence):
        return False

    return True


def _get_master_shot_sequence_paths(sequence_name, sequence_folder_path):
    sequence_folder_path = _clean_game_path(sequence_folder_path)

    asset_paths = unreal.EditorAssetLibrary.list_assets(
        sequence_folder_path,
        recursive=False,
        include_folder=False,
    )

    master_paths = []

    for asset_path in asset_paths:
        asset_path = _clean_game_path(asset_path)

        if _is_master_shot_sequence_asset(asset_path, sequence_name):
            master_paths.append(asset_path)

    master_paths.sort(key=lambda path: _extract_asset_name(path))
    return master_paths


def _build_data_asset_object_path(sequence_folder_path, shot_name):
    data_asset_name = f"{shot_name}_Data"

    package_path = _join_game_path(
        sequence_folder_path,
        shot_name,
        data_asset_name,
    )

    if not package_path:
        return ""

    return f"{package_path}.{data_asset_name}"


def _find_fallback_data_asset(sequence_folder_path, shot_name):
    shot_folder_path = _join_game_path(sequence_folder_path, shot_name)

    if not _is_safe_unreal_path(shot_folder_path):
        _log_warning(f"Skipping unsafe shot folder path: {shot_folder_path}")
        return None, ""

    if not unreal.EditorAssetLibrary.does_directory_exist(shot_folder_path):
        _log_warning(f"Shot folder does not exist: {shot_folder_path}")
        return None, ""

    asset_paths = unreal.EditorAssetLibrary.list_assets(
        shot_folder_path,
        recursive=False,
        include_folder=False,
    )

    preferred_name = f"{shot_name}_Data"
    fallback_path = ""

    for asset_path in asset_paths:
        asset_path = _clean_game_path(asset_path)
        asset_name = _extract_asset_name(asset_path)

        if asset_name == preferred_name:
            fallback_path = asset_path
            break

        if asset_name.endswith("_Data") and not fallback_path:
            fallback_path = asset_path

    if not fallback_path:
        return None, ""

    if not _is_safe_unreal_path(fallback_path):
        _log_warning(f"Skipping unsafe fallback data asset path: {fallback_path}")
        return None, ""

    loaded = unreal.load_asset(fallback_path)
    if not loaded:
        _log_warning(f"Fallback data asset failed to load: {fallback_path}")
        return None, ""

    return loaded, fallback_path


def _load_shot_data_asset(sequence_folder_path, shot_name):
    expected_path = _build_data_asset_object_path(sequence_folder_path, shot_name)

    if not _is_safe_unreal_path(expected_path.split(".", 1)[0]):
        _log_warning(f"Skipping unsafe expected data asset path: {expected_path}")
        return None, ""

    _log(f"Checking data asset: {expected_path}")

    if unreal.EditorAssetLibrary.does_asset_exist(expected_path):
        loaded = unreal.load_asset(expected_path)
        if loaded:
            return loaded, expected_path

        _log_warning(f"Expected data asset exists but failed to load: {expected_path}")

    return _find_fallback_data_asset(sequence_folder_path, shot_name)


def _get_playback_range(level_sequence_asset):
    try:
        start_frame = int(level_sequence_asset.get_playback_start())
        end_frame = int(level_sequence_asset.get_playback_end())
        return start_frame, end_frame
    except Exception as exc:
        _log_error(f"Failed to read playback range: {exc}")
        return None, None


def _set_frame_property(data_asset, property_name, value):
    try:
        data_asset.get_editor_property(property_name)
    except Exception:
        _log_error(f"Data asset does not expose property: {property_name}")
        return False

    try:
        data_asset.set_editor_property(property_name, int(value))
        return True
    except Exception as exc:
        _log_error(f"Failed to set {property_name}={value}: {exc}")
        return False


def _cache_one_shot(sequence_folder_path, master_sequence_path):
    master_sequence_path = _clean_game_path(master_sequence_path)
    shot_name = _extract_asset_name(master_sequence_path)

    _log("--------------------------------------------------")
    _log(f"Processing shot: {shot_name}")
    _log(f"Master sequence: {master_sequence_path}")

    if not _is_safe_unreal_path(master_sequence_path):
        _log_warning(f"Skipping unsafe master sequence path: {master_sequence_path}")
        return False

    master_sequence = unreal.EditorAssetLibrary.load_asset(master_sequence_path)
    if not master_sequence or not isinstance(master_sequence, unreal.LevelSequence):
        _log_warning(f"Skipping invalid master sequence: {master_sequence_path}")
        return False

    start_frame, end_frame = _get_playback_range(master_sequence)
    if start_frame is None or end_frame is None:
        _log_warning(f"Skipping shot because frame range could not be read: {shot_name}")
        return False

    data_asset, data_asset_path = _load_shot_data_asset(sequence_folder_path, shot_name)
    if not data_asset:
        _log_warning(f"Missing shot data asset for shot: {shot_name}")
        return False

    start_ok = _set_frame_property(data_asset, "StartFrame", start_frame)
    end_ok = _set_frame_property(data_asset, "EndFrame", end_frame)

    if not start_ok or not end_ok:
        _log_error(f"Failed setting StartFrame/EndFrame on: {data_asset_path}")
        return False

    save_ok = unreal.EditorAssetLibrary.save_loaded_asset(data_asset)
    if not save_ok:
        _log_error(f"Failed to save data asset: {data_asset_path}")
        return False

    _log(
        f"Updated {shot_name}: "
        f"StartFrame={start_frame}, "
        f"EndFrame={end_frame}, "
        f"DataAsset={data_asset_path}"
    )
    return True


def run(show_name="", sequence_name=""):
    """
    One-time migration script.

    Caches master Level Sequence playback ranges onto matching BP_ShotDataAsset
    StartFrame / EndFrame integer properties.

    Args:
        show_name:
            Optional. If blank, auto-detects current show using _showholder.

        sequence_name:
            Optional. If supplied, only processes that sequence, for example "MNF".

    Returns:
        dict summary
    """
    _log("----- run() called -----")
    _log(f"Raw show_name: {show_name!r}")
    _log(f"Raw sequence_name: {sequence_name!r}")

    clean_show_name = _sanitize_show_name(show_name)
    clean_sequence_name = _sanitize_sequence_name(sequence_name)

    if not clean_show_name:
        clean_show_name = _find_current_show_name()

    if not clean_show_name:
        _log_error("Could not resolve show name. Aborting.")
        return {
            "success": False,
            "updated": 0,
            "failed": 0,
            "message": "Could not resolve show name.",
        }

    _log(f"Using show name: {clean_show_name}")

    if clean_sequence_name:
        _log(f"Sequence filter: {clean_sequence_name}")
    else:
        _log("No sequence filter. Scanning all valid sequence folders.")

    sequence_folders = _get_sequence_folders(clean_show_name, clean_sequence_name)

    updated_count = 0
    failed_count = 0
    scanned_master_count = 0

    for sequence_name_clean, sequence_folder_path in sequence_folders:
        sequence_folder_path = _clean_game_path(sequence_folder_path)

        _log("==================================================")
        _log(f"Scanning sequence: {sequence_name_clean}")
        _log(f"Sequence folder: {sequence_folder_path}")

        master_sequence_paths = _get_master_shot_sequence_paths(
            sequence_name_clean,
            sequence_folder_path,
        )

        _log(f"Found {len(master_sequence_paths)} master shot sequence(s).")

        for master_sequence_path in master_sequence_paths:
            scanned_master_count += 1

            if _cache_one_shot(sequence_folder_path, master_sequence_path):
                updated_count += 1
            else:
                failed_count += 1

    _log("==================================================")
    _log("Frame range cache migration complete.")
    _log(f"Sequences scanned: {len(sequence_folders)}")
    _log(f"Master shots scanned: {scanned_master_count}")
    _log(f"Data assets updated: {updated_count}")
    _log(f"Failed shots: {failed_count}")
    _log("==================================================")

    return {
        "success": failed_count == 0,
        "sequences_scanned": len(sequence_folders),
        "master_shots_scanned": scanned_master_count,
        "updated": updated_count,
        "failed": failed_count,
        "message": "Done",
    }


if __name__ == "__main__":
    run()