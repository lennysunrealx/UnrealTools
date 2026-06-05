"""
Duplicate an existing shot Level Sequence and its shot subsequences.

Blueprint usage:
    import create_duplicate_shot
    import importlib
    importlib.reload(create_duplicate_shot)

    result = create_duplicate_shot.run(
        show_name,
        sequence_name,
        old_shot_name,
        new_shot_name,
    )

What this does:
    - Validates that the old master shot sequence exists.
    - Validates that the new master shot sequence does not already exist.
    - Duplicates the old master shot sequence to the new shot name.
    - Removes subsequence tracks from the duplicated master sequence.
    - Recursively duplicates the old shot SubSequences folder contents.
    - Renames duplicated subsequence assets from old_shot_name to new_shot_name.
    - Places duplicated subsequences into the matching new SubSequences subfolders.
    - Rebuilds the new master sequence with the duplicated subsequences.

Returns:
    str: New master sequence asset path on success, or "" on failure.
"""

import re
import unreal


LOG_PREFIX = "[CreateDuplicateShot]"

CORE_SUBSEQUENCE_ORDER = ["ANM", "CAM", "ENV", "FX", "LGT", "LVL", "PREVIS"]
VERSION_PATTERN = re.compile(r"_v\d{3}$", re.IGNORECASE)


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_warning(message):
    unreal.log_warning(f"{LOG_PREFIX} Warning: {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} Error: {message}")


def _sanitize_show_name(value):
    if value is None:
        return ""
    return "".join(ch for ch in str(value) if ch.isalnum())


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


def _ensure_folder(path):
    if unreal.EditorAssetLibrary.does_directory_exist(path):
        return True
    if unreal.EditorAssetLibrary.make_directory(path):
        _log(f"Created folder: {path}")
        return True
    _log_error(f"Failed to create folder: {path}")
    return False


def _get_asset_name_from_package_path(package_path):
    package_path = _get_package_path(package_path)
    return package_path.rsplit("/", 1)[-1]


def _get_object_path_from_package_path(package_path):
    asset_name = package_path.rsplit("/", 1)[-1]
    return f"{package_path}.{asset_name}"


def _get_package_path(asset_path):
    """
    Convert either package paths or dotted object paths to package paths.

    Examples:
        /Game/Foo/Bar -> /Game/Foo/Bar
        /Game/Foo/Bar.Bar -> /Game/Foo/Bar
    """
    if not asset_path:
        return ""

    value = str(asset_path)
    folder_path, asset_reference_name = value.rsplit("/", 1)
    package_name = asset_reference_name.split(".", 1)[0]
    return f"{folder_path}/{package_name}"


def _add_asset_path_variants(path_map, source_path, value):
    package_path = _get_package_path(source_path)
    object_path = _get_object_path_from_package_path(package_path)
    path_map[package_path] = value
    path_map[object_path] = value


def _is_level_sequence_asset(asset_path):
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    return asset is not None and isinstance(asset, unreal.LevelSequence)


def _get_sequence_tracks(sequence):
    if hasattr(sequence, "get_tracks"):
        return sequence.get_tracks()

    if hasattr(sequence, "get_master_tracks"):
        return sequence.get_master_tracks()

    _log_error("Unable to inspect sequence tracks: sequence has neither get_tracks() nor get_master_tracks().")
    return []


def _add_subsequence_track(sequence):
    if hasattr(sequence, "add_track"):
        return sequence.add_track(unreal.MovieSceneSubTrack)

    if hasattr(sequence, "add_master_track"):
        return sequence.add_master_track(unreal.MovieSceneSubTrack)

    _log_error("Unable to create subsequence track: sequence has neither add_track() nor add_master_track().")
    return None


def _remove_sequence_track(sequence, track):
    if hasattr(sequence, "remove_track"):
        try:
            return bool(sequence.remove_track(track))
        except TypeError:
            sequence.remove_track(track)
            return True
        except Exception as exc:
            _log_warning(f"remove_track failed: {exc}")

    if hasattr(sequence, "remove_master_track"):
        try:
            return bool(sequence.remove_master_track(track))
        except TypeError:
            sequence.remove_master_track(track)
            return True
        except Exception as exc:
            _log_warning(f"remove_master_track failed: {exc}")

    return False


def _get_track_sections(track):
    if hasattr(track, "get_sections"):
        return track.get_sections()

    if hasattr(unreal, "MovieSceneTrackExtensions") and hasattr(unreal.MovieSceneTrackExtensions, "get_sections"):
        return unreal.MovieSceneTrackExtensions.get_sections(track)

    _log_error("Unable to inspect track sections: track has no get_sections() and MovieSceneTrackExtensions.get_sections() is unavailable.")
    return []


def _remove_track_section(track, section):
    if hasattr(track, "remove_section"):
        try:
            track.remove_section(section)
            return True
        except Exception as exc:
            _log_warning(f"remove_section failed: {exc}")

    if hasattr(unreal, "MovieSceneTrackExtensions") and hasattr(unreal.MovieSceneTrackExtensions, "remove_section"):
        try:
            unreal.MovieSceneTrackExtensions.remove_section(track, section)
            return True
        except Exception as exc:
            _log_warning(f"MovieSceneTrackExtensions.remove_section failed: {exc}")

    return False


def _set_subsequence_reference(section, sequence_asset):
    if hasattr(section, "set_sequence"):
        section.set_sequence(sequence_asset)
        return True

    if hasattr(section, "set_sub_sequence"):
        section.set_sub_sequence(sequence_asset)
        return True

    try:
        section.set_editor_property("sub_sequence", sequence_asset)
        return True
    except Exception:
        return False


def _get_subsequence_reference(section):
    if hasattr(section, "get_sequence"):
        return section.get_sequence()

    if hasattr(section, "get_sub_sequence"):
        return section.get_sub_sequence()

    try:
        return section.get_editor_property("sub_sequence")
    except Exception:
        return None


def _frame_to_int(value):
    if value is None:
        return None

    if isinstance(value, int) and not isinstance(value, bool):
        return value

    if hasattr(value, "value"):
        try:
            return int(value.value)
        except Exception:
            return None

    try:
        return int(value)
    except Exception:
        return None


def _get_section_start_frame(section):
    if hasattr(section, "get_start_frame"):
        try:
            return _frame_to_int(section.get_start_frame())
        except Exception:
            return None
    return None


def _get_section_end_frame(section):
    if hasattr(section, "get_end_frame"):
        try:
            return _frame_to_int(section.get_end_frame())
        except Exception:
            return None
    return None


def _set_section_range(section, start_frame, end_frame):
    if start_frame is None or end_frame is None:
        return False

    if hasattr(section, "set_range"):
        section.set_range(start_frame, end_frame)
        return True

    range_applied = False

    if hasattr(section, "set_start_frame"):
        section.set_start_frame(start_frame)
        range_applied = True

    if hasattr(section, "set_end_frame"):
        section.set_end_frame(end_frame)
        range_applied = True

    if hasattr(section, "set_start_frame_bounded"):
        section.set_start_frame_bounded(False)

    if hasattr(section, "set_end_frame_bounded"):
        section.set_end_frame_bounded(False)

    return range_applied


def _get_section_row_index(section):
    if hasattr(section, "get_row_index"):
        try:
            return int(section.get_row_index())
        except Exception:
            return None
    return None


def _set_section_row_index(section, row_index):
    if row_index is None:
        return False

    if hasattr(section, "set_row_index"):
        try:
            section.set_row_index(row_index)
            return True
        except Exception:
            return False

    return False


def _capture_old_subsequence_sections(master_sequence):
    descriptors = []

    for track in _get_sequence_tracks(master_sequence):
        if not isinstance(track, unreal.MovieSceneSubTrack):
            continue

        for section in _get_track_sections(track):
            sub_sequence = _get_subsequence_reference(section)
            if not sub_sequence:
                continue

            old_reference_path = _get_package_path(sub_sequence.get_path_name())
            descriptors.append(
                {
                    "old_reference_path": old_reference_path,
                    "start_frame": _get_section_start_frame(section),
                    "end_frame": _get_section_end_frame(section),
                    "row_index": _get_section_row_index(section),
                }
            )

    _log(f"Captured old subsequence sections: {len(descriptors)}")
    return descriptors


def _remove_all_subsequence_tracks(master_sequence):
    removed_tracks = 0
    cleared_sections = 0

    for track in list(_get_sequence_tracks(master_sequence)):
        if not isinstance(track, unreal.MovieSceneSubTrack):
            continue

        if _remove_sequence_track(master_sequence, track):
            removed_tracks += 1
            continue

        _log_warning("Could not remove a MovieSceneSubTrack directly. Clearing its sections instead.")
        for section in list(_get_track_sections(track)):
            if _remove_track_section(track, section):
                cleared_sections += 1

    _log(f"Removed subsequence tracks: {removed_tracks}")
    if cleared_sections:
        _log_warning(f"Cleared subsequence sections from tracks that could not be removed: {cleared_sections}")


def _get_relative_path(asset_path, root_path):
    package_path = _get_package_path(asset_path)
    root_path = root_path.rstrip("/")

    if package_path == root_path:
        return ""

    prefix = f"{root_path}/"
    if not package_path.startswith(prefix):
        return ""

    return package_path[len(prefix):]


def _replace_shot_name_in_asset_name(old_asset_name, old_shot_name, new_shot_name):
    if old_asset_name.startswith(old_shot_name):
        return f"{new_shot_name}{old_asset_name[len(old_shot_name):]}"

    if old_shot_name in old_asset_name:
        return old_asset_name.replace(old_shot_name, new_shot_name)

    _log_warning(
        f"Subsequence asset name '{old_asset_name}' did not contain old shot name '{old_shot_name}'. "
        f"Prefixing with new shot name."
    )
    return f"{new_shot_name}_{old_asset_name}"


def _infer_subsequence_folder_name(asset_name, old_shot_name, new_shot_name):
    normalized_name = asset_name

    if normalized_name.startswith(new_shot_name):
        remainder = normalized_name[len(new_shot_name):]
    elif normalized_name.startswith(old_shot_name):
        remainder = normalized_name[len(old_shot_name):]
    else:
        remainder = normalized_name

    remainder = remainder.lstrip("_")
    remainder = VERSION_PATTERN.sub("", remainder)

    if not remainder:
        return "MISC"

    return remainder.split("_", 1)[0].upper()


def _get_destination_subsequence_folder(old_asset_path, old_root, new_root, old_shot_name, new_shot_name, new_asset_name):
    relative_path = _get_relative_path(old_asset_path, old_root)
    relative_parts = [part for part in relative_path.split("/") if part]

    if len(relative_parts) > 1:
        old_relative_folder = "/".join(relative_parts[:-1])
        new_relative_folder = old_relative_folder.replace(old_shot_name, new_shot_name)
        return f"{new_root}/{new_relative_folder}"

    folder_name = _infer_subsequence_folder_name(new_asset_name, old_shot_name, new_shot_name)
    return f"{new_root}/{folder_name}"


def _sort_subsequence_item(item):
    asset_path, _sequence_asset = item
    asset_name = _get_asset_name_from_package_path(asset_path)

    suffix_folder = "ZZZ"
    parts = _get_package_path(asset_path).split("/")
    if "SubSequences" in parts:
        index = parts.index("SubSequences")
        if index + 1 < len(parts) - 1:
            suffix_folder = parts[index + 1]

    try:
        order_index = CORE_SUBSEQUENCE_ORDER.index(suffix_folder.upper())
    except ValueError:
        order_index = len(CORE_SUBSEQUENCE_ORDER)

    return order_index, suffix_folder, asset_name


def _list_old_subsequence_assets(old_subsequence_root):
    if not unreal.EditorAssetLibrary.does_directory_exist(old_subsequence_root):
        _log_warning(f"Old SubSequences folder does not exist: {old_subsequence_root}")
        return []

    listed_assets = unreal.EditorAssetLibrary.list_assets(
        old_subsequence_root,
        recursive=True,
        include_folder=False,
    )

    level_sequence_assets = []
    for asset_path in listed_assets:
        package_path = _get_package_path(asset_path)
        if _is_level_sequence_asset(package_path):
            level_sequence_assets.append(package_path)
        else:
            _log_warning(f"Skipping non-LevelSequence asset in SubSequences folder: {package_path}")

    return level_sequence_assets


def _duplicate_subsequence_assets(old_subsequence_root, new_subsequence_root, old_shot_name, new_shot_name):
    old_subsequence_asset_paths = _list_old_subsequence_assets(old_subsequence_root)
    if not old_subsequence_asset_paths:
        _log_warning("No old subsequence Level Sequence assets were found to duplicate.")
        return [], {}

    duplicated_subsequence_items = []
    old_to_new_package_path_map = {}

    for old_asset_path in old_subsequence_asset_paths:
        old_asset_name = _get_asset_name_from_package_path(old_asset_path)
        new_asset_name = _replace_shot_name_in_asset_name(old_asset_name, old_shot_name, new_shot_name)
        new_package_folder = _get_destination_subsequence_folder(
            old_asset_path,
            old_subsequence_root,
            new_subsequence_root,
            old_shot_name,
            new_shot_name,
            new_asset_name,
        )
        new_asset_path = f"{new_package_folder}/{new_asset_name}"

        if unreal.EditorAssetLibrary.does_asset_exist(new_asset_path):
            _log_error(f"Destination subsequence asset already exists: {new_asset_path}")
            return [], {}

        if not _ensure_folder(new_package_folder):
            return [], {}

        _log(f"Duplicating subsequence: {old_asset_path} -> {new_asset_path}")
        duplicated_asset = unreal.EditorAssetLibrary.duplicate_asset(old_asset_path, new_asset_path)
        if not duplicated_asset:
            _log_error(f"Failed to duplicate subsequence asset: {old_asset_path} -> {new_asset_path}")
            return [], {}

        loaded_asset = unreal.EditorAssetLibrary.load_asset(new_asset_path)
        if not loaded_asset or not isinstance(loaded_asset, unreal.LevelSequence):
            _log_error(f"Duplicated asset is invalid or not a Level Sequence: {new_asset_path}")
            return [], {}

        if not unreal.EditorAssetLibrary.save_loaded_asset(loaded_asset):
            _log_error(f"Failed to save duplicated subsequence: {new_asset_path}")
            return [], {}

        duplicated_subsequence_items.append((new_asset_path, loaded_asset))
        _add_asset_path_variants(old_to_new_package_path_map, old_asset_path, new_asset_path)

    duplicated_subsequence_items.sort(key=_sort_subsequence_item)
    _log(f"Duplicated subsequence assets: {len(duplicated_subsequence_items)}")
    return duplicated_subsequence_items, old_to_new_package_path_map


def _rebuild_master_subsequence_tracks(master_sequence, duplicated_subsequence_items, old_section_descriptors, old_to_new_package_path_map):
    added_sections = 0

    if old_section_descriptors:
        for descriptor in old_section_descriptors:
            old_reference_path = descriptor.get("old_reference_path", "")
            new_asset_path = old_to_new_package_path_map.get(_get_package_path(old_reference_path))
            if not new_asset_path:
                new_asset_path = old_to_new_package_path_map.get(_get_object_path_from_package_path(_get_package_path(old_reference_path)))

            if not new_asset_path:
                _log_warning(f"Could not find duplicated subsequence for old reference: {old_reference_path}")
                continue

            new_subsequence_asset = unreal.EditorAssetLibrary.load_asset(new_asset_path)
            if not new_subsequence_asset or not isinstance(new_subsequence_asset, unreal.LevelSequence):
                _log_warning(f"New subsequence asset could not be loaded: {new_asset_path}")
                continue

            if _add_subsequence_to_master(
                master_sequence,
                new_subsequence_asset,
                new_asset_path,
                descriptor.get("start_frame"),
                descriptor.get("end_frame"),
                descriptor.get("row_index"),
            ):
                added_sections += 1

    if added_sections:
        _log(f"Rebuilt master using old master subsequence order. Added sections: {added_sections}")
        return added_sections

    _log_warning("No subsequences were rebuilt from old master references. Falling back to all duplicated subsequences.")
    for new_asset_path, new_subsequence_asset in duplicated_subsequence_items:
        playback_start = None
        playback_end = None

        if hasattr(new_subsequence_asset, "get_playback_start"):
            try:
                playback_start = int(new_subsequence_asset.get_playback_start())
            except Exception:
                playback_start = None

        if hasattr(new_subsequence_asset, "get_playback_end"):
            try:
                playback_end = int(new_subsequence_asset.get_playback_end())
            except Exception:
                playback_end = None

        if _add_subsequence_to_master(
            master_sequence,
            new_subsequence_asset,
            new_asset_path,
            playback_start,
            playback_end,
            None,
        ):
            added_sections += 1

    _log(f"Fallback rebuilt master subsequences. Added sections: {added_sections}")
    return added_sections


def _add_subsequence_to_master(master_sequence, subsequence_asset, asset_path, start_frame, end_frame, row_index):
    track = _add_subsequence_track(master_sequence)
    if not track:
        _log_error(f"Failed to create subsequence track for: {asset_path}")
        return False

    section = track.add_section()
    if not section:
        _log_error(f"Failed to create subsequence section for: {asset_path}")
        return False

    if not _set_subsequence_reference(section, subsequence_asset):
        _log_error(f"Failed to assign subsequence asset to section: {asset_path}")
        return False

    if _set_section_range(section, start_frame, end_frame):
        _log(f"Set section range {start_frame}-{end_frame} for: {asset_path}")
    else:
        _log_warning(f"Section range was not applied for: {asset_path}")

    _set_section_row_index(section, row_index)
    _log(f"Added subsequence to duplicated master: {asset_path}")
    return True


def run(show_name, sequence_name, old_shot_name, new_shot_name):
    try:
        sanitized_show_name = _sanitize_show_name(show_name)
        sanitized_sequence_name = _sanitize_sequence_name(sequence_name)
        sanitized_old_shot_name = _sanitize_shot_name(old_shot_name)
        sanitized_new_shot_name = _sanitize_shot_name(new_shot_name)

        _log(f"Sanitized show_name: {sanitized_show_name}")
        _log(f"Sanitized sequence_name: {sanitized_sequence_name}")
        _log(f"Sanitized old_shot_name: {sanitized_old_shot_name}")
        _log(f"Sanitized new_shot_name: {sanitized_new_shot_name}")

        if not sanitized_show_name:
            _log_error("show_name was empty after sanitizing.")
            return ""

        if not sanitized_sequence_name:
            _log_error("sequence_name was empty after sanitizing.")
            return ""

        if not sanitized_old_shot_name:
            _log_error("old_shot_name was empty after sanitizing.")
            return ""

        if not sanitized_new_shot_name:
            _log_error("new_shot_name was empty after sanitizing.")
            return ""

        if sanitized_old_shot_name == sanitized_new_shot_name:
            _log_error("old_shot_name and new_shot_name cannot be the same.")
            return ""

        base_sequence_folder = f"/Game/_{sanitized_show_name}/Sequences/{sanitized_sequence_name}"
        sequence_holder_path = f"{base_sequence_folder}/_sequenceholder"
        old_master_sequence_path = f"{base_sequence_folder}/{sanitized_old_shot_name}"
        new_master_sequence_path = f"{base_sequence_folder}/{sanitized_new_shot_name}"
        old_subsequence_root = f"{old_master_sequence_path}/SubSequences"
        new_shot_folder = new_master_sequence_path
        new_subsequence_root = f"{new_shot_folder}/SubSequences"

        if not unreal.EditorAssetLibrary.does_directory_exist(base_sequence_folder):
            _log_error(f"Sequence folder does not exist: {base_sequence_folder}")
            return ""

        if not unreal.EditorAssetLibrary.does_asset_exist(sequence_holder_path):
            _log_error(f"Sequence folder does not contain required '_sequenceholder': {sequence_holder_path}")
            return ""

        if not unreal.EditorAssetLibrary.does_asset_exist(old_master_sequence_path):
            _log_error(f"Old master shot Level Sequence does not exist: {old_master_sequence_path}")
            return ""

        if unreal.EditorAssetLibrary.does_asset_exist(new_master_sequence_path):
            _log_error(f"New master shot Level Sequence already exists: {new_master_sequence_path}")
            return ""

        if unreal.EditorAssetLibrary.does_directory_exist(new_shot_folder):
            _log_error(f"New shot content folder already exists: {new_shot_folder}")
            return ""

        old_master_sequence = unreal.EditorAssetLibrary.load_asset(old_master_sequence_path)
        if not old_master_sequence or not isinstance(old_master_sequence, unreal.LevelSequence):
            _log_error(f"Old master asset is invalid or not a Level Sequence: {old_master_sequence_path}")
            return ""

        old_section_descriptors = _capture_old_subsequence_sections(old_master_sequence)

        _log(f"Duplicating master shot sequence: {old_master_sequence_path} -> {new_master_sequence_path}")
        new_master_sequence = unreal.EditorAssetLibrary.duplicate_asset(old_master_sequence_path, new_master_sequence_path)
        if not new_master_sequence:
            _log_error(f"Failed to duplicate master shot sequence: {old_master_sequence_path} -> {new_master_sequence_path}")
            return ""

        new_master_sequence = unreal.EditorAssetLibrary.load_asset(new_master_sequence_path)
        if not new_master_sequence or not isinstance(new_master_sequence, unreal.LevelSequence):
            _log_error(f"Duplicated master asset is invalid or not a Level Sequence: {new_master_sequence_path}")
            return ""

        if not _ensure_folder(new_shot_folder):
            return ""

        if not _ensure_folder(new_subsequence_root):
            return ""

        _remove_all_subsequence_tracks(new_master_sequence)

        duplicated_subsequence_items, old_to_new_package_path_map = _duplicate_subsequence_assets(
            old_subsequence_root,
            new_subsequence_root,
            sanitized_old_shot_name,
            sanitized_new_shot_name,
        )

        if old_to_new_package_path_map:
            added_sections = _rebuild_master_subsequence_tracks(
                new_master_sequence,
                duplicated_subsequence_items,
                old_section_descriptors,
                old_to_new_package_path_map,
            )
            if duplicated_subsequence_items and added_sections <= 0:
                _log_error("Duplicated subsequences were created, but none were added to the new master sequence.")
                return ""
        else:
            _log_warning("No subsequence mapping was created. The new master sequence will remain without subsequences.")

        if not unreal.EditorAssetLibrary.save_loaded_asset(new_master_sequence):
            _log_error(f"Failed to save duplicated master sequence: {new_master_sequence_path}")
            return ""

        _log(f"Duplicated shot successfully: {new_master_sequence_path}")
        return new_master_sequence_path

    except Exception as exc:
        _log_error(str(exc))
        return ""
