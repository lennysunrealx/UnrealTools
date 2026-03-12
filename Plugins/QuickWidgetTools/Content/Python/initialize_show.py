# -*- coding: utf-8 -*-
"""
initialize_show.py

Designed to be called from an Editor Utility Widget via:
    import initialize_show
    import importlib
    importlib.reload(initialize_show)
    initialize_show.run(show_name)

What it does:
- Accepts a show name string from Blueprint
- Sanitizes it into a safe Unreal folder name like: _MyCoolShow
- Creates the folder tree under /Game/_ShowName
- Creates a Blueprint asset named "_showholder" in the root show folder
- Creates a Blueprint asset named "_folderholder" in each subfolder
- The Blueprint parent class is Object
- Safe to re-run
- Logs all actions
"""

import re
import traceback
import unreal


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

DEFAULT_SHOW_NAME = "ShowName"
PLACEHOLDER_ASSET_NAME = "_folderholder"
ROOT_PLACEHOLDER_ASSET_NAME = "_showholder"

FOLDER_TREE = {
    "Assets": [
        "Characters",
        "Environments",
        "Props",
        "Foliage",
        "Vehicles",
        "Materials",
        "Misc",
        "FX",
    ],
    "Maps": [
        "Layout",
        "Lighting",
        "Master",
    ],
    "Sequences": [],
    "RenderSettings": [
        "OCIO",
    ],
    "Audio": [],
}


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

def log(message):
    unreal.log(f"[InitializeShow] {message}")


def log_warning(message):
    unreal.log_warning(f"[InitializeShow] {message}")


def log_error(message):
    unreal.log_error(f"[InitializeShow] {message}")


# -----------------------------------------------------------------------------
# Name utilities
# -----------------------------------------------------------------------------

def to_pascal_case(raw_text):
    parts = re.findall(r"[A-Za-z0-9]+", raw_text or "")
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def sanitize_show_name(user_text):
    """
    Rules:
    - remove spaces / symbols
    - convert to PascalCase
    - prevent empty result
    - prevent starting with a number
    - prefix underscore so it sorts near the top
    """
    cleaned = to_pascal_case((user_text or "").strip())
    cleaned = re.sub(r"[^A-Za-z0-9]", "", cleaned)

    if not cleaned:
        cleaned = DEFAULT_SHOW_NAME

    if cleaned[0].isdigit():
        cleaned = "Show" + cleaned

    return "_" + cleaned


# -----------------------------------------------------------------------------
# Path helpers
# -----------------------------------------------------------------------------

def join_game_path(parent, child):
    return f"{parent.rstrip('/')}/{child.strip('/')}"


def build_all_game_paths(show_folder_name):
    """
    Returns every folder path we want, including the root show folder.
    """
    root = f"/Game/{show_folder_name}"
    paths = [root]

    for top_level, children in FOLDER_TREE.items():
        top_path = join_game_path(root, top_level)
        paths.append(top_path)

        for child in children:
            child_path = join_game_path(top_path, child)
            paths.append(child_path)

    return paths


def get_placeholder_asset_name(folder_game_path, root_game_path):
    if folder_game_path.rstrip('/') == root_game_path.rstrip('/'):
        return ROOT_PLACEHOLDER_ASSET_NAME
    return PLACEHOLDER_ASSET_NAME


def get_placeholder_asset_path(folder_game_path, root_game_path):
    placeholder_asset_name = get_placeholder_asset_name(folder_game_path, root_game_path)
    return f"{folder_game_path.rstrip('/')}/{placeholder_asset_name}"


# -----------------------------------------------------------------------------
# Unreal folder helpers
# -----------------------------------------------------------------------------

def ensure_unreal_directory(game_path):
    """
    Creates the Unreal directory if missing.
    Returns:
        "created" or "exists"
    Raises on unexpected errors.
    """
    if unreal.EditorAssetLibrary.does_directory_exist(game_path):
        return "exists"

    ok = unreal.EditorAssetLibrary.make_directory(game_path)
    if not ok:
        if unreal.EditorAssetLibrary.does_directory_exist(game_path):
            return "exists"
        raise RuntimeError(f"Failed to create directory: {game_path}")

    return "created"


# -----------------------------------------------------------------------------
# Blueprint placeholder helpers
# -----------------------------------------------------------------------------

def delete_asset_if_broken(asset_path):
    """
    If an asset exists at the path but is broken/invalid, try deleting it so it
    can be recreated.
    """
    if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        return False

    loaded = unreal.EditorAssetLibrary.load_asset(asset_path)
    if loaded is not None:
        return False

    log_warning(f"Found broken asset, deleting so it can be recreated: {asset_path}")
    deleted = unreal.EditorAssetLibrary.delete_asset(asset_path)
    if not deleted:
        raise RuntimeError(f"Failed to delete broken asset: {asset_path}")

    return True


def ensure_placeholder_blueprint(folder_game_path, root_game_path):
    """
    Ensures a placeholder Blueprint asset exists in the given folder.
    The Blueprint parent class is Object.

    Returns:
        ("created", asset_path) or ("exists", asset_path)
    """
    placeholder_asset_name = get_placeholder_asset_name(folder_game_path, root_game_path)
    asset_path = get_placeholder_asset_path(folder_game_path, root_game_path)

    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        loaded_existing = unreal.EditorAssetLibrary.load_asset(asset_path)
        if loaded_existing is not None:
            return "exists", asset_path

        delete_asset_if_broken(asset_path)

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", unreal.Object)
    factory.set_editor_property("edit_after_new", False)

    asset_obj = asset_tools.create_asset(
        asset_name=placeholder_asset_name,
        package_path=folder_game_path,
        asset_class=unreal.Blueprint,
        factory=factory
    )

    if not asset_obj:
        raise RuntimeError(f"Failed to create Blueprint placeholder: {asset_path}")

    saved = unreal.EditorAssetLibrary.save_asset(asset_path, only_if_is_dirty=False)
    if not saved:
        raise RuntimeError(f"Created placeholder Blueprint but failed to save: {asset_path}")

    loaded_after_save = unreal.EditorAssetLibrary.load_asset(asset_path)
    if loaded_after_save is None:
        raise RuntimeError(f"Placeholder Blueprint was created but could not be loaded after save: {asset_path}")

    return "created", asset_path


# -----------------------------------------------------------------------------
# Scan / preview helpers
# -----------------------------------------------------------------------------

def scan_missing_items(show_name):
    """
    Useful if you later want a preview mode from Blueprint.
    Returns:
        dict
    """
    sanitized_show_name = sanitize_show_name(show_name)
    all_game_paths = build_all_game_paths(sanitized_show_name)
    root_game_path = f"/Game/{sanitized_show_name}"

    missing_folder_count = 0
    missing_asset_count = 0

    for folder_path in all_game_paths:
        if not unreal.EditorAssetLibrary.does_directory_exist(folder_path):
            missing_folder_count += 1

        asset_path = get_placeholder_asset_path(folder_path, root_game_path)
        if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            missing_asset_count += 1

    return {
        "requested_show_name": show_name,
        "sanitized_show_name": sanitized_show_name,
        "root_game_path": root_game_path,
        "total_target_folders": len(all_game_paths),
        "missing_folders": missing_folder_count,
        "missing_assets": missing_asset_count,
    }


# -----------------------------------------------------------------------------
# Main creation logic
# -----------------------------------------------------------------------------

def create_show_structure(requested_show_name):
    sanitized_show_name = sanitize_show_name(requested_show_name)
    root_game_path = f"/Game/{sanitized_show_name}"
    all_game_paths = build_all_game_paths(sanitized_show_name)
    root_placeholder_asset_path = get_placeholder_asset_path(root_game_path, root_game_path)

    log(f"Requested show name: {requested_show_name}")
    log(f"Sanitized show name: {sanitized_show_name}")
    log(f"Target game path: {root_game_path}")

    created_folders = 0
    existing_folders = 0
    created_assets = 0
    existing_assets = 0

    for folder_path in all_game_paths:
        folder_result = ensure_unreal_directory(folder_path)
        if folder_result == "created":
            created_folders += 1
            log(f"Created folder: {folder_path}")
        else:
            existing_folders += 1
            log(f"Folder already exists: {folder_path}")

        asset_result, asset_path = ensure_placeholder_blueprint(
            folder_game_path=folder_path,
            root_game_path=root_game_path,
        )
        if asset_result == "created":
            created_assets += 1
            log(f"Created placeholder Blueprint: {asset_path}")
        else:
            existing_assets += 1
            log(f"Placeholder Blueprint already exists: {asset_path}")

    try:
        unreal.EditorAssetLibrary.save_directory(root_game_path, only_if_is_dirty=False, recursive=True)
    except Exception as exc:
        log_warning(f"save_directory warning on {root_game_path}: {exc}")

    try:
        if unreal.EditorAssetLibrary.does_asset_exist(root_placeholder_asset_path):
            unreal.EditorAssetLibrary.sync_browser_to_objects([root_placeholder_asset_path])
    except Exception as exc:
        log_warning(f"sync_browser_to_objects warning: {exc}")

    summary = {
        "requested_show_name": requested_show_name,
        "sanitized_show_name": sanitized_show_name,
        "root_game_path": root_game_path,
        "root_placeholder_asset_path": root_placeholder_asset_path,
        "total_target_folders": len(all_game_paths),
        "created_folders": created_folders,
        "existing_folders": existing_folders,
        "created_assets": created_assets,
        "existing_assets": existing_assets,
    }

    log("Done.")
    log("Summary:")
    log(f"  Requested Show Name: {summary['requested_show_name']}")
    log(f"  Sanitized Show Name: {summary['sanitized_show_name']}")
    log(f"  Root Path: {summary['root_game_path']}")
    log(f"  Root Placeholder: {summary['root_placeholder_asset_path']}")
    log(f"  Total Target Folders: {summary['total_target_folders']}")
    log(f"  Created folders: {summary['created_folders']}")
    log(f"  Existing folders: {summary['existing_folders']}")
    log(f"  Created placeholder Blueprints: {summary['created_assets']}")
    log(f"  Existing placeholder Blueprints: {summary['existing_assets']}")

    return summary


# -----------------------------------------------------------------------------
# Cleanup helper
# -----------------------------------------------------------------------------

def delete_all_placeholder_assets(show_name):
    """
    Deletes _showholder at the root and _folderholder in subfolders for a given show.
    """
    sanitized_show_name = sanitize_show_name(show_name)
    root_game_path = f"/Game/{sanitized_show_name}"
    all_game_paths = build_all_game_paths(sanitized_show_name)

    deleted_count = 0

    for folder_path in all_game_paths:
        asset_path = get_placeholder_asset_path(folder_path, root_game_path)
        if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            deleted = unreal.EditorAssetLibrary.delete_asset(asset_path)
            if deleted:
                deleted_count += 1
                log(f"Deleted placeholder Blueprint: {asset_path}")
            else:
                log_warning(f"Failed to delete placeholder Blueprint: {asset_path}")

    log(f"Deleted {deleted_count} placeholder Blueprints for show {sanitized_show_name}")
    return deleted_count


# -----------------------------------------------------------------------------
# Entry point for Blueprint
# -----------------------------------------------------------------------------

def run(show_name):
    """
    Main entry point called from the Execute Python Script node.
    """
    try:
        requested_show_name = (show_name or "").strip()
        if not requested_show_name:
            requested_show_name = DEFAULT_SHOW_NAME

        return create_show_structure(requested_show_name)

    except Exception as exc:
        log_error(f"Failed to initialize show: {exc}")
        log_error(traceback.format_exc())
        raise
