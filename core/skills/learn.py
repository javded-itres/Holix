"""Turn a source (text / path / URL / session hint) into a staged skill draft."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from core.hub.normalize import slugify_skill_name
from core.skills.proposal import SkillProposalStore
from core.tools.browser.policy import validate_fetch_url

MAX_SOURCE_CHARS = 40_000
_MAX_FILES = 12

LEARN_TURN_PROMPT = """\
You are authoring a reusable Holix skill from the source below.

Rules:
- Follow the house contract: When to Use, Procedure, Pitfalls, Verification.
- Prefer `skill_manage` action=patch if an existing skill already covers this.
- New skills: `skill_manage` action=create. That **stages a draft** for human \
approval — it does not write a live skill or assign it to main.
- Do not invent commands. Frame steps with Holix tools \
(`read_file`, `skill_view`, `mcp_context7_*`, …).
- Do not encode a one-off timeout as "never use this tool".
- If the source is huge, put the core model in SKILL.md and keep extras short.

Source / request:
{hint}
"""


def _read_path_blob(path: Path) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")[:MAX_SOURCE_CHARS]
    if not path.is_dir():
        raise FileNotFoundError(str(path))
    parts: list[str] = []
    names = ("SKILL.md", "README.md", "README", "AGENTS.md")
    for name in names:
        candidate = path / name
        if candidate.is_file():
            parts.append(f"# {name}\n{candidate.read_text(encoding='utf-8', errors='replace')}")
        if sum(len(p) for p in parts) >= MAX_SOURCE_CHARS:
            break
    extras = sorted(p for p in path.rglob("*.md") if p.is_file() and p.name not in names)
    for extra in extras[:_MAX_FILES]:
        if sum(len(p) for p in parts) >= MAX_SOURCE_CHARS:
            break
        parts.append(
            f"# {extra.relative_to(path)}\n"
            f"{extra.read_text(encoding='utf-8', errors='replace')[:8000]}"
        )
    if not parts:
        raise ValueError(f"no readable markdown under {path}")
    return "\n\n".join(parts)[:MAX_SOURCE_CHARS]


def _read_url(url: str) -> str:
    safe = validate_fetch_url(url)
    parsed = urlparse(safe)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("only http(s) URLs with a host are allowed")
    if parsed.username or parsed.password:
        raise ValueError("URL userinfo is not allowed")
    rebuilt = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        rebuilt += f":{parsed.port}"
    rebuilt += parsed.path or "/"
    if parsed.query:
        rebuilt += f"?{parsed.query}"
    rebuilt = validate_fetch_url(rebuilt)
    with httpx.Client(
        timeout=20.0,
        follow_redirects=False,
        headers={"User-Agent": "Holix-Learn/1.0"},
    ) as client:
        resp = client.get(rebuilt)
        resp.raise_for_status()
        return (resp.text or "")[:MAX_SOURCE_CHARS]


def _draft_markdown(*, hint: str, source_label: str, blob: str) -> str:
    excerpt = (blob or "").strip() or hint
    return (
        "## When to Use\n"
        f"When working on: {hint or source_label}\n\n"
        "## Procedure\n"
        "1. Review the source material below and apply the same steps.\n"
        "2. Prefer existing Holix tools over invented commands.\n\n"
        "## Pitfalls\n"
        "- Do not copy transient errors (timeouts, 429) as permanent rules.\n\n"
        "## Verification\n"
        "Confirm the procedure still matches the live tools and docs.\n\n"
        f"## Source ({source_label})\n\n"
        f"{excerpt[:12000]}\n"
    )


def stage_learn_proposal(
    skills_dir: Path | str,
    *,
    hint: str,
    text: str = "",
    path: str = "",
    url: str = "",
    source_session: str = "",
    workspace_root: str | Path | None = None,
    profile: str = "",
) -> dict[str, Any]:
    """Stage a learn-draft. Does not call the LLM (agent /learn does that)."""
    hint = (hint or "").strip()
    blob = (text or "").strip()
    label = "text"
    if path:
        if not workspace_root:
            raise ValueError("path learn requires workspace_root")
        base = os.path.realpath(os.path.expanduser(str(workspace_root)))
        raw = os.path.expanduser(str(path))
        joined = raw if os.path.isabs(raw) else os.path.join(base, raw)
        target = os.path.realpath(joined)
        if target != base and not target.startswith(base + os.sep):
            raise ValueError(f"path escapes {base}: {path}")
        root = Path(target)
        blob = _read_path_blob(root)
        label = str(root)
        hint = hint or root.name
    elif url:
        blob = _read_url(url)
        label = url
        hint = hint or urlparse(url).path.rsplit("/", 1)[-1] or "web-source"
    elif not blob:
        if not hint:
            raise ValueError("provide hint, text, path, or url")
        blob = hint
        label = "hint"

    name = slugify_skill_name(hint) or "learned-skill"
    if name == "learned-skill" and label not in {"text", "hint"}:
        name = slugify_skill_name(Path(label).stem) or name
    from core.skills.lifecycle import resolve_skill_locale
    from core.skills.quality import heuristic_quality

    content = _draft_markdown(hint=hint, source_label=label, blob=blob)
    description = (hint or label)[:80]
    locale = resolve_skill_locale(profile or None)
    store = SkillProposalStore(skills_dir)
    rec = store.stage(
        name=name,
        action="create",
        content=content,
        description=description,
        tags=["learn"],
        origin="learn",
        source_session=source_session,
        reason=f"learn:{label}",
        # Path/URL ingest is not agent-scored — keep below auto-approve.
        quality_score=min(
            45,
            heuristic_quality({"action": "create", "description": description, "content": content}),
        ),
        locale=locale,
    )
    return rec


def learn_turn_prompt(hint: str) -> str:
    return LEARN_TURN_PROMPT.format(hint=(hint or "").strip() or "(this conversation)")
