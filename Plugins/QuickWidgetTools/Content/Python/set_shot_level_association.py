import unreal


_LOG_PREFIX = "[SetShotLevelAssociation]"
_PROPERTY_NAMES = [
    "AssociatedLevel",
    "Level",
    "LevelAssociation",
    "AssociatedLevelStored",
]


def _log(message):
    unreal.log(f"{_LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{_LOG_PREFIX} {message}")


def _sanitize_show_name(show_name):
    cleaned = "".join(ch for ch in str(show_name or "").strip().strip("/") if ch.isalnum())
    if cleaned.startswith("_"):
        cleaned = cleaned[1:]
    return cleaned


def _sanitize_sequence_name(sequence_name):
    return "".join(
        ch for ch in str(sequence_name or "").strip().strip("/") if ch.isalnum() or ch == "_"
    )


def _sanitize_shot_name(shot_name):
    return "".join(
        ch for ch in str(shot_name or "").strip().strip("/") if ch.isalnum() or ch == "_"
    )


def _sanitize_level_path(level_path):
    raw = str(level_path or "").strip()
    if not raw:
        return ""

    value = raw.strip("\"'")
    for prefix in ("SoftObjectPath(", "TopLevelAssetPath("):
        if value.startswith(prefix) and value.endswith(")"):
            value = value[len(prefix) : -1].strip().strip("\"'")
            break

    if value.endswith(".umap"):
        value = value[:-5]

    if value.startswith("/Game") and "." not in value:
        asset_name = value.rsplit("/", 1)[-1]
        value = f"{value}.{asset_name}"

    return value


def _build_shot_folder_path(show_name, sequence_name, shot_name):
    return f"/Game/_{show_name}/Sequences/{sequence_name}/{shot_name}"


def _build_expected_data_asset_path(shot_folder_path, shot_name):
    asset_name = f"{shot_name}_Data"
    return f"{shot_folder_path}/{asset_name}.{asset_name}"


def _load_data_asset(data_asset_object_path):
    if not unreal.EditorAssetLibrary.does_asset_exist(data_asset_object_path):
        return None

    return unreal.load_asset(data_asset_object_path)


def _find_fallback_data_asset_in_folder(shot_folder_path, shot_name):
    if not unreal.EditorAssetLibrary.does_directory_exist(shot_folder_path):
        return None

    asset_paths = unreal.EditorAssetLibrary.list_assets(
        shot_folder_path,
        recursive=False,
        include_folder=False,
    )

    preferred_name = f"{shot_name}_Data"
    exact_match_path = ""
    fallback_candidate_path = ""

    for asset_path in asset_paths:
        leaf = asset_path.rsplit("/", 1)[-1]
        asset_name = leaf.split(".", 1)[0]

        if asset_name == preferred_name:
            exact_match_path = asset_path
            break

        if asset_name.endswith("_Data") and not fallback_candidate_path:
            fallback_candidate_path = asset_path

    selected_path = exact_match_path or fallback_candidate_path
    if not selected_path:
        return None

    return unreal.load_asset(selected_path)


def _get_level_property_name(shot_data_asset):
    for property_name in _PROPERTY_NAMES:
        try:
            shot_data_asset.get_editor_property(property_name)
            return property_name
        except Exception:
            continue

    return ""


def _get_current_level_value(shot_data_asset, property_name):
    try:
        return shot_data_asset.get_editor_property(property_name)
    except Exception:
        return None


def _convert_level_value_to_asset_path(level_value):
    if level_value is None:
        return ""

    if isinstance(level_value, str):
        return level_value.strip()

    for getter_name in ("get_asset_path_name", "get_path_name"):
        getter = getattr(level_value, getter_name, None)
        if callable(getter):
            try:
                raw_path = getter()
                if isinstance(raw_path, str) and raw_path.strip():
                    return raw_path.strip()
            except Exception:
                pass

    try:
        text_value = str(level_value).strip()
    except Exception:
        text_value = ""

    if not text_value or text_value in ("None", "null"):
        return ""

    return text_value


def _normalize_compare_path(path_value):
    cleaned = _sanitize_level_path(path_value)
    if not cleaned:
        return ""

    value = cleaned.strip()
    if value.endswith(".umap"):
        value = value[:-5]

    if value.startswith("/Game") and "." not in value:
        asset_name = value.rsplit("/", 1)[-1]
        value = f"{value}.{asset_name}"

    return value


def _set_level_property_value(shot_data_asset, property_name, normalized_level_path):
    if not normalized_level_path:
        for clear_value in (None, unreal.SoftObjectPath(""), ""):
            try:
                shot_data_asset.set_editor_property(property_name, clear_value)
                return True
            except Exception:
                continue
        return False

    loaded_level_asset = unreal.load_asset(normalized_level_path)
    if loaded_level_asset:
        try:
            shot_data_asset.set_editor_property(property_name, loaded_level_asset)
            return True
        except Exception:
            pass

    try:
        soft_path = unreal.SoftObjectPath(normalized_level_path)
        shot_data_asset.set_editor_property(property_name, soft_path)
        return True
    except Exception:
        pass

    try:
        shot_data_asset.set_editor_property(property_name, normalized_level_path)
        return True
    except Exception:
        return False


def run(show_name, sequence_name, shot_name, level_path):
    _log("----- run() called -----")
    _log(
        "Raw inputs: "
        f"show_name={show_name!r}, sequence_name={sequence_name!r}, "
        f"shot_name={shot_name!r}, level_path={level_path!r}"
    )

    try:
        clean_show_name = _sanitize_show_name(show_name)
        clean_sequence_name = _sanitize_sequence_name(sequence_name)
        clean_shot_name = _sanitize_shot_name(shot_name)
        clean_level_path = _sanitize_level_path(level_path)

        _log(
            "Sanitized inputs: "
            f"show_name={clean_show_name!r}, sequence_name={clean_sequence_name!r}, "
            f"shot_name={clean_shot_name!r}, level_path={clean_level_path!r}"
        )

        if not clean_show_name or not clean_sequence_name or not clean_shot_name:
            _log_error("Required sanitized identifiers are empty.")
            _log("Final return value: False")
            return False

        shot_folder_path = _build_shot_folder_path(
            clean_show_name,
            clean_sequence_name,
            clean_shot_name,
        )
        expected_data_asset_path = _build_expected_data_asset_path(
            shot_folder_path,
            clean_shot_name,
        )

        _log(f"Resolved data asset path: {expected_data_asset_path}")

        shot_data_asset = _load_data_asset(expected_data_asset_path)
        if not shot_data_asset:
            _log("Direct data asset load failed. Trying fallback search in shot folder.")
            shot_data_asset = _find_fallback_data_asset_in_folder(
                shot_folder_path,
                clean_shot_name,
            )

        if not shot_data_asset:
            _log_error("Failed to load shot data asset from expected path or fallback search.")
            _log("Final return value: False")
            return False

        property_name = _get_level_property_name(shot_data_asset)
        if not property_name:
            _log_error(f"No supported level association property found. Tried: {_PROPERTY_NAMES}")
            _log("Final return value: False")
            return False

        _log(f"Property name used: {property_name}")

        current_value = _get_current_level_value(shot_data_asset, property_name)
        current_raw_path = _convert_level_value_to_asset_path(current_value)

        current_normalized = _normalize_compare_path(current_raw_path)
        incoming_normalized = _normalize_compare_path(clean_level_path)

        _log(f"Current normalized level path: {current_normalized!r}")
        _log(f"Incoming normalized level path: {incoming_normalized!r}")

        if current_normalized == incoming_normalized:
            _log("Path compare result: matched")
            _log("Update skipped: existing value already matches incoming level path.")
            _log("Final return value: True")
            return True

        _log("Path compare result: differed")

        if not _set_level_property_value(shot_data_asset, property_name, incoming_normalized):
            _log_error("Failed to set level association property value.")
            _log("Final return value: False")
            return False

        _log("Update applied: level association property updated.")

        save_result = unreal.EditorAssetLibrary.save_loaded_asset(shot_data_asset)
        _log(f"Save result: {save_result}")

        if not save_result:
            _log_error("Failed to save shot data asset after update.")
            _log("Final return value: False")
            return False

        _log("Final return value: True")
        return True

    except Exception as exc:
        _log_error(f"Unexpected failure: {exc}")
        _log("Final return value: False")
        return False
