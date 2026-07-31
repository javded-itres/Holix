"""HTTP client for remote A2A agents."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

import httpx

from core.a2a.models import A2AMessage, new_id

logger = logging.getLogger(__name__)


class A2AClientError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class A2AClient:
    """Discover Agent Cards and send messages to remote A2A servers."""

    def __init__(
        self,
        base_url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout_s: float = 300.0,
    ) -> None:
        self.base_url = (base_url or "").strip().rstrip("/")
        if not self.base_url:
            raise A2AClientError("base_url is required")
        self.headers = dict(headers or {})
        self.timeout_s = max(5.0, float(timeout_s or 300))

    def _rpc_url(self) -> str:
        # Prefer base itself as JSON-RPC endpoint; card may refine
        return self.base_url

    async def fetch_agent_card(self) -> dict[str, Any]:
        candidates = [
            urljoin(self.base_url + "/", ".well-known/agent.json"),
            urljoin(self.base_url + "/", ".well-known/agent-card.json"),
            f"{self.base_url}/.well-known/agent.json",
            # When base is host root
            urljoin(self.base_url.rsplit("/a2a", 1)[0] + "/", ".well-known/agent.json")
            if "/a2a" in self.base_url
            else None,
        ]
        last_err: str | None = None
        async with httpx.AsyncClient(timeout=min(30.0, self.timeout_s)) as client:
            for url in candidates:
                if not url:
                    continue
                try:
                    resp = await client.get(url, headers=self.headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, dict) and (data.get("name") or data.get("url")):
                            # Update base from card if present
                            card_url = str(data.get("url") or "").strip().rstrip("/")
                            if card_url:
                                self.base_url = card_url
                            return data
                    last_err = f"{url} → HTTP {resp.status_code}"
                except Exception as exc:
                    last_err = f"{url} → {exc}"
        raise A2AClientError(f"Agent Card not found ({last_err or 'no candidates'})")

    async def send_message(
        self,
        text: str,
        *,
        context_id: str | None = None,
        configuration: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send user text via JSON-RPC message/send (A2A 0.3/1.0)."""
        msg = A2AMessage.from_user_text(text, context_id=context_id)
        params: dict[str, Any] = {
            "message": msg.model_dump(exclude_none=True),
        }
        if configuration:
            params["configuration"] = configuration

        payload = {
            "jsonrpc": "2.0",
            "id": new_id("rpc_"),
            "method": "message/send",
            "params": params,
        }
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            try:
                resp = await client.post(
                    self._rpc_url(),
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        **self.headers,
                    },
                )
            except httpx.TimeoutException as exc:
                raise A2AClientError(f"Remote A2A timeout after {self.timeout_s}s") from exc
            except httpx.HTTPError as exc:
                raise A2AClientError(f"Remote A2A HTTP error: {exc}") from exc

        if resp.status_code >= 400:
            raise A2AClientError(
                f"Remote A2A HTTP {resp.status_code}: {resp.text[:500]}",
                status_code=resp.status_code,
            )
        try:
            data = resp.json()
        except Exception as exc:
            raise A2AClientError(f"Invalid JSON from remote A2A: {exc}") from exc

        if isinstance(data, dict) and data.get("error"):
            err = data["error"]
            if isinstance(err, dict):
                raise A2AClientError(
                    f"A2A RPC error {err.get('code')}: {err.get('message')}"
                )
            raise A2AClientError(f"A2A RPC error: {err}")

        result = data.get("result") if isinstance(data, dict) else data
        if not isinstance(result, dict):
            raise A2AClientError("A2A message/send returned non-object result")
        return result

    async def get_task(self, task_id: str, *, history_length: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"id": task_id}
        if history_length is not None:
            params["historyLength"] = history_length
        payload = {
            "jsonrpc": "2.0",
            "id": new_id("rpc_"),
            "method": "tasks/get",
            "params": params,
        }
        async with httpx.AsyncClient(timeout=min(60.0, self.timeout_s)) as client:
            resp = await client.post(
                self._rpc_url(),
                json=payload,
                headers={"Content-Type": "application/json", **self.headers},
            )
        if resp.status_code >= 400:
            raise A2AClientError(
                f"tasks/get HTTP {resp.status_code}: {resp.text[:400]}",
                status_code=resp.status_code,
            )
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            err = data["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise A2AClientError(f"tasks/get error: {msg}")
        result = data.get("result") if isinstance(data, dict) else data
        if not isinstance(result, dict):
            raise A2AClientError("tasks/get returned non-object")
        return result


def extract_task_text(task: dict[str, Any]) -> str:
    """Best-effort plain text from an A2A Task response."""
    if not isinstance(task, dict):
        return str(task)
    # status.message
    status = task.get("status") or {}
    if isinstance(status, dict):
        msg = status.get("message")
        if isinstance(msg, dict):
            parts = msg.get("parts") or []
            texts = [
                str(p.get("text"))
                for p in parts
                if isinstance(p, dict) and p.get("text")
            ]
            if texts:
                return "\n".join(texts)
    # artifacts
    for art in task.get("artifacts") or []:
        if not isinstance(art, dict):
            continue
        parts = art.get("parts") or []
        texts = [
            str(p.get("text"))
            for p in parts
            if isinstance(p, dict) and p.get("text")
        ]
        if texts:
            return "\n".join(texts)
    # history last agent message
    for msg in reversed(task.get("history") or []):
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role") or "") != "agent":
            continue
        parts = msg.get("parts") or []
        texts = [
            str(p.get("text"))
            for p in parts
            if isinstance(p, dict) and p.get("text")
        ]
        if texts:
            return "\n".join(texts)
    return ""
