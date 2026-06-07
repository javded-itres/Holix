"""Parse install source identifiers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


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
        slug = spec.split(":", 1)[1].strip()
        ver = None
        if "@" in slug:
            slug, ver = slug.rsplit("@", 1)
        return ParsedSource("clawhub", slug, version=ver, as_name=as_name)

    m = _SKILLS_SH_RE.match(spec)
    if m or spec.lower().startswith("skills-sh/"):
        return ParsedSource("skills-sh", spec, as_name=as_name)

    if spec.lower().startswith("git:"):
        return ParsedSource("git", spec[4:].strip(), as_name=as_name)

    if spec.startswith(("http://", "https://")):
        if spec.rstrip("/").endswith("SKILL.md"):
            return ParsedSource("url", spec, as_name=as_name)
        return ParsedSource("git", spec, as_name=as_name)

    if "github.com" in spec or spec.endswith(".git"):
        return ParsedSource("git", spec, as_name=as_name)

    if spec.startswith(("./", "../", "/", "~")) or "/" in spec:
        return ParsedSource("path", spec, as_name=as_name)

    # default: ClawHub slug
    ver = None
    slug = spec
    if "@" in slug:
        slug, ver = slug.rsplit("@", 1)
    return ParsedSource("clawhub", slug, version=ver, as_name=as_name)


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