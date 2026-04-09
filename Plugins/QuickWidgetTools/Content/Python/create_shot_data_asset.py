import re
import unreal


LOG_PREFIX = "[CreateShotDataAsset]"

# Update this path to your BP_ShotDataAsset Blueprint asset if needed.
# Expected format: /Game/Path/To/BP_ShotDataAsset.BP_ShotDataAsset
BP_SHOT_DATA_ASSET_BLUEPRINT_PATH = "/QuickWidgetTools/Misc/BP_ShotDataAsset.BP_ShotDataAsset"


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} {message}")


def _sanitize_show_name(value):
    if value is None:
        return ""
    return "".join(ch for ch in str(value) if ch.isalnum())


def _sanitize_sequence_or_shot_name(value):
    if value is None:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", str(value))
    return cleaned.upper()


def _resolve_data_asset_class():
    _log(f"Resolving Blueprint asset path: {BP_SHOT_DATA_ASSET_BLUEPRINT_PATH}")
    blueprint_asset = unreal.EditorAssetLibrary.load_asset(BP_SHOT_DATA_ASSET_BLUEPRINT_PATH)
    if not blueprint_asset:
        _log_error(
            "Failed to load BP_ShotDataAsset Blueprint asset from "
            f"'{BP_SHOT_DATA_ASSET_BLUEPRINT_PATH}'."
        )
        return None

    generated_class = None

    if hasattr(blueprint_asset, "generated_class"):
        generated_class_attr = blueprint_asset.generated_class
        if callable(generated_class_attr):
            generated_class = generated_class_attr()
        else:
            generated_class = generated_class_attr

    if not generated_class:
        generated_class_path = f"{BP_SHOT_DATA_ASSET_BLUEPRINT_PATH}_C"
        generated_class = unreal.load_object(None, generated_class_path)

    if not generated_class:
        _log_error(
            "Failed to resolve generated class for BP_ShotDataAsset from "
            f"'{BP_SHOT_DATA_ASSET_BLUEPRINT_PATH}'."
        )
        return None

    _log(f"Final resolved generated class: {generated_class}")
    return generated_class


def _set_active_and_save(asset_object, asset_path):
    if not asset_object:
        _log_error(f"Asset object is invalid: {asset_path}")
        return ""

    set_active_success = False
    try:
        asset_object.set_editor_property("IsActive", True)
        set_active_success = True
    except Exception as exc:
        _log_error(f"Failed to set IsActive=True on '{asset_path}': {exc}")

    _log(f"IsActive set success for '{asset_path}': {set_active_success}")
    if not set_active_success:
        return ""

    if not unreal.EditorAssetLibrary.save_loaded_asset(asset_object):
        _log_error(f"Failed to save asset: {asset_path}")
        return ""

    return asset_path


def run(ShotName, SequenceName, ShowName):
    """
    Create (or update) one shot data asset instance for the given shot folder.

    Args:
        ShotName (str): Shot identifier.
        SequenceName (str): Sequence identifier.
        ShowName (str): Show identifier.

    Returns:
        str: Final asset path on success, or "" on failure.
    """
    sanitized_show_name = _sanitize_show_name(ShowName)
    sanitized_sequence_name = _sanitize_sequence_or_shot_name(SequenceName)
    sanitized_shot_name = _sanitize_sequence_or_shot_name(ShotName)

    if not sanitized_show_name:
        _log_error("Sanitized ShowName is empty.")
        return ""

    if not sanitized_sequence_name:
        _log_error("Sanitized SequenceName is empty.")
        return ""

    if not sanitized_shot_name:
        _log_error("Sanitized ShotName is empty.")
        return ""

    target_folder = (
        f"/Game/_{sanitized_show_name}/Sequences/"
        f"{sanitized_sequence_name}/{sanitized_shot_name}"
    )
    asset_name = f"{sanitized_shot_name}_Data"
    asset_path = f"{target_folder}/{asset_name}"

    if not unreal.EditorAssetLibrary.does_directory_exist(target_folder):
        _log_error(f"Target shot folder does not exist: {target_folder}")
        return ""

    data_asset_class = _resolve_data_asset_class()
    if not data_asset_class:
        return ""

    existing_asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if existing_asset:
        _log(f"Asset already exists. Updating IsActive: {asset_path}")
        _log(f"Created/loaded asset object class: {existing_asset.get_class()}")
        return _set_active_and_save(existing_asset, asset_path)

    factory = unreal.DataAssetFactory()
    if hasattr(factory, "data_asset_class"):
        factory.set_editor_property("data_asset_class", data_asset_class)

    _log(f"Creating shot data asset: {asset_path}")
    created_asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        asset_name=asset_name,
        package_path=target_folder,
        asset_class=data_asset_class,
        factory=factory,
    )

    if not created_asset:
        _log_error(f"Failed to create shot data asset: {asset_path}")
        return ""

    _log(f"Created/loaded asset object class: {created_asset.get_class()}")
    loaded_asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    return _set_active_and_save(loaded_asset, asset_path)
