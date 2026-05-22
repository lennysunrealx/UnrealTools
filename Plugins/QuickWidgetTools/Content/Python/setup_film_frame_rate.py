# -*- coding: utf-8 -*-
"""Set default Level Sequence display rate to 24fps in DefaultEngine.ini."""

from __future__ import annotations

import os
from typing import List

try:
    import unreal
except Exception:  # Unreal module is only available in editor/runtime environments.
    unreal = None


LOG_PREFIX = "[SetupFilmFrameRate]"
SECTION_HEADER = "[/Script/LevelSequence.LevelSequenceProjectSettings]"
SETTING_KEY = "LevelSequence.DefaultDisplayRate"
SETTING_VALUE = "24fps"
SETTING_LINE = f"{SETTING_KEY}={SETTING_VALUE}"


def _log(message: str) -> None:
    text = f"{LOG_PREFIX} {message}"
    if unreal is not None:
        unreal.log(text)
    else:
        print(text)


def _project_root() -> str:
    if unreal is not None:
        try:
            project_file = unreal.Paths.get_project_file_path()
            if project_file:
                return os.path.dirname(os.path.abspath(project_file))
        except Exception:
            pass

        try:
            project_dir = unreal.Paths.project_dir()
            if project_dir:
                return os.path.abspath(project_dir)
        except Exception:
            pass

    cwd = os.getcwd()
    return os.path.abspath(cwd)


def _find_section_bounds(lines: List[str], header: str) -> tuple[int, int]:
    """Return (header_index, section_end_index_exclusive), or (-1, -1) if missing."""
    header_index = -1
    for idx, line in enumerate(lines):
        if line.strip() == header:
            header_index = idx
            break

    if header_index == -1:
        return -1, -1

    end_index = len(lines)
    for idx in range(header_index + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end_index = idx
            break

    return header_index, end_index


def run() -> str:
    """Ensure Level Sequence default display rate is set to 24fps.

    Returns:
        str: Full path to Config/DefaultEngine.ini on success, empty string on failure.
    """
    try:
        root = _project_root()
        ini_path = os.path.abspath(os.path.normpath(os.path.join(root, "Config", "DefaultEngine.ini")))
        _log(f"Target ini path: {ini_path}")

        os.makedirs(os.path.dirname(ini_path), exist_ok=True)

        if os.path.exists(ini_path):
            with open(ini_path, "r", encoding="utf-8", newline="") as f:
                lines = f.readlines()
        else:
            lines = []

        original_lines = list(lines)
        header_index, end_index = _find_section_bounds(lines, SECTION_HEADER)

        if header_index == -1:
            if lines and lines[-1] and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += "\n"
            if lines and lines[-1].strip() != "":
                lines.append("\n")
            lines.append(f"{SECTION_HEADER}\n")
            lines.append(f"{SETTING_LINE}\n")
            _log("Added LevelSequence project settings section and default display rate.")
        else:
            setting_indices = []
            for idx in range(header_index + 1, end_index):
                stripped = lines[idx].strip()
                if not stripped or stripped.startswith((";", "#")):
                    continue
                if stripped.startswith(SETTING_KEY + "="):
                    setting_indices.append(idx)

            if not setting_indices:
                insert_at = end_index
                lines.insert(insert_at, f"{SETTING_LINE}\n")
                _log("Added missing LevelSequence.DefaultDisplayRate setting.")
            else:
                first_idx = setting_indices[0]
                current = lines[first_idx].rstrip("\r\n")
                if current.strip() != SETTING_LINE:
                    line_ending = "\n"
                    if lines[first_idx].endswith("\r\n"):
                        line_ending = "\r\n"
                    lines[first_idx] = f"{SETTING_LINE}{line_ending}"
                    _log("Updated LevelSequence.DefaultDisplayRate to 24fps.")
                else:
                    _log("LevelSequence.DefaultDisplayRate already set to 24fps.")

                for dup_idx in reversed(setting_indices[1:]):
                    del lines[dup_idx]

        if lines != original_lines:
            with open(ini_path, "w", encoding="utf-8", newline="") as f:
                f.writelines(lines)
            _log("Saved DefaultEngine.ini changes.")
        else:
            _log("No changes needed.")

        return ini_path
    except Exception as exc:
        _log(f"Failed to update DefaultEngine.ini: {exc}")
        return ""
