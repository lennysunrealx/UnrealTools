"""Read a per-user shot manager scroll offset for the current Unreal project.

Reads from:
    /Saved/Config/WindowsEditor/QuickWidgetToolsSettings.ini

Intended for use from an Execute Python Script node.

Blueprint usage:
    import get_savedScrollOffset
    import importlib
    importlib.reload(get_savedScrollOffset)
    saved_scroll_offset = get_savedScrollOffset.run()

Returns:
    saved_scroll_offset : float
"""

import os
import unreal

_LOG_PREFIX = "[GetSavedScrollOffset]"
_SETTINGS_FILE_NAME = "QuickWidgetToolsSettings.ini"
_SECTION = "/Script/QuickWidgetTools.ShotManagerSettings"
_KEY = "SavedScrollOffset"


def _log(message):
    unreal.log(f"{_LOG_PREFIX} {message}")


def _log_warning(message):
    unreal.log_warning(f"{_LOG_PREFIX} Warning: {message}")


def _log_error(message):
    unreal.log_error(f"{_LOG_PREFIX} Error: {message}")


def _find_config_dir(project_dir):
    candidates = [
        os.path.join(project_dir, "Saved", "Config", "WindowsEditor"),
        os.path.join(project_dir, "Saved", "Config", "Windows"),
        os.path.join(project_dir, "Saved", "Config"),
    ]

    for folder in candidates:
        _log(f"Checking config folder candidate: {folder}")
        if os.path.isdir(folder):
            _log(f"Using existing config folder: {folder}")
            return folder

    fallback = os.path.join(project_dir, "Saved", "Config", "WindowsEditor")
    _log_warning(f"No candidate config folder existed. Falling back to: {fallback}")
    return fallback


def _get_settings_file_path():
    project_dir = unreal.Paths.project_dir()
    _log(f"Project dir: {project_dir}")

    config_dir = _find_config_dir(project_dir)
    settings_path = os.path.join(config_dir, _SETTINGS_FILE_NAME)
    settings_path = os.path.normpath(settings_path)

    _log(f"Resolved settings file path: {settings_path}")
    return settings_path


def _read_text_file(path):
    if not os.path.exists(path):
        return ""

    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _find_section_bounds(lines, section_name):
    section_header = f"[{section_name}]"
    section_start = -1
    section_end = len(lines)

    for i, line in enumerate(lines):
        if line.strip() == section_header:
            section_start = i
            break

    if section_start == -1:
        return -1, -1

    for i in range(section_start + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section_end = i
            break

    return section_start, section_end


def _get_section_value(text, section_name, key):
    lines = text.splitlines()
    section_start, section_end = _find_section_bounds(lines, section_name)

    if section_start == -1:
        return ""

    prefix = f"{key}="
    for i in range(section_start + 1, section_end):
        stripped = lines[i].strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()

    return ""


def run():
    try:
        settings_path = _get_settings_file_path()
        if not os.path.exists(settings_path):
            _log_warning("Settings file does not exist yet. Returning default value 0.0")
            return 0.0

        text = _read_text_file(settings_path)
        _log(f"Read {len(text)} characters from settings file.")

        value = _get_section_value(text, _SECTION, _KEY)
        if value == "":
            _log_warning("No saved scroll offset found. Returning default value 0.0")
            return 0.0

        try:
            saved_scroll_offset = float(value)
        except Exception:
            _log_error(f"Saved value was not a valid float: '{value}'")
            return 0.0

        if saved_scroll_offset < 0.0:
            saved_scroll_offset = 0.0

        _log(f"Returning saved scroll offset: {saved_scroll_offset}")
        return saved_scroll_offset

    except Exception as exc:
        _log_error(str(exc))
        return 0.0