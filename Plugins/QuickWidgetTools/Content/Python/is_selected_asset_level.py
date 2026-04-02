"""
Checks whether the Blueprint-passed selected asset array contains exactly one valid
level/map asset and returns True/False for Blueprint branching.
"""

import unreal


_LOG_PREFIX = "[IsSelectedAssetLevel]"


def _log(message):
    unreal.log(f"{_LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{_LOG_PREFIX} {message}")


def _safe_class_name(asset):
    if asset is None:
        return "None"

    try:
        asset_class = asset.get_class()
        if asset_class:
            return asset_class.get_name()
    except Exception:
        pass

    try:
        return type(asset).__name__
    except Exception:
        return "Unknown"


def _is_world_asset_object(asset):
    if asset is None:
        return False

    try:
        asset_class = asset.get_class()
        world_class = unreal.World.static_class()
        if asset_class and world_class:
            return bool(unreal.SystemLibrary.class_is_child_of(asset_class, world_class))
    except Exception:
        pass

    try:
        return isinstance(asset, unreal.World)
    except Exception:
        return False


def _is_world_asset_data(asset):
    if asset is None:
        return False

    asset_data = None
    try:
        if isinstance(asset, unreal.AssetData):
            asset_data = asset
    except Exception:
        asset_data = None

    if asset_data is None:
        return False

    try:
        world_class_path = unreal.World.static_class().get_class_path_name()
        asset_class_path = asset_data.asset_class_path
        if world_class_path and asset_class_path:
            if asset_class_path == world_class_path:
                return True
    except Exception:
        pass

    try:
        asset_class_name = str(asset_data.asset_class).strip()
        if asset_class_name == "World":
            return True
    except Exception:
        pass

    return False


def _is_world_asset(selected_asset):
    return _is_world_asset_object(selected_asset) or _is_world_asset_data(selected_asset)


def run(selected_assets):
    _log("run() started")

    result = False

    try:
        if selected_assets is None:
            _log("Selection is missing (selected_assets is None)")
            _log("Final return value: False")
            return False

        try:
            selection_count = len(selected_assets)
        except Exception:
            _log_error("Selection is not a sized collection")
            _log("Final return value: False")
            return False

        _log(f"Selection count: {selection_count}")

        if selection_count != 1:
            _log("Selection must contain exactly one asset")
            _log("Final return value: False")
            return False

        selected_asset = selected_assets[0]
        _log(f"Selected asset object: {selected_asset}")

        class_name = _safe_class_name(selected_asset)
        _log(f"Selected asset class name: {class_name}")

        is_world = _is_world_asset(selected_asset)
        _log(f"Recognized as World asset: {is_world}")

        result = bool(is_world)
    except Exception as exc:
        _log_error(f"Unexpected error: {exc}")
        result = False

    _log(f"Final return value: {result}")
    return result
