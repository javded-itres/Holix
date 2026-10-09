"""MikroLLM group directory: neighbors this agent can see and message."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


class MikroLLMError(RuntimeError):
    """The gateway refused or could not return the group directory."""


@dataclass
class MikroLLMLink:
    """Gateway that holds this agent's agt-… membership."""

    url: str
    token: str = ""
    token_file: str = ""

    def bearer(self) -> str:
        direct = (self.token or "").strip()
        if direct:
            return direct
        path = (self.token_file or "").strip()
        if not path:
            return ""
        file = Path(os.path.expanduser(path))
        if not file.is_file():
            return ""
        return file.read_text(encoding="utf-8", errors="replace").strip()


def parse_mikrollm(raw: Any) -> MikroLLMLink | None:
    """Build a link from the ``a2a.mikrollm`` mapping. Env fills empty fields."""
    data = raw if isinstance(raw, dict) else {}
    url = str(os.getenv("HOLIX_MIKROLLM_A2A_URL") or data.get("url") or "").strip().rstrip("/")
    token = str(os.getenv("HOLIX_MIKROLLM_A2A_TOKEN") or data.get("token") or "").strip()
    token_file = str(
        os.getenv("HOLIX_MIKROLLM_A2A_TOKEN_FILE") or data.get("token_file") or ""
    ).strip()
    if not url and not token and not token_file:
        return None
    return MikroLLMLink(url=url, token=token, token_file=token_file)


async def fetch_directory(link: MikroLLMLink) -> dict[str, Any]:
    """GET /a2a/directory. Returns the gateway JSON (self + agents)."""
    token = link.bearer()
    if not link.url or not token:
        raise MikroLLMError("MikroLLM URL or agent token is missing")
    url = link.url.rstrip("/") + "/a2a/directory"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        raise MikroLLMError(f"directory HTTP {resp.status_code}")
    data = resp.json()
    if not isinstance(data, dict):
        raise MikroLLMError("directory is not an object")
    return data


async def post_group_message(
    link: MikroLLMLink,
    *,
    group: str,
    to: str,
    text: str,
) -> dict[str, Any]:
    """POST /a2a/messages. The gateway stores the line and delivers it."""
    token = link.bearer()
    if not link.url or not token:
        raise MikroLLMError("MikroLLM URL or agent token is missing")
    url = link.url.rstrip("/") + "/a2a/messages"
    body = {"group": group, "to": to, "text": text}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
        )
    if resp.status_code not in (200, 201):
        raise MikroLLMError(f"message HTTP {resp.status_code}")
    data = resp.json()
    if not isinstance(data, dict):
        raise MikroLLMError("message response is not an object")
    return data


def neighbor_rows(directory: dict[str, Any]) -> list[dict[str, Any]]:
    """Public cards of other members. Self is not included."""
    rows: list[dict[str, Any]] = []
    for item in directory.get("agents") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        groups = item.get("groups") if isinstance(item.get("groups"), list) else []
        skills = item.get("skills") if isinstance(item.get("skills"), list) else []
        rows.append(
            {
                "name": name,
                "display_name": str(item.get("display_name") or ""),
                "company": str(item.get("company") or ""),
                "description": str(item.get("description") or ""),
                "skills": skills,
                "groups": [str(g) for g in groups if str(g).strip()],
                "source": "mikrollm",
            }
        )
    return rows
