from __future__ import annotations

import os
from typing import Any

import requests


class GithubAlertError(RuntimeError):
    pass


ALERT_TITLE = "inreach-bot automation health"


def post_or_update_alert(message: str) -> None:
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPOSITORY")
    if not token or not repo:
        return

    owner, name = repo.split("/", 1)
    base = f"https://api.github.com/repos/{owner}/{name}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    issue_number = _find_open_alert_issue(base, headers)
    body = f"Automation alert:\n\n{message}"
    if issue_number:
        requests.post(f"{base}/issues/{issue_number}/comments", headers=headers, json={"body": body}, timeout=30)
        return

    payload: dict[str, Any] = {
        "title": ALERT_TITLE,
        "body": body,
        "labels": ["automation-alert"],
    }
    resp = requests.post(f"{base}/issues", headers=headers, json=payload, timeout=30)
    if resp.status_code >= 300:
        raise GithubAlertError(f"Failed to create alert issue: {resp.status_code} {resp.text}")


def _find_open_alert_issue(base: str, headers: dict[str, str]) -> int | None:
    params = {"state": "open", "per_page": 100}
    resp = requests.get(f"{base}/issues", headers=headers, params=params, timeout=30)
    if resp.status_code >= 300:
        return None
    for issue in resp.json():
        if issue.get("pull_request"):
            continue
        if issue.get("title") == ALERT_TITLE:
            return int(issue["number"])
    return None