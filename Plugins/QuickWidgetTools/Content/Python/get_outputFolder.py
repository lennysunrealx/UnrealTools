"""
Load a per-user render output folder for the current Unreal project.

Reads from:
    <Project>/Saved/Config/WindowsEditor/QuickWidgetToolsSettings.ini

Intended for use from an Execute Python Script node.

Blueprint usage:
    import get_outputFolder
    import importlib
    importlib.reload(get_outputFolder)
    output_path = get_outputFolder.run()

Returns:
    The saved output path as a string, or "" if not found.
"""

import os
import unreal


_LOG_PREFIX = "[GetOutputFolder]"
_SETTINGS_FILE_NAME = "QuickWidgetToolsSettings.ini"
_SECTION = "/Script/QuickWidgetTools.RenderToolSettings"
_KEY = "OutputPath"


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


def _collect_section_headers(lines, max_count=20):
    headers = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            headers.append(stripped)
            if len(headers) >= max_count:
                break
    return headers


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
        return "", -1, -1

    prefix = f"{key}="
    for i in range(section_start + 1, section_end):
        stripped = lines[i].strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip(), section_start, i

    return "", section_start, -1


def _find_key_anywhere(text, key):
    prefix = f"{key}="
    lines = text.splitlines()
    matches = []

    current_section = "<no section yet>"
    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped
            continue

        if stripped.startswith(prefix):
            matches.append((i + 1, current_section, stripped))

    return matches


def run():
    try:
        settings_path = _get_settings_file_path()
        if not os.path.exists(settings_path):
            _log_warning("Settings file does not exist yet.")
            return ""

        text = _read_text_file(settings_path)
        _log(f"Read {len(text)} characters from settings file.")

        lines = text.splitlines()
        _log(f"Settings file contains {len(lines)} lines.")

        value, section_line_index, key_line_index = _get_section_value(text, _SECTION, _KEY)

        if value:
            _log(f"Found target section at line {section_line_index + 1}")
            _log(f"Found key at line {key_line_index + 1}")
            _log(f"Loaded OutputPath='{value}'")
            return value

        _log_warning(f"Target section/key not found: [{_SECTION}] {_KEY}")

        headers = _collect_section_headers(lines, max_count=15)
        if headers:
            _log("Section headers in settings file:")
            for header in headers:
                _log(f"  {header}")

        global_matches = _find_key_anywhere(text, _KEY)
        if global_matches:
            _log_warning(f"Found {_KEY} elsewhere in settings file:")
            for line_no, section_name, line_text in global_matches[:10]:
                _log_warning(f"  line {line_no} section {section_name}: {line_text}")
        else:
            _log_warning(f"No '{_KEY}=' key found anywhere in the settings file.")

        return ""

    except Exception as exc:
        _log_error(str(exc))
        return ""