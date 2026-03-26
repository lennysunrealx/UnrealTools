import unreal


_LOG_PREFIX = "[GetShotActiveState]"


def _log(message):
    unreal.log(f"{_LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{_LOG_PREFIX} {message}")


def _log_return(value):
    _log(f"Returning value: {value!r}")
    return value


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
    _log("----- run() called -----")
    _log(f"Input show_name: {show_name!r}")
    _log(f"Input sequence_name: {sequence_name!r}")
    _log(f"Input shot_name: {shot_name!r}")

    clean_show_name = _sanitize_name(show_name, "show_name")
    clean_sequence_name = _sanitize_name(sequence_name, "sequence_name")
    clean_shot_name = _sanitize_name(shot_name, "shot_name")

    _log(f"Sanitized show_name: {clean_show_name!r}")
    _log(f"Sanitized sequence_name: {clean_sequence_name!r}")
    _log(f"Sanitized shot_name: {clean_shot_name!r}")

    if (
        clean_show_name is None
        or clean_sequence_name is None
        or clean_shot_name is None
    ):
        _log_error("Input validation failed.")
        return _log_return(False)

    normalized_show_name = (
        clean_show_name[1:] if clean_show_name.startswith("_") else clean_show_name
    )
    _log(f"Normalized show_name for path building: {normalized_show_name!r}")

    shot_folder_path = (
        f"/Game/_{normalized_show_name}/Sequences/"
        f"{clean_sequence_name}/{clean_shot_name}"
    )

    asset_name = f"{clean_shot_name}_Data"
    asset_object_path = f"{shot_folder_path}/{asset_name}.{asset_name}"

    _log(f"Resolved shot folder path: {shot_folder_path}")
    _log(f"Resolved data asset object path: {asset_object_path}")

    shot_data_asset = unreal.load_asset(asset_object_path)

    if not shot_data_asset:
        _log_error(f"Asset found: False")
        _log_error(f"Asset not found or failed to load: {asset_object_path}")
        return _log_return(False)

    _log("Asset found: True")
    _log(f"Loaded asset object: {shot_data_asset}")

    try:
        is_active = shot_data_asset.get_editor_property("IsActive")
    except Exception as exc:
        _log_error(f"Asset does not expose IsActive property: {exc}")
        return _log_return(False)

    if not isinstance(is_active, bool):
        _log_error(
            f"IsActive value is not bool. Type: {type(is_active).__name__}, Value: {is_active!r}"
        )
        return _log_return(False)

    _log(f"Read IsActive value: {is_active!r}")
    return _log_return(is_active)


if __name__ == "__main__":
    _log("Module loaded. Call run(show_name, sequence_name, shot_name).")
