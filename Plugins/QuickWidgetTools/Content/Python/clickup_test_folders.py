import json
import urllib.request
import urllib.error
import unreal


LOG_PREFIX = "[ClickUpTestFolders]"


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} {message}")


def run(api_token, space_id):
    token = str(api_token or "").strip()
    clean_space_id = str(space_id or "").strip()

    if not token:
        _log_error("API token was empty.")
        return []

    if not clean_space_id:
        _log_error("space_id was empty.")
        return []

    url = f"https://api.clickup.com/api/v2/space/{clean_space_id}/folder"
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

        folders = data.get("folders", [])
        if not folders:
            _log("No folders were returned.")
            return []

        results = []

        for folder in folders:
            folder_id = str(folder.get("id", ""))
            folder_name = str(folder.get("name", ""))
            _log(f"Folder: {folder_name} | ID: {folder_id}")
            results.append({
                "id": folder_id,
                "name": folder_name,
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