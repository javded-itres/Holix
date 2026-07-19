"""ClawHub public API client (https://clawhub.ai)."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_REGISTRY = "https://clawhub.ai"
USER_AGENT = "Holix/1.0 (+https://github.com/javded-itres/Holix)"

# clawhub:@owner/slug or owner/slug (optional @version handled by sources.py)
_OWNER_SLUG_RE = re.compile(
    r"^@?(?P<owner>[A-Za-z0-9_.-]+)/(?P<slug>[A-Za-z0-9_.-]+)$"
)


@dataclass
class ClawHubSearchHit:
    slug: str
    display_name: str
    summary: str
    version: str | None
    owner_handle: str | None

    @property
    def qualified_slug(self) -> str:
        """Install ref: @owner/slug when owner known, else bare slug."""
        if self.owner_handle:
            return f"@{self.owner_handle}/{self.slug}"
        return self.slug

    @property
    def install_spec(self) -> str:
        spec = f"clawhub:{self.qualified_slug}"
        if self.version:
            spec = f"{spec}@{self.version}"
        return spec


def parse_clawhub_ref(ref: str) -> tuple[str | None, str]:
    """Split clawhub skill ref into (owner_handle|None, bare_slug)."""
    text = (ref or "").strip()
    if not text:
        raise ValueError("empty clawhub ref")
    # Strip leading clawhub: if present
    if text.lower().startswith("clawhub:"):
        text = text.split(":", 1)[1].strip()
    # Drop version suffix only when it looks like semver (not @owner/…)
    if text.count("@") == 1 and not text.startswith("@"):
        # slug@version
        text, _ver = text.rsplit("@", 1)
    elif text.startswith("@") and text.count("@") >= 2:
        # @owner/slug@version
        text, _ver = text.rsplit("@", 1)
    m = _OWNER_SLUG_RE.match(text)
    if m:
        return m.group("owner"), m.group("slug")
    # bare slug (may still be ambiguous on API)
    bare = text[1:] if text.startswith("@") else text
    return None, bare.strip("/")


class ClawHubClient:
    def __init__(self, base_url: str = DEFAULT_REGISTRY) -> None:
        self.base_url = base_url.rstrip("/")

    def _get(
        self,
        path: str,
        params: dict[str, str] | None = None,
        retries: int = 1,
        *,
        timeout: float = 10.0,
        allow_409: bool = False,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 409 and allow_409:
                    body = e.read().decode("utf-8", errors="replace")
                    try:
                        payload = json.loads(body) if body else {}
                    except json.JSONDecodeError:
                        payload = {"message": body}
                    raise AmbiguousSkillSlugError(payload, slug=path) from e
                if e.code == 429 and attempt < retries:
                    retry_after = int(e.headers.get("Retry-After", "2"))
                    time.sleep(min(retry_after, 5))
                    last_err = e
                    continue
                # attach body for debugging
                try:
                    detail = e.read().decode("utf-8", errors="replace")[:300]
                except Exception:
                    detail = ""
                if detail:
                    raise urllib.error.HTTPError(
                        e.url, e.code, f"{e.reason}: {detail}", e.headers, None
                    ) from e
                raise
            except Exception as e:
                last_err = e
                if attempt < retries:
                    time.sleep(0.35)
                    continue
                raise last_err from None
        raise RuntimeError("unreachable")

    def _get_text(
        self,
        path: str,
        params: dict[str, str],
        *,
        timeout: float = 30.0,
        retries: int = 2,
    ) -> str:
        url = f"{self.base_url}{path}?" + urllib.parse.urlencode(params)
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read().decode("utf-8")
            except Exception as e:
                last_err = e
                if attempt < retries:
                    time.sleep(0.4 * (attempt + 1))
                    continue
                raise last_err from None
        raise RuntimeError("unreachable")

    def _owner_params(self, owner: str | None) -> dict[str, str]:
        if not owner:
            return {}
        # API accepts both; send owner (verified working).
        return {"owner": owner}

    def browse(self, *, limit: int = 20) -> list[ClawHubSearchHit]:
        """Top skills by downloads (no query)."""
        data = self._get(
            "/api/v1/skills",
            {"limit": str(limit), "sort": "downloads", "nonSuspiciousOnly": "true"},
        )
        return self._hits_from_items(data.get("items", []))

    def search(self, query: str, *, limit: int = 10) -> list[ClawHubSearchHit]:
        data = self._get(
            "/api/v1/search",
            {"q": query, "limit": str(limit), "nonSuspiciousOnly": "true"},
        )
        return self._hits_from_results(data.get("results", []))

    def _hits_from_results(self, rows: list) -> list[ClawHubSearchHit]:
        hits: list[ClawHubSearchHit] = []
        for row in rows:
            owner = row.get("owner") or {}
            handle = owner.get("handle") or row.get("ownerHandle")
            hits.append(
                ClawHubSearchHit(
                    slug=row.get("slug", ""),
                    display_name=row.get("displayName", row.get("slug", "")),
                    summary=(row.get("summary") or "")[:200],
                    version=row.get("version"),
                    owner_handle=handle,
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
            owner = row.get("owner") or skill.get("owner") or {}
            handle = None
            if isinstance(owner, dict):
                handle = owner.get("handle")
            handle = handle or row.get("ownerHandle") or skill.get("ownerHandle")
            hits.append(
                ClawHubSearchHit(
                    slug=skill.get("slug", ""),
                    display_name=skill.get("displayName", skill.get("slug", "")),
                    summary=(skill.get("summary") or "")[:200],
                    version=version,
                    owner_handle=handle,
                )
            )
        return hits

    def resolve_owner_slug(
        self,
        ref: str,
        *,
        owner: str | None = None,
    ) -> tuple[str | None, str]:
        """Return (owner, bare_slug), resolving AMBIGUOUS_SKILL_SLUG via API matches."""
        parsed_owner, slug = parse_clawhub_ref(ref)
        owner = owner or parsed_owner
        if owner:
            return owner, slug
        # Probe detail endpoint; on 409 pick first match.
        try:
            self._get(
                f"/api/v1/skills/{urllib.parse.quote(slug)}",
                allow_409=True,
                timeout=10.0,
            )
            return None, slug
        except AmbiguousSkillSlugError as exc:
            match = exc.pick_match()
            if not match:
                raise ValueError(
                    f"ClawHub slug '{slug}' is ambiguous; install with "
                    f"clawhub:@owner/{slug} (e.g. from search results)"
                ) from exc
            return match[0], match[1]

    def get_skill(self, slug: str, *, owner: str | None = None) -> dict[str, Any]:
        owner, bare = self.resolve_owner_slug(slug, owner=owner)
        params = self._owner_params(owner)
        try:
            return self._get(
                f"/api/v1/skills/{urllib.parse.quote(bare)}",
                params or None,
                allow_409=True,
            )
        except AmbiguousSkillSlugError as exc:
            match = exc.pick_match()
            if not match:
                raise
            owner, bare = match
            return self._get(
                f"/api/v1/skills/{urllib.parse.quote(bare)}",
                self._owner_params(owner),
            )

    def resolve_version(
        self,
        slug: str,
        version: str | None = None,
        *,
        owner: str | None = None,
    ) -> tuple[str, str | None, str]:
        """Return (version, owner, bare_slug)."""
        owner, bare = self.resolve_owner_slug(slug, owner=owner)
        if version:
            return str(version), owner, bare
        data = self.get_skill(bare, owner=owner)
        # Re-read owner from response when available
        resp_owner = (data.get("owner") or {}).get("handle") if isinstance(data.get("owner"), dict) else None
        owner = owner or resp_owner
        latest = data.get("latestVersion") or {}
        ver = latest.get("version")
        if not ver:
            tags = (data.get("skill") or {}).get("tags") or {}
            ver = tags.get("latest")
        if not ver:
            raise ValueError(f"No version found for skill '{bare}'")
        return str(ver), owner, bare

    def list_version_files(
        self,
        slug: str,
        version: str,
        *,
        owner: str | None = None,
    ) -> list[str]:
        owner, bare = self.resolve_owner_slug(slug, owner=owner)
        data = self._get(
            f"/api/v1/skills/{urllib.parse.quote(bare)}/versions/{urllib.parse.quote(version)}",
            self._owner_params(owner) or None,
            retries=2,
        )
        version_obj = data.get("version") or {}
        return [f["path"] for f in version_obj.get("files", []) if f.get("path")]

    def download_file(
        self,
        slug: str,
        path: str,
        version: str,
        *,
        owner: str | None = None,
    ) -> str:
        owner, bare = self.resolve_owner_slug(slug, owner=owner)
        params = {
            "path": path,
            "version": version,
            **self._owner_params(owner),
        }
        return self._get_text(
            f"/api/v1/skills/{urllib.parse.quote(bare)}/file",
            params,
            retries=2,
        )

    def fetch_skill_bundle(
        self,
        slug: str,
        version: str | None = None,
        *,
        owner: str | None = None,
    ) -> tuple[str, dict[str, str], str | None, str]:
        """Download skill files.

        Returns (version, files, owner, bare_slug).
        """
        ver, owner, bare = self.resolve_version(slug, version, owner=owner)
        paths = self.list_version_files(bare, ver, owner=owner)
        if not paths:
            raise ValueError(f"Skill '{bare}' has no files")
        files: dict[str, str] = {}
        for rel in paths:
            if rel.endswith("/") or rel.startswith(".."):
                continue
            files[rel] = self.download_file(bare, rel, ver, owner=owner)
        return ver, files, owner, bare


class AmbiguousSkillSlugError(Exception):
    """ClawHub returned 409 AMBIGUOUS_SKILL_SLUG."""

    def __init__(self, payload: dict[str, Any], *, slug: str = "") -> None:
        self.payload = payload or {}
        self.slug = slug
        msg = self.payload.get("message") or "Ambiguous skill slug"
        super().__init__(msg)

    def pick_match(self) -> tuple[str, str] | None:
        matches = self.payload.get("matches") or []
        if not matches:
            return None
        # Prefer first match (API order); refs look like @owner/slug
        m0 = matches[0]
        handle = m0.get("ownerHandle") or ""
        slug = m0.get("slug") or ""
        ref = m0.get("ref") or ""
        if handle and slug:
            return str(handle), str(slug)
        if ref:
            return parse_clawhub_ref(ref)
        return None
