import re
import unreal


LOG_PREFIX = "[SetFrameRange]"


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_warning(message):
    unreal.log_warning(f"{LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} {message}")


def _sanitize_name(raw_value, label, force_upper=False):
    if raw_value is None:
        return "", f"{label} is missing (None)."

    raw_text = str(raw_value)
    text = raw_text.strip()
    if not text:
        return "", f"{label} is empty."

    cleaned = re.sub(r"\s+", "", text)
    cleaned = re.sub(r"[^A-Za-z0-9_\-]", "", cleaned)
    if force_upper:
        cleaned = cleaned.upper()

    if not cleaned:
        return "", f"{label} became empty after sanitization. raw='{raw_text}'"

    return cleaned, None


def _parse_frame_number(raw_value, label):
    if raw_value is None:
        return None, f"{label} is missing (None)."

    if isinstance(raw_value, bool):
        return None, f"{label} must be an integer, not bool. raw='{raw_value}'"

    try:
        text = str(raw_value).strip()
    except Exception as exc:
        return None, f"{label} could not be converted to text for parsing. raw='{raw_value}', error='{exc}'"

    if text == "":
        return None, f"{label} is empty after stripping whitespace. raw='{raw_value}'"

    try:
        value = int(text)
    except Exception:
        return None, f"{label} could not be converted to int. raw='{raw_value}', stripped='{text}'"

    return value, None


def _resolve_paths(show_name, sequence_name, shot_name):
    sequence_root = f"/Game/_{show_name}/Sequences/{sequence_name}"
    master_sequence_path = f"{sequence_root}/{shot_name}"
    shot_folder = f"{sequence_root}/{shot_name}"
    subsequences_folder = f"{shot_folder}/SubSequences"
    render_passes_folder = f"{shot_folder}/RenderPasses"

    return {
        "sequence_root": sequence_root,
        "master_sequence_path": master_sequence_path,
        "shot_folder": shot_folder,
        "subsequences_folder": subsequences_folder,
        "render_passes_folder": render_passes_folder,
    }


def _list_level_sequences_in_folder(folder_path):
    if not unreal.EditorAssetLibrary.does_directory_exist(folder_path):
        _log_warning(f"Folder does not exist: {folder_path}")
        return []

    try:
        asset_paths = unreal.EditorAssetLibrary.list_assets(
            folder_path, recursive=False, include_folder=False
        )
    except TypeError:
        asset_paths = unreal.EditorAssetLibrary.list_assets(folder_path, False, False)
    except Exception as exc:
        _log_error(f"Failed to list assets in folder '{folder_path}': {exc}")
        return []

    level_sequence_paths = []
    for asset_path in asset_paths:
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if isinstance(asset, unreal.LevelSequence):
            level_sequence_paths.append(asset_path)

    return level_sequence_paths


def _load_level_sequence(asset_path, label):
    if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        _log_error(f"{label} not found at path: {asset_path}")
        return None

    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not asset:
        _log_error(f"Failed to load {label}: {asset_path}")
        return None

    if not isinstance(asset, unreal.LevelSequence):
        _log_error(f"{label} is not a LevelSequence: {asset_path}")
        return None

    return asset


def _get_playback_range(sequence):
    return int(sequence.get_playback_start()), int(sequence.get_playback_end())


def _sync_section_ranges_if_needed(sequence_path, sequence, start_frame, end_frame):
    sections_checked = 0
    sections_updated = 0

    try:
        tracks = sequence.get_tracks()
    except Exception as exc:
        _log_warning(f"Section sync skipped for '{sequence_path}' (could not get tracks): {exc}")
        return {"checked": sections_checked, "updated": sections_updated}

    for track in tracks:
        try:
            sections = track.get_sections()
        except Exception:
            continue

        for section in sections:
            sections_checked += 1

            try:
                section_start = int(section.get_start_frame())
                section_end = int(section.get_end_frame())
            except Exception:
                continue

            if section_start == start_frame and section_end == end_frame:
                continue

            try:
                section.set_range(start_frame, end_frame)
                sections_updated += 1
                _log(
                    f"Section updated: sequence={sequence_path}, section={section.get_name()}, "
                    f"old_start={section_start}, old_end={section_end}, "
                    f"new_start={start_frame}, new_end={end_frame}"
                )
            except Exception as exc:
                _log_warning(
                    f"Failed to update section range: sequence={sequence_path}, "
                    f"section={section.get_name()}, error={exc}"
                )

    return {"checked": sections_checked, "updated": sections_updated}


def _update_sequence_if_needed(sequence_path, sequence, start_frame, end_frame):
    current_start, current_end = _get_playback_range(sequence)
    _log(
        f"Sequence current range: path={sequence_path}, "
        f"current_start={current_start}, current_end={current_end}"
    )
    _log(
        f"Sequence requested range: path={sequence_path}, "
        f"requested_start={start_frame}, requested_end={end_frame}"
    )

    playback_changed = False
    if current_start != start_frame or current_end != end_frame:
        sequence.set_playback_start(start_frame)
        sequence.set_playback_end(end_frame)
        playback_changed = True

        new_start, new_end = _get_playback_range(sequence)
        _log(
            f"Sequence playback updated: path={sequence_path}, "
            f"new_start={new_start}, new_end={new_end}"
        )
    else:
        _log(f"Sequence playback skipped (already matches requested range): {sequence_path}")

    section_sync_result = _sync_section_ranges_if_needed(
        sequence_path, sequence, start_frame, end_frame
    )

    any_changes = playback_changed or section_sync_result["updated"] > 0
    if not any_changes:
        _log(
            f"Sequence skipped (no playback/section changes needed): {sequence_path}. "
            f"sections_checked={section_sync_result['checked']}, "
            f"sections_updated={section_sync_result['updated']}"
        )
        return {"updated": False, "saved": True}

    save_ok = unreal.EditorAssetLibrary.save_loaded_asset(sequence)
    if not save_ok:
        _log_error(f"Failed to save updated sequence: {sequence_path}")
        return {"updated": True, "saved": False}

    _log(
        f"Sequence updated and saved: {sequence_path}. "
        f"playback_changed={playback_changed}, "
        f"sections_checked={section_sync_result['checked']}, "
        f"sections_updated={section_sync_result['updated']}"
    )
    return {"updated": True, "saved": True}


def run(show_name, sequence_name, shot_name, start_frame, end_frame):
    """Set playback frame range on shot master + SubSequences + RenderPasses."""
    _log("run() started")
    _log(
        "Raw incoming arguments: "
        f"show_name={show_name}, sequence_name={sequence_name}, shot_name={shot_name}, "
        f"start_frame={start_frame}, end_frame={end_frame}"
    )

    clean_show_name, err = _sanitize_name(show_name, "show_name", force_upper=False)
    if err:
        _log_error(f"Validation failed before return False: {err}")
        return False

    clean_sequence_name, err = _sanitize_name(sequence_name, "sequence_name", force_upper=False)
    if err:
        _log_error(f"Validation failed before return False: {err}")
        return False

    clean_shot_name, err = _sanitize_name(shot_name, "shot_name", force_upper=False)
    if err:
        _log_error(f"Validation failed before return False: {err}")
        return False

    _log(
        "Sanitized string arguments: "
        f"show_name_raw={show_name}, show_name_sanitized={clean_show_name}; "
        f"sequence_name_raw={sequence_name}, sequence_name_sanitized={clean_sequence_name}; "
        f"shot_name_raw={shot_name}, shot_name_sanitized={clean_shot_name}"
    )

    clean_start_frame, err = _parse_frame_number(start_frame, "start_frame")
    if err:
        _log_error(f"Validation failed before return False: {err}")
        return False

    clean_end_frame, err = _parse_frame_number(end_frame, "end_frame")
    if err:
        _log_error(f"Validation failed before return False: {err}")
        return False

    _log(
        "Parsed frame integers: "
        f"start_frame_raw={start_frame}, start_frame_parsed={clean_start_frame}; "
        f"end_frame_raw={end_frame}, end_frame_parsed={clean_end_frame}"
    )

    if clean_end_frame < clean_start_frame:
        _log_error(
            "Validation failed before return False: end_frame is less than start_frame. "
            f"start_frame={clean_start_frame}, end_frame={clean_end_frame}"
        )
        return False

    paths = _resolve_paths(clean_show_name, clean_sequence_name, clean_shot_name)
    _log(f"Resolved sequence root: {paths['sequence_root']}")
    _log(f"Resolved master sequence path: {paths['master_sequence_path']}")
    _log(f"Resolved shot folder path: {paths['shot_folder']}")
    _log(f"Resolved SubSequences folder path: {paths['subsequences_folder']}")
    _log(f"Resolved RenderPasses folder path: {paths['render_passes_folder']}")

    master_sequence = _load_level_sequence(paths["master_sequence_path"], "Master sequence")
    _log(f"Master sequence found: {bool(master_sequence)}")
    if not master_sequence:
        _log_error("Cannot continue before return False: master sequence is required.")
        return False

    subsequence_paths = _list_level_sequences_in_folder(paths["subsequences_folder"])
    render_pass_paths = _list_level_sequences_in_folder(paths["render_passes_folder"])

    _log(f"SubSequences found ({len(subsequence_paths)}): {subsequence_paths}")
    _log(f"RenderPasses found ({len(render_pass_paths)}): {render_pass_paths}")

    target_paths = [paths["master_sequence_path"]] + subsequence_paths + render_pass_paths

    updated_count = 0
    skipped_count = 0
    failed_paths = []

    for sequence_path in target_paths:
        label = "Master sequence" if sequence_path == paths["master_sequence_path"] else "Child sequence"
        sequence = _load_level_sequence(sequence_path, label)
        if not sequence:
            failed_paths.append(sequence_path)
            continue

        try:
            result = _update_sequence_if_needed(
                sequence_path, sequence, clean_start_frame, clean_end_frame
            )
        except Exception as exc:
            _log_error(f"Unexpected update failure for '{sequence_path}': {exc}")
            failed_paths.append(sequence_path)
            continue

        if not result["saved"]:
            failed_paths.append(sequence_path)
            continue

        if result["updated"]:
            updated_count += 1
        else:
            skipped_count += 1

    if failed_paths:
        _log_error(
            "Failed before return False: one or more sequences could not be updated/saved. "
            f"failed_count={len(failed_paths)}, failed_paths={failed_paths}"
        )
        return False

    _log(
        "Success summary: "
        f"total_targets={len(target_paths)}, updated={updated_count}, skipped={skipped_count}, "
        f"requested_start={clean_start_frame}, requested_end={clean_end_frame}"
    )
    return True
