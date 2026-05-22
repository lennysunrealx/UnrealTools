import json
import urllib.request
import urllib.error
import unreal


LOG_PREFIX = "[ClickUpTestTeams]"


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} {message}")


def run(api_token):
    token = str(api_token or "").strip()

    if not token:
        _log_error("API token was empty.")
        return []

    url = "https://api.clickup.com/api/v2/team"
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

        teams = data.get("teams", [])
        if not teams:
            _log("No teams/workspaces were returned.")
            return []

        results = []

        for team in teams:
            team_id = str(team.get("id", ""))
            team_name = str(team.get("name", ""))
            _log(f"Team: {team_name} | ID: {team_id}")
            results.append({
                "id": team_id,
                "name": team_name,
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