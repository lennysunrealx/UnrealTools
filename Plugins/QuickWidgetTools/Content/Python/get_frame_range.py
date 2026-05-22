"""Get playback frame range for a master shot Level Sequence asset.

This module is intended for use from Unreal's Execute Python Script node and
returns a soft-failure tuple ("", "") when anything goes wrong.
"""

import unreal


_LOG_PREFIX = "[GetFrameRange]"


def _log(message):
    unreal.log(f"{_LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{_LOG_PREFIX} Error: {message}")


def _sanitize_show_name(show_name):
    value = str(show_name or "").strip().lstrip("_")
    return f"_{value}" if value else ""


def _sanitize_sequence_name(sequence_name):
    return str(sequence_name or "").strip().strip("/")


def _sanitize_shot_name(shot_name):
    return str(shot_name or "").strip()


def _build_asset_path(show_name, sequence_name, shot_name):
    return f"/Game/{show_name}/Sequences/{sequence_name}/{shot_name}.{shot_name}"


def _to_display_rate_frame(level_sequence, frame_number):
    display_rate = level_sequence.get_display_rate()
    tick_resolution = level_sequence.get_tick_resolution()

    # Convert tick-resolution frame number to display-rate frame number.
    converted = unreal.FrameRate.transform_time(
        source_time=unreal.FrameTime(frame_number),
        source_rate=tick_resolution,
        destination_rate=display_rate,
    )
    return int(converted.frame_number.value)


def run(show_name, sequence_name, shot_name):
    """Return (start_frame, end_frame) for the master shot Level Sequence.

    On failure this returns ("", "") and logs a clear error.
    """
    safe_show_name = _sanitize_show_name(show_name)
    safe_sequence_name = _sanitize_sequence_name(sequence_name)
    safe_shot_name = _sanitize_shot_name(shot_name)

    if not safe_show_name or not safe_sequence_name or not safe_shot_name:
        _log_error(
            "Invalid inputs. Expected non-empty show_name, sequence_name, and shot_name."
        )
        return "", ""

    asset_path = _build_asset_path(safe_show_name, safe_sequence_name, safe_shot_name)
    sequence_asset = unreal.EditorAssetLibrary.load_asset(asset_path)

    if not sequence_asset:
        _log_error(f"Sequence asset not found at: {asset_path}")
        return "", ""

    if not isinstance(sequence_asset, unreal.LevelSequence):
        _log_error(
            "Asset is not a LevelSequence at: "
            f"{asset_path} (type: {sequence_asset.get_class().get_name()})"
        )
        return "", ""

    playback_start = sequence_asset.get_playback_start()
    playback_end = sequence_asset.get_playback_end()

    start_frame = _to_display_rate_frame(sequence_asset, playback_start)
    end_frame = _to_display_rate_frame(sequence_asset, playback_end)

    _log(f"Found sequence: {asset_path}")
    _log(f"Start frame: {start_frame}")
    _log(f"End frame: {end_frame}")

    return start_frame, end_frame


if __name__ == "__main__":
    # Example usage for manual testing in Unreal's Python console.
    run("Marathon", "ABC", "ABC_000_0900")
