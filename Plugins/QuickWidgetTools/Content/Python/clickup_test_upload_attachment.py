import json
import mimetypes
import os
import uuid
import urllib.request
import urllib.error
import unreal


LOG_PREFIX = "[ClickUpTestUploadAttachment]"


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} {message}")


def _guess_content_type(file_path):
    guessed, _encoding = mimetypes.guess_type(file_path)
    if guessed:
        return guessed
    return "application/octet-stream"


def _build_multipart_body(file_path, field_name="attachment"):
    boundary = f"----ClickUpBoundary{uuid.uuid4().hex}"
    file_name = os.path.basename(file_path)
    content_type = _guess_content_type(file_path)

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


def _post_task_comment(api_token, task_id, comment_text):
    url = f"https://api.clickup.com/api/v2/task/{task_id}/comment"

    payload = {
        "comment_text": comment_text,
        "notify_all": False,
    }

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

    with urllib.request.urlopen(request, timeout=30) as response:
        response_text = response.read().decode("utf-8")
        return json.loads(response_text)


def run(api_token, task_id, file_path, shot_name):
    token = str(api_token or "").strip()
    clean_task_id = str(task_id or "").strip()
    clean_file_path = os.path.normpath(str(file_path or "").strip().strip("\"'"))
    clean_shot_name = str(shot_name or "").strip()

    if not token:
        _log_error("API token was empty.")
        return False

    if not clean_task_id:
        _log_error("task_id was empty.")
        return False

    if not clean_file_path:
        _log_error("file_path was empty.")
        return False

    if not clean_shot_name:
        _log_error("shot_name was empty.")
        return False

    if not os.path.isfile(clean_file_path):
        _log_error(f"File does not exist: {clean_file_path}")
        return False

    file_size = os.path.getsize(clean_file_path)
    _log(f"Task ID: {clean_task_id}")
    _log(f"File Path: {clean_file_path}")
    _log(f"File Size: {file_size} bytes")

    upload_url = f"https://api.clickup.com/api/v2/task/{clean_task_id}/attachment"

    try:
        body_bytes, content_type_header, file_name = _build_multipart_body(clean_file_path)

        _log(f"Multipart filename being sent: {file_name}")
        _log(f"Multipart content type: {content_type_header}")

        request = urllib.request.Request(
            upload_url,
            data=body_bytes,
            headers={
                "Authorization": token,
                "Content-Type": content_type_header,
                "Content-Length": str(len(body_bytes)),
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=120) as response:
            response_text = response.read().decode("utf-8")
            data = json.loads(response_text)

        _log("Attachment uploaded successfully.")
        _log(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")

        comment_text = (
            f"{clean_shot_name} Unreal Render Complete\n"
            f"@Lenny Gordon @Sam Goldwater @Stephanie Katritos"
        )

        _log("Posting follow-up task comment...")
        comment_response = _post_task_comment(token, clean_task_id, comment_text)
        _log(f"Comment created successfully: {json.dumps(comment_response, indent=2, ensure_ascii=False)}")

        return True

    except urllib.error.HTTPError as exc:
        try:
            error_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = "<could not read error body>"
        _log_error(f"HTTPError: {exc.code} {exc.reason}")
        _log_error(f"Response body: {error_body}")
        return False

    except urllib.error.URLError as exc:
        _log_error(f"URLError: {exc}")
        return False

    except Exception as exc:
        _log_error(f"Unexpected error: {exc}")
        return False