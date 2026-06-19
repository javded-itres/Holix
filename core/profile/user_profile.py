"""User profile persisted in ``USER.md`` and strategic memory."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from core.env_loader import profile_dir_path

USER_MD_FILENAME = "USER.md"
DEFAULT_MAX_CHARS = 8000


def user_path(profile: str | None = None) -> Path:
    from core.profile.names import validate_profile_name

    return profile_dir_path(validate_profile_name(profile)) / USER_MD_FILENAME


def _read_user_raw(profile: str | None = None) -> str:
    path = user_path(profile)
    if not path.is_file():
        return ""
    try:
        from core.crypto.profile_files import read_profile_file_text

        name = (profile or "default").strip() or "default"
        return read_profile_file_text(path, profile=name).strip()
    except OSError:
        return ""


def user_profile_exists(profile: str | None = None) -> bool:
    return bool(_read_user_raw(profile))


def load_user_md(profile: str | None = None, *, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    text = _read_user_raw(profile)
    if not text:
        return ""
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n… [truncated]"
    return text


def format_user_block(profile: str | None = None) -> str:
    body = load_user_md(profile)
    if not body:
        return ""
    name = (profile or "default").strip() or "default"
    return (
        f"## User profile (profiles/{name}/{USER_MD_FILENAME})\n"
        "Persistent facts about the human you assist. Follow these preferences.\n\n"
        f"{body}"
    )


def _format_user_markdown(fields: dict[str, str]) -> str:
    lines = ["# User profile", ""]
    identity: list[str] = []
    if fields.get("name"):
        identity.append(f"- **Name:** {fields['name']}")
    if fields.get("preferred_name"):
        identity.append(f"- **Preferred address:** {fields['preferred_name']}")
    if identity:
        lines.extend(["## Identity", *identity, ""])

    if fields.get("work_style"):
        lines.extend(["## Working style", fields["work_style"], ""])

    if fields.get("language_preference"):
        lines.extend(["## Language", fields["language_preference"], ""])

    if fields.get("notes"):
        lines.extend(["## Notes", fields["notes"], ""])

    return "\n".join(lines).strip() + "\n"


def _parse_user_fields(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("- **Name:**"):
            out["name"] = line.split(":", 1)[1].strip()
        elif line.startswith("- **Preferred address:**"):
            out["preferred_name"] = line.split(":", 1)[1].strip()
    if "## Working style" in text:
        part = text.split("## Working style", 1)[1]
        chunk = part.split("##", 1)[0].strip()
        if chunk:
            out["work_style"] = chunk
    if "## Language" in text:
        part = text.split("## Language", 1)[1]
        chunk = part.split("##", 1)[0].strip()
        if chunk:
            out["language_preference"] = chunk
    if "## Notes" in text:
        out["notes"] = text.split("## Notes", 1)[1].strip()
    return out


def update_user_profile(
    profile: str | None = None,
    *,
    name: str | None = None,
    preferred_name: str | None = None,
    work_style: str | None = None,
    language_preference: str | None = None,
    notes: str | None = None,
    append_notes: bool = False,
) -> tuple[str, dict[str, str]]:
    """Merge user fields into USER.md. Returns (action, merged_fields)."""
    path = user_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)

    merged = _parse_user_fields(_read_user_raw(profile))
    for key, val in (
        ("name", name),
        ("preferred_name", preferred_name),
        ("work_style", work_style),
        ("language_preference", language_preference),
    ):
        if val and str(val).strip():
            merged[key] = str(val).strip()

    if notes and str(notes).strip():
        note_text = str(notes).strip()
        if append_notes and merged.get("notes"):
            merged["notes"] = f"{merged['notes']}\n\n{note_text}"
        else:
            merged["notes"] = note_text

    action = "created" if not path.is_file() else "updated"
    from core.crypto.profile_files import write_profile_file_text

    name = (profile or "default").strip() or "default"
    write_profile_file_text(path, _format_user_markdown(merged), profile=name)
    return action, merged


async def sync_user_to_strategic_memory(
    profile: str,
    fields: dict[str, str],
    *,
    source: str = "onboarding",
) -> None:
    """Mirror key user facts into strategic LTM for semantic recall."""
    from core.tools.execution_context import get_memory_facade

    facade = get_memory_facade()
    if facade is None or not getattr(facade.config, "enable_long_term_memory", True):
        return
    try:
        strategic = facade.strategic
    except RuntimeError:
        return

    if fields.get("name"):
        await strategic.store_strategy(
            key="user_display_name",
            content=fields["name"],
            category="user_profile",
            source=source,
            metadata={"profile": profile},
        )
    if fields.get("preferred_name"):
        await strategic.store_strategy(
            key="user_preferred_address",
            content=fields["preferred_name"],
            category="user_profile",
            source=source,
            metadata={"profile": profile},
        )
    if fields.get("work_style"):
        await strategic.store_strategy(
            key="user_work_style",
            content=fields["work_style"],
            category="user_profile",
            source=source,
            metadata={"profile": profile},
        )
    if fields.get("language_preference"):
        await strategic.store_strategy(
            key="user_language_preference",
            content=fields["language_preference"],
            category="user_profile",
            source=source,
            metadata={"profile": profile},
        )
    if fields.get("notes"):
        await strategic.store_strategy(
            key="user_notes",
            content=fields["notes"][:2000],
            category="user_profile",
            source=source,
            metadata={"profile": profile},
        )

    summary_bits = [f"{k}: {v}" for k, v in fields.items() if v]
    if summary_bits:
        await strategic.store_strategy(
            key="user_profile_summary",
            content="; ".join(summary_bits)[:1500],
            category="user_profile",
            source=source,
            metadata={"profile": profile, "fields": json.dumps(fields, ensure_ascii=False)},
        )


async def record_onboarding_episode(profile: str, summary: str) -> None:
    from core.tools.execution_context import get_memory_facade

    facade = get_memory_facade()
    if facade is None:
        return
    try:
        await facade.episodic.store_episode(
            f"profile:{profile}:onboarding",
            summary,
            "success",
            metadata={
                "type": "onboarding",
                "profile": profile,
                "completed_at": datetime.now(UTC).isoformat(),
            },
        )
    except Exception:
        pass