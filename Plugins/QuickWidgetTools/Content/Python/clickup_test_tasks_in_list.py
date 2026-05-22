import json
import urllib.parse
import urllib.request
import urllib.error
import unreal


LOG_PREFIX = "[ClickUpTestTasksInList]"


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} {message}")


def run(api_token, list_id):
    token = str(api_token or "").strip()
    clean_list_id = str(list_id or "").strip()

    if not token:
        _log_error("API token was empty.")
        return []

    if not clean_list_id:
        _log_error("list_id was empty.")
        return []

    query = urllib.parse.urlencode({
        "archived": "false",
        "subtasks": "true",
    })
    url = f"https://api.clickup.com/api/v2/list/{clean_list_id}/task?{query}"

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": token,
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_text = response.read().decode("utf-8")
            data = json.loads(response_text)

        tasks = data.get("tasks", [])
        if not tasks:
            _log("No tasks were returned.")
            return []

        results = []

        for task in tasks:
            task_id = str(task.get("id", ""))
            task_name = str(task.get("name", ""))
            status_name = str(task.get("status", {}).get("status", ""))
            _log(f"Task: {task_name} | ID: {task_id} | Status: {status_name}")
            results.append({
                "id": task_id,
                "name": task_name,
                "status": status_name,
            })

        return results

    except urllib.error.HTTPError as exc:
        try:
            error_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = "<could not read error body>"
        _log_error(f"HTTPError: {exc.code} {exc.reason}")
        _log_error(f"Response body: {error_body}")
        return []

    except urllib.error.URLError as exc:
        _log_error(f"URLError: {exc}")
        return []

    except Exception as exc:
        _log_error(f"Unexpected error: {exc}")
        return []