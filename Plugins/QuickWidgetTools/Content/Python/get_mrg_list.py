"""
Utility for Blueprint Execute Python Script nodes to list Movie Render Graph assets.

Expected usage in Blueprint-driven Python:
    import get_mrg_list
    import importlib
    importlib.reload(get_mrg_list)
    mrg_names = get_mrg_list.run(folder_path)
"""

import unreal

_LOG_PREFIX = "[GetMRGList]"


def _log(message):
    unreal.log("{} {}".format(_LOG_PREFIX, message))


def _log_warning(message):
    unreal.log_warning("{} Warning: {}".format(_LOG_PREFIX, message))


def _log_error(message):
    unreal.log_error("{} Error: {}".format(_LOG_PREFIX, message))


def _sanitize_folder_path(folder_path):
    if not isinstance(folder_path, str):
        return ""

    normalized = folder_path.strip()
    if not normalized:
        return ""

    if not normalized.startswith("/"):
        normalized = "/{}".format(normalized)

    return normalized.rstrip("/") or "/"


def _asset_class_debug_string(asset_data):
    try:
        class_path = asset_data.asset_class_path

        asset_name = ""
        package_name = ""

        if hasattr(class_path, "asset_name"):
            asset_name = str(class_path.asset_name)

        if hasattr(class_path, "package_name"):
            package_name = str(class_path.package_name)

        return "asset_class={}, class_path_asset_name={}, class_path_package_name={}".format(
            str(getattr(asset_data, "asset_class", "")),
            asset_name,
            package_name,
        )
    except Exception as exc:
        return "class debug unavailable: {}".format(exc)


def _is_movie_render_graph_asset(asset_data):
    """
    Be generous in detection and log what we're seeing.
    """
    debug_text = _asset_class_debug_string(asset_data).lower()

    object_path = ""
    package_path = ""
    asset_name = ""

    try:
        object_path = str(asset_data.object_path).lower()
    except Exception:
        pass

    try:
        package_path = str(asset_data.package_path).lower()
    except Exception:
        pass

    try:
        asset_name = str(asset_data.asset_name).lower()
    except Exception:
        pass

    haystack = " | ".join([debug_text, object_path, package_path, asset_name])

    tokens = [
        "movierendergraph",
        "moviegraphconfig",
        "movie render graph",
        "mrg",
    ]

    return any(token in haystack for token in tokens)


def run(folder_path):
    """Return sorted Movie Render Graph asset names from a mounted content folder."""
    try:
        _log("Raw folder_path input: {}".format(repr(folder_path)))

        content_path = _sanitize_folder_path(folder_path)
        _log("Sanitized content path: {}".format(content_path))

        if not content_path:
            _log_error("Invalid folder_path input: {}".format(repr(folder_path)))
            return []

        directory_exists = unreal.EditorAssetLibrary.does_directory_exist(content_path)
        _log("does_directory_exist({}) -> {}".format(content_path, directory_exists))

        if not directory_exists:
            _log_warning("Folder does not exist in mounted content: {}".format(content_path))
            return []

        asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()
        assets = asset_registry.get_assets_by_path(unreal.Name(content_path), recursive=True)

        _log("Asset Registry returned {} asset(s) under {}".format(len(assets), content_path))

        if not assets:
            _log_warning("No assets found at all in that folder.")
            return []

        _log("Listing discovered assets for debugging:")
        for asset_data in assets:
            try:
                _log(
                    "  asset_name='{}' package_path='{}' object_path='{}' {}".format(
                        str(asset_data.asset_name),
                        str(asset_data.package_path),
                        str(asset_data.object_path),
                        _asset_class_debug_string(asset_data),
                    )
                )
            except Exception as exc:
                _log_warning("  Failed to inspect one asset: {}".format(exc))

        mrg_names = []
        for asset_data in assets:
            if _is_movie_render_graph_asset(asset_data):
                mrg_name = str(asset_data.asset_name)
                _log("Accepted as Movie Render Graph asset: {}".format(mrg_name))
                mrg_names.append(mrg_name)
            else:
                _log("Rejected asset: {}".format(str(asset_data.asset_name)))

        mrg_names = sorted(list(set(mrg_names)))
        _log("Found {} Movie Render Graph asset(s) in {}".format(len(mrg_names), content_path))
        _log("Final returned names: {}".format(mrg_names))
        return mrg_names

    except Exception as exc:
        _log_error("Failed to collect Movie Render Graph assets: {}".format(exc))
        return []