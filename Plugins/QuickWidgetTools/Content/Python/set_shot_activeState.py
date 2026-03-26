import unreal


_LOG_PREFIX = "[SetShotActiveState]"


def _log(message):
    unreal.log(f"{_LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{_LOG_PREFIX} {message}")


def _sanitize_name(value, label):
    if not isinstance(value, str):
        _log_error(f"Invalid {label}: expected string, got {type(value).__name__}")
        return None

    cleaned = value.strip()
    if not cleaned:
        _log_error(f"Invalid {label}: value is empty")
        return None

    if "/" in cleaned or "\\" in cleaned or "." in cleaned:
        _log_error(f"Invalid {label}: contains unsupported path characters")
        return None

    return cleaned


def run(show_name, sequence_name, shot_name, is_active):
    _log(
        "Requested inputs: "
        f"show_name={show_name!r}, sequence_name={sequence_name!r}, "
        f"shot_name={shot_name!r}, is_active={is_active!r}"
    )

    clean_show_name = _sanitize_name(show_name, "show_name")
    clean_sequence_name = _sanitize_name(sequence_name, "sequence_name")
    clean_shot_name = _sanitize_name(shot_name, "shot_name")

    if clean_show_name is None or clean_sequence_name is None or clean_shot_name is None:
        return False

    if not isinstance(is_active, bool):
        _log_error(f"Invalid is_active: expected bool, got {type(is_active).__name__}")
        return False

    normalized_show_name = clean_show_name[1:] if clean_show_name.startswith("_") else clean_show_name

    shot_folder_path = f"/Game/_{normalized_show_name}/Sequences/{clean_sequence_name}/{clean_shot_name}"
    asset_name = f"{clean_shot_name}_Data"
    asset_path = f"{shot_folder_path}/{asset_name}.{asset_name}"

    _log(f"Resolved shot folder path: {shot_folder_path}")
    _log(f"Resolved asset path: {asset_path}")

    shot_data_asset = unreal.load_asset(asset_path)
    if not shot_data_asset:
        _log_error(f"Asset not found or failed to load: {asset_path}")
        _log("Asset found: False")
        return False

    _log("Asset found: True")

    try:
        shot_data_asset.get_editor_property("IsActive")
    except Exception as exc:
        _log_error(f"Asset does not expose IsActive property: {exc}")
        return False

    try:
        shot_data_asset.set_editor_property("IsActive", is_active)
    except Exception as exc:
        _log_error(f"Failed to set IsActive: {exc}")
        return False

    save_ok = unreal.EditorAssetLibrary.save_loaded_asset(shot_data_asset)
    if not save_ok:
        _log_error(f"Failed to save asset: {asset_path}")
        return False

    _log(f"Final IsActive value written: {is_active}")
    return is_active


if __name__ == "__main__":
    _log("Module loaded. Call run(show_name, sequence_name, shot_name, is_active) from Unreal.")
