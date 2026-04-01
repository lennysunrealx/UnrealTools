import unreal


_LOG_PREFIX = "[ConvertLevelShotData]"


def _log(message):
    unreal.log(f"{_LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{_LOG_PREFIX} {message}")


def _sanitize_show_name(show_name):
    if not isinstance(show_name, str):
        _log_error(
            f"Invalid show_name: expected string, got {type(show_name).__name__}"
        )
        return ""

    cleaned = show_name.strip().strip("/")
    if cleaned.startswith("_"):
        cleaned = cleaned[1:]

    if not cleaned:
        _log_error("Invalid show_name: value is empty after sanitization")
        return ""

    return cleaned


def _sanitize_sequence_name(sequence_name):
    if not isinstance(sequence_name, str):
        _log_error(
            f"Invalid sequence_name: expected string, got {type(sequence_name).__name__}"
        )
        return ""

    cleaned = sequence_name.strip().strip("/")
    if not cleaned:
        _log_error("Invalid sequence_name: value is empty after sanitization")
        return ""

    return cleaned


def _sanitize_shot_name(shot_name):
    if not isinstance(shot_name, str):
        _log_error(
            f"Invalid shot_name: expected string, got {type(shot_name).__name__}"
        )
        return ""

    cleaned = shot_name.strip().strip("/")
    if not cleaned:
        _log_error("Invalid shot_name: value is empty after sanitization")
        return ""

    return cleaned


def _sanitize_level_path(level_path):
    if level_path is None:
        return ""

    if not isinstance(level_path, str):
        _log_error(
            f"Invalid level_path: expected string, got {type(level_path).__name__}"
        )
        return ""

    return level_path.strip()


def _build_master_sequence_asset_path(show_name, sequence_name, shot_name):
    return f"/Game/_{show_name}/Sequences/{sequence_name}/{shot_name}.{shot_name}"


def _load_sequence_asset(show_name, sequence_name, shot_name):
    sequence_asset_path = _build_master_sequence_asset_path(
        show_name,
        sequence_name,
        shot_name,
    )
    _log(f"Rebuilt master sequence asset path: {sequence_asset_path}")

    if not unreal.EditorAssetLibrary.does_asset_exist(sequence_asset_path):
        _log_error(f"Master sequence asset does not exist: {sequence_asset_path}")
        return None

    sequence_asset = unreal.load_asset(sequence_asset_path)
    if not sequence_asset:
        _log_error(f"Failed to load master sequence asset: {sequence_asset_path}")
        return None

    asset_class = sequence_asset.get_class().get_name()
    if not isinstance(sequence_asset, unreal.LevelSequence):
        _log_error(
            "Loaded sequence asset is not a LevelSequence. "
            f"Class: {asset_class}, Path: {sequence_asset_path}"
        )
        return None

    _log(
        "Loaded master sequence asset successfully. "
        f"Class: {asset_class}, Path: {sequence_asset_path}"
    )
    return sequence_asset


def _load_level_asset(level_path):
    _log(f"Incoming level_path: {level_path!r}")

    if not level_path:
        _log("Level path is blank. Returning None for level asset.")
        return None

    if not unreal.EditorAssetLibrary.does_asset_exist(level_path):
        _log_error(f"Level asset does not exist: {level_path}")
        return None

    level_asset = unreal.load_asset(level_path)
    if not level_asset:
        _log_error(f"Failed to load level asset: {level_path}")
        return None

    asset_class = level_asset.get_class().get_name()
    if not isinstance(level_asset, unreal.World):
        _log(
            "Loaded level asset but class is not World. "
            f"Class: {asset_class}, Path: {level_path}"
        )
    else:
        _log(f"Loaded level asset successfully. Class: {asset_class}, Path: {level_path}")

    return level_asset


def run(show_name, sequence_name, shot_name, level_path):
    sequence_asset = None
    level_asset = None

    _log("----- run() called -----")
    _log(f"Raw input show_name: {show_name!r}")
    _log(f"Raw input sequence_name: {sequence_name!r}")
    _log(f"Raw input shot_name: {shot_name!r}")
    _log(f"Raw input level_path: {level_path!r}")

    try:
        clean_show_name = _sanitize_show_name(show_name)
        clean_sequence_name = _sanitize_sequence_name(sequence_name)
        clean_shot_name = _sanitize_shot_name(shot_name)
        clean_level_path = _sanitize_level_path(level_path)

        _log(f"Sanitized show_name: {clean_show_name!r}")
        _log(f"Sanitized sequence_name: {clean_sequence_name!r}")
        _log(f"Sanitized shot_name: {clean_shot_name!r}")
        _log(f"Sanitized level_path: {clean_level_path!r}")

        if clean_show_name and clean_sequence_name and clean_shot_name:
            sequence_asset = _load_sequence_asset(
                clean_show_name,
                clean_sequence_name,
                clean_shot_name,
            )
        else:
            _log_error(
                "Sequence load skipped due to invalid sanitized show/sequence/shot input."
            )

        level_asset = _load_level_asset(clean_level_path)

    except Exception as exc:
        _log_error(f"Unhandled error in run(): {exc}")

    _log(
        "Final return summary: "
        f"sequence_asset={'loaded' if sequence_asset else 'None'}, "
        f"level_asset={'loaded' if level_asset else 'None'}"
    )
    return sequence_asset, level_asset
