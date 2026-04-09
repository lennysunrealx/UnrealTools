import unreal

_LOG_PREFIX = "[OpenAssociatedLevel]"


def _log(message):
    unreal.log(f"{_LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{_LOG_PREFIX} {message}")


def _sanitize_level_package_path(level_package_path):
    if level_package_path is None:
        return ""

    sanitized = str(level_package_path).strip()
    if "." in sanitized:
        sanitized = sanitized.split(".", 1)[0].strip()

    return sanitized


def run(level_package_path):
    result = False

    try:
        _log(f"Raw input: {level_package_path}")

        sanitized_path = _sanitize_level_package_path(level_package_path)
        _log(f"Sanitized input: {sanitized_path}")

        if not sanitized_path:
            _log_error("load_map attempted: False (invalid sanitized path)")
            _log("load_map succeeded: False")
            _log("Final return value: False")
            return False

        _log("load_map attempted: True")
        result = bool(unreal.EditorLoadingAndSavingUtils.load_map(sanitized_path))
        _log(f"load_map succeeded: {result}")
    except Exception as exc:
        _log_error(f"Exception while opening map: {exc}")
        result = False

    _log(f"Final return value: {result}")
    return result
