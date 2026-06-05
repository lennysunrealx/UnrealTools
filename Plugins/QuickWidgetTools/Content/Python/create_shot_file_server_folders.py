"""
Create file-server folders for a shot using the saved show file server path.

Reads the show root from:
    <Project>/Saved/Config/WindowsEditor/QuickWidgetToolsSettings.ini

Target key:
    [/Script/QuickWidgetTools.RenderToolSettings]
    ShowFileServerPath=F:/Defect Dropbox/defect/s3bishop

Creates the per-shot folder structure that matches the example shot folders
from PortablePipeTools show_manager_core.py.

Blueprint usage:
    import create_shot_file_server_folders
    import importlib
    importlib.reload(create_shot_file_server_folders)
    success = create_shot_file_server_folders.run(show_name, sequence_name, shot_name)

Example:
    show root: F:/Defect Dropbox/defect/s3bishop
    sequence_name: ABC
    shot_name: ABC_000_0050

Creates:
    F:/Defect Dropbox/defect/s3bishop/sequences/ABC/ABC_000_0050/...

Returns:
    "true" on success
    "" on failure
"""

import json
import os
import re
import unreal


_LOG_PREFIX = "[CreateShotFileServerFolders]"
_SETTINGS_FILE_NAME = "QuickWidgetToolsSettings.ini"
_SECTION = "/Script/QuickWidgetTools.RenderToolSettings"
_SHOW_FILE_SERVER_PATH_KEY = "ShowFileServerPath"
_SHOW_MANIFEST_FILE_NAME = "_show_manifest.json"

SHOT_RELATIVE_FOLDER_TEMPLATES = (
    "sequences/{sequence_name}",
    "sequences/{sequence_name}/_output",

    "sequences/{sequence_name}/{shot_name}",
    "sequences/{sequence_name}/{shot_name}/anim/_output",
    "sequences/{sequence_name}/{shot_name}/anim/maya",

    "sequences/{sequence_name}/{shot_name}/fx/_output",
    "sequences/{sequence_name}/{shot_name}/fx/houdini",

    "sequences/{sequence_name}/{shot_name}/lite/_output",
    "sequences/{sequence_name}/{shot_name}/lite/unreal/_output/{shot_name}_beauty_v001",
    "sequences/{sequence_name}/{shot_name}/lite/unreal/_output/_hero",

    "sequences/{sequence_name}/{shot_name}/lvl/_output",
    "sequences/{sequence_name}/{shot_name}/lvl/unreal",
    "sequences/{sequence_name}/{shot_name}/lvl/maya",
    "sequences/{sequence_name}/{shot_name}/lvl/blender",

    "sequences/{sequence_name}/{shot_name}/comp/_output",
    "sequences/{sequence_name}/{shot_name}/comp/nuke",
    "sequences/{sequence_name}/{shot_name}/comp/natron",
    "sequences/{sequence_name}/{shot_name}/comp/davinci",

    "sequences/{sequence_name}/{shot_name}/mesh/_output",
    "sequences/{sequence_name}/{shot_name}/mesh/maya",
    "sequences/{sequence_name}/{shot_name}/mesh/blender",
    "sequences/{sequence_name}/{shot_name}/mesh/zbrush",

    "sequences/{sequence_name}/{shot_name}/_output",
    "sequences/{sequence_name}/{shot_name}/reference",
)


def _log(message):
    unreal.log(f"{_LOG_PREFIX} {message}")


def _log_warning(message):
    unreal.log_warning(f"{_LOG_PREFIX} Warning: {message}")


def _log_error(message):
    unreal.log_error(f"{_LOG_PREFIX} Error: {message}")


def _normalize_file_path(path_value):
    value = str(path_value or "").strip()
    if not value:
        return ""
    return value.replace("\\", "/").rstrip("/")


def _sanitize_show_name(value):
    if value is None:
        return ""
    return str(value).strip()


def _sanitize_sequence_name(value):
    if value is None:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", str(value))
    return cleaned.upper()


def _sanitize_shot_name(value):
    if value is None:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", str(value))
    return cleaned.upper()


def _derive_sequence_name(shot_name):
    sequence_name = shot_name.split("_", 1)[0].strip()
    return sequence_name.upper()


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


def _get_saved_show_file_server_path():
    settings_path = _get_settings_file_path()
    if not os.path.exists(settings_path):
        _log_error(f"Settings file does not exist yet: {settings_path}")
        return ""

    text = _read_text_file(settings_path)
    saved_path = _get_section_value(text, _SECTION, _SHOW_FILE_SERVER_PATH_KEY)
    saved_path = _normalize_file_path(saved_path)

    if not saved_path:
        _log_error(
            f"Could not find [{_SECTION}] {_SHOW_FILE_SERVER_PATH_KEY} in settings file: {settings_path}"
        )
        return ""

    _log(f"Loaded {_SHOW_FILE_SERVER_PATH_KEY}: {saved_path}")
    return saved_path


def _get_manifest_path(show_root):
    return os.path.join(show_root, _SHOW_MANIFEST_FILE_NAME)


def _log_manifest_status(show_root, show_name):
    manifest_path = os.path.normpath(_get_manifest_path(show_root))

    if not os.path.exists(manifest_path):
        _log_warning(f"Show manifest was not found: {manifest_path}")
        return

    _log(f"Found show manifest: {manifest_path}")

    try:
        with open(manifest_path, "r", encoding="utf-8-sig") as f:
            manifest_data = json.load(f)
    except Exception as exc:
        _log_warning(f"Could not read show manifest JSON. {exc}")
        return

    manifest_show_name = str(manifest_data.get("ShowName", "")).strip()
    if not manifest_show_name:
        _log_warning("Show manifest does not contain a ShowName value.")
        return

    if show_name and manifest_show_name != show_name:
        _log_warning(
            f"Input show_name '{show_name}' does not match manifest ShowName '{manifest_show_name}'."
        )
        return

    _log(f"Manifest ShowName='{manifest_show_name}'")


def _build_relative_folder_paths(sequence_name, shot_name):
    relative_folders = []
    for template in SHOT_RELATIVE_FOLDER_TEMPLATES:
        relative_folders.append(
            template.format(
                sequence_name=sequence_name,
                shot_name=shot_name,
            )
        )
    return relative_folders


def _create_folders(show_root, relative_folder_paths):
    created_folders = []
    existing_folders = []

    for relative_path in relative_folder_paths:
        folder_path = os.path.normpath(os.path.join(show_root, relative_path))

        if os.path.isdir(folder_path):
            existing_folders.append(folder_path)
            _log(f"Folder already exists: {folder_path}")
            continue

        os.makedirs(folder_path, exist_ok=True)
        created_folders.append(folder_path)
        _log(f"Created folder: {folder_path}")

    missing_folders = [
        os.path.normpath(os.path.join(show_root, relative_path))
        for relative_path in relative_folder_paths
        if not os.path.isdir(os.path.normpath(os.path.join(show_root, relative_path)))
    ]

    return created_folders, existing_folders, missing_folders


def run(show_name, sequence_name, shot_name):
    try:
        _log(f"Raw show_name input: {show_name}")
        _log(f"Raw sequence_name input: {sequence_name}")
        _log(f"Raw shot_name input: {shot_name}")

        sanitized_show_name = _sanitize_show_name(show_name)
        sanitized_sequence_name = _sanitize_sequence_name(sequence_name)
        sanitized_shot_name = _sanitize_shot_name(shot_name)

        if not sanitized_sequence_name:
            _log_error("sequence_name was empty after sanitizing.")
            return ""

        if not sanitized_shot_name:
            _log_error("shot_name was empty after sanitizing.")
            return ""

        derived_sequence_name = _derive_sequence_name(sanitized_shot_name)
        if derived_sequence_name and derived_sequence_name != sanitized_sequence_name:
            _log_warning(
                f"Input sequence_name '{sanitized_sequence_name}' does not match sequence derived from shot_name '{derived_sequence_name}'. "
                f"Using input sequence_name '{sanitized_sequence_name}'."
            )

        show_root = _get_saved_show_file_server_path()
        if not show_root:
            return ""

        if not os.path.isdir(show_root):
            _log_error(f"Saved show file server path does not exist or is not a folder: {show_root}")
            return ""

        _log(f"Using show file server path: {show_root}")
        _log(f"Sanitized sequence name: {sanitized_sequence_name}")
        _log(f"Sanitized shot name: {sanitized_shot_name}")

        _log_manifest_status(show_root, sanitized_show_name)

        relative_folder_paths = _build_relative_folder_paths(sanitized_sequence_name, sanitized_shot_name)
        created_folders, existing_folders, missing_folders = _create_folders(show_root, relative_folder_paths)

        _log(f"Created folders: {len(created_folders)}")
        _log(f"Already existing folders: {len(existing_folders)}")
        _log(f"Missing folders after create: {len(missing_folders)}")

        if missing_folders:
            for folder_path in missing_folders[:25]:
                _log_error(f"Missing folder: {folder_path}")
            return ""

        return "true"

    except Exception as exc:
        _log_error(str(exc))
        return ""
