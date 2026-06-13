"""Search skills.sh ecosystem via GitHub (vercel-labs catalogs)."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

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


def search_skills_sh(query: str, *, limit: int = 10) -> list[SkillsShHit]:
    """Search GitHub for SKILL.md files in known skills.sh repos."""
    hits: list[SkillsShHit] = []
    for repo in DEFAULT_REPOS:
        url = (
            "https://api.github.com/search/code?"
            + urllib.parse.urlencode({"q": f"repo:{repo} {query} filename:SKILL.md", "per_page": str(min(limit, 30))})
        )
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/vnd.github+json",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
        for item in data.get("items", []):
            path = item.get("path", "")
            if not path.endswith("SKILL.md"):
                continue
            owner_repo = repo
            skill_path = Path(path)
            skill_dir = str(skill_path.parent) if skill_path.name == "SKILL.md" else path
            skill_name = skill_path.parent.name or "skill"
            spec = f"skills-sh/{owner_repo}/{skill_dir}" if skill_dir else f"skills-sh/{owner_repo}"
            hits.append(
                SkillsShHit(
                    repo=owner_repo,
                    path=path,
                    skill_name=skill_name,
                    install_spec=spec,
                    html_url=item.get("html_url", ""),
                )
            )
            if len(hits) >= limit:
                return hits
    return hits[:limit]