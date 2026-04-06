"""Utility for Blueprint Execute Python Script nodes to list Movie Render Graph assets.

Expected usage in Blueprint-driven Python:
    import get_mrg_list
    import importlib
    importlib.reload(get_mrg_list)
    mrg_names = get_mrg_list.run(folder_path)
"""

import unreal

_LOG_PREFIX = "[GetMRGList]"
_MRG_CLASS_TOKENS = {"MovieRenderGraphConfig", "MovieRenderGraph"}


def _log(message):
    unreal.log("{} {}".format(_LOG_PREFIX, message))


def _log_error(message):
    unreal.log_error("{} {}".format(_LOG_PREFIX, message))


def _sanitize_folder_path(folder_path):
    if not isinstance(folder_path, str):
        return ""

    normalized = folder_path.strip()
    if not normalized:
        return ""

    if not normalized.startswith("/"):
        normalized = "/{}".format(normalized)

    return normalized.rstrip("/") or "/"


def _class_path_name(asset_data):
    class_path = asset_data.asset_class_path

    if hasattr(class_path, "asset_name"):
        return str(class_path.asset_name)

    return str(class_path)


def _is_movie_render_graph_asset(asset_data):
    class_name = _class_path_name(asset_data)

    if class_name in _MRG_CLASS_TOKENS:
        return True

    lowered = class_name.lower()
    return "movierendergraph" in lowered


def run(folder_path):
    """Return sorted Movie Render Graph asset names from a mounted content folder."""
    try:
        content_path = _sanitize_folder_path(folder_path)
        if not content_path:
            _log_error("Invalid folder_path input: {}".format(repr(folder_path)))
            return []

        if not unreal.EditorAssetLibrary.does_directory_exist(content_path):
            _log("Folder does not exist: {}".format(content_path))
            return []

        asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()
        assets = asset_registry.get_assets_by_path(unreal.Name(content_path), recursive=True)

        mrg_names = []
        for asset_data in assets:
            if _is_movie_render_graph_asset(asset_data):
                mrg_names.append(str(asset_data.asset_name))

        mrg_names.sort()
        _log("Found {} Movie Render Graph asset(s) in {}".format(len(mrg_names), content_path))
        return mrg_names

    except Exception as exc:
        _log_error("Failed to collect Movie Render Graph assets: {}".format(exc))
        return []
