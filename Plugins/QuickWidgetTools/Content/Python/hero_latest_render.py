import os
import re
import shutil

import unreal


LOG_PREFIX = "[HeroLatestRender]"

# This matches the current render output convention used by add_to_render_queue.py,
# build_active_hero_links.py, and build_active_beauty_mp4_dump.py.
RENDER_CONTEXT_SEGMENTS = ["lite", "unreal", "_output"]

# Only these image extensions will be copied into _hero.
IMAGE_EXTENSIONS = {
    ".exr",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
}

# Per-shot state property candidates.
IS_ACTIVE_PROPERTY_CANDIDATES = [
    "IsActive",
    "is_active",
]

# Expected settings file location / key.
SETTINGS_FILE_NAME = "QuickWidgetToolsSettings.ini"
SETTINGS_SECTION = "/Script/QuickWidgetTools.RenderToolSettings"
SETTINGS_KEY = "OutputPath"

SHOT_NAME_PATTERN = re.compile(r"^([A-Za-z0-9]+)_(\d{3})_(\d{4,})$")


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
    match = SHOT_NAME_PATTERN.fullmatch(str(asset_name or ""))
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

    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _find_section_bounds(lines, section_name):
    section_header = f"[{section_name}]"
    section_start = -1
    section_end = len(lines)

    for index, line in enumerate(lines):
        if line.strip() == section_header:
            section_start = index
            break

    if section_start == -1:
        return -1, -1

    for index in range(section_start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section_end = index
            break

    return section_start, section_end


def _get_section_value(text, section_name, key):
    lines = text.splitlines()
    section_start, section_end = _find_section_bounds(lines, section_name)

    if section_start == -1:
        return ""

    prefix = f"{key}="
    for index in range(section_start + 1, section_end):
        stripped = lines[index].strip()
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

    return unreal.load_asset(fallback_candidate_path)


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
    active_shot_names = [shot_name for _shot_number, shot_name in active_rows]

    _log(f"Found {len(active_shot_names)} active shot(s): {active_shot_names}")
    return active_shot_names


def _normalize_sequence_output_root(sequences_root, sequence_name):
    """
    We want:
        <sequences_root>/<SEQ>

    But if the provided root already ends with the sequence folder, do not double it.
    """
    normalized_root = os.path.normpath(str(sequences_root or "").strip().strip("\"'"))
    normalized_sequence = _sanitize_sequence_name(sequence_name)

    if not normalized_root:
        return ""

    if os.path.basename(normalized_root).upper() == normalized_sequence:
        return normalized_root

    return os.path.normpath(os.path.join(normalized_root, normalized_sequence))


def _build_shot_output_folder_path(sequence_output_root, shot_name):
    return os.path.normpath(
        os.path.join(
            sequence_output_root,
            shot_name,
            *RENDER_CONTEXT_SEGMENTS,
        )
    )


def _build_hero_folder_path(sequence_output_root, shot_name):
    return os.path.normpath(
        os.path.join(
            sequence_output_root,
            shot_name,
            *RENDER_CONTEXT_SEGMENTS,
            "_hero",
        )
    )


def _build_beauty_version_folder_pattern(shot_name):
    """
    Strictly matches:
        SHOTNAME_beauty_v###
    Example:
        MNF_000_7600_beauty_v055
    """
    return re.compile(rf"^{re.escape(shot_name)}_beauty_v(\d{{3}})$", re.IGNORECASE)


def _find_latest_beauty_version_folder(output_folder, shot_name):
    if not os.path.isdir(output_folder):
        _log_warning(f"Output folder missing for active shot '{shot_name}': {output_folder}")
        return "", 0

    pattern = _build_beauty_version_folder_pattern(shot_name)
    candidates = []

    try:
        entries = list(os.scandir(output_folder))
    except Exception as exc:
        _log_error(f"Failed scanning output folder '{output_folder}': {exc}")
        return "", 0

    for entry in entries:
        if not entry.is_dir(follow_symlinks=False):
            continue

        match = pattern.fullmatch(entry.name)
        if not match:
            continue

        try:
            version_number = int(match.group(1))
        except Exception:
            continue

        candidates.append((version_number, os.path.normpath(entry.path)))

    if not candidates:
        return "", 0

    candidates.sort(key=lambda item: item[0], reverse=True)
    latest_version, latest_folder = candidates[0]

    _log(
        f"Latest beauty render folder for '{shot_name}': "
        f"v{latest_version:03d} | {latest_folder}"
    )

    return latest_folder, latest_version


def _dedupe_paths(paths):
    deduped = []
    seen = set()

    for path in paths:
        norm = os.path.normpath(str(path))
        if norm not in seen:
            seen.add(norm)
            deduped.append(norm)

    return deduped


def _find_image_files(render_version_folder):
    image_files = []

    if not os.path.isdir(render_version_folder):
        return image_files

    try:
        entries = list(os.scandir(render_version_folder))
    except Exception as exc:
        _log_error(f"Failed scanning render version folder '{render_version_folder}': {exc}")
        return image_files

    for entry in entries:
        if not entry.is_file():
            continue

        ext = os.path.splitext(entry.name)[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            continue

        image_files.append(os.path.normpath(entry.path))

    return _dedupe_paths(sorted(image_files))


def _clear_directory_contents(folder_path):
    if not os.path.isdir(folder_path):
        return False

    try:
        entries = list(os.scandir(folder_path))
    except Exception as exc:
        _log_error(f"Failed to scan hero folder before clear '{folder_path}': {exc}")
        return False

    for entry in entries:
        entry_path = entry.path

        try:
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry_path)
            else:
                os.remove(entry_path)
        except Exception as exc:
            _log_error(f"Failed deleting hero entry '{entry_path}': {exc}")
            return False

    return True


def _ensure_clean_hero_folder(hero_folder):
    if os.path.isdir(hero_folder):
        if not _clear_directory_contents(hero_folder):
            return False

        return True

    try:
        os.makedirs(hero_folder, exist_ok=True)
        return True
    except Exception as exc:
        _log_error(f"Failed to create hero folder '{hero_folder}': {exc}")
        return False


def _make_hero_filename(file_name):
    """
    Mirrors mrg_callbacks_hero.py:
        MNF_000_7600_beauty_v055.1001.exr
    becomes:
        MNF_000_7600.1001.exr

    Non-frame-numbered files keep their original name.
    """
    stem, ext = os.path.splitext(file_name)

    match = re.match(r"^(.*)\.(\d+)$", stem)
    if not match:
        return file_name

    base_name = match.group(1)
    frame_number = match.group(2)

    tokens = base_name.split("_")
    if len(tokens) < 3:
        return file_name

    shot_name = "_".join(tokens[:3])
    return f"{shot_name}.{frame_number}{ext}"


def _copy_images_to_hero(render_version_folder, hero_folder, shot_name):
    image_files = _find_image_files(render_version_folder)

    if not image_files:
        _log_warning(
            f"No image files found in latest beauty render folder for '{shot_name}': "
            f"{render_version_folder}"
        )
        return 0, 0

    if not _ensure_clean_hero_folder(hero_folder):
        _log_error(f"Could not prepare hero folder for '{shot_name}': {hero_folder}")
        return 0, len(image_files)

    copied_count = 0
    failed_count = 0

    for source_path in image_files:
        try:
            if not os.path.isfile(source_path):
                failed_count += 1
                _log_warning(f"Source file missing at copy time: {source_path}")
                continue

            file_name = os.path.basename(source_path)
            new_file_name = _make_hero_filename(file_name)
            dest_path = os.path.join(hero_folder, new_file_name)

            shutil.copy2(source_path, dest_path)
            copied_count += 1

        except Exception as exc:
            failed_count += 1
            _log_warning(f"Failed to copy file '{source_path}': {exc}")

    return copied_count, failed_count


def _new_result(sequence_name, sequence_output_root):
    return {
        "success": True,
        "sequence_name": sequence_name,
        "sequence_output_root": sequence_output_root,
        "active_shots_found": 0,
        "shots_processed": 0,
        "shots_heroed": 0,
        "frames_copied": 0,
        "copy_failures": 0,
        "missing_output_folders": [],
        "missing_beauty_versions": [],
        "missing_image_files": [],
        "failed_shots": [],
        "message": "",
    }


def _join(values):
    return ",".join(str(value) for value in values) if values else ""


def _format_summary_string(result):
    return (
        f"success={1 if result.get('success') else 0};"
        f"sequence_name={result.get('sequence_name', '')};"
        f"active_shots_found={int(result.get('active_shots_found', 0))};"
        f"shots_processed={int(result.get('shots_processed', 0))};"
        f"shots_heroed={int(result.get('shots_heroed', 0))};"
        f"frames_copied={int(result.get('frames_copied', 0))};"
        f"copy_failures={int(result.get('copy_failures', 0))};"
        f"missing_output_folders={_join(result.get('missing_output_folders', []))};"
        f"missing_beauty_versions={_join(result.get('missing_beauty_versions', []))};"
        f"missing_image_files={_join(result.get('missing_image_files', []))};"
        f"failed_shots={_join(result.get('failed_shots', []))};"
        f"sequence_output_root={result.get('sequence_output_root', '')};"
        f"message={result.get('message', '')}"
    )


def run(sequence_name, sequences_root=None):
    """
    Rebuild _hero folders for all ACTIVE shots in a sequence from each shot's latest
    strictly-named beauty version folder.

    Inputs:
        sequence_name:
            Example: "MNF"

        sequences_root:
            Optional. Example:
                F:/Defect Dropbox/defect/nightfall/sequences

            If omitted, this reads OutputPath from:
                Saved/Config/WindowsEditor/QuickWidgetToolsSettings.ini

            If the provided path already ends with the sequence name, it will not append it twice.

    Output:
        Returns a semicolon-delimited summary string, matching the style of add_to_render_queue.py.
    """
    _log("----- run() called -----")
    _log(f"Raw sequence_name: {sequence_name!r}")
    _log(f"Raw sequences_root: {sequences_root!r}")

    clean_sequence_name = _sanitize_sequence_name(sequence_name)
    if not clean_sequence_name:
        result = _new_result("", "")
        result["success"] = False
        result["message"] = "sequence_name is invalid after sanitization."
        _log_error(result["message"])
        return _format_summary_string(result)

    show_name = _find_current_show_name()
    if not show_name:
        result = _new_result(clean_sequence_name, "")
        result["success"] = False
        result["message"] = "Could not resolve current show."
        return _format_summary_string(result)

    output_root = str(sequences_root or "").strip().strip("\"'")
    if output_root:
        output_root = os.path.normpath(output_root)
        _log(f"Using provided sequences_root: {output_root}")
    else:
        output_root = _get_saved_output_root()

    if not output_root:
        result = _new_result(clean_sequence_name, "")
        result["success"] = False
        result["message"] = "No sequences_root was provided and saved OutputPath could not be resolved."
        _log_error(result["message"])
        return _format_summary_string(result)

    sequence_output_root = _normalize_sequence_output_root(output_root, clean_sequence_name)
    _log(f"Sequence output root: {sequence_output_root}")

    result = _new_result(clean_sequence_name, sequence_output_root)

    active_shot_names = _get_active_shot_names(show_name, clean_sequence_name)
    result["active_shots_found"] = len(active_shot_names)

    if not active_shot_names:
        result["success"] = False
        result["message"] = "No active shots found. Nothing to hero."
        _log_warning(result["message"])
        return _format_summary_string(result)

    for shot_name in active_shot_names:
        result["shots_processed"] += 1

        shot_output_folder = _build_shot_output_folder_path(sequence_output_root, shot_name)
        hero_folder = _build_hero_folder_path(sequence_output_root, shot_name)

        if not os.path.isdir(shot_output_folder):
            _log_warning(
                f"Output folder missing for active shot '{shot_name}': {shot_output_folder}"
            )
            result["missing_output_folders"].append(shot_name)
            continue

        latest_folder, latest_version = _find_latest_beauty_version_folder(
            shot_output_folder,
            shot_name,
        )

        if not latest_folder:
            _log_warning(
                f"No strictly named beauty version folder found for active shot '{shot_name}' "
                f"under: {shot_output_folder}"
            )
            result["missing_beauty_versions"].append(shot_name)
            continue

        image_files = _find_image_files(latest_folder)
        if not image_files:
            _log_warning(
                f"Latest beauty version folder has no image files for active shot '{shot_name}': "
                f"{latest_folder}"
            )
            result["missing_image_files"].append(shot_name)
            continue

        _log(
            f"Heroing '{shot_name}' from latest beauty version v{latest_version:03d}: "
            f"{latest_folder}"
        )
        _log(f"Hero folder: {hero_folder}")

        copied_count, failed_count = _copy_images_to_hero(
            latest_folder,
            hero_folder,
            shot_name,
        )

        result["frames_copied"] += copied_count
        result["copy_failures"] += failed_count

        if copied_count > 0:
            result["shots_heroed"] += 1
            _log(
                f"Finished '{shot_name}': copied_count={copied_count}, "
                f"failed_count={failed_count}"
            )
        else:
            result["failed_shots"].append(shot_name)
            _log_error(
                f"Failed to copy any frames for '{shot_name}'. failed_count={failed_count}"
            )

    success = (
        result["shots_heroed"] > 0
        and not result["failed_shots"]
        and result["copy_failures"] == 0
    )

    result["success"] = success

    if result["shots_heroed"] == 0:
        result["message"] = "No _hero folders were rebuilt."
    else:
        result["message"] = (
            f"Rebuilt _hero folders for {result['shots_heroed']} active shot(s). "
            f"Copied {result['frames_copied']} frame(s)."
        )

    _log("==================================================")
    _log(f"Show: {show_name}")
    _log(f"Sequence: {clean_sequence_name}")
    _log(f"Sequence output root: {sequence_output_root}")
    _log(f"Active shots found: {result['active_shots_found']}")
    _log(f"Shots processed: {result['shots_processed']}")
    _log(f"Shots heroed: {result['shots_heroed']}")
    _log(f"Frames copied: {result['frames_copied']}")
    _log(f"Copy failures: {result['copy_failures']}")
    _log(f"Missing output folders: {result['missing_output_folders']}")
    _log(f"Missing beauty versions: {result['missing_beauty_versions']}")
    _log(f"Missing image files: {result['missing_image_files']}")
    _log(f"Failed shots: {result['failed_shots']}")
    _log("==================================================")

    return _format_summary_string(result)
