"""
Create file-server folders for a pipeline asset using the saved show file server path.

Blueprint usage:
    import create_asset_folders_fileserver
    import importlib
    importlib.reload(create_asset_folders_fileserver)

    asset_file_server_path = create_asset_folders_fileserver.run(asset_name)

What this does:
    - Reads ShowFileServerPath from QuickWidgetToolsSettings.ini.
    - Finds/creates the assets folder inside the saved show root.
    - Creates an asset folder named after asset_name.
    - Creates a curated asset folder scaffold, using the same explicit-template style
      as create_shot_file_server_folders.py.

Example:
    ShowFileServerPath=F:/Defect Dropbox/defect/s3bishop
    asset_name=prp_ExampleProp

Creates:
    F:/Defect Dropbox/defect/s3bishop/assets/prp_ExampleProp/...

Returns:
    str: File-server asset folder path on success, or "" on failure.
"""

import os
import re
import traceback
import unreal


LOG_PREFIX = "[CreateAssetFoldersFileServer]"
_SETTINGS_FILE_NAME = "QuickWidgetToolsSettings.ini"
_SECTION = "/Script/QuickWidgetTools.RenderToolSettings"
_SHOW_FILE_SERVER_PATH_KEY = "ShowFileServerPath"
ASSETS_FOLDER_NAME = "assets"

ASSET_RELATIVE_FOLDER_TEMPLATES = (
    "{asset_name}",
    "{asset_name}/_output",
    "{asset_name}/reference",

    "{asset_name}/anim/_output",
    "{asset_name}/anim/maya",

    "{asset_name}/rig/_output",
    "{asset_name}/rig/maya",

    "{asset_name}/fx/_output",
    "{asset_name}/fx/houdini",
    "{asset_name}/fx/emberLiquiGen",

    "{asset_name}/lite/_output",
    "{asset_name}/lite/unreal/_output",
    "{asset_name}/lite/unreal/_output/_hero",

    "{asset_name}/lvl/_output",
    "{asset_name}/lvl/unreal",
    "{asset_name}/lvl/maya",
    "{asset_name}/lvl/blender",

    "{asset_name}/comp/_output",
    "{asset_name}/comp/nuke",
    "{asset_name}/comp/natron",
    "{asset_name}/comp/davinci",

    "{asset_name}/mesh/_output",
    "{asset_name}/mesh/maya",
    "{asset_name}/mesh/blender",
    "{asset_name}/mesh/zbrush",
    "{asset_name}/mesh/substance",
)


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_warning(message):
    unreal.log_warning(f"{LOG_PREFIX} Warning: {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} Error: {message}")


def _sanitize_asset_name(value):
    if value is None:
        return ""

    cleaned = str(value).strip()
    cleaned = cleaned.replace(" ", "_").replace("-", "_")
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_.")

    if cleaned and cleaned[0].isdigit():
        cleaned = f"asset_{cleaned}"

    return cleaned


def _normalize_file_path(path_value):
    value = str(path_value or "").strip()
    if not value:
        return ""
    return value.replace("\\", "/").rstrip("/")


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


def _build_relative_asset_folders(asset_name):
    relative_folders = []
    for template in ASSET_RELATIVE_FOLDER_TEMPLATES:
        relative_folders.append(template.format(asset_name=asset_name))
    return relative_folders


def _create_folder(path):
    normalized_path = os.path.normpath(path)

    if os.path.isdir(normalized_path):
        _log(f"Folder already exists: {normalized_path}")
        return "exists"

    os.makedirs(normalized_path, exist_ok=True)
    if os.path.isdir(normalized_path):
        _log(f"Created folder: {normalized_path}")
        return "created"

    raise RuntimeError(f"Failed to create folder: {normalized_path}")


def run(asset_name):
    try:
        _log(f"Raw asset_name input: {asset_name!r}")

        sanitized_asset_name = _sanitize_asset_name(asset_name)
        if not sanitized_asset_name:
            _log_error("asset_name was empty after sanitizing.")
            return ""

        show_root = _get_saved_show_file_server_path()
        if not show_root:
            return ""

        if not os.path.isdir(show_root):
            _log_error(f"Saved show file server path does not exist or is not a folder: {show_root}")
            return ""

        assets_root = os.path.normpath(os.path.join(show_root, ASSETS_FOLDER_NAME))
        asset_root = os.path.normpath(os.path.join(assets_root, sanitized_asset_name))

        _log(f"Using show file server path: {show_root}")
        _log(f"Assets root: {assets_root}")
        _log(f"Asset root: {asset_root}")

        created_count = 0
        existing_count = 0

        if _create_folder(assets_root) == "created":
            created_count += 1
        else:
            existing_count += 1

        relative_asset_folders = _build_relative_asset_folders(sanitized_asset_name)

        for relative_folder in relative_asset_folders:
            folder_path = os.path.join(assets_root, relative_folder)
            result = _create_folder(folder_path)
            if result == "created":
                created_count += 1
            else:
                existing_count += 1

        missing_folders = []
        for relative_folder in relative_asset_folders:
            folder_path = os.path.normpath(os.path.join(assets_root, relative_folder))
            if not os.path.isdir(folder_path):
                missing_folders.append(folder_path)

        _log(f"Created folders: {created_count}")
        _log(f"Already existing folders: {existing_count}")
        _log(f"Missing folders after create: {len(missing_folders)}")

        if missing_folders:
            for folder_path in missing_folders[:25]:
                _log_error(f"Missing folder: {folder_path}")
            return ""

        return asset_root.replace("\\", "/")

    except Exception as exc:
        _log_error(str(exc))
        _log_error(traceback.format_exc())
        return ""
