"""HTTP client for MAX platform API (https://dev.max.ru/docs-api)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

MAX_API_BASE = "https://platform-api.max.ru"
DEFAULT_TIMEOUT_S = 35.0


class MaxApiError(Exception):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class MaxClient:
    def __init__(
        self,
        access_token: str,
        *,
        base_url: str = MAX_API_BASE,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.access_token = access_token.strip()
        self.base_url = base_url.rstrip("/")
        self._session = session
        self._owns_session = session is None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> MaxClient:
        await self._ensure_session()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT_S)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        if self._session is not None and self._owns_session:
            await self._session.close()
        self._session = None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": self.access_token}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        http_timeout_s: float | None = None,
    ) -> Any:
        last_error: MaxApiError | None = None
        for attempt in range(4):
            try:
                return await self._request_once(
                    method,
                    path,
                    params=params,
                    json_body=json_body,
                    http_timeout_s=http_timeout_s,
                )
            except MaxApiError as exc:
                last_error = exc
                if exc.status == 429 and attempt < 3:
                    await asyncio.sleep(min(2**attempt, 8))
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise MaxApiError("MAX API request failed")

    async def _request_once(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        http_timeout_s: float | None = None,
    ) -> Any:
        await self._ensure_session()
        assert self._session is not None
        url = f"{self.base_url}{path}"
        req_timeout = aiohttp.ClientTimeout(
            total=http_timeout_s if http_timeout_s is not None else DEFAULT_TIMEOUT_S
        )
        async with self._lock:
            async with self._session.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json_body,
                timeout=req_timeout,
            ) as resp:
                if resp.status == 204:
                    return None
                try:
                    data = await resp.json(content_type=None)
                except aiohttp.ContentTypeError:
                    text = await resp.text()
                    raise MaxApiError(
                        f"MAX API {resp.status}: {text[:200]}",
                        status=resp.status,
                    ) from None
                if resp.status >= 400:
                    detail = data
                    if isinstance(data, dict):
                        detail = data.get("message") or data.get("error") or data
                    raise MaxApiError(f"MAX API {resp.status}: {detail}", status=resp.status)
                return data

    async def get_me(self) -> dict[str, Any]:
        result = await self._request("GET", "/me")
        return result if isinstance(result, dict) else {}

    async def set_my_commands(self, commands: list[dict[str, str]]) -> dict[str, Any]:
        """Publish slash commands to MAX (PATCH /me, up to 32 items)."""
        result = await self._request("PATCH", "/me", json_body={"commands": commands})
        return result if isinstance(result, dict) else {}

    async def get_updates(
        self,
        *,
        marker: int | None = None,
        limit: int = 100,
        timeout: int = 5,
        types: list[str] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "timeout": timeout}
        if marker is not None:
            params["marker"] = marker
        if types:
            params["types"] = ",".join(types)
        http_timeout_s = max(DEFAULT_TIMEOUT_S, float(timeout) + 5.0)
        result = await self._request(
            "GET",
            "/updates",
            params=params,
            http_timeout_s=http_timeout_s,
        )
        return result if isinstance(result, dict) else {"updates": [], "marker": marker}

    async def send_message(
        self,
        text: str,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        fmt: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        link: dict[str, Any] | None = None,
        notify: bool = True,
    ) -> dict[str, Any]:
        if user_id is None and chat_id is None:
            raise ValueError("user_id or chat_id is required")
        if chat_id is not None and user_id is not None:
            user_id = None
        params: dict[str, Any] = {}
        if user_id is not None:
            params["user_id"] = user_id
        if chat_id is not None:
            params["chat_id"] = chat_id
        body: dict[str, Any] = {"text": text, "notify": notify}
        if fmt:
            body["format"] = fmt
        if attachments:
            body["attachments"] = attachments
        if link:
            body["link"] = link
        result = await self._request("POST", "/messages", params=params, json_body=body)
        out_mid = None
        if isinstance(result, dict):
            from integrations.max.models import message_id_from_response

            out_mid = message_id_from_response(result)
        recipient = None
        if isinstance(result, dict):
            msg = result.get("message")
            if isinstance(msg, dict):
                recipient = msg.get("recipient")
        logger.info(
            "MAX send_message ok (user_id=%s, chat_id=%s, chars=%d, fmt=%s, out_mid=%s, api_recipient=%s)",
            user_id,
            chat_id,
            len(text),
            fmt,
            out_mid,
            recipient,
        )
        return result if isinstance(result, dict) else {}

    async def answer_callback(
        self,
        callback_id: str,
        *,
        message: dict[str, Any] | None = None,
        notification: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if message is not None:
            body["message"] = message
        if notification is not None:
            body["notification"] = notification
        result = await self._request(
            "POST",
            "/answers",
            params={"callback_id": callback_id},
            json_body=body or None,
        )
        return result if isinstance(result, dict) else {}

    async def delete_message(self, message_id: str) -> None:
        await self._request("DELETE", "/messages", params={"message_id": message_id})

    async def send_chat_action(
        self,
        chat_id: int,
        *,
        action: str = "typing_on",
    ) -> dict[str, Any]:
        """Send bot action to a chat (e.g. typing_on while the agent is working)."""
        result = await self._request(
            "POST",
            f"/chats/{chat_id}/actions",
            json_body={"action": action},
        )
        return result if isinstance(result, dict) else {}

    async def edit_message(
        self,
        message_id: str,
        text: str,
        *,
        fmt: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"text": text}
        if fmt:
            body["format"] = fmt
        if attachments:
            body["attachments"] = attachments
        result = await self._request(
            "PUT",
            "/messages",
            params={"message_id": message_id},
            json_body=body,
        )
        logger.info(
            "MAX edit_message ok (message_id=%s, chars=%d, fmt=%s)",
            message_id,
            len(text),
            fmt,
        )
        return result if isinstance(result, dict) else {}

    async def list_subscriptions(self) -> list[dict[str, Any]]:
        result = await self._request("GET", "/subscriptions")
        if isinstance(result, dict):
            subs = result.get("subscriptions")
            if isinstance(subs, list):
                return [s for s in subs if isinstance(s, dict)]
        if isinstance(result, list):
            return [s for s in result if isinstance(s, dict)]
        return []

    async def subscribe_webhook(
        self,
        url: str,
        *,
        update_types: list[str] | None = None,
        secret: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"url": url}
        if update_types:
            body["update_types"] = update_types
        if secret:
            body["secret"] = secret
        result = await self._request("POST", "/subscriptions", json_body=body)
        return result if isinstance(result, dict) else {}

    async def delete_subscription(self, url: str) -> dict[str, Any] | None:
        result = await self._request("DELETE", "/subscriptions", params={"url": url})
        return result if isinstance(result, dict) else None

    async def get_message(self, message_id: str) -> dict[str, Any]:
        result = await self._request("GET", f"/messages/{message_id}")
        return result if isinstance(result, dict) else {}

    async def get_video(self, video_token: str) -> dict[str, Any]:
        result = await self._request("GET", f"/videos/{video_token}")
        return result if isinstance(result, dict) else {}

    async def request_upload_url(self, upload_type: str) -> dict[str, Any]:
        result = await self._request("POST", "/uploads", params={"type": upload_type})
        return result if isinstance(result, dict) else {}

    async def download_url(self, url: str, dest: Path) -> int:
        await self._ensure_session()
        assert self._session is not None
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with self._session.get(url, headers=self._headers()) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise MaxApiError(f"Download {resp.status}: {text[:200]}", status=resp.status)
            data = await resp.read()
            dest.write_bytes(data)
            return len(data)

    async def upload_file_multipart(self, upload_url: str, path: Path) -> dict[str, Any]:
        await self._ensure_session()
        assert self._session is not None
        data = aiohttp.FormData()
        data.add_field(
            "data",
            path.open("rb"),
            filename=path.name,
            content_type="application/octet-stream",
        )
        async with self._session.post(upload_url, headers=self._headers(), data=data) as resp:
            try:
                payload = await resp.json(content_type=None)
            except aiohttp.ContentTypeError:
                text = await resp.text()
                raise MaxApiError(f"Upload {resp.status}: {text[:200]}", status=resp.status) from None
            if resp.status >= 400:
                detail = payload
                if isinstance(payload, dict):
                    detail = payload.get("message") or payload.get("error") or payload
                raise MaxApiError(f"Upload {resp.status}: {detail}", status=resp.status)
            return payload if isinstance(payload, dict) else {}