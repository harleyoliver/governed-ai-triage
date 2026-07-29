"""
JIRA Cloud client for governed-ai-triage.

Two modes, controlled by `mock`:
- mock=True  -> reads data/jira_mock/tickets.json for fetch(), and
                writes to data/jira_mock/write_log.jsonl instead
                of calling the API. No network or API credentials needed.
- mock=False -> JIRA Cloud REST API v3 calls using Basic Auth
                (email + API token), stdlib urllib only.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MOCK_TICKETS_PATH = Path("data/jira_mock/tickets.json")
MOCK_WRITE_LOG_PATH = Path("data/jira_mock/write_log.jsonl")


@dataclass
class JiraTicket:
    key: str
    summary: str
    description: str
    reporter_name: str
    reporter_email: str
    priority: str
    status: str
    created: str

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "JiraTicket":
        f = raw["fields"]
        return cls(
            key=raw["key"],
            summary=f.get("summary", ""),
            description=f.get("description", "") or "",
            reporter_name=(f.get("reporter") or {}).get("displayName", "Unknown"),
            reporter_email=(f.get("reporter") or {}).get("emailAddress", ""),
            priority=(f.get("priority") or {}).get("name", "Unknown"),
            status=(f.get("status") or {}).get("name", "Unknown"),
            created=f.get("created", ""),
        )

    def to_ticket_dict(self) -> dict[str, Any]:
        """Shape this into the same ticket dict format in src/pipeline.py"""
        return {
            "id": self.key,
            "source": "jira",
            "subject": self.summary,
            "body": f"Reporter: {self.reporter_name} <{self.reporter_email}>\n\n{self.description}",
            "reported_priority": self.priority,
            "status": self.status,
            "created": self.created,
        }


class JiraClientError(RuntimeError):
    pass


class JiraClient:
    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        mock: bool = True,
    ):
        self.mock = mock
        self.base_url = (base_url or os.environ.get("JIRA_BASE_URL", "")).rstrip("/")
        self.email = email or os.environ.get("JIRA_EMAIL", "")
        self.api_token = api_token or os.environ.get("JIRA_API_TOKEN", "")

        if not self.mock and not (self.base_url and self.email and self.api_token):
            raise JiraClientError(
                "Live mode requires JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN "
                "(set in .env, or pass --mock to run without them)."
            )

    # ---------- fetch ----------

    def fetch_tickets(self, jql: str, max_results: int = 15) -> list[JiraTicket]:
        if self.mock:
            return self._fetch_mock()
        return self._fetch_live(jql, max_results)

    def _fetch_mock(self) -> list[JiraTicket]:
        if not MOCK_TICKETS_PATH.exists():
            raise JiraClientError(f"Mock fixture not found: {MOCK_TICKETS_PATH}")
        raw = json.loads(MOCK_TICKETS_PATH.read_text())
        return [JiraTicket.from_api(t) for t in raw]

    def _fetch_live(self, jql: str, max_results: int) -> list[JiraTicket]:
        params = urllib.parse.urlencode({"jql": jql, "maxResults": max_results})
        url = f"{self.base_url}/rest/api/3/search?{params}"
        resp = self._request(url, method="GET")
        return [JiraTicket.from_api(issue) for issue in resp.get("issues", [])]

    # ---------- write-back ----------

    def add_comment(self, issue_key: str, text: str) -> None:
        body = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": text}]}
                ],
            }
        }
        if self.mock:
            self._log_mock_write("add_comment", issue_key, {"text": text})
            return
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/comment"
        self._request(url, method="POST", body=body)

    def add_label(self, issue_key: str, label: str) -> None:
        body = {"update": {"labels": [{"add": label}]}}
        if self.mock:
            self._log_mock_write("add_label", issue_key, {"label": label})
            return
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"
        self._request(url, method="PUT", body=body)

    def transition_issue(self, issue_key: str, transition_name: str) -> None:
        if self.mock:
            self._log_mock_write("transition", issue_key, {"transition": transition_name})
            return
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions"
        transitions = self._request(url, method="GET").get("transitions", [])
        match = next(
            (t for t in transitions if t["name"].lower() == transition_name.lower()),
            None,
        )
        if not match:
            raise JiraClientError(
                f"No transition named '{transition_name}' available for {issue_key}"
            )
        self._request(url, method="POST", body={"transition": {"id": match["id"]}})

    # ---------- internals ----------

    def _log_mock_write(self, action: str, issue_key: str, payload: dict) -> None:
        MOCK_WRITE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"action": action, "issue_key": issue_key, **payload}
        with MOCK_WRITE_LOG_PATH.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def _request(self, url: str, method: str, body: dict | None = None) -> dict:
        auth = base64.b64encode(f"{self.email}:{self.api_token}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raise JiraClientError(f"JIRA API error {e.code} on {method} {url}: {e.read()}") from e
        except urllib.error.URLError as e:
            raise JiraClientError(f"JIRA API unreachable: {e}") from e