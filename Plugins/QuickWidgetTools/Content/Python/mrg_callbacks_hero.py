import os
import re
import shutil
import unreal


@unreal.uclass()
class MRGHero(unreal.MovieGraphScriptBase):
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

        log_prefix = "[QuickWidgetToolsMRG_Hero]"

        success = self._get_render_success(in_output_data)
        if not success:
            unreal.log_warning(f"{log_prefix} Render was not successful. Skipping hero copy.")
            return

        all_file_paths = self._collect_output_file_paths(in_output_data)
        frame_files = self._filter_image_files(all_file_paths)
        if not frame_files:
            unreal.log_warning(f"{log_prefix} No rendered image sequence files found.")
            return

        frame_files = sorted(frame_files)

        render_output_folder = os.path.dirname(frame_files[0])
        parent_folder = os.path.dirname(render_output_folder)
        hero_folder = os.path.join(parent_folder, "_hero")

        unreal.log(f"{log_prefix} Render Output Folder: {render_output_folder}")
        unreal.log(f"{log_prefix} Parent Folder: {parent_folder}")
        unreal.log(f"{log_prefix} Hero Folder: {hero_folder}")

        if os.path.isdir(hero_folder):
            try:
                shutil.rmtree(hero_folder)
                unreal.log(f"{log_prefix} Deleted existing hero folder.")
            except Exception as exc:
                unreal.log_error(f"{log_prefix} Failed to delete existing hero folder: {exc}")
                return

        try:
            os.makedirs(hero_folder, exist_ok=True)
            unreal.log(f"{log_prefix} Created new hero folder.")
        except Exception as exc:
            unreal.log_error(f"{log_prefix} Failed to create hero folder: {exc}")
            return

        copied_count = 0
        for source_path in frame_files:
            try:
                file_name = os.path.basename(source_path)
                new_file_name = self._make_hero_filename(file_name)
                dest_path = os.path.join(hero_folder, new_file_name)
                shutil.copy2(source_path, dest_path)
                copied_count += 1
            except Exception as exc:
                unreal.log_warning(f"{log_prefix} Failed to copy file: {source_path} | {exc}")

        unreal.log("==================================================")
        unreal.log(f"{log_prefix} Hero Folder Updated: {hero_folder}")
        unreal.log(f"{log_prefix} Files Copied: {copied_count}")
        unreal.log("==================================================")

    def _get_render_success(self, in_output_data):
        try:
            return bool(in_output_data.success)
        except Exception:
            try:
                return bool(in_output_data.b_success)
            except Exception:
                return False

    def _collect_output_file_paths(self, in_output_data):
        collected = []

        try:
            graph_data = in_output_data.graph_data
            for render_output_data in graph_data:
                self._collect_from_render_output_data(render_output_data, collected)
        except Exception as exc:
            unreal.log_warning(f"[QuickWidgetToolsMRG_Hero] Failed while collecting from graph_data: {exc}")

        return self._dedupe_paths(collected)

    def _collect_from_render_output_data(self, render_output_data, collected):
        try:
            if not hasattr(render_output_data, "render_layer_data"):
                return

            render_layer_data = render_output_data.render_layer_data

            for identifier_data in render_layer_data:
                output_info = render_layer_data[identifier_data]
                self._collect_from_output_info(output_info, collected)
        except Exception as exc:
            unreal.log_warning(f"[QuickWidgetToolsMRG_Hero] Failed while collecting from render_output_data: {exc}")

    def _collect_from_output_info(self, output_info, collected):
        try:
            if hasattr(output_info, "file_paths"):
                for file_path in output_info.file_paths:
                    collected.append(str(file_path))
        except Exception as exc:
            unreal.log_warning(f"[QuickWidgetToolsMRG_Hero] Failed while collecting from output_info: {exc}")

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

        return self._dedupe_paths(frame_files)

    def _make_hero_filename(self, file_name):
        """
        Examples:
        - ABC_000_0050_beautyHDlinear_v001.1001.exr -> ABC_000_0050.1001.exr
        - ABC_000_0050_beauty_v017.1001.exr -> ABC_000_0050.1001.exr

        Goal:
        keep only the first three underscore-delimited shot tokens:
        [SEQ]_[SHOT_SHORT]_[SHOT_LONG].[frame].[ext]
        """
        stem, ext = os.path.splitext(file_name)

        match = re.match(r"^(.*)\.(\d+)$", stem)
        if not match:
            return file_name

        base_name = match.group(1)
        frame_number = match.group(2)

        tokens = base_name.split("_")
        if len(tokens) < 3:
            return file_name

        shot_name = "_".join(tokens[:3])
        return f"{shot_name}.{frame_number}{ext}"

    def _dedupe_paths(self, paths):
        deduped = []
        seen = set()

        for path in paths:
            norm = os.path.normpath(str(path))
            if norm not in seen:
                seen.add(norm)
                deduped.append(norm)

        return deduped
