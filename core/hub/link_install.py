"""Turn a pasted skill or MCP link into a workspace install.

A bare URL, or a short «подключи / install» plus one URL, is a share link.
Ordinary pages are not. Skills land in ``<workspace>/.holix/skills``. MCP
servers land in ``<workspace>/.holix/config.yaml``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

_URL_RE = re.compile(r"https?://[^\s<>'\"\]]+")
_INSTALL_INTENT_RE = re.compile(
    r"(?i)(подключ|добав|постав|установ|install|connect|\badd\b|enable|\bmcp\b|скилл|skill)"
)
_HINT_MARK = "[Holix] This message shares a skill or MCP link."
_GIT_HOSTS = frozenset({"github.com", "www.github.com", "gitlab.com", "www.gitlab.com"})
_SKILL_HOSTS = frozenset({"skills.sh", "www.skills.sh"})
_CLAWHUB_HOSTS = frozenset({"clawhub.ai", "www.clawhub.ai"})


@dataclass(frozen=True)
class ShareLink:
    """Classified URL. ``kind`` is skill-spec, skill-git, mcp-http, mcp-sse, mcp-git, or repo."""

    kind: str
    url: str
    spec: str = ""
    git_url: str = ""
    ref: str | None = None
    subpath: str | None = None
    name: str = ""


@dataclass
class ShareInstallResult:
    kind: str
    name: str
    skills: list[str] = field(default_factory=list)
    mcp: dict | None = None
    detail: str = ""


def classify_share_link(url: str) -> ShareLink | None:
    """Return a skill or MCP link, or None for an ordinary web page."""
    raw = _clean_url(url)
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    host = parts.hostname.lower()
    path = parts.path or ""
    stripped = urlunsplit((parts.scheme, parts.netloc, path, "", ""))

    if host in _SKILL_HOSTS:
        segments = [item for item in path.split("/") if item]
        if len(segments) < 2:
            return None
        spec = "skills-sh/" + "/".join(segments)
        return ShareLink("skill-spec", stripped, spec=spec, name=_server_name(segments[-1]))

    if host in _CLAWHUB_HOSTS:
        segments = [item for item in path.split("/") if item]
        if segments and segments[0] == "skills":
            segments = segments[1:]
        if len(segments) < 2:
            return None
        owner = segments[0][1:] if segments[0].startswith("@") else segments[0]
        slug = segments[1]
        if not owner or not slug:
            return None
        spec = f"clawhub:@{owner}/{slug}"
        return ShareLink("skill-spec", stripped, spec=spec, name=_server_name(slug))

    git = _parse_git_web(host, path)
    if git is not None:
        return git

    if host in {"raw.githubusercontent.com"} and path.rstrip("/").endswith("SKILL.md"):
        return ShareLink("skill-spec", stripped, spec=stripped, name=_name_from_skill_path(path))

    lower_path = path.rstrip("/").lower()
    if lower_path.endswith("/sse"):
        return ShareLink("mcp-sse", raw, name=_http_server_name(host))
    if lower_path.endswith("/mcp"):
        return ShareLink("mcp-http", raw, name=_http_server_name(host))
    return None


def share_link_to_install(text: str) -> str | None:
    """The one URL in a bare message or a short install request."""
    raw = (text or "").strip()
    if not raw or _HINT_MARK in raw:
        return None
    found = [_clean_url(item) for item in _URL_RE.findall(raw)]
    if len(found) != 1:
        return None
    url = found[0]
    if classify_share_link(url) is None:
        return None
    remainder = _URL_RE.sub(" ", raw).strip()
    if not remainder:
        return url
    if len(remainder) <= 180 and _INSTALL_INTENT_RE.search(remainder):
        return url
    return None


def expand_user_message_for_share_link(text: str) -> str:
    """Tell the agent to install when the user dropped a skill or MCP link."""
    url = share_link_to_install(text)
    if not url:
        return text
    return (
        f"{text.rstrip()}\n\n{_HINT_MARK} "
        f"Call workspace_holix now with action=install_link and link={url!r}. "
        "Do not edit ~/.holix/profiles and do not ask the user to run a shell command."
    )


def install_share_link(url: str, *, skills_dir: Path) -> ShareInstallResult:
    """Install a classified link. Skills use the hub importer. MCP git clones stay out of the profile."""
    link = classify_share_link(url)
    if link is None:
        raise ValueError("This link is not a skill or an MCP server.")

    if link.kind == "mcp-http":
        return _http_result(link, transport="http")
    if link.kind == "mcp-sse":
        return _http_result(link, transport="sse")
    if link.kind == "skill-spec":
        return _install_skill_spec(link, skills_dir)
    if link.kind == "skill-git":
        return _install_skill_git(link, skills_dir)
    if link.kind == "mcp-git":
        try:
            return _install_mcp_git(link)
        except ValueError:
            return _install_skill_git(link, skills_dir)
    try:
        return _install_skill_git(link, skills_dir)
    except ValueError as exc:
        if "No SKILL.md" not in str(exc):
            raise
        return _install_mcp_git(link)


def _http_result(link: ShareLink, *, transport: str) -> ShareInstallResult:
    from core.mcp.remote_bridge import build_remote_http_config

    if transport == "http":
        spec = build_remote_http_config(link.url)
    else:
        spec = {
            "transport": "sse",
            "url": link.url,
            "timeout": 60.0,
            "default_risk_level": "medium",
        }
    return ShareInstallResult(
        "mcp",
        link.name,
        mcp=spec,
        detail=f"{transport} {_redact_link(link.url)}",
    )


def _install_skill_spec(link: ShareLink, skills_dir: Path) -> ShareInstallResult:
    from core.hub.importer import SkillImporter

    result = SkillImporter(skills_dir).install(link.spec)
    names = list(result.skill_names or [result.skill_name])
    return ShareInstallResult("skill", names[0], skills=names, detail=link.spec)


def _install_skill_git(link: ShareLink, skills_dir: Path) -> ShareInstallResult:
    from core.hub.importer import SkillImporter

    result = SkillImporter(skills_dir)._install_git(
        link.git_url,
        ref=link.ref,
        subpath=link.subpath,
        source_label=link.url,
        install_spec=link.url,
    )
    names = list(result.skill_names or [result.skill_name])
    return ShareInstallResult("skill", names[0], skills=names, detail=_redact_link(link.url))


def _install_mcp_git(link: ShareLink) -> ShareInstallResult:
    from core.mcp.installer import auto_prepare, clone_or_update_git, detected_mcp_command

    name = link.name or "mcp"
    cloned = clone_or_update_git(link.git_url, name)
    if link.ref:
        from core.mcp.installer import _run

        _run(["git", "-C", str(cloned), "checkout", link.ref], check=False)
    found = detected_mcp_command(cloned)
    if found is None:
        raise ValueError(f"No SKILL.md and no MCP entrypoint in {link.git_url}")
    auto_prepare(cloned, found[0])
    found = detected_mcp_command(cloned) or found
    command, args, notes = found
    spec: dict = {
        "transport": "stdio",
        "command": command,
        "args": args,
        "_source": "git",
    }
    if notes:
        spec["_notes"] = notes
    detail = notes or f"stdio {command}"
    return ShareInstallResult("mcp", name, mcp=spec, detail=detail)


def _parse_git_web(host: str, path: str) -> ShareLink | None:
    if host not in _GIT_HOSTS:
        return None
    parts = [item for item in path.split("/") if item]
    if host.startswith("gitlab"):
        if "-" in parts:
            dash = parts.index("-")
            if dash < 2:
                return None
            owner_repo = parts[:dash]
            rest = parts[dash + 1 :]
        else:
            owner_repo = parts
            rest = []
        if len(owner_repo) < 2:
            return None
        repo = owner_repo[-1].removesuffix(".git")
        owner = "/".join([*owner_repo[:-1]])
    else:
        if len(parts) < 2:
            return None
        owner, repo = parts[0], parts[1].removesuffix(".git")
        rest = parts[2:]
    git_url = f"https://{host.removeprefix('www.')}/{owner}/{repo}.git"
    ref: str | None = None
    subpath: str | None = None
    if len(rest) >= 2 and rest[0] in {"tree", "blob"}:
        ref = rest[1]
        if len(rest) > 2:
            subpath = "/".join(rest[2:])
    elif rest and rest[0] not in {"", "tree", "blob"}:
        return None
    name = _server_name(repo)
    display = git_url
    if subpath and (subpath.endswith("SKILL.md") or _looks_like_skill_path(subpath)):
        if subpath.endswith("SKILL.md") and host.removeprefix("www.") == "github.com" and ref:
            raw = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{subpath}"
            return ShareLink("skill-spec", raw, spec=raw, name=_name_from_skill_path(subpath))
        skill_path = str(Path(subpath).parent) if subpath.endswith("SKILL.md") else subpath
        if skill_path == ".":
            skill_path = None
        return ShareLink(
            "skill-git",
            display,
            git_url=git_url,
            ref=ref,
            subpath=skill_path,
            name=name,
        )
    if "mcp" in repo.lower() and "skill" not in repo.lower():
        return ShareLink("mcp-git", display, git_url=git_url, ref=ref, subpath=subpath, name=name)
    return ShareLink("repo", display, git_url=git_url, ref=ref, subpath=subpath, name=name)


def _looks_like_skill_path(subpath: str) -> bool:
    pieces = [item.lower() for item in subpath.split("/") if item]
    return "skill" in pieces or "skills" in pieces or subpath.endswith("SKILL.md")


def _name_from_skill_path(path: str) -> str:
    parts = [item for item in path.split("/") if item and item != "SKILL.md"]
    return _server_name(parts[-1] if parts else "skill")


def _http_server_name(host: str) -> str:
    labels = [item for item in host.split(".") if item]
    if not labels:
        return "mcp"
    base = labels[0]
    if base in {"mcp", "www", "api"} and len(labels) > 1:
        base = labels[1]
    return _server_name(base)


def _server_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    if not cleaned or not cleaned[0].isalnum():
        cleaned = f"mcp-{cleaned}".strip("-")
    return (cleaned or "mcp")[:64]


def _clean_url(url: str) -> str:
    return (url or "").strip().rstrip(").,;>]\"'")


def _redact_link(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))
