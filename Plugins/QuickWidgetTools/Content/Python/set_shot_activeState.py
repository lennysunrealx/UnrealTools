import unreal

_LOG_PREFIX = "[SetShotActiveState]"


def _log(message):
    unreal.log(f"{_LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{_LOG_PREFIX} {message}")


def _log_return(value):
    _log(f"Returning value: {value!r}")
    return value


def _sanitize_name(value, label):
    if not isinstance(value, str):
        _log_error(
            f"Invalid {label}: expected string, got {type(value).__name__}"
        )
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


def run(show_name, sequence_name, shot_name, is_active):
    _log("----- run() called -----")
    _log(f"Input show_name: {show_name!r}")
    _log(f"Input sequence_name: {sequence_name!r}")
    _log(f"Input shot_name: {shot_name!r}")
    _log(f"Input is_active: {is_active!r}")

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

    if not isinstance(is_active, bool):
        _log_error(
            f"Invalid is_active: expected bool, got {type(is_active).__name__}"
        )
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
    asset_path = f"{shot_folder_path}/{asset_name}.{asset_name}"

    _log(f"Resolved shot folder path: {shot_folder_path}")
    _log(f"Resolved data asset object path: {asset_path}")

    shot_data_asset = unreal.load_asset(asset_path)

    if not shot_data_asset:
        _log_error(f"Asset not found or failed to load: {asset_path}")
        return _log_return(False)

    _log(f"Loaded asset object: {shot_data_asset}")

    try:
        loaded_asset_path = shot_data_asset.get_path_name()
    except Exception as exc:
        loaded_asset_path = None
        _log_error(f"Could not query loaded asset path: {exc}")

    _log(f"Loaded data asset file location: {loaded_asset_path!r}")

    try:
        current_is_active = shot_data_asset.get_editor_property("IsActive")
        _log(f"Current asset IsActive before set: {current_is_active!r}")
    except Exception as exc:
        _log_error(f"Asset does not expose IsActive property: {exc}")
        return _log_return(False)

    try:
        shot_data_asset.set_editor_property("IsActive", is_active)
        _log(f"Set IsActive to: {is_active!r}")
    except Exception as exc:
        _log_error(f"Failed to set IsActive: {exc}")
        return _log_return(False)

    try:
        updated_is_active = shot_data_asset.get_editor_property("IsActive")
        _log(f"Asset IsActive after set, before save: {updated_is_active!r}")
    except Exception as exc:
        _log_error(f"Failed reading IsActive after set: {exc}")
        return _log_return(False)

    save_ok = unreal.EditorAssetLibrary.save_loaded_asset(shot_data_asset)
    _log(f"Save result: {save_ok!r}")

    if not save_ok:
        _log_error(f"Failed to save asset: {asset_path}")
        return _log_return(False)

    try:
        final_is_active = shot_data_asset.get_editor_property("IsActive")
        _log(f"Final asset IsActive after save: {final_is_active!r}")
    except Exception as exc:
        _log_error(f"Failed reading final IsActive after save: {exc}")
        return _log_return(False)

    return _log_return(final_is_active)


if __name__ == "__main__":
    _log("Module loaded. Call run(show_name, sequence_name, shot_name, is_active).")