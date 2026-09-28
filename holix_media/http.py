"""Minimal async HTTP helper (injectable in tests)."""

from __future__ import annotations

from typing import Any, Protocol


class HttpTransport(Protocol):
    async def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: float = 120.0,
    ) -> dict[str, Any]: ...

    async def get_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float = 60.0,
    ) -> dict[str, Any]: ...

    async def get_bytes(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 120.0,
    ) -> tuple[bytes, str]: ...


class HttpxTransport:
    async def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.post(url, headers=headers, json=json)
            if resp.is_error:
                detail = (resp.text or "")[:500]
                raise RuntimeError(f"HTTP {resp.status_code} {url}: {detail}")
            data = resp.json()
            return data if isinstance(data, dict) else {"data": data}

    async def get_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.is_error:
                detail = (resp.text or "")[:500]
                raise RuntimeError(f"HTTP {resp.status_code} {url}: {detail}")
            data = resp.json()
            return data if isinstance(data, dict) else {"data": data}

    async def get_bytes(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 120.0,
    ) -> tuple[bytes, str]:
        import httpx

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers or {})
            resp.raise_for_status()
            ctype = (resp.headers.get("content-type") or "application/octet-stream").split(";")[0]
            return resp.content, ctype
