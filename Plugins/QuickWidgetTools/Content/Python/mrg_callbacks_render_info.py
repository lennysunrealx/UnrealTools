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

    @unreal.ufunction(override=True)
    def on_job_finished(self, in_job_copy, in_output_data):
        super().on_job_finished(in_job_copy, in_output_data)

        log_prefix = "[QuickWidgetToolsMRG]"

        all_file_paths = self._collect_output_file_paths(in_output_data)
        frame_files = self._filter_image_files(all_file_paths)

        if not frame_files:
            unreal.log_warning(f"{log_prefix} No rendered image sequence files found")
            return

        frame_records = self._build_frame_records(frame_files)

        if not frame_records:
            unreal.log_warning(f"{log_prefix} No valid frame timestamps found")
            return

        frame_records.sort(key=lambda item: item[1])

        first_frame_path, first_time = frame_records[0]
        last_frame_path, last_time = frame_records[-1]

        frame_count = len(frame_records)
        total_render_seconds = max(0.0, last_time - first_time)

        # Suggested formula:
        # (last - first) / (frames - 1)
        per_frame_seconds = (
            total_render_seconds / max(frame_count - 1, 1)
        )

        render_output_folder = os.path.dirname(first_frame_path)

        unreal.log("==================================================")
        unreal.log(f"{log_prefix} Render Output Folder: {render_output_folder}")
        unreal.log(f"{log_prefix} Rendered Frame Count: {frame_count}")
        unreal.log(f"{log_prefix} Total Render Time: {total_render_seconds:.2f} sec")
        unreal.log(f"{log_prefix} Render Time Per Frame: {per_frame_seconds:.2f} sec")
        unreal.log("==================================================")

    def _collect_output_file_paths(self, in_output_data):
        collected = []

        try:
            graph_data = in_output_data.graph_data

            for render_output_data in graph_data:
                self._collect_from_render_output_data(render_output_data, collected)

        except Exception as exc:
            unreal.log_warning(f"[QuickWidgetToolsMRG] Failed while collecting from graph_data: {exc}")

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
            unreal.log_warning(f"[QuickWidgetToolsMRG] Failed while collecting from render_output_data: {exc}")

    def _collect_from_output_info(self, output_info, collected):
        try:
            if hasattr(output_info, "file_paths"):
                for file_path in output_info.file_paths:
                    collected.append(str(file_path))
        except Exception as exc:
            unreal.log_warning(f"[QuickWidgetToolsMRG] Failed while collecting from output_info: {exc}")

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
                    f"[QuickWidgetToolsMRG] Could not read timestamp for: {frame_path} | {exc}"
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