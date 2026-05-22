import json
import mimetypes
import os
import re
import uuid
import urllib.parse
import urllib.request
import urllib.error

import unreal


@unreal.uclass()
class MRGSendClickUpPostRender(unreal.MovieGraphScriptBase):
    LOG_PREFIX = "[SendClickUpPostRender]"

    CLICKUP_DATA_FILE_NAME = "clickup_data.json"

    # New ClickUp layout:
    # Space: Nightfall
    # Folder: Nightfall Production / Nightfall Productions
    # List: MNF Shots
    # Task: MNF_000_0150
    DEFAULT_LIST_NAME = "MNF Shots"

    OUTPUT_DIRECTORY_VARIABLE_NAME = "OutputDirectory"
    FILE_NAME_VARIABLE_NAME = "FileNameFormat"
    MP4_FILE_NAME_VARIABLE_NAME = "MP4FileNameFormat"

    VIDEO_EXTENSIONS = {
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
    }

    IMAGE_EXTENSIONS = {
        ".exr",
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".tif",
        ".tiff",
    }

    # -------------------------------------------------------------------------
    # Unreal callback entry
    # -------------------------------------------------------------------------

    @unreal.ufunction(override=True)
    def on_job_finished(self, in_job_copy, in_output_data):
        super().on_job_finished(in_job_copy, in_output_data)
        self.run_post_render(in_job_copy, in_output_data)

    # -------------------------------------------------------------------------
    # Main flow
    # -------------------------------------------------------------------------

    def run_post_render(self, in_job_copy, in_output_data):
        self._log("on_job_finished")

        if not self._get_render_success(in_output_data):
            self._log_warning("Render was not successful. Skipping ClickUp post-render actions.")
            return False

        config = self._load_clickup_data()
        if not config:
            return False

        token = str(config.get("user_token", "")).strip()
        space_name = str(config.get("space_name", "")).strip()
        folder_name = str(config.get("folder_name", "")).strip()
        list_name = str(config.get("list_name", "") or self.DEFAULT_LIST_NAME).strip()
        supervisors = config.get("supervisors", [])

        if not token:
            self._log_error("clickup_data.json is missing user_token.")
            return False

        if not space_name:
            self._log_error("clickup_data.json is missing space_name.")
            return False

        if not folder_name:
            self._log_error("clickup_data.json is missing folder_name.")
            return False

        if not list_name:
            self._log_error("ClickUp list name is empty. Set list_name in clickup_data.json or use DEFAULT_LIST_NAME.")
            return False

        output_directory = self._resolve_job_variable_string(
            in_job_copy,
            self.OUTPUT_DIRECTORY_VARIABLE_NAME,
        )
        file_name_format = self._resolve_job_variable_string(
            in_job_copy,
            self.FILE_NAME_VARIABLE_NAME,
        )
        mp4_file_name_format = self._resolve_job_variable_string(
            in_job_copy,
            self.MP4_FILE_NAME_VARIABLE_NAME,
        )

        self._log(f"Resolved OutputDirectory: {output_directory!r}")
        self._log(f"Resolved FileNameFormat: {file_name_format!r}")
        self._log(f"Resolved MP4FileNameFormat: {mp4_file_name_format!r}")

        all_file_paths = self._collect_output_file_paths(in_output_data)
        video_files = self._filter_video_files(all_file_paths)
        image_files = self._filter_image_files(all_file_paths)

        self._log(f"Collected output file path count: {len(all_file_paths)}")
        self._log(f"Collected video file count: {len(video_files)}")
        self._log(f"Collected image file count: {len(image_files)}")

        shot_name = self._derive_shot_name(
            mp4_file_name_format=mp4_file_name_format,
            file_name_format=file_name_format,
            output_directory=output_directory,
            video_files=video_files,
        )

        if not shot_name:
            self._log_error("Could not derive shot_name from MRG variables or output files.")
            return False

        self._log(f"Resolved shot_name: {shot_name}")

        mp4_file_path = self._build_mp4_file_path(
            output_directory=output_directory,
            mp4_file_name_format=mp4_file_name_format,
            shot_name=shot_name,
            video_files=video_files,
        )

        if not mp4_file_path:
            self._log_error("Could not build MP4 file path from MRG variables or output files.")
            return False

        self._log(f"Resolved MP4 path: {mp4_file_path}")

        if not os.path.isfile(mp4_file_path):
            self._log_error(f"MP4 file does not exist: {mp4_file_path}")
            return False

        exr_location_path = self._build_exr_location_path(
            output_directory=output_directory,
            image_files=image_files,
        )
        self._log(f"Resolved EXR location path: {exr_location_path}")

        team_id = self._find_first_team_id(token)
        if not team_id:
            self._log_error("Could not resolve ClickUp team/workspace ID.")
            return False

        self._log(f"Resolved team_id: {team_id}")

        space_id = self._find_space_id_by_name(token, team_id, space_name)
        if not space_id:
            self._log_error(f"Could not find space by name: {space_name}")
            return False

        self._log(f"Resolved space_id: {space_id}")

        folder_id = self._find_folder_id_by_name_with_fallbacks(token, space_id, folder_name)
        if not folder_id:
            self._log_error(f"Could not find folder by name: {folder_name}")
            return False

        self._log(f"Resolved folder_id: {folder_id}")

        list_id = self._find_list_id_by_name(token, folder_id, list_name)
        if not list_id:
            self._log_error(f"Could not find ClickUp list by name: {list_name}")
            return False

        self._log(f"Resolved list_id: {list_id}")

        # New task naming convention:
        # Task is named exactly like the animated Level Sequence, for example:
        # MNF_000_0150
        task_name = shot_name

        task_id = self._find_task_id_by_name(token, list_id, task_name)
        if not task_id:
            self._log_error(f"Could not find task by name: {task_name}")
            return False

        self._log(f"Resolved task_id: {task_id}")

        attachment_ok = self._upload_attachment(
            api_token=token,
            task_id=task_id,
            file_path=mp4_file_path,
        )
        if not attachment_ok:
            self._log_error("Attachment upload failed.")
            return False

        comment_ok = self._post_render_complete_comment(
            api_token=token,
            task_id=task_id,
            shot_name=shot_name,
            supervisors=supervisors,
            exr_location_path=exr_location_path,
            mp4_file_path=mp4_file_path,
        )
        if not comment_ok:
            self._log_error("Render-complete comment failed.")
            return False

        self._log("ClickUp post-render actions completed successfully.")
        return True

    # -------------------------------------------------------------------------
    # Config
    # -------------------------------------------------------------------------

    def _get_clickup_data_file_path(self):
        module_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.normpath(os.path.join(module_dir, self.CLICKUP_DATA_FILE_NAME))

    def _load_clickup_data(self):
        path = self._get_clickup_data_file_path()
        self._log(f"clickup_data.json path: {path}")

        if not os.path.isfile(path):
            self._log_error(f"clickup_data.json does not exist: {path}")
            return None

        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self._log("Loaded clickup_data.json successfully.")
            return data
        except Exception as exc:
            self._log_error(f"Failed to read clickup_data.json: {exc}")
            return None

    # -------------------------------------------------------------------------
    # Render success
    # -------------------------------------------------------------------------

    def _get_render_success(self, in_output_data):
        try:
            return bool(in_output_data.success)
        except Exception:
            try:
                return bool(in_output_data.b_success)
            except Exception:
                return False

    # -------------------------------------------------------------------------
    # Shot name / mp4 path
    # -------------------------------------------------------------------------

    def _derive_shot_name(self, mp4_file_name_format, file_name_format, output_directory, video_files):
        candidates = [
            mp4_file_name_format,
            file_name_format,
            os.path.basename(str(output_directory or "").rstrip("/\\"))
        ]

        for video_file in video_files:
            candidates.append(os.path.basename(video_file))
            candidates.append(os.path.splitext(os.path.basename(video_file))[0])

        for candidate in candidates:
            shot_name = self._extract_shot_name(candidate)
            if shot_name:
                return shot_name

        return ""

    def _extract_shot_name(self, text):
        raw = str(text or "").strip()
        if not raw:
            return ""

        match = re.search(r"([A-Za-z0-9]+_\d{3}_\d{4,})", raw)
        if not match:
            return ""

        return match.group(1).upper()

    def _build_mp4_file_path(self, output_directory, mp4_file_name_format, shot_name, video_files):
        clean_output_directory = self._normalize_folder_path(output_directory)
        clean_mp4_file_name_format = str(mp4_file_name_format or "").strip()

        if clean_output_directory and clean_mp4_file_name_format:
            mp4_root = os.path.dirname(clean_output_directory)
            mp4_file_path = os.path.join(mp4_root, f"{clean_mp4_file_name_format}.mp4")
            normalized = os.path.normpath(mp4_file_path)
            if os.path.isfile(normalized):
                return normalized

        if video_files:
            shot_name_upper = str(shot_name or "").upper()
            prioritized = []
            fallback = []

            for video_file in video_files:
                name_upper = os.path.basename(video_file).upper()
                if shot_name_upper and shot_name_upper in name_upper:
                    prioritized.append(video_file)
                else:
                    fallback.append(video_file)

            ordered = prioritized + fallback
            if ordered:
                return ordered[0]

        if clean_output_directory and shot_name:
            mp4_root = os.path.dirname(clean_output_directory)
            candidates = self._find_mp4_candidates(mp4_root, shot_name)
            if candidates:
                return candidates[0]

        return ""

    def _find_mp4_candidates(self, folder_path, shot_name):
        if not os.path.isdir(folder_path):
            return []

        shot_name_upper = str(shot_name or "").upper()
        candidates = []

        try:
            for entry in os.scandir(folder_path):
                if not entry.is_file():
                    continue

                file_name = entry.name
                if not file_name.lower().endswith(".mp4"):
                    continue

                if shot_name_upper not in file_name.upper():
                    continue

                candidates.append(entry.path)
        except Exception as exc:
            self._log_warning(f"Failed scanning for MP4 candidates in '{folder_path}': {exc}")
            return []

        candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return [os.path.normpath(p) for p in candidates]

    def _build_exr_location_path(self, output_directory, image_files):
        clean_output_directory = self._normalize_folder_path(output_directory)
        if clean_output_directory:
            return os.path.normpath(clean_output_directory)

        if image_files:
            first_image = image_files[0]
            return os.path.normpath(os.path.dirname(first_image))

        return ""

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

            if hasattr(render_layer_data, "items"):
                for _identifier_data, output_info in render_layer_data.items():
                    self._collect_from_output_info(output_info, collected)
                return

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

    def _filter_video_files(self, all_file_paths):
        video_files = []

        for file_path in all_file_paths:
            if not file_path:
                continue

            normalized_path = os.path.normpath(str(file_path))
            ext = os.path.splitext(normalized_path)[1].lower()

            if ext not in self.VIDEO_EXTENSIONS:
                continue

            if not os.path.isfile(normalized_path):
                continue

            video_files.append(normalized_path)

        video_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return self._dedupe_paths(video_files)

    def _filter_image_files(self, all_file_paths):
        image_files = []

        for file_path in all_file_paths:
            if not file_path:
                continue

            normalized_path = os.path.normpath(str(file_path))
            ext = os.path.splitext(normalized_path)[1].lower()

            if ext not in self.IMAGE_EXTENSIONS:
                continue

            if not os.path.isfile(normalized_path):
                continue

            image_files.append(normalized_path)

        image_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return self._dedupe_paths(image_files)

    def _dedupe_paths(self, paths):
        deduped = []
        seen = set()

        for path in paths:
            norm = os.path.normpath(str(path))
            if norm not in seen:
                seen.add(norm)
                deduped.append(norm)

        return deduped

    # -------------------------------------------------------------------------
    # ClickUp hierarchy lookup
    # -------------------------------------------------------------------------

    def _find_first_team_id(self, api_token):
        data = self._request_json("https://api.clickup.com/api/v2/team", api_token)
        teams = data.get("teams", [])
        if not teams:
            return ""

        first_team_id = str(teams[0].get("id", "")).strip()
        return first_team_id

    def _find_space_id_by_name(self, api_token, team_id, target_name):
        url = f"https://api.clickup.com/api/v2/team/{team_id}/space"
        data = self._request_json(url, api_token)
        spaces = data.get("spaces", [])

        target = self._normalize_name(target_name)
        for space in spaces:
            name = str(space.get("name", "")).strip()
            space_id = str(space.get("id", "")).strip()
            self._log(f"Space Candidate: {name} | ID: {space_id}")
            if self._normalize_name(name) == target:
                return space_id

        return ""

    def _find_folder_id_by_name_with_fallbacks(self, api_token, space_id, target_name):
        target_text = str(target_name or "").strip()
        candidates = [target_text]

        # Gentle fallback for the singular/plural typo:
        # Nightfall Production vs Nightfall Productions.
        lower_target = target_text.lower()
        if lower_target.endswith(" production"):
            candidates.append(target_text + "s")
        elif lower_target.endswith(" productions"):
            candidates.append(target_text[:-1])

        seen = set()
        for candidate in candidates:
            normalized = self._normalize_name(candidate)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)

            folder_id = self._find_folder_id_by_name(api_token, space_id, candidate)
            if folder_id:
                return folder_id

        return ""

    def _find_folder_id_by_name(self, api_token, space_id, target_name):
        url = f"https://api.clickup.com/api/v2/space/{space_id}/folder"
        data = self._request_json(url, api_token)
        folders = data.get("folders", [])

        target = self._normalize_name(target_name)
        for folder in folders:
            name = str(folder.get("name", "")).strip()
            folder_id = str(folder.get("id", "")).strip()
            self._log(f"Folder Candidate: {name} | ID: {folder_id}")
            if self._normalize_name(name) == target:
                return folder_id

        return ""

    def _find_list_id_by_name(self, api_token, folder_id, target_name):
        url = f"https://api.clickup.com/api/v2/folder/{folder_id}/list"
        data = self._request_json(url, api_token)
        lists = data.get("lists", [])

        target = self._normalize_name(target_name)
        for item in lists:
            name = str(item.get("name", "")).strip()
            list_id = str(item.get("id", "")).strip()
            self._log(f"List Candidate: {name} | ID: {list_id}")
            if self._normalize_name(name) == target:
                return list_id

        return ""

    def _find_task_id_by_name(self, api_token, list_id, target_name):
        """
        Find the parent ClickUp task for a shot.

        New ClickUp structure:
            List: MNF Shots
            Parent task name: MNF_000_0150
            Subtasks: lite final, anim final, env final, fx final, etc.

        Important:
            We search parent tasks first with subtasks=false.
            The older version used subtasks=true, which could return child rows like
            "lite final" and miss the parent shot task.
        """
        clean_target_name = str(target_name or "").strip()
        if not clean_target_name:
            self._log_error("Cannot find task because target_name is empty.")
            return ""

        self._log(
            f"Searching for ClickUp parent task named exactly: {clean_target_name} "
            f"in list_id={list_id}"
        )

        # Primary search: parent tasks only.
        task_id = self._find_task_id_by_name_paginated(
            api_token=api_token,
            list_id=list_id,
            target_name=clean_target_name,
            include_subtasks=False,
        )
        if task_id:
            return task_id

        self._log_warning(
            f"Parent task not found with subtasks=false. "
            f"Trying fallback search with subtasks=true for: {clean_target_name}"
        )

        # Fallback: include subtasks just in case ClickUp behaves differently.
        # This should not usually be needed for the new MNF Shots layout.
        task_id = self._find_task_id_by_name_paginated(
            api_token=api_token,
            list_id=list_id,
            target_name=clean_target_name,
            include_subtasks=True,
        )
        if task_id:
            return task_id

        self._log_error(f"No ClickUp task matched target name: {clean_target_name}")
        return ""

    def _find_task_id_by_name_paginated(self, api_token, list_id, target_name, include_subtasks):
        target = self._normalize_name(target_name)

        page = 0
        max_pages = 25
        total_checked = 0

        while page < max_pages:
            query = urllib.parse.urlencode({
                "archived": "false",
                "subtasks": "true" if include_subtasks else "false",
                "page": str(page),
            })

            url = f"https://api.clickup.com/api/v2/list/{list_id}/task?{query}"
            self._log(
                f"Requesting ClickUp tasks page={page}, "
                f"subtasks={include_subtasks}"
            )

            data = self._request_json(url, api_token)
            tasks = data.get("tasks", [])

            self._log(
                f"Task page returned count={len(tasks)}, "
                f"page={page}, subtasks={include_subtasks}"
            )

            if not tasks:
                break

            for task in tasks:
                name = str(task.get("name", "")).strip()
                task_id = str(task.get("id", "")).strip()
                total_checked += 1

                self._log(f"Task Candidate: {name} | ID: {task_id}")

                if self._normalize_name(name) == target:
                    self._log(
                        f"Matched ClickUp task: {name} | ID: {task_id} | "
                        f"subtasks={include_subtasks} | page={page}"
                    )
                    return task_id

            try:
                if bool(data.get("last_page", False)):
                    self._log("ClickUp reported last_page=true.")
                    break
            except Exception:
                pass

            page += 1

        self._log_warning(
            f"No match found after checking {total_checked} task candidate(s). "
            f"target={target_name}, subtasks={include_subtasks}"
        )
        return ""

    # -------------------------------------------------------------------------
    # Attachment upload
    # -------------------------------------------------------------------------

    def _upload_attachment(self, api_token, task_id, file_path):
        clean_file_path = os.path.normpath(str(file_path or "").strip().strip("\"'"))
        if not os.path.isfile(clean_file_path):
            self._log_error(f"Attachment file does not exist: {clean_file_path}")
            return False

        upload_url = f"https://api.clickup.com/api/v2/task/{task_id}/attachment"
        body_bytes, content_type_header, file_name = self._build_multipart_body(clean_file_path)

        self._log(f"Uploading attachment: {file_name}")
        self._log(f"Attachment path: {clean_file_path}")

        request = urllib.request.Request(
            upload_url,
            data=body_bytes,
            headers={
                "Authorization": api_token,
                "Content-Type": content_type_header,
                "Content-Length": str(len(body_bytes)),
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                response_text = response.read().decode("utf-8")
                data = json.loads(response_text)

            self._log("Attachment uploaded successfully.")
            self._log(f"Attachment Response: {json.dumps(data, ensure_ascii=False)}")
            return True

        except urllib.error.HTTPError as exc:
            error_body = self._read_http_error_body(exc)
            self._log_error(f"Attachment HTTPError: {exc.code} {exc.reason}")
            self._log_error(f"Attachment Response Body: {error_body}")
            return False

        except urllib.error.URLError as exc:
            self._log_error(f"Attachment URLError: {exc}")
            return False

        except Exception as exc:
            self._log_error(f"Attachment unexpected error: {exc}")
            return False

    def _build_multipart_body(self, file_path, field_name="attachment"):
        boundary = f"----ClickUpBoundary{uuid.uuid4().hex}"
        file_name = os.path.basename(file_path)
        content_type = self._guess_content_type(file_path)

        with open(file_path, "rb") as handle:
            file_bytes = handle.read()

        parts = []
        boundary_bytes = boundary.encode("utf-8")

        parts.append(b"--" + boundary_bytes + b"\r\n")
        parts.append(
            (
                f'Content-Disposition: form-data; name="{field_name}"; filename="{file_name}"\r\n'
            ).encode("utf-8")
        )
        parts.append((f"Content-Type: {content_type}\r\n\r\n").encode("utf-8"))
        parts.append(file_bytes)
        parts.append(b"\r\n")
        parts.append(b"--" + boundary_bytes + b"--\r\n")

        body = b"".join(parts)
        content_type_header = f"multipart/form-data; boundary={boundary}"
        return body, content_type_header, file_name

    def _guess_content_type(self, file_path):
        guessed, _encoding = mimetypes.guess_type(file_path)
        if guessed:
            return guessed
        return "application/octet-stream"

    # -------------------------------------------------------------------------
    # Comment posting with real mentions
    # -------------------------------------------------------------------------

    def _post_render_complete_comment(self, api_token, task_id, shot_name, supervisors, exr_location_path, mp4_file_path):
        supervisor_user_ids = []
        for supervisor in supervisors:
            try:
                user_id = int(supervisor.get("user_id"))
                supervisor_user_ids.append(user_id)
            except Exception:
                continue

        if not supervisor_user_ids:
            self._log_error("No valid supervisor user_ids were found in clickup_data.json.")
            return False

        exr_location_display = self._shorten_path_from_defect(exr_location_path)
        mp4_location_display = self._shorten_path_from_defect(mp4_file_path)

        comment_text = (
            f"\n{shot_name} render is complete."
            f"\nEXR Location: {exr_location_display}"
            f"\nMP4 Location: {mp4_location_display}"
        )

        comment_blocks = []

        for index, user_id in enumerate(supervisor_user_ids):
            comment_blocks.append({
                "type": "tag",
                "user": {
                    "id": user_id
                }
            })
            if index < len(supervisor_user_ids) - 1:
                comment_blocks.append({"text": " "})

        comment_blocks.append({
            "text": comment_text
        })

        payload = {
            "comment": comment_blocks,
            "notify_all": False,
        }

        url = f"https://api.clickup.com/api/v2/task/{task_id}/comment"
        body_bytes = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=body_bytes,
            headers={
                "Authorization": api_token,
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_text = response.read().decode("utf-8")
                data = json.loads(response_text)

            self._log("Render-complete comment created successfully.")
            self._log(f"Comment EXR Location: {exr_location_display}")
            self._log(f"Comment MP4 Location: {mp4_location_display}")
            self._log(f"Comment Response: {json.dumps(data, ensure_ascii=False)}")
            return True

        except urllib.error.HTTPError as exc:
            error_body = self._read_http_error_body(exc)
            self._log_error(f"Comment HTTPError: {exc.code} {exc.reason}")
            self._log_error(f"Comment Response Body: {error_body}")
            return False

        except urllib.error.URLError as exc:
            self._log_error(f"Comment URLError: {exc}")
            return False

        except Exception as exc:
            self._log_error(f"Comment unexpected error: {exc}")
            return False

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _shorten_path_from_defect(self, path_value):
        normalized = os.path.normpath(str(path_value or "").strip().strip("\"'"))
        if not normalized:
            return ""

        backslash_path = normalized.replace("/", "\\")
        lowered = backslash_path.lower()
        marker = "\\defect\\"
        index = lowered.find(marker)
        if index >= 0:
            return backslash_path[index:]

        return backslash_path

    def _request_json(self, url, api_token):
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": api_token,
                "Content-Type": "application/json",
            },
            method="GET",
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            response_text = response.read().decode("utf-8")
            return json.loads(response_text)

    def _read_http_error_body(self, exc):
        try:
            return exc.read().decode("utf-8", errors="replace")
        except Exception:
            return "<could not read error body>"

    def _normalize_name(self, value):
        text = str(value or "").strip().lower()
        return " ".join(text.split())

    def _normalize_folder_path(self, folder_path):
        text = str(folder_path or "").strip().strip("\"'")
        if not text:
            return ""
        return os.path.normpath(text)

    # -------------------------------------------------------------------------
    # MRG variable lookup
    # -------------------------------------------------------------------------

    def _resolve_job_variable_string(self, in_job_copy, variable_name):
        try:
            value = self._find_variable_value_anywhere(in_job_copy, variable_name, max_depth=4)
            normalized = self._normalize_possible_variable_value(value)
            if normalized:
                return normalized
        except Exception as exc:
            self._log_warning(f"Variable lookup failed for '{variable_name}': {exc}")

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

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------

    def _log(self, message):
        unreal.log(f"{self.LOG_PREFIX} {message}")

    def _log_warning(self, message):
        unreal.log_warning(f"{self.LOG_PREFIX} Warning: {message}")

    def _log_error(self, message):
        unreal.log_error(f"{self.LOG_PREFIX} Error: {message}")
