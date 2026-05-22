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

    HERO_FOLDER_NAME = "_hero"
    LOG_PREFIX = "[QuickWidgetToolsMRG_Hero]"

    @unreal.ufunction(override=True)
    def on_job_finished(self, in_job_copy, in_output_data):
        super().on_job_finished(in_job_copy, in_output_data)

        success = self._get_render_success(in_output_data)
        if not success:
            self._log_warning("Render was not successful. Skipping hero copy.")
            return

        all_file_paths = self._collect_output_file_paths(in_output_data)
        frame_files = self._filter_image_files(all_file_paths)

        if not frame_files:
            self._log_warning("No rendered image sequence files found.")
            return

        frame_files = sorted(frame_files)

        render_output_folder = os.path.dirname(frame_files[0])
        parent_folder = os.path.dirname(render_output_folder)
        hero_folder = os.path.join(parent_folder, self.HERO_FOLDER_NAME)

        if os.path.isdir(hero_folder):
            if not self._clear_directory_contents(hero_folder):
                self._log_error(f"Failed to clear existing hero folder contents: {hero_folder}")
                return
        else:
            try:
                os.makedirs(hero_folder, exist_ok=True)
            except Exception as exc:
                self._log_error(f"Failed to create hero folder '{hero_folder}': {exc}")
                return

        copied_count = 0
        failed_count = 0

        for source_path in frame_files:
            try:
                if not os.path.isfile(source_path):
                    failed_count += 1
                    self._log_warning(f"Source file missing at copy time: {source_path}")
                    continue

                file_name = os.path.basename(source_path)
                new_file_name = self._make_hero_filename(file_name)
                dest_path = os.path.join(hero_folder, new_file_name)

                shutil.copy2(source_path, dest_path)
                copied_count += 1

            except Exception as exc:
                failed_count += 1
                self._log_warning(f"Failed to copy file '{source_path}': {exc}")

        if copied_count == 0:
            self._log_error("Zero files copied into _hero folder.")
            return

        self._log("==================================================")
        self._log(f"Source Folder: {render_output_folder}")
        self._log(f"Hero Folder: {hero_folder}")
        self._log(f"Copied Count: {copied_count}")
        self._log(f"Failed Count: {failed_count}")
        self._log("==================================================")

    def _clear_directory_contents(self, folder_path):
        if not os.path.isdir(folder_path):
            return False

        try:
            entries = list(os.scandir(folder_path))
        except Exception as exc:
            self._log_error(f"Failed to scan folder before clear '{folder_path}': {exc}")
            return False

        for entry in entries:
            entry_path = entry.path
            try:
                if entry.is_dir(follow_symlinks=False):
                    shutil.rmtree(entry_path)
                else:
                    os.remove(entry_path)
            except Exception as exc:
                self._log_error(f"Failed deleting hero entry '{entry_path}': {exc}")
                return False

        return True

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
        except Exception as exc:
            self._log_warning(f"Failed while reading graph_data: {exc}")
            return collected

        try:
            for render_output_data in graph_data:
                self._collect_from_render_output_data(render_output_data, collected)
        except Exception as exc:
            self._log_warning(f"Failed while collecting from graph_data: {exc}")

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
            self._log_warning(f"Failed while collecting from render_output_data: {exc}")

    def _collect_from_output_info(self, output_info, collected):
        try:
            if hasattr(output_info, "file_paths"):
                for file_path in output_info.file_paths:
                    collected.append(str(file_path))
        except Exception as exc:
            self._log_warning(f"Failed while collecting from output_info: {exc}")

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

    def _log(self, message):
        unreal.log(f"{self.LOG_PREFIX} {message}")

    def _log_warning(self, message):
        unreal.log_warning(f"{self.LOG_PREFIX} Warning: {message}")

    def _log_error(self, message):
        unreal.log_error(f"{self.LOG_PREFIX} Error: {message}")