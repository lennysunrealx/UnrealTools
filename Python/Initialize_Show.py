# -*- coding: utf-8 -*-
"""
InitializeShow.py

Drop this into your project's Python folder so QuickPy can discover it.

What it does:
- Opens a small Qt window called "Initialize Show"
- Lets the user enter a show name
- Sanitizes the show name into a safe Unreal folder name like: _MyCoolShow
- Shows a confirmation dialog with:
    - Show Name
    - Final folder path
    - Number of folders to create
    - Number of _folderholder assets to create
- Creates the folder tree under /Game/_ShowName
- Creates a tiny DataAsset named "_folderholder" in each folder
- Safe to re-run
- Logs all actions

Notes:
- Uses RenderSettings instead of Render Settings
- Uses OCIO instead of Ocio
- Uses Unreal DataAsset placeholder assets so folders remain visible in Content Browser
"""

import re
import traceback
import unreal

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

WINDOW_TITLE = "Initialize Show"
DEFAULT_SHOW_NAME = "ShowName"
PLACEHOLDER_ASSET_NAME = "_folderholder"

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

# Keep window alive
_GLOBAL_INIT_SHOW_WINDOW = None


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

def log(message):
    unreal.log("[InitializeShow] {0}".format(message))


def log_warning(message):
    unreal.log_warning("[InitializeShow] {0}".format(message))


def log_error(message):
    unreal.log_error("[InitializeShow] {0}".format(message))


# -----------------------------------------------------------------------------
# Name utilities
# -----------------------------------------------------------------------------

def to_pascal_case(raw_text):
    parts = re.findall(r"[A-Za-z0-9]+", raw_text or "")
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def sanitize_show_name(user_text):
    """
    Rules:
    - remove spaces
    - remove all non alphanumeric characters
    - convert to PascalCase
    - prevent empty result
    - prevent starting with a number
    - prefix underscore so it sorts near the top
    """
    cleaned = to_pascal_case((user_text or "").strip())
    cleaned = re.sub(r"[^A-Za-z0-9]", "", cleaned)

    if not cleaned:
        cleaned = "ShowName"

    if cleaned[0].isdigit():
        cleaned = "Show" + cleaned

    return "_" + cleaned


# -----------------------------------------------------------------------------
# Path helpers
# -----------------------------------------------------------------------------

def join_game_path(parent, child):
    return "{0}/{1}".format(parent.rstrip("/"), child.strip("/"))


def build_all_game_paths(show_folder_name):
    """
    Returns every folder path we want, including the root show folder.
    """
    root = "/Game/{0}".format(show_folder_name)
    paths = [root]

    for top_level, children in FOLDER_TREE.items():
        top_path = join_game_path(root, top_level)
        paths.append(top_path)

        for child in children:
            child_path = join_game_path(top_path, child)
            paths.append(child_path)

    return paths


def get_placeholder_asset_path(folder_game_path):
    return "{0}/{1}".format(folder_game_path.rstrip("/"), PLACEHOLDER_ASSET_NAME)


# -----------------------------------------------------------------------------
# Unreal asset helpers
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
        # Check again in case it succeeded but returned oddly
        if unreal.EditorAssetLibrary.does_directory_exist(game_path):
            return "exists"
        raise RuntimeError("Failed to create directory: {0}".format(game_path))

    return "created"


def ensure_placeholder_data_asset(folder_game_path):
    """
    Ensures a DataAsset named _folderholder exists in the given folder.
    Returns:
        ("created", asset_path) or ("exists", asset_path)
    """
    asset_path = get_placeholder_asset_path(folder_game_path)

    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        return "exists", asset_path

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

    factory = unreal.DataAssetFactory()
    factory.set_editor_property("data_asset_class", unreal.DataAsset)
    factory.set_editor_property("edit_after_new", False)

    asset_obj = asset_tools.create_asset(
        asset_name=PLACEHOLDER_ASSET_NAME,
        package_path=folder_game_path,
        asset_class=unreal.DataAsset,
        factory=factory
    )

    if not asset_obj:
        raise RuntimeError("Failed to create DataAsset: {0}".format(asset_path))

    # Save it right away
    saved = unreal.EditorAssetLibrary.save_asset(asset_path, only_if_is_dirty=False)
    if not saved:
        log_warning("Created asset but save_asset returned False: {0}".format(asset_path))

    return "created", asset_path


def scan_missing_items(all_game_paths):
    """
    Returns:
        missing_folder_count,
        missing_asset_count
    """
    missing_folder_count = 0
    missing_asset_count = 0

    for folder_path in all_game_paths:
        if not unreal.EditorAssetLibrary.does_directory_exist(folder_path):
            missing_folder_count += 1

        asset_path = get_placeholder_asset_path(folder_path)
        if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            missing_asset_count += 1

    return missing_folder_count, missing_asset_count


# -----------------------------------------------------------------------------
# Main creation logic
# -----------------------------------------------------------------------------

def create_show_structure(requested_show_name):
    sanitized_show_name = sanitize_show_name(requested_show_name)
    root_game_path = "/Game/{0}".format(sanitized_show_name)
    all_game_paths = build_all_game_paths(sanitized_show_name)

    log("Requested show name: {0}".format(requested_show_name))
    log("Sanitized show name: {0}".format(sanitized_show_name))
    log("Target game path: {0}".format(root_game_path))

    created_folders = 0
    existing_folders = 0
    created_assets = 0
    existing_assets = 0

    for folder_path in all_game_paths:
        # Folder
        folder_result = ensure_unreal_directory(folder_path)
        if folder_result == "created":
            created_folders += 1
            log("Created folder: {0}".format(folder_path))
        else:
            existing_folders += 1
            log("Folder already exists: {0}".format(folder_path))

        # Placeholder asset
        asset_result, asset_path = ensure_placeholder_data_asset(folder_path)
        if asset_result == "created":
            created_assets += 1
            log("Created placeholder asset: {0}".format(asset_path))
        else:
            existing_assets += 1
            log("Placeholder already exists: {0}".format(asset_path))

    try:
        unreal.EditorAssetLibrary.save_directory(root_game_path, only_if_is_dirty=False, recursive=True)
    except Exception as exc:
        log_warning("save_directory warning on {0}: {1}".format(root_game_path, exc))

    # Sync browser so the user sees the result
    try:
        unreal.EditorAssetLibrary.sync_browser_to_objects([root_game_path])
    except Exception:
        pass

    log("Done.")
    log("Summary:")
    log("  Created folders: {0}".format(created_folders))
    log("  Existing folders: {0}".format(existing_folders))
    log("  Created placeholder assets: {0}".format(created_assets))
    log("  Existing placeholder assets: {0}".format(existing_assets))

    return {
        "requested_show_name": requested_show_name,
        "sanitized_show_name": sanitized_show_name,
        "root_game_path": root_game_path,
        "total_target_folders": len(all_game_paths),
        "created_folders": created_folders,
        "existing_folders": existing_folders,
        "created_assets": created_assets,
        "existing_assets": existing_assets,
    }


# -----------------------------------------------------------------------------
# Qt UI
# -----------------------------------------------------------------------------

def try_import_qt():
    try:
        from PySide2 import QtWidgets, QtCore
        return {
            "QtWidgets": QtWidgets,
            "QtCore": QtCore,
            "binding_name": "PySide2",
        }
    except Exception:
        pass

    try:
        from PySide6 import QtWidgets, QtCore
        return {
            "QtWidgets": QtWidgets,
            "QtCore": QtCore,
            "binding_name": "PySide6",
        }
    except Exception:
        pass

    return None


def launch_ui():
    qt = try_import_qt()
    if not qt:
        log_error("PySide2/PySide6 not found. This tool needs Qt support for the UI window.")
        return

    QtWidgets = qt["QtWidgets"]
    QtCore = qt["QtCore"]

    class InitializeShowWindow(QtWidgets.QDialog):
        def __init__(self, parent=None):
            super(InitializeShowWindow, self).__init__(parent)
            self.setWindowTitle(WINDOW_TITLE)
            self.setMinimumWidth(460)
            self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
            self.build_ui()

        def build_ui(self):
            main_layout = QtWidgets.QVBoxLayout(self)

            form_layout = QtWidgets.QFormLayout()
            self.show_name_line_edit = QtWidgets.QLineEdit()
            self.show_name_line_edit.setText(DEFAULT_SHOW_NAME)
            form_layout.addRow("Show Name:", self.show_name_line_edit)
            main_layout.addLayout(form_layout)

            self.preview_label = QtWidgets.QLabel("")
            self.preview_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            main_layout.addWidget(self.preview_label)

            button_row = QtWidgets.QHBoxLayout()
            button_row.addStretch()

            self.ok_button = QtWidgets.QPushButton("Ok")
            self.cancel_button = QtWidgets.QPushButton("Cancel")

            button_row.addWidget(self.ok_button)
            button_row.addWidget(self.cancel_button)
            main_layout.addLayout(button_row)

            self.show_name_line_edit.textChanged.connect(self.update_preview)
            self.ok_button.clicked.connect(self.on_ok_clicked)
            self.cancel_button.clicked.connect(self.close)

            self.update_preview()

        def update_preview(self):
            requested = self.show_name_line_edit.text().strip()
            sanitized = sanitize_show_name(requested)
            root_game_path = "/Game/{0}".format(sanitized)
            all_game_paths = build_all_game_paths(sanitized)

            missing_folder_count, missing_asset_count = scan_missing_items(all_game_paths)

            self.preview_label.setText(
                "Preview:\n"
                "  Final Folder Name: {0}\n"
                "  Final Folder Path: {1}\n"
                "  Total Target Folders: {2}\n"
                "  Missing Folders: {3}\n"
                "  Missing _folderholder Assets: {4}".format(
                    sanitized,
                    root_game_path,
                    len(all_game_paths),
                    missing_folder_count,
                    missing_asset_count,
                )
            )

        def on_ok_clicked(self):
            requested = self.show_name_line_edit.text().strip() or DEFAULT_SHOW_NAME
            sanitized = sanitize_show_name(requested)
            root_game_path = "/Game/{0}".format(sanitized)
            all_game_paths = build_all_game_paths(sanitized)

            missing_folder_count, missing_asset_count = scan_missing_items(all_game_paths)

            confirm_text = (
                "Show Name: {0}\n"
                "Final Folder Name: {1}\n"
                "Final Folder Path: {2}\n"
                "Folders to create: {3}\n"
                "Placeholder assets to create: {4}\n\n"
                "Confirm?"
            ).format(
                requested,
                sanitized,
                root_game_path,
                missing_folder_count,
                missing_asset_count,
            )

            result = QtWidgets.QMessageBox.question(
                self,
                "Confirm Initialize Show",
                confirm_text,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes,
            )

            if result != QtWidgets.QMessageBox.Yes:
                log("User cancelled during confirmation.")
                return

            try:
                summary = create_show_structure(requested)

                QtWidgets.QMessageBox.information(
                    self,
                    "Initialize Show Complete",
                    (
                        "Done.\n\n"
                        "Requested Show Name: {0}\n"
                        "Sanitized Show Name: {1}\n"
                        "Root Path: {2}\n"
                        "Created Folders: {3}\n"
                        "Existing Folders: {4}\n"
                        "Created Placeholder Assets: {5}\n"
                        "Existing Placeholder Assets: {6}"
                    ).format(
                        summary["requested_show_name"],
                        summary["sanitized_show_name"],
                        summary["root_game_path"],
                        summary["created_folders"],
                        summary["existing_folders"],
                        summary["created_assets"],
                        summary["existing_assets"],
                    ),
                )

                self.close()

            except Exception as exc:
                log_error("Failed to initialize show: {0}".format(exc))
                log_error(traceback.format_exc())

                QtWidgets.QMessageBox.critical(
                    self,
                    "Initialize Show Failed",
                    "An error occurred:\n\n{0}".format(exc),
                )

    global _GLOBAL_INIT_SHOW_WINDOW

    try:
        if _GLOBAL_INIT_SHOW_WINDOW is not None:
            _GLOBAL_INIT_SHOW_WINDOW.close()
            _GLOBAL_INIT_SHOW_WINDOW.deleteLater()
    except Exception:
        pass

    _GLOBAL_INIT_SHOW_WINDOW = InitializeShowWindow()
    _GLOBAL_INIT_SHOW_WINDOW.show()
    _GLOBAL_INIT_SHOW_WINDOW.raise_()
    _GLOBAL_INIT_SHOW_WINDOW.activateWindow()

    log("Launched {0} UI using {1}".format(WINDOW_TITLE, qt["binding_name"]))


# -----------------------------------------------------------------------------
# Entry
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    launch_ui()