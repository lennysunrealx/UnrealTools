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


def _asset_data_from_anything(asset):
    if asset is None:
        _log("AssetData conversion skipped: selected asset is None")
        return None

    try:
        if isinstance(asset, unreal.AssetData):
            _log("AssetData conversion succeeded: selected item is already AssetData")
            return asset
    except Exception as exc:
        _log_error(f"AssetData isinstance check failed: {exc}")

    try:
        asset_data = unreal.AssetRegistryHelpers.create_asset_data(asset)
        if asset_data:
            _log("AssetData conversion succeeded via AssetRegistryHelpers.create_asset_data")
            return asset_data
    except Exception as exc:
        _log_error(f"AssetData conversion raised error: {exc}")

    _log("AssetData conversion failed")
    return None


def _is_world_asset_data(asset_data):
    if asset_data is None:
        _log("AssetData is None; cannot be an exact World asset")
        return False

    try:
        world_class_path = unreal.World.static_class().get_class_path_name()
    except Exception as exc:
        _log_error(f"Could not read World class path: {exc}")
        world_class_path = None

    asset_class_path = None
    try:
        asset_class_path = asset_data.asset_class_path
        _log(f"AssetData asset class path: {asset_class_path}")
    except Exception as exc:
        _log_error(f"Could not read AssetData asset_class_path: {exc}")

    if world_class_path is not None and asset_class_path is not None:
        if asset_class_path == world_class_path:
            _log("Exact World class-path match succeeded")
            return True
        _log("Exact asset class path did not match World")

    asset_class_name = None
    try:
        asset_class_name = str(asset_data.asset_class).strip()
        _log(f"AssetData asset class name: {asset_class_name}")
        if asset_class_name == "World":
            _log("Fallback exact asset class name match succeeded: World")
            return True
    except Exception as exc:
        _log_error(f"Could not read AssetData asset_class: {exc}")

    _log("Selected asset is not an exact World asset")

    return False


def _is_world_asset(selected_asset):
    # Strict validation intentionally uses exact asset-registry identity only.
    # Broad inheritance/object-instance checks (for example class_is_child_of or
    # isinstance) are intentionally avoided because they can allow non-map assets
    # such as Blueprints to pass in some editor contexts.
    asset_data = _asset_data_from_anything(selected_asset)
    return _is_world_asset_data(asset_data)


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
        _log(f"Exact World match succeeded: {is_world}")

        result = bool(is_world)
    except Exception as exc:
        _log_error(f"Unexpected error: {exc}")
        result = False

    _log(f"Final return value: {result}")
    return result
