import json
import urllib.request
import urllib.error
import unreal


LOG_PREFIX = "[ClickUpTestLists]"


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} {message}")


def run(api_token, folder_id):
    token = str(api_token or "").strip()
    clean_folder_id = str(folder_id or "").strip()

    if not token:
        _log_error("API token was empty.")
        return []

    if not clean_folder_id:
        _log_error("folder_id was empty.")
        return []

    url = f"https://api.clickup.com/api/v2/folder/{clean_folder_id}/list"
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

        lists = data.get("lists", [])
        if not lists:
            _log("No lists were returned.")
            return []

        results = []

        for item in lists:
            list_id = str(item.get("id", ""))
            list_name = str(item.get("name", ""))
            _log(f"List: {list_name} | ID: {list_id}")
            results.append({
                "id": list_id,
                "name": list_name,
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