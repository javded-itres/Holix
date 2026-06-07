"""ClawHub public API client (https://clawhub.ai)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_REGISTRY = "https://clawhub.ai"
USER_AGENT = "Helix/1.0 (+https://github.com/yourusername/helix)"


@dataclass
class ClawHubSearchHit:
    slug: str
    display_name: str
    summary: str
    version: str | None
    owner_handle: str | None


class ClawHubClient:
    def __init__(self, base_url: str = DEFAULT_REGISTRY) -> None:
        self.base_url = base_url.rstrip("/")

    def _get(self, path: str, params: dict[str, str] | None = None, retries: int = 2) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries:
                    retry_after = int(e.headers.get("Retry-After", "2"))
                    time.sleep(min(retry_after, 10))
                    last_err = e
                    continue
                raise
            except Exception as e:
                last_err = e
                if attempt < retries:
                    time.sleep(1)
                    continue
                raise last_err from None
        raise RuntimeError("unreachable")

    def _get_text(self, path: str, params: dict[str, str]) -> str:
        url = f"{self.base_url}{path}?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")

    def browse(self, *, limit: int = 20) -> list[ClawHubSearchHit]:
        """Top skills by downloads (no query)."""
        data = self._get(
            "/api/v1/skills",
            {"limit": str(limit), "sort": "downloads", "nonSuspiciousOnly": "true"},
        )
        return self._hits_from_items(data.get("items", []))

    def search(self, query: str, *, limit: int = 10) -> list[ClawHubSearchHit]:
        data = self._get("/api/v1/search", {"q": query, "limit": str(limit), "nonSuspiciousOnly": "true"})
        return self._hits_from_results(data.get("results", []))

    def _hits_from_results(self, rows: list) -> list[ClawHubSearchHit]:
        hits: list[ClawHubSearchHit] = []
        for row in rows:
            owner = row.get("owner") or {}
            hits.append(
                ClawHubSearchHit(
                    slug=row.get("slug", ""),
                    display_name=row.get("displayName", row.get("slug", "")),
                    summary=(row.get("summary") or "")[:200],
                    version=row.get("version"),
                    owner_handle=owner.get("handle"),
                )
            )
        return hits

    def _hits_from_items(self, items: list) -> list[ClawHubSearchHit]:
        hits: list[ClawHubSearchHit] = []
        for row in items:
            skill = row.get("skill") or row
            latest = row.get("latestVersion") or {}
            tags = (skill.get("tags") or {}) if isinstance(skill.get("tags"), dict) else {}
            version = latest.get("version") or tags.get("latest")
            hits.append(
                ClawHubSearchHit(
                    slug=skill.get("slug", ""),
                    display_name=skill.get("displayName", skill.get("slug", "")),
                    summary=(skill.get("summary") or "")[:200],
                    version=version,
                    owner_handle=None,
                )
            )
        return hits

    def resolve_version(self, slug: str, version: str | None = None) -> str:
        if version:
            return version
        data = self._get(f"/api/v1/skills/{urllib.parse.quote(slug)}")
        latest = data.get("latestVersion") or {}
        ver = latest.get("version")
        if not ver:
            tags = (data.get("skill") or {}).get("tags") or {}
            ver = tags.get("latest")
        if not ver:
            raise ValueError(f"No version found for skill '{slug}'")
        return str(ver)

    def list_version_files(self, slug: str, version: str) -> list[str]:
        data = self._get(f"/api/v1/skills/{urllib.parse.quote(slug)}/versions/{urllib.parse.quote(version)}")
        version_obj = data.get("version") or {}
        return [f["path"] for f in version_obj.get("files", []) if f.get("path")]

    def download_file(self, slug: str, path: str, version: str) -> str:
        return self._get_text(
            f"/api/v1/skills/{urllib.parse.quote(slug)}/file",
            {"path": path, "version": version},
        )

    def fetch_skill_bundle(self, slug: str, version: str | None = None) -> tuple[str, dict[str, str]]:
        ver = self.resolve_version(slug, version)
        paths = self.list_version_files(slug, ver)
        if not paths:
            raise ValueError(f"Skill '{slug}' has no files")
        files: dict[str, str] = {}
        for rel in paths:
            if rel.endswith("/") or rel.startswith(".."):
                continue
            files[rel] = self.download_file(slug, rel, ver)
        return ver, files