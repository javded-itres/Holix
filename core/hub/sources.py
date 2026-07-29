"""Parse install source identifiers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.url_utils import spec_looks_like_github


@dataclass
class ParsedSource:
    kind: str  # clawhub | git | url | path | skills-sh | claude
    ref: str
    version: str | None = None
    as_name: str | None = None


_SKILLS_SH_RE = re.compile(
    r"^skills-sh/(?P<owner>[^/]+)/(?P<repo>[^/]+)(?:/(?P<path>.+))?$",
    re.I,
)


def parse_install_source(spec: str, *, as_name: str | None = None) -> ParsedSource:
    spec = spec.strip()
    if not spec:
        raise ValueError("empty install source")

    if spec.lower().startswith(("hermes:", "hermeshub:")):
        slug = spec.split(":", 1)[1].strip()
        if "@" in slug:
            slug, _ver = slug.rsplit("@", 1)
        return ParsedSource("hermes", slug.strip(), as_name=as_name)

    if spec.lower().startswith("claude:"):
        body = spec.split(":", 1)[1].strip()
        marketplace = "claude-official"
        plugin = body
        if "@" in body:
            plugin, marketplace = body.rsplit("@", 1)
        return ParsedSource("claude", plugin.strip(), version=None, as_name=as_name)

    if spec.startswith("clawhub:"):
        body = spec.split(":", 1)[1].strip()
        body, ver = _split_clawhub_ref_version(body)
        return ParsedSource("clawhub", body, version=ver, as_name=as_name)

    m = _SKILLS_SH_RE.match(spec)
    if m or spec.lower().startswith("skills-sh/"):
        return ParsedSource("skills-sh", spec, as_name=as_name)

    if spec.lower().startswith("git:"):
        return ParsedSource("git", spec[4:].strip(), as_name=as_name)

    if spec.startswith(("http://", "https://")):
        # Audit #7: never fetch skills/extensions over plain HTTP.
        if spec.startswith("http://"):
            raise ValueError(
                "Insecure HTTP install sources are not allowed; use HTTPS "
                f"(got {spec!r})"
            )
        if spec.rstrip("/").endswith("SKILL.md"):
            return ParsedSource("url", spec, as_name=as_name)
        return ParsedSource("git", spec, as_name=as_name)

    if spec_looks_like_github(spec):
        return ParsedSource("git", spec, as_name=as_name)

    if spec.startswith(("./", "../", "/", "~")) or "/" in spec:
        return ParsedSource("path", spec, as_name=as_name)

    # default: ClawHub slug / @owner/slug
    slug, ver = _split_clawhub_ref_version(spec)
    return ParsedSource("clawhub", slug, version=ver, as_name=as_name)


_CLAW_VER_RE = re.compile(
    r"^(?P<ref>.+)@(?P<ver>[0-9]+(?:\.[0-9A-Za-z_-]+)*)$"
)


def _split_clawhub_ref_version(body: str) -> tuple[str, str | None]:
    """Split clawhub ref and trailing @version without breaking @owner/slug."""
    text = (body or "").strip()
    if not text:
        return text, None
    m = _CLAW_VER_RE.match(text)
    if not m:
        return text, None
    ref, ver = m.group("ref"), m.group("ver")
    # Avoid treating "@owner" alone as ref with version "…"
    if ref == "@" or ref.endswith("@"):
        return text, None
    return ref, ver


def skills_sh_to_git_url(spec: str) -> tuple[str, str | None]:
    """skills-sh/owner/repo/path -> clone URL + subpath within repo."""
    m = _SKILLS_SH_RE.match(spec)
    if not m:
        raise ValueError(f"Invalid skills-sh spec: {spec}")
    owner, repo, sub = m.group("owner"), m.group("repo"), m.group("path")
    url = f"https://github.com/{owner}/{repo}.git"
    return url, sub


def git_ref_from_spec(spec: str) -> tuple[str, str | None]:
    """Split git URL and optional #ref."""
    if "#" in spec and not spec.startswith("http"):
        repo, ref = spec.rsplit("#", 1)
        return repo, ref
    if "#" in spec:
        base, ref = spec.rsplit("#", 1)
        if not ref.startswith("/"):
            return base, ref
    return spec, None