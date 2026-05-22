import json
import urllib.request
import urllib.error
import unreal


LOG_PREFIX = "[ClickUpFindUserIdByName]"


def _log(message):
    unreal.log(f"{LOG_PREFIX} {message}")


def _log_warning(message):
    unreal.log_warning(f"{LOG_PREFIX} Warning: {message}")


def _log_error(message):
    unreal.log_error(f"{LOG_PREFIX} Error: {message}")


def _normalize_name(value):
    text = str(value or "").strip()
    lowered = text.lower()
    collapsed = " ".join(lowered.split())
    return collapsed


def _safe_member_name(member):
    profile = member.get("user", member)
    username = str(profile.get("username", "") or "").strip()
    email = str(profile.get("email", "") or "").strip()
    initials = str(profile.get("initials", "") or "").strip()

    if username:
        return username
    if email:
        return email
    if initials:
        return initials
    return ""


def _safe_member_id(member):
    profile = member.get("user", member)
    value = profile.get("id", "")
    return str(value).strip()


def _request_json(url, api_token):
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


def _get_task_members(api_token, task_id):
    url = f"https://api.clickup.com/api/v2/task/{task_id}/member"
    data = _request_json(url, api_token)
    members = data.get("members", [])

    _log(f"Task members returned: {len(members)}")
    for member in members:
        _log(
            f"Task Member: {_safe_member_name(member)} | ID: {_safe_member_id(member)}"
        )

    return members


def _get_list_members(api_token, list_id):
    url = f"https://api.clickup.com/api/v2/list/{list_id}/member"
    data = _request_json(url, api_token)
    members = data.get("members", [])

    _log(f"List members returned: {len(members)}")
    for member in members:
        _log(
            f"List Member: {_safe_member_name(member)} | ID: {_safe_member_id(member)}"
        )

    return members


def _find_match_in_members(members, target_name):
    clean_target = _normalize_name(target_name)
    if not clean_target:
        return ""

    # Pass 1: exact normalized match
    for member in members:
        member_name = _safe_member_name(member)
        if _normalize_name(member_name) == clean_target:
            return _safe_member_id(member)

    # Pass 2: substring match either direction
    for member in members:
        member_name = _safe_member_name(member)
        normalized_member_name = _normalize_name(member_name)

        if clean_target in normalized_member_name or normalized_member_name in clean_target:
            return _safe_member_id(member)

    return ""


def run(api_token, target_name, task_id="", list_id=""):
    token = str(api_token or "").strip()
    clean_target_name = str(target_name or "").strip()
    clean_task_id = str(task_id or "").strip()
    clean_list_id = str(list_id or "").strip()

    _log(f"Target Name: {clean_target_name!r}")
    _log(f"Task ID: {clean_task_id!r}")
    _log(f"List ID: {clean_list_id!r}")

    if not token:
        _log_error("API token was empty.")
        return ""

    if not clean_target_name:
        _log_error("target_name was empty.")
        return ""

    # Try task members first
    if clean_task_id:
        try:
            task_members = _get_task_members(token, clean_task_id)
            match_id = _find_match_in_members(task_members, clean_target_name)
            if match_id:
                _log(f"Matched in task members: {clean_target_name} -> {match_id}")
                return match_id
            _log_warning(f"No task member match found for: {clean_target_name}")
        except urllib.error.HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                error_body = "<could not read error body>"
            _log_error(f"Task member HTTPError: {exc.code} {exc.reason}")
            _log_error(f"Task member response body: {error_body}")
        except urllib.error.URLError as exc:
            _log_error(f"Task member URLError: {exc}")
        except Exception as exc:
            _log_error(f"Unexpected task member error: {exc}")

    # Then try list members
    if clean_list_id:
        try:
            list_members = _get_list_members(token, clean_list_id)
            match_id = _find_match_in_members(list_members, clean_target_name)
            if match_id:
                _log(f"Matched in list members: {clean_target_name} -> {match_id}")
                return match_id
            _log_warning(f"No list member match found for: {clean_target_name}")
        except urllib.error.HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                error_body = "<could not read error body>"
            _log_error(f"List member HTTPError: {exc.code} {exc.reason}")
            _log_error(f"List member response body: {error_body}")
        except urllib.error.URLError as exc:
            _log_error(f"List member URLError: {exc}")
        except Exception as exc:
            _log_error(f"Unexpected list member error: {exc}")

    _log_warning(f"No user ID found for target name: {clean_target_name}")
    return ""