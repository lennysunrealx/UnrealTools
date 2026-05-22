import json
import urllib.request
import urllib.error
import unreal


LOG_PREFIX = "[ClickUpTestAuth]"


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} {message}")


def run(api_token):
    token = str(api_token or "").strip()

    if not token:
        _log_error("API token was empty.")
        return False

    url = "https://api.clickup.com/api/v2/user"
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

        user_data = data.get("user", {})
        username = user_data.get("username", "")
        email = user_data.get("email", "")

        _log(f"Auth succeeded.")
        _log(f"Username: {username}")
        _log(f"Email: {email}")
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