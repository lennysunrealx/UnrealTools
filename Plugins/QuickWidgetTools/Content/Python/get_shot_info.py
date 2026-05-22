import re
import unreal


LOG_PREFIX = "[GetShotInfo]"

SHOT_NAME_PATTERN = re.compile(r"^([A-Za-z0-9]+)_(\d{3})_(\d{4,})$")

IS_ACTIVE_PROPERTY_NAME = "IsActive"
LEVEL_PATH_PROPERTY_NAME = "AssociatedLevelPathString"
START_FRAME_PROPERTY_NAME = "StartFrame"
END_FRAME_PROPERTY_NAME = "EndFrame"


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
        text = _clean_game_path(part).strip("/")
        if not text:
            continue
        cleaned_parts.append(text)

    if not cleaned_parts:
        return ""

    if str(parts[0] or "").strip().startswith("/"):
        return "/" + "/".join(cleaned_parts)

    if cleaned_parts[0] == "Game" or cleaned_parts[0].startswith("Game"):
        return "/" + "/".join(cleaned_parts)

    return "/".join(cleaned_parts)


def _extract_asset_name(asset_path):
    leaf = str(asset_path).rstrip("/").rsplit("/", 1)[-1]
    return leaf.split(".", 1)[0]


def _sanitize_show_name(show_name):
    cleaned = "".join(ch for ch in str(show_name or "").strip().strip("/") if ch.isalnum())
    if cleaned.startswith("_"):
        cleaned = cleaned[1:]
    return cleaned


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


def _get_sequence_folders(show_name):
    sequences_root = _join_game_path("/Game", f"_{show_name}", "Sequences")

    if not unreal.EditorAssetLibrary.does_directory_exist(sequences_root):
        _log_error(f"Sequences folder does not exist: {sequences_root}")
        return []

    children = unreal.EditorAssetLibrary.list_assets(
        sequences_root,
        recursive=False,
        include_folder=True,
    )

    sequence_folders = []

    for child_path in children:
        child_path = _clean_game_path(child_path)

        if not unreal.EditorAssetLibrary.does_directory_exist(child_path):
            continue

        sequence_name = child_path.rsplit("/", 1)[-1]
        sequenceholder_asset_path = _join_game_path(child_path, "_sequenceholder")

        if not unreal.EditorAssetLibrary.does_asset_exist(sequenceholder_asset_path):
            _log(f"Skipping folder missing _sequenceholder: {child_path}")
            continue

        sequence_folders.append((sequence_name.upper(), child_path))

    sequence_folders.sort(key=lambda row: row[0])
    return sequence_folders


def _get_shot_folders_in_sequence(sequence_name, sequence_folder_path):
    children = unreal.EditorAssetLibrary.list_assets(
        sequence_folder_path,
        recursive=False,
        include_folder=True,
    )

    shot_folders = []

    for child_path in children:
        child_path = _clean_game_path(child_path)

        if not unreal.EditorAssetLibrary.does_directory_exist(child_path):
            continue

        shot_name = child_path.rsplit("/", 1)[-1]

        match = SHOT_NAME_PATTERN.fullmatch(shot_name)
        if not match:
            continue

        if match.group(1).upper() != sequence_name.upper():
            continue

        shot_folders.append((int(match.group(3)), shot_name, child_path))

    shot_folders.sort(key=lambda row: row[0])
    return shot_folders


def _build_expected_data_asset_path(shot_folder_path, shot_name):
    data_asset_name = f"{shot_name}_Data"
    package_path = _join_game_path(shot_folder_path, data_asset_name)
    return f"{package_path}.{data_asset_name}"


def _find_fallback_data_asset_in_shot_folder(shot_folder_path, shot_name):
    if not unreal.EditorAssetLibrary.does_directory_exist(shot_folder_path):
        return None, ""

    asset_paths = unreal.EditorAssetLibrary.list_assets(
        shot_folder_path,
        recursive=False,
        include_folder=False,
    )

    preferred_name = f"{shot_name}_Data"
    fallback_candidate_path = ""

    for asset_path in asset_paths:
        asset_name = _extract_asset_name(asset_path)

        if asset_name == preferred_name:
            fallback_candidate_path = asset_path
            break

        if asset_name.endswith("_Data") and not fallback_candidate_path:
            fallback_candidate_path = asset_path

    if not fallback_candidate_path:
        return None, ""

    loaded = unreal.load_asset(fallback_candidate_path)
    if not loaded:
        _log_warning(f"Fallback shot data asset failed to load: {fallback_candidate_path}")
        return None, ""

    return loaded, fallback_candidate_path


def _load_shot_data_asset(shot_folder_path, shot_name):
    expected_data_asset_path = _build_expected_data_asset_path(shot_folder_path, shot_name)

    if unreal.EditorAssetLibrary.does_asset_exist(expected_data_asset_path):
        loaded = unreal.load_asset(expected_data_asset_path)
        if loaded:
            return loaded, expected_data_asset_path

        _log_warning(f"Expected shot data asset exists but failed to load: {expected_data_asset_path}")

    return _find_fallback_data_asset_in_shot_folder(shot_folder_path, shot_name)


def _read_bool_property(asset, property_name, shot_name):
    try:
        value = asset.get_editor_property(property_name)
    except Exception as exc:
        _log_warning(f"Shot data asset for '{shot_name}' does not expose {property_name}: {exc}")
        return False

    return bool(value)


def _read_int_property(asset, property_name, shot_name):
    try:
        value = asset.get_editor_property(property_name)
    except Exception as exc:
        _log_warning(f"Shot data asset for '{shot_name}' does not expose {property_name}: {exc}")
        return ""

    if isinstance(value, bool):
        _log_warning(f"Shot data asset property {property_name} for '{shot_name}' is bool, expected int.")
        return ""

    try:
        return int(value)
    except Exception as exc:
        _log_warning(
            f"Shot data asset property {property_name} for '{shot_name}' could not convert to int. "
            f"Value={value!r}, Error={exc}"
        )
        return ""


def _read_string_property(asset, property_name, shot_name):
    try:
        value = asset.get_editor_property(property_name)
    except Exception as exc:
        _log_warning(f"Shot data asset for '{shot_name}' does not expose {property_name}: {exc}")
        return ""

    text = str(value or "").strip().strip("\"'")
    if not text or text in ("None", "null"):
        return ""

    if text.startswith("SoftObjectPath(") and text.endswith(")"):
        text = text[len("SoftObjectPath("):-1].strip().strip("\"'")

    text = text.replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")

    if text.endswith(".umap"):
        text = text[:-5]

    if text.startswith("/Game/") and "." not in text:
        asset_name = text.rstrip("/").rsplit("/", 1)[-1]
        text = f"{text}.{asset_name}"

    return text


def _collect_active_shot_infos(show_name):
    active_rows = []

    sequence_folders = _get_sequence_folders(show_name)
    _log(f"Found {len(sequence_folders)} valid sequence folder(s).")

    for sequence_name, sequence_folder_path in sequence_folders:
        _log(f"Scanning sequence folder: {sequence_folder_path}")

        shot_folders = _get_shot_folders_in_sequence(sequence_name, sequence_folder_path)
        _log(f"Found {len(shot_folders)} shot folder candidate(s) in {sequence_name}.")

        for shot_number, shot_name, shot_folder_path in shot_folders:
            shot_data_asset, data_asset_path = _load_shot_data_asset(shot_folder_path, shot_name)

            if not shot_data_asset:
                _log_warning(f"Missing shot data asset for shot: {shot_name}")
                continue

            is_active = _read_bool_property(
                shot_data_asset,
                IS_ACTIVE_PROPERTY_NAME,
                shot_name,
            )

            if not is_active:
                continue

            associated_level_path = _read_string_property(
                shot_data_asset,
                LEVEL_PATH_PROPERTY_NAME,
                shot_name,
            )

            start_frame = _read_int_property(
                shot_data_asset,
                START_FRAME_PROPERTY_NAME,
                shot_name,
            )

            end_frame = _read_int_property(
                shot_data_asset,
                END_FRAME_PROPERTY_NAME,
                shot_name,
            )

            active_rows.append(
                {
                    "sequence_name": sequence_name,
                    "shot_number": shot_number,
                    "shot_name": shot_name,
                    "associated_level_path": associated_level_path,
                    "start_frame": start_frame,
                    "end_frame": end_frame,
                    "data_asset_path": data_asset_path,
                }
            )

    active_rows.sort(key=lambda row: (row["sequence_name"], row["shot_number"], row["shot_name"]))
    return active_rows


def _print_active_shot_report(active_rows):
    _log("---- Active Shot Info")
    _log("--------------------------------------------------")
    _log("Shot Name - AssociatedLevelPathString - StartFrame - EndFrame")
    _log("--------------------------------------------------")

    for row in active_rows:
        _log(
            f"{row['shot_name']} - "
            f"{row['associated_level_path']} - "
            f"{row['start_frame']} - "
            f"{row['end_frame']}"
        )

    _log("--------------------------------------------------")
    _log(f"Active shot count: {len(active_rows)}")


def run(show_name=""):
    """
    Print all active shots from BP_ShotDataAsset data.

    Scans:
        /Game/_[Show]/Sequences/[SEQ]/[SHOT]/[SHOT]_Data

    Prints:
        Shot Name - AssociatedLevelPathString - StartFrame - EndFrame

    Args:
        show_name:
            Optional. If blank, auto-detects current show using _showholder.

    Returns:
        list[dict]
    """
    _log("----- run() called -----")
    _log(f"Raw show_name: {show_name!r}")

    clean_show_name = _sanitize_show_name(show_name)
    if not clean_show_name:
        clean_show_name = _find_current_show_name()

    if not clean_show_name:
        _log_error("Could not resolve show name. Returning empty list.")
        return []

    _log(f"Using show name: {clean_show_name}")

    active_rows = _collect_active_shot_infos(clean_show_name)
    _print_active_shot_report(active_rows)

    return active_rows


if __name__ == "__main__":
    run()
