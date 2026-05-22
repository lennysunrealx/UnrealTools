import re
import unreal


LOG_PREFIX = "[CreateSequence]"


def _log(message: str) -> None:
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_error(message: str) -> None:
    unreal.log_error(f"{LOG_PREFIX} {message}")


def _sanitize_show_name(show_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", show_name or "")


def _sanitize_sequence_name(sequence_name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9]", "", sequence_name or "")
    return sanitized.upper()


def _ensure_folder(folder_path: str) -> bool:
    if unreal.EditorAssetLibrary.does_directory_exist(folder_path):
        _log(f"Folder already exists: {folder_path}")
        return True

    created = unreal.EditorAssetLibrary.make_directory(folder_path)
    if created:
        _log(f"Created folder: {folder_path}")
        return True

    if unreal.EditorAssetLibrary.does_directory_exist(folder_path):
        _log(f"Folder exists after create attempt: {folder_path}")
        return True

    _log_error(f"Failed to create folder: {folder_path}")
    return False


def _create_placeholder_if_missing(sequence_folder: str) -> bool:
    asset_name = "_sequenceholder"
    asset_path = f"{sequence_folder}/{asset_name}"

    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        _log(f"Placeholder already exists: {asset_path}")
        return True

    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", unreal.Object)

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    created_asset = asset_tools.create_asset(asset_name, sequence_folder, unreal.Blueprint, factory)

    if created_asset:
        _log(f"Created placeholder Blueprint: {asset_path}")
        return True

    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        _log(f"Placeholder exists after create attempt: {asset_path}")
        return True

    _log_error(f"Failed to create placeholder Blueprint: {asset_path}")
    return False


def run(show_name, sequence_name):
    """
    Create /Game/_[sanitized_show_name]/Sequences/[sanitized_sequence_name]
    and a Blueprint placeholder named _sequenceholder in that folder.

    Returns:
        str: Final sequence folder path on success, or "" on failure.
    """
    sanitized_show_name = _sanitize_show_name(show_name)
    sanitized_sequence_name = _sanitize_sequence_name(sequence_name)

    if not sanitized_show_name:
        _log_error("Sanitized show name is empty. Aborting.")
        return ""

    if not sanitized_sequence_name:
        _log_error("Sanitized sequence name is empty. Aborting.")
        return ""

    show_folder = f"/Game/_{sanitized_show_name}"
    sequences_folder = f"{show_folder}/Sequences"
    sequence_folder = f"{sequences_folder}/{sanitized_sequence_name}"

    _log(f"Resolved show folder: {show_folder}")
    _log(f"Resolved sequence folder: {sequence_folder}")

    if not _ensure_folder(show_folder):
        return ""

    if not _ensure_folder(sequences_folder):
        return ""

    if not _ensure_folder(sequence_folder):
        return ""

    if not _create_placeholder_if_missing(sequence_folder):
        return ""

    _log(f"Done: {sequence_folder}")
    return sequence_folder
