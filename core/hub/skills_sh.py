"""Search skills.sh ecosystem via GitHub (vercel-labs catalogs)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

USER_AGENT = "Holix/1.0"
DEFAULT_REPOS = (
    "vercel-labs/agent-skills",
    "vercel-labs/skills",
)


@dataclass
class SkillsShHit:
    repo: str
    path: str
    skill_name: str
    install_spec: str
    html_url: str


def _github_json(url: str, *, timeout: float = 10.0) -> object | None:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        logger.debug("skills.sh github request failed %s: %s", url, exc)
        return None


def _list_repo_skill_dirs(repo: str, *, limit: int = 40) -> list[SkillsShHit]:
    """List skill folders via Contents API (works without code-search auth)."""
    hits: list[SkillsShHit] = []
    # Common layouts: skills/, packages/, root-level skill dirs
    for prefix in ("skills", "packages", ""):
        if len(hits) >= limit:
            break
        url = (
            f"https://api.github.com/repos/{repo}/contents/{prefix}"
            if prefix
            else f"https://api.github.com/repos/{repo}/contents"
        )
        data = _github_json(url, timeout=8.0)
        if not isinstance(data, list):
            continue
        for item in data:
            if item.get("type") != "dir":
                continue
            name = item.get("name") or ""
            if not name or name.startswith(".") or name in {"docs", "scripts", ".github"}:
                continue
            rel = f"{prefix}/{name}" if prefix else name
            # Prefer dirs that look like skills (heuristic: name not meta)
            hits.append(
                SkillsShHit(
                    repo=repo,
                    path=f"{rel}/SKILL.md",
                    skill_name=name,
                    install_spec=f"skills-sh/{repo}/{rel}",
                    html_url=item.get("html_url") or "",
                )
            )
            if len(hits) >= limit:
                break
    return hits


def search_skills_sh(query: str, *, limit: int = 10) -> list[SkillsShHit]:
    """Search GitHub for SKILL.md files in known skills.sh repos.

    Uses code search when available; falls back to listing skill directories
    (code search often requires auth and fails silently on many servers).
    """
    q = (query or "").strip()
    hits: list[SkillsShHit] = []

    if q:
        for repo in DEFAULT_REPOS:
            url = (
                "https://api.github.com/search/code?"
                + urllib.parse.urlencode(
                    {
                        "q": f"repo:{repo} {q} filename:SKILL.md",
                        "per_page": str(min(limit, 30)),
                    }
                )
            )
            data = _github_json(url, timeout=10.0)
            if not isinstance(data, dict):
                continue
            for item in data.get("items", []):
                path = item.get("path", "")
                if not path.endswith("SKILL.md"):
                    continue
                skill_path = Path(path)
                skill_dir = str(skill_path.parent) if skill_path.name == "SKILL.md" else path
                skill_name = skill_path.parent.name or "skill"
                spec = (
                    f"skills-sh/{repo}/{skill_dir}"
                    if skill_dir
                    else f"skills-sh/{repo}"
                )
                hits.append(
                    SkillsShHit(
                        repo=repo,
                        path=path,
                        skill_name=skill_name,
                        install_spec=spec,
                        html_url=item.get("html_url", ""),
                    )
                )
                if len(hits) >= limit:
                    return hits

    # Fallback / browse: directory listing + local filter
    if len(hits) < limit:
        listed: list[SkillsShHit] = []
        for repo in DEFAULT_REPOS:
            listed.extend(_list_repo_skill_dirs(repo, limit=max(limit * 3, 30)))
        if q:
            ql = q.lower()
            listed = [
                h
                for h in listed
                if ql in h.skill_name.lower() or ql in h.path.lower()
            ]
        # de-dupe by install_spec
        seen: set[str] = {h.install_spec for h in hits}
        for h in listed:
            if h.install_spec in seen:
                continue
            hits.append(h)
            seen.add(h.install_spec)
            if len(hits) >= limit:
                break

    return hits[:limit]
