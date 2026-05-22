import json
import urllib.request
import urllib.error
import unreal


LOG_PREFIX = "[ClickUpTestCreateTaskComment]"


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} {message}")


def run(api_token, task_id, leading_text, mention_user_id, trailing_text=""):
    token = str(api_token or "").strip()
    clean_task_id = str(task_id or "").strip()
    clean_leading_text = str(leading_text or "")
    clean_mention_user_id = str(mention_user_id or "").strip()
    clean_trailing_text = str(trailing_text or "")

    if not token:
        _log_error("API token was empty.")
        return False

    if not clean_task_id:
        _log_error("task_id was empty.")
        return False

    if not clean_mention_user_id:
        _log_error("mention_user_id was empty.")
        return False

    url = f"https://api.clickup.com/api/v2/task/{clean_task_id}/comment"

    comment_blocks = []

    if clean_leading_text:
        comment_blocks.append({
            "text": clean_leading_text
        })

    comment_blocks.append({
        "type": "tag",
        "user": {
            "id": int(clean_mention_user_id)
        }
    })

    if clean_trailing_text:
        comment_blocks.append({
            "text": clean_trailing_text
        })

    payload = {
        "comment": comment_blocks,
        "notify_all": False,
    }

    body_bytes = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body_bytes,
        headers={
            "Authorization": token,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_text = response.read().decode("utf-8")
            data = json.loads(response_text)

        comment_id = str(data.get("id", ""))
        _log("Comment created successfully.")
        _log(f"Task ID: {clean_task_id}")
        _log(f"Comment ID: {comment_id}")
        _log(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
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