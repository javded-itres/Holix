"""HermesHub public skills catalog (GitHub: amanning3390/hermeshub)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

HERMES_REPO = "amanning3390/hermeshub"
HERMES_GIT_URL = f"https://github.com/{HERMES_REPO}.git"
GITHUB_CONTENTS_API = f"https://api.github.com/repos/{HERMES_REPO}/contents/skills"
USER_AGENT = "Helix/1.0 (+https://github.com/yourusername/helix)"


@dataclass
class HermesHubHit:
    slug: str
    name: str
    description: str
    category: str
    install_spec: str


def _github_get(url: str) -> object:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_hermes_skills(*, limit: int = 50) -> list[HermesHubHit]:
    """List skill directories from the HermesHub GitHub repo."""
    try:
        data = _github_get(GITHUB_CONTENTS_API)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return _list_from_marketplace_api(limit=limit)
        raise
    if not isinstance(data, list):
        return []

    hits: list[HermesHubHit] = []
    for item in data[:limit]:
        if item.get("type") != "dir":
            continue
        slug = item.get("name", "")
        if not slug or slug.startswith("."):
            continue
        hits.append(
            HermesHubHit(
                slug=slug,
                name=slug,
                description="",
                category="hermes",
                install_spec=f"hermes:{slug}",
            )
        )
    return hits


def _list_from_marketplace_api(*, limit: int) -> list[HermesHubHit]:
    """Fallback when GitHub API is rate-limited."""
    url = "https://hermeshub.xyz/api/v1/skills/marketplace?" + urllib.parse.urlencode(
        {"limit": str(limit), "page": "1"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    hits: list[HermesHubHit] = []
    for row in data.get("skills", [])[:limit]:
        slug = row.get("slug") or row.get("name", "")
        if not slug:
            continue
        hits.append(
            HermesHubHit(
                slug=slug,
                name=row.get("name", slug),
                description=(row.get("short_description") or "")[:200],
                category=row.get("category", "hermes"),
                install_spec=f"hermes:{slug}",
            )
        )
    return hits


def search_hermes_skills(query: str, *, limit: int = 20) -> list[HermesHubHit]:
    """Filter HermesHub skills by slug/name/description."""
    q = query.strip().lower()
    all_skills = list_hermes_skills(limit=100)
    if not q:
        return all_skills[:limit]

    scored: list[tuple[int, HermesHubHit]] = []
    for hit in all_skills:
        hay = f"{hit.slug} {hit.name} {hit.description}".lower()
        if q in hay:
            score = 0 if hit.slug.lower() == q else (1 if hit.slug.lower().startswith(q) else 2)
            scored.append((score, hit))
    scored.sort(key=lambda x: x[0])
    return [h for _, h in scored[:limit]]


def hermes_skill_subpath(slug: str) -> str:
    """Path within hermeshub repo for a skill bundle."""
    safe = re.sub(r"[^a-zA-Z0-9._-]", "-", slug.strip()).strip("-")
    if not safe:
        raise ValueError("empty hermes skill slug")
    return f"skills/{safe}"