"""Persist a per-user shot manager scroll offset for the current Unreal project.

Writes to:
    /Saved/Config/WindowsEditor/QuickWidgetToolsSettings.ini

Intended for use from an Execute Python Script node.

Blueprint usage:
    import set_savedScrollOffset
    import importlib
    importlib.reload(set_savedScrollOffset)
    set_savedScrollOffset.run(saved_scroll_offset)

Input:
    saved_scroll_offset : float

Returns:
    nothing
"""

import os
import unreal

_LOG_PREFIX = "[SetSavedScrollOffset]"
_SETTINGS_FILE_NAME = "QuickWidgetToolsSettings.ini"
_SECTION = "/Script/QuickWidgetTools.ShotManagerSettings"
_KEY = "SavedScrollOffset"


def _log(message):
    unreal.log(f"{_LOG_PREFIX} {message}")


def _log_warning(message):
    unreal.log_warning(f"{_LOG_PREFIX} Warning: {message}")


def _log_error(message):
    unreal.log_error(f"{_LOG_PREFIX} Error: {message}")


def _normalize_value(saved_scroll_offset):
    try:
        value = float(saved_scroll_offset)
    except Exception:
        return None

    if value < 0.0:
        value = 0.0

    return str(value)


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


def _write_text_file(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


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


def _upsert_section_key(existing_text, section_name, key, value):
    lines = existing_text.splitlines()
    section_header = f"[{section_name}]"
    new_key_line = f"{key}={value}"

    section_start, section_end = _find_section_bounds(lines, section_name)

    if section_start == -1:
        _log(f"Section not found. Appending new section: {section_header}")

        if existing_text and not existing_text.endswith("\n"):
            existing_text += "\n"
        if existing_text and not existing_text.endswith("\n\n"):
            existing_text += "\n"

        existing_text += f"{section_header}\n{new_key_line}\n"
        return existing_text

    _log(f"Found section at lines {section_start + 1}-{section_end}")

    prefix = f"{key}="
    for i in range(section_start + 1, section_end):
        stripped = lines[i].strip()
        if stripped.startswith(prefix):
            _log(f"Existing key found on line {i + 1}. Replacing value.")
            lines[i] = new_key_line
            return "\n".join(lines) + "\n"

    _log(f"Key not found inside existing section. Inserting before line {section_end + 1}.")
    lines.insert(section_end, new_key_line)
    return "\n".join(lines) + "\n"


def run(saved_scroll_offset):
    try:
        _log(f"Raw saved_scroll_offset input: {saved_scroll_offset}")

        normalized_value = _normalize_value(saved_scroll_offset)
        if normalized_value is None:
            _log_error("saved_scroll_offset was invalid.")
            return

        _log(f"Normalized saved_scroll_offset: {normalized_value}")

        settings_path = _get_settings_file_path()
        settings_dir = os.path.dirname(settings_path)

        _log(f"Ensuring settings directory exists: {settings_dir}")
        os.makedirs(settings_dir, exist_ok=True)

        before_text = _read_text_file(settings_path)
        _log(f"Read {len(before_text)} characters from settings file before write.")

        previous_value = _get_section_value(before_text, _SECTION, _KEY)
        if previous_value != "":
            _log(f"Previous saved value was: {previous_value}")
        else:
            _log("No previous saved value found in target section.")

        updated_text = _upsert_section_key(before_text, _SECTION, _KEY, normalized_value)
        _write_text_file(settings_path, updated_text)

        after_text = _read_text_file(settings_path)
        verified_value = _get_section_value(after_text, _SECTION, _KEY)

        if verified_value != normalized_value:
            _log_error(
                f"Post-write verification failed. Expected '{normalized_value}' but found '{verified_value}'"
            )
            return

        _log(f"Post-write verification succeeded. {_KEY}='{verified_value}'")
        _log(f"Wrote settings file: {settings_path}")

    except Exception as exc:
        _log_error(str(exc))