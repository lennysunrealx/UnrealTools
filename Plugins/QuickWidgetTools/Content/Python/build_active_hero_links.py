import os
import re
import shutil
import subprocess
from datetime import datetime

import unreal


LOG_PREFIX = "[BuildActiveHeroLinks]"

# This matches your current render output convention.
RENDER_CONTEXT_SEGMENTS = ["lite", "unreal", "_output"]

# Per-shot state property candidates.
IS_ACTIVE_PROPERTY_CANDIDATES = [
    "IsActive",
    "is_active",
]

# Expected settings file location / key.
SETTINGS_FILE_NAME = "QuickWidgetToolsSettings.ini"
SETTINGS_SECTION = "/Script/QuickWidgetTools.RenderToolSettings"
SETTINGS_KEY = "OutputPath"


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_warning(message):
    unreal.log_warning(f"{LOG_PREFIX} Warning: {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} Error: {message}")


def _sanitize_show_name(show_name):
    return "".join(ch for ch in str(show_name or "") if ch.isalnum())


def _sanitize_sequence_name(sequence_name):
    cleaned = "".join(
        ch for ch in str(sequence_name or "") if ch.isalnum() or ch == "_"
    )
    return cleaned.upper()


def _extract_asset_name(asset_path):
    leaf = str(asset_path).rsplit("/", 1)[-1]
    return leaf.split(".", 1)[0]


def _parse_shot_name(asset_name):
    match = re.fullmatch(r"([A-Za-z0-9]+)_(\d{3})_(\d{4,})", asset_name)
    if not match:
        return None
    return {
        "sequence_prefix": match.group(1).upper(),
        "shot_number": int(match.group(3)),
    }


def _find_config_dir(project_dir):
    candidates = [
        os.path.join(project_dir, "Saved", "Config", "WindowsEditor"),
        os.path.join(project_dir, "Saved", "Config", "Windows"),
        os.path.join(project_dir, "Saved", "Config"),
    ]

    for folder in candidates:
        if os.path.isdir(folder):
            return folder

    return os.path.join(project_dir, "Saved", "Config", "WindowsEditor")


def _get_settings_file_path():
    project_dir = unreal.Paths.project_dir()
    config_dir = _find_config_dir(project_dir)
    return os.path.normpath(os.path.join(config_dir, SETTINGS_FILE_NAME))


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


def _get_saved_output_root():
    settings_path = _get_settings_file_path()
    _log(f"Settings path: {settings_path}")

    if not os.path.exists(settings_path):
        _log_error("Settings file does not exist.")
        return ""

    text = _read_text_file(settings_path)
    output_path = _get_section_value(text, SETTINGS_SECTION, SETTINGS_KEY).strip()

    if not output_path:
        _log_error("OutputPath was not found in QuickWidgetToolsSettings.ini.")
        return ""

    normalized = os.path.normpath(output_path)
    _log(f"Saved output root: {normalized}")
    return normalized


def _find_current_show_name():
    asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()
    sub_paths = asset_registry.get_sub_paths("/Game", recurse=False)
    candidate_folders = sorted(
        path for path in sub_paths if path.split("/")[-1].startswith("_")
    )

    for folder_path in candidate_folders:
        folder_name = folder_path.split("/")[-1]
        showholder_asset_path = f"{folder_path}/_showholder"
        if unreal.EditorAssetLibrary.does_asset_exist(showholder_asset_path):
            show_name = folder_name[1:] if folder_name.startswith("_") else folder_name
            _log(f"Current show resolved: {show_name}")
            return show_name

    _log_error("Could not find current show folder with _showholder.")
    return ""


def _build_expected_data_asset_path(shot_folder_path, shot_name):
    asset_name = f"{shot_name}_Data"
    return f"{shot_folder_path}/{asset_name}.{asset_name}"


def _find_fallback_data_asset_in_shot_folder(shot_folder_path, shot_name):
    editor_asset_lib = unreal.EditorAssetLibrary

    if not editor_asset_lib.does_directory_exist(shot_folder_path):
        return None

    asset_paths = editor_asset_lib.list_assets(
        shot_folder_path,
        recursive=False,
        include_folder=False,
    )

    preferred_name = f"{shot_name}_Data"
    fallback_candidate_path = ""

    for asset_path in asset_paths:
        asset_name = _extract_asset_name(asset_path)
        if asset_name == preferred_name:
            fallback_candidate_path = asset_path
            break

        if asset_name.endswith("_Data") and not fallback_candidate_path:
            fallback_candidate_path = asset_path

    if not fallback_candidate_path:
        return None

    loaded = unreal.load_asset(fallback_candidate_path)
    return loaded


def _load_data_asset_for_shot(sequence_folder_path, shot_name):
    shot_folder_path = f"{sequence_folder_path}/{shot_name}"
    expected_data_asset_path = _build_expected_data_asset_path(shot_folder_path, shot_name)

    if unreal.EditorAssetLibrary.does_asset_exist(expected_data_asset_path):
        loaded = unreal.load_asset(expected_data_asset_path)
        if loaded:
            return loaded

    return _find_fallback_data_asset_in_shot_folder(shot_folder_path, shot_name)


def _get_is_active_for_shot(shot_data_asset):
    if not shot_data_asset:
        return False

    for property_name in IS_ACTIVE_PROPERTY_CANDIDATES:
        try:
            value = shot_data_asset.get_editor_property(property_name)
            return bool(value)
        except Exception:
            continue

    _log_warning("Shot data asset did not expose IsActive.")
    return False


def _get_active_shot_names(show_name, sequence_name):
    sanitized_show_name = _sanitize_show_name(show_name)
    sanitized_sequence_name = _sanitize_sequence_name(sequence_name)

    if not sanitized_show_name:
        _log_error("Sanitized show_name is empty.")
        return []

    if not sanitized_sequence_name:
        _log_error("Sanitized sequence_name is empty.")
        return []

    sequence_folder_path = f"/Game/_{sanitized_show_name}/Sequences/{sanitized_sequence_name}"
    sequenceholder_path = f"{sequence_folder_path}/_sequenceholder"

    if not unreal.EditorAssetLibrary.does_directory_exist(sequence_folder_path):
        _log_error(f"Sequence folder does not exist: {sequence_folder_path}")
        return []

    if not unreal.EditorAssetLibrary.does_asset_exist(sequenceholder_path):
        _log_error(f"Missing _sequenceholder: {sequenceholder_path}")
        return []

    asset_paths = unreal.EditorAssetLibrary.list_assets(
        sequence_folder_path,
        recursive=False,
        include_folder=False,
    )

    active_rows = []

    for asset_path in asset_paths:
        asset_name = _extract_asset_name(asset_path)

        if asset_name == "_sequenceholder":
            continue

        parsed = _parse_shot_name(asset_name)
        if not parsed:
            continue

        if parsed["sequence_prefix"] != sanitized_sequence_name:
            continue

        asset_obj = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not asset_obj or not isinstance(asset_obj, unreal.LevelSequence):
            continue

        shot_data_asset = _load_data_asset_for_shot(sequence_folder_path, asset_name)
        is_active = _get_is_active_for_shot(shot_data_asset)

        if is_active:
            active_rows.append((parsed["shot_number"], asset_name))

    active_rows.sort(key=lambda row: row[0])
    active_shot_names = [shot_name for _, shot_name in active_rows]

    _log(f"Found {len(active_shot_names)} active shot(s): {active_shot_names}")
    return active_shot_names


def _normalize_sequence_output_root(output_root, sequence_name):
    """
    We want:
        <saved_output_root>/<SEQ>

    But if the saved root already ends with the sequence folder, do not double it.
    """
    normalized_root = os.path.normpath(output_root)
    normalized_sequence = _sanitize_sequence_name(sequence_name)

    if os.path.basename(normalized_root).upper() == normalized_sequence:
        return normalized_root

    return os.path.join(normalized_root, normalized_sequence)


def _build_hero_folder_path(sequence_output_root, shot_name):
    return os.path.join(
        sequence_output_root,
        shot_name,
        *RENDER_CONTEXT_SEGMENTS,
        "_hero",
    )


def _ensure_directory(path):
    os.makedirs(path, exist_ok=True)
    return os.path.normpath(path)


def _safe_remove_existing_path(path):
    if not os.path.lexists(path):
        return

    if os.path.islink(path):
        os.unlink(path)
        return

    if os.path.isdir(path):
        shutil.rmtree(path)
        return

    os.remove(path)


def _is_directory_empty(path):
    try:
        with os.scandir(path) as entries:
            return not any(entries)
    except Exception as exc:
        _log_warning(f"Could not inspect directory contents for '{path}': {exc}")
        return False


def _create_junction(link_path, target_path):
    """
    Creates a Windows directory junction:
        mklink /J "link_path" "target_path"
    """
    parent_dir = os.path.dirname(link_path)
    os.makedirs(parent_dir, exist_ok=True)

    _safe_remove_existing_path(link_path)

    cmd = [
        "cmd",
        "/c",
        "mklink",
        "/J",
        link_path,
        target_path,
    ]

    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        shell=False,
    )

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        _log_error(
            f"mklink failed for '{link_path}' -> '{target_path}' | "
            f"returncode={completed.returncode} | stdout='{stdout}' | stderr='{stderr}'"
        )
        return False

    _log(f"Created junction: {link_path} -> {target_path}")
    return True


def run(sequence_name):
    """
    Build a timestamped RV-friendly hero review folder for all ACTIVE shots in a sequence.

    Input:
        sequence_name (str), example: "MNF"

    Output:
        Returns the created dump folder path on success, or "" on failure.
    """
    _log("----- run() called -----")
    _log(f"Raw sequence_name: {sequence_name!r}")

    clean_sequence_name = _sanitize_sequence_name(sequence_name)
    if not clean_sequence_name:
        _log_error("sequence_name is invalid after sanitization.")
        return ""

    show_name = _find_current_show_name()
    if not show_name:
        return ""

    output_root = _get_saved_output_root()
    if not output_root:
        return ""

    sequence_output_root = _normalize_sequence_output_root(output_root, clean_sequence_name)
    _log(f"Sequence output root: {sequence_output_root}")

    active_shot_names = _get_active_shot_names(show_name, clean_sequence_name)
    if not active_shot_names:
        _log_warning("No active shots found. Nothing to link.")
        return ""

    sequence_dump_root = _ensure_directory(
        os.path.join(sequence_output_root, "_output")
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    dump_folder = os.path.join(sequence_dump_root, f"{timestamp}_heros")
    _ensure_directory(dump_folder)

    _log(f"Dump folder: {dump_folder}")

    links_created = 0
    missing_hero_folders = []
    empty_hero_folders = []

    for shot_name in active_shot_names:
        hero_folder = _build_hero_folder_path(sequence_output_root, shot_name)
        hero_folder = os.path.normpath(hero_folder)

        if not os.path.isdir(hero_folder):
            _log_warning(f"Hero folder missing for active shot '{shot_name}': {hero_folder}")
            missing_hero_folders.append(shot_name)
            continue

        is_empty = _is_directory_empty(hero_folder)
        link_name = f"{shot_name}_empty" if is_empty else shot_name
        link_path = os.path.join(dump_folder, link_name)

        if is_empty:
            _log_warning(
                f"Hero folder exists but is empty for active shot '{shot_name}': {hero_folder}"
            )
            empty_hero_folders.append(shot_name)

        if _create_junction(link_path, hero_folder):
            links_created += 1

    _log("==================================================")
    _log(f"Show: {show_name}")
    _log(f"Sequence: {clean_sequence_name}")
    _log(f"Active shots found: {len(active_shot_names)}")
    _log(f"Links created: {links_created}")
    _log(f"Missing hero folders: {missing_hero_folders}")
    _log(f"Empty hero folders: {empty_hero_folders}")
    _log(f"Final dump folder: {dump_folder}")
    _log("==================================================")

    if links_created == 0:
        _log_warning("No hero links were created.")
        return ""

    return os.path.normpath(dump_folder)