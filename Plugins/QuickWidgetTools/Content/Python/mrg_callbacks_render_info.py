import os
import unreal


@unreal.uclass()
class MRGRenderInfo(unreal.MovieGraphScriptBase):

    IMAGE_EXTENSIONS = {
        ".exr",
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".tif",
        ".tiff",
    }

    VIDEO_EXTENSIONS = {
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
    }

    LOG_PREFIX = "[QuickWidgetToolsMRG]"
    OUTPUT_DIRECTORY_VARIABLE_NAME = "OutputDirectory"
    MP4_FILE_NAME_VARIABLE_NAME = "MP4FileNameFormat"
    RENDER_LOG_FOLDER_NAME = "RenderLog"

    @unreal.ufunction(override=True)
    def on_job_finished(self, in_job_copy, in_output_data):
        super().on_job_finished(in_job_copy, in_output_data)

        all_file_paths = self._collect_output_file_paths(in_output_data)
        frame_files = self._filter_image_files(all_file_paths)

        if not frame_files:
            unreal.log_warning(f"{self.LOG_PREFIX} No rendered image sequence files found")
            return

        frame_records = self._build_frame_records(frame_files)

        if not frame_records:
            unreal.log_warning(f"{self.LOG_PREFIX} No valid frame timestamps found")
            return

        frame_records.sort(key=lambda item: item[1])

        first_frame_path, first_time = frame_records[0]
        last_frame_path, last_time = frame_records[-1]

        frame_count = len(frame_records)
        total_render_seconds = max(0.0, last_time - first_time)
        per_frame_seconds = total_render_seconds / max(frame_count - 1, 1)

        derived_render_output_folder = os.path.dirname(first_frame_path)

        output_directory_value = self._resolve_job_variable_string(
            in_job_copy,
            self.OUTPUT_DIRECTORY_VARIABLE_NAME,
        )
        render_output_folder = self._normalize_folder_path(output_directory_value)

        if not render_output_folder:
            render_output_folder = derived_render_output_folder
            unreal.log_warning(
                f"{self.LOG_PREFIX} Could not resolve '{self.OUTPUT_DIRECTORY_VARIABLE_NAME}' "
                f"from job. Falling back to derived output folder: {render_output_folder}"
            )
        else:
            unreal.log(f"{self.LOG_PREFIX} Resolved job variable OutputDirectory: {render_output_folder}")

        mp4_file_name_value = self._resolve_job_variable_string(
            in_job_copy,
            self.MP4_FILE_NAME_VARIABLE_NAME,
        )
        log_file_stem = self._sanitize_file_stem(mp4_file_name_value)

        if not log_file_stem:
            log_file_stem = self._derive_file_stem_from_video_outputs(all_file_paths)

        if not log_file_stem:
            log_file_stem = self._derive_file_stem_from_frame_path(first_frame_path)

        if not log_file_stem:
            log_file_stem = "RenderInfo"

        unreal.log(f"{self.LOG_PREFIX} Render log file stem: {log_file_stem}")

        summary_lines = [
            "==================================================",
            f"{self.LOG_PREFIX} Render Output Folder: {render_output_folder}",
            f"{self.LOG_PREFIX} Rendered Frame Count: {frame_count}",
            f"{self.LOG_PREFIX} Total Render Time: {total_render_seconds:.2f} sec",
            f"{self.LOG_PREFIX} Render Time Per Frame: {per_frame_seconds:.2f} sec",
            "==================================================",
        ]

        for line in summary_lines:
            unreal.log(line)

        self._write_summary_log(
            render_output_folder=render_output_folder,
            log_file_stem=log_file_stem,
            summary_lines=summary_lines,
        )

    def _collect_output_file_paths(self, in_output_data):
        collected = []

        try:
            graph_data = in_output_data.graph_data

            for render_output_data in graph_data:
                self._collect_from_render_output_data(render_output_data, collected)

        except Exception as exc:
            unreal.log_warning(
                f"{self.LOG_PREFIX} Failed while collecting from graph_data: {exc}"
            )

        return self._dedupe_paths(collected)

    def _collect_from_render_output_data(self, render_output_data, collected):
        try:
            if not hasattr(render_output_data, "render_layer_data"):
                return

            render_layer_data = render_output_data.render_layer_data

            if hasattr(render_layer_data, "items"):
                for identifier_data, output_info in render_layer_data.items():
                    self._collect_from_output_info(output_info, collected)

        except Exception as exc:
            unreal.log_warning(
                f"{self.LOG_PREFIX} Failed while collecting from render_output_data: {exc}"
            )

    def _collect_from_output_info(self, output_info, collected):
        try:
            if hasattr(output_info, "file_paths"):
                for file_path in output_info.file_paths:
                    collected.append(str(file_path))
        except Exception as exc:
            unreal.log_warning(
                f"{self.LOG_PREFIX} Failed while collecting from output_info: {exc}"
            )

    def _filter_image_files(self, all_file_paths):
        frame_files = []

        for file_path in all_file_paths:
            if not file_path:
                continue

            normalized_path = os.path.normpath(str(file_path))
            ext = os.path.splitext(normalized_path)[1].lower()

            if ext not in self.IMAGE_EXTENSIONS:
                continue

            if not os.path.isfile(normalized_path):
                continue

            frame_files.append(normalized_path)

        return self._dedupe_paths(sorted(frame_files))

    def _build_frame_records(self, frame_files):
        frame_records = []

        for frame_path in frame_files:
            try:
                modified_time = os.path.getmtime(frame_path)
                frame_records.append((frame_path, modified_time))
            except OSError as exc:
                unreal.log_warning(
                    f"{self.LOG_PREFIX} Could not read timestamp for: {frame_path} | {exc}"
                )

        return frame_records

    def _dedupe_paths(self, paths):
        deduped = []
        seen = set()

        for path in paths:
            norm = os.path.normpath(str(path))
            if norm not in seen:
                seen.add(norm)
                deduped.append(norm)

        return deduped

    def _normalize_folder_path(self, folder_path):
        text = str(folder_path or "").strip().strip("\"'")
        if not text:
            return ""

        normalized = os.path.normpath(text)
        return normalized

    def _sanitize_file_stem(self, value):
        raw = str(value or "").strip().strip("\"'")
        if not raw:
            return ""

        invalid_chars = '<>:"/\\|?*'
        cleaned = "".join("_" if ch in invalid_chars else ch for ch in raw).strip()
        cleaned = cleaned.rstrip(". ")

        return cleaned

    def _derive_file_stem_from_video_outputs(self, all_file_paths):
        for file_path in all_file_paths:
            if not file_path:
                continue

            normalized_path = os.path.normpath(str(file_path))
            ext = os.path.splitext(normalized_path)[1].lower()

            if ext not in self.VIDEO_EXTENSIONS:
                continue

            return os.path.splitext(os.path.basename(normalized_path))[0]

        return ""

    def _derive_file_stem_from_frame_path(self, frame_path):
        if not frame_path:
            return ""

        base_name = os.path.basename(str(frame_path))
        stem, _ext = os.path.splitext(base_name)

        if "." in stem:
            stem = stem.rsplit(".", 1)[0]

        return self._sanitize_file_stem(stem)

    def _write_summary_log(self, render_output_folder, log_file_stem, summary_lines):
        if not render_output_folder:
            unreal.log_warning(
                f"{self.LOG_PREFIX} Could not write render log because render_output_folder was empty."
            )
            return

        render_log_root = os.path.dirname(render_output_folder)
        render_log_folder = os.path.join(render_log_root, self.RENDER_LOG_FOLDER_NAME)
        log_file_path = os.path.join(render_log_folder, f"{log_file_stem}.txt")

        unreal.log(f"{self.LOG_PREFIX} Render log root: {render_log_root}")
        unreal.log(f"{self.LOG_PREFIX} RenderLog folder: {render_log_folder}")
        unreal.log(f"{self.LOG_PREFIX} RenderLog file: {log_file_path}")

        try:
            os.makedirs(render_log_folder, exist_ok=True)
            unreal.log(f"{self.LOG_PREFIX} Ensured RenderLog folder exists: {render_log_folder}")
        except Exception as exc:
            unreal.log_error(
                f"{self.LOG_PREFIX} Failed to create RenderLog folder '{render_log_folder}': {exc}"
            )
            return

        try:
            with open(log_file_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(summary_lines) + "\n")
            unreal.log(f"{self.LOG_PREFIX} Wrote render info log: {log_file_path}")
        except Exception as exc:
            unreal.log_error(
                f"{self.LOG_PREFIX} Failed to write render info log '{log_file_path}': {exc}"
            )

    def _resolve_job_variable_string(self, in_job_copy, variable_name):
        try:
            value = self._find_variable_value_anywhere(in_job_copy, variable_name, max_depth=4)
            normalized = self._normalize_possible_variable_value(value)
            if normalized:
                return normalized
        except Exception as exc:
            unreal.log_warning(
                f"{self.LOG_PREFIX} Variable lookup failed for '{variable_name}': {exc}"
            )

        return ""

    def _find_variable_value_anywhere(self, root_object, variable_name, max_depth=4):
        visited = set()
        return self._find_variable_value_recursive(
            current_object=root_object,
            variable_name=variable_name,
            visited=visited,
            depth=0,
            max_depth=max_depth,
        )

    def _find_variable_value_recursive(self, current_object, variable_name, visited, depth, max_depth):
        if current_object is None:
            return None

        if depth > max_depth:
            return None

        object_id = id(current_object)
        if object_id in visited:
            return None
        visited.add(object_id)

        direct_match = self._extract_variable_from_container(current_object, variable_name)
        if direct_match is not None:
            return direct_match

        next_objects = self._collect_child_objects(current_object)

        for child in next_objects:
            value = self._find_variable_value_recursive(
                current_object=child,
                variable_name=variable_name,
                visited=visited,
                depth=depth + 1,
                max_depth=max_depth,
            )
            if value is not None:
                return value

        return None

    def _collect_child_objects(self, obj):
        children = []

        attribute_names = [
            "graph_preset",
            "preset",
            "job",
            "job_copy",
            "graph_config",
            "configuration",
            "variable_assignments",
            "job_variable_assignments",
            "graph_variable_assignments",
            "variables",
        ]

        method_names = [
            "get_graph_preset",
            "get_preset",
            "get_configuration",
            "get_config",
            "get_variable_assignments",
            "get_job_variable_assignments",
            "get_graph_variable_assignments",
        ]

        for name in attribute_names:
            try:
                value = getattr(obj, name)
                children.append(value)
            except Exception:
                continue

        for name in method_names:
            try:
                method = getattr(obj, name, None)
                if callable(method):
                    children.append(method())
            except Exception:
                continue

        return children

    def _extract_variable_from_container(self, container, variable_name):
        normalized_target = str(variable_name or "").strip().lower()
        if not normalized_target:
            return None

        if hasattr(container, "items"):
            try:
                for key, value in container.items():
                    key_text = str(key).strip().lower()
                    if key_text == normalized_target:
                        return value
                    extracted = self._extract_assignment_value_if_named(key, value, normalized_target)
                    if extracted is not None:
                        return extracted
            except Exception:
                pass

        iterable = None
        if isinstance(container, (list, tuple, set)):
            iterable = container
        else:
            try:
                iter(container)
                iterable = container
            except Exception:
                iterable = None

        if iterable is not None and not isinstance(container, (str, bytes)):
            try:
                for item in iterable:
                    extracted = self._extract_assignment_value_if_named(item, None, normalized_target)
                    if extracted is not None:
                        return extracted
            except Exception:
                pass

        extracted = self._extract_assignment_value_if_named(container, None, normalized_target)
        if extracted is not None:
            return extracted

        return None

    def _extract_assignment_value_if_named(self, item, paired_value, normalized_target):
        candidate_names = []

        for attr_name in ("name", "variable_name", "member_name", "label"):
            try:
                value = getattr(item, attr_name)
                candidate_names.append(str(value))
            except Exception:
                pass

        for method_name in ("get_name", "get_member_name", "get_variable_name"):
            try:
                method = getattr(item, method_name, None)
                if callable(method):
                    candidate_names.append(str(method()))
            except Exception:
                pass

        for candidate_name in candidate_names:
            if candidate_name.strip().lower() != normalized_target:
                continue

            if paired_value is not None:
                return paired_value

            for attr_name in ("value", "string_value", "resolved_value"):
                try:
                    return getattr(item, attr_name)
                except Exception:
                    pass

            for method_name in ("get_value", "get_resolved_value", "get_value_string"):
                try:
                    method = getattr(item, method_name, None)
                    if callable(method):
                        return method()
                except Exception:
                    pass

        return None

    def _normalize_possible_variable_value(self, value):
        if value is None:
            return ""

        if isinstance(value, str):
            return value.strip()

        for method_name in ("to_string", "get_asset_path_name", "get_path_name"):
            try:
                method = getattr(value, method_name, None)
                if callable(method):
                    result = method()
                    if result is not None:
                        text = str(result).strip()
                        if text and text.lower() not in ("none", "null"):
                            return text
            except Exception:
                pass

        try:
            text = str(value).strip()
            if text and text.lower() not in ("none", "null"):
                return text
        except Exception:
            pass

        return ""