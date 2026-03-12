import re
import unreal


LOG_PREFIX = "[GetSequences]"


def _log(message: str) -> None:
    unreal.log(f"{LOG_PREFIX} {message}")


def _sanitize_show_name(show_name: str) -> str:
    """Keep only letters and numbers; preserve case."""
    return re.sub(r"[^A-Za-z0-9]", "", show_name or "")


def run(show_name):
    """
    Return valid sequence folder names from:
        /Game/_[sanitized_show_name]/Sequences

    A folder is valid only if it directly contains:
        _sequenceholder
    """
    sanitized_show_name = _sanitize_show_name(show_name)
    sequences_folder = f"/Game/_{sanitized_show_name}/Sequences"

    _log(f"Input show_name: '{show_name}'")
    _log(f"Sanitized show_name: '{sanitized_show_name}'")
    _log(f"Target sequences folder: {sequences_folder}")

    if not sanitized_show_name:
        _log("Sanitized show name is empty. Returning [].")
        return []

    if not unreal.EditorAssetLibrary.does_directory_exist(sequences_folder):
        _log(f"Sequences folder does not exist: {sequences_folder}. Returning [].")
        return []

    children = unreal.EditorAssetLibrary.list_assets(
        sequences_folder,
        recursive=False,
        include_folder=True,
    )

    valid_sequences = []
    for child_path in children:
        if not unreal.EditorAssetLibrary.does_directory_exist(child_path):
            continue

        sequence_name = child_path.rsplit("/", 1)[-1]
        holder_path = f"{child_path}/_sequenceholder"

        if unreal.EditorAssetLibrary.does_asset_exist(holder_path):
            valid_sequences.append(sequence_name)
            _log(f"Valid sequence folder found: {sequence_name}")
        else:
            _log(f"Skipping folder (missing _sequenceholder): {sequence_name}")

    valid_sequences = sorted(valid_sequences)
    _log(f"Final sequence list ({len(valid_sequences)}): {valid_sequences}")
    return valid_sequences
