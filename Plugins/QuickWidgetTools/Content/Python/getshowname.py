import unreal


def run():
    """Find the active show folder under /Game and return its show name (without leading underscore)."""
    show_name = ""
    log_prefix = "[GetShowName]"

    asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()

    # Gather only top-level folder paths directly under /Game.
    sub_paths = asset_registry.get_sub_paths("/Game", recurse=False)
    candidate_folders = sorted(path for path in sub_paths if path.split("/")[-1].startswith("_"))

    unreal.log(f"{log_prefix} Found {len(candidate_folders)} underscore-prefixed top-level folder(s) under /Game.")

    for folder_path in candidate_folders:
        folder_name = folder_path.split("/")[-1]
        showholder_asset_path = f"{folder_path}/_showholder"

        if unreal.EditorAssetLibrary.does_asset_exist(showholder_asset_path):
            show_name = folder_name[1:] if folder_name.startswith("_") else folder_name
            unreal.log(
                f"{log_prefix} Valid show folder found: {folder_path} (show_name='{show_name}')."
            )
            return show_name

        unreal.log(f"{log_prefix} Skipping {folder_path}: missing asset '{showholder_asset_path}'.")

    unreal.log_warning(f"{log_prefix} No valid show folder found under /Game.")
    return show_name
