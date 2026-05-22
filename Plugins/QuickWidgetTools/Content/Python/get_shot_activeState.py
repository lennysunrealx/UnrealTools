import unreal


_LOG_PREFIX = "[GetShotActiveState]"


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
        _log_error(
            f"Invalid {label}: contains unsupported path characters: {cleaned!r}"
        )
        return None

    return cleaned


def run(show_name, sequence_name, shot_name):
    clean_show_name = _sanitize_name(show_name, "show_name")
    clean_sequence_name = _sanitize_name(sequence_name, "sequence_name")
    clean_shot_name = _sanitize_name(shot_name, "shot_name")

    if (
        clean_show_name is None
        or clean_sequence_name is None
        or clean_shot_name is None
    ):
        _log_error("Input validation failed.")
        return False

    normalized_show_name = (
        clean_show_name[1:] if clean_show_name.startswith("_") else clean_show_name
    )

    shot_folder_path = (
        f"/Game/_{normalized_show_name}/Sequences/"
        f"{clean_sequence_name}/{clean_shot_name}"
    )

    asset_name = f"{clean_shot_name}_Data"
    asset_object_path = f"{shot_folder_path}/{asset_name}.{asset_name}"

    shot_data_asset = unreal.load_asset(asset_object_path)

    if not shot_data_asset:
        _log_error(f"Asset not found or failed to load: {asset_object_path}")
        return False

    try:
        is_active = shot_data_asset.get_editor_property("IsActive")
    except Exception as exc:
        _log_error(f"Asset does not expose IsActive property: {exc}")
        return False

    if not isinstance(is_active, bool):
        _log_error(
            f"IsActive value is not bool. Type: {type(is_active).__name__}, Value: {is_active!r}"
        )
        return False

    return is_active