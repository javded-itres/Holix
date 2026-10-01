"""Show configured image/video model notes in messenger chat only on opt-in.

The ``describe_media_model`` tool returns a block that starts with
``Configured image models:`` or ``Configured video models:``. That text stays
out of Telegram and MAX unless the user turns on extended mode in the status
menu. The flag is per profile and defaults to off.
"""

from __future__ import annotations

import re
from typing import Any

_HEADING_RE = re.compile(
    r"^(?:[#>*\s-]*)(?:\*\*|__)?\s*"
    r"Configured (image models|video models|models)\s*:"
    r"(?:\*\*|__)?\s*$",
    re.IGNORECASE,
)
_CARD_LINE_RE = re.compile(
    r"^(?:"
    r"kind: .*"
    r"|provider: .*"
    r"|type: .*"
    r"|model: .*"
    r"|note: .*"
    r"|accepts_reference: .*"
    r"|parameters from the model catalog:"
    r"|parameters:"
    r"|The catalog did not list parameters\..*"
    r"|Use only these parameters\..*"
    r"|hub mode: .*"
    r"|hub supported_generation: .*"
    r"|hub upstream: .*"
    r"|hub model card: .*"
    r"|last generation:"
    r"|To revise that result,.*"
    r"|\(none\)"
    r")$",
    re.IGNORECASE,
)
_FENCE_RE = re.compile(r"^\s*```")


def media_models_visible_for_profile(profile: str | None) -> bool:
    """True only when this profile explicitly opted in. Unset means off."""
    name = str(profile or "").strip()
    if not name:
        return False
    try:
        from cli.core import get_profile_manager

        cfg = get_profile_manager().load_profile(name)
    except Exception:
        return False
    return bool(getattr(cfg, "show_media_models_in_chat", None))


def set_media_models_visible_for_host(host: Any, enabled: bool) -> bool:
    """Persist the opt-in on the host profile. Returns the stored flag."""
    enabled = bool(enabled)
    profile = str(getattr(host, "profile", None) or "").strip()
    if not profile:
        raise ValueError("No active profile to update show_media_models_in_chat")

    from cli.core import get_profile_manager

    manager = get_profile_manager()
    cfg = manager.load_profile(profile)
    cfg.show_media_models_in_chat = enabled
    manager.save_profile(profile, cfg)
    return enabled


def filter_media_model_tool_notice(tool_name: str, body: str, *, visible: bool) -> str:
    """Drop generation-model dumps from a live tool notice.

    The chat copy is attached to the final answer, and only in extended mode.
    """
    text = body or ""
    if (tool_name or "").strip() == "describe_media_model":
        return ""
    if visible:
        return text
    return strip_configured_media_blocks(text)


def shape_media_models_chat(
    content: str,
    *,
    visible: bool,
    recent_tool_results: list[dict[str, Any]] | None = None,
) -> str:
    """Hide model lists, or append the tool's list once when the user opted in.

    Safe to call twice: a list already appended is stripped and added back once.
    """
    raw = content or ""
    if not visible:
        return strip_configured_media_blocks(raw).strip()

    kept = strip_configured_media_blocks(raw, kinds=("image models", "video models")).strip()
    blocks = _detail_blocks(recent_tool_results)
    if not blocks:
        blocks = _extract_blocks(raw, kinds=("image models", "video models"))
    extra = [block for block in blocks if block not in kept]
    if not extra:
        return kept
    if not kept:
        return "\n\n".join(extra)
    return kept + "\n\n" + "\n\n".join(extra)


def strip_configured_media_blocks(
    text: str,
    *,
    kinds: tuple[str, ...] | None = None,
) -> str:
    """Remove configured-model sections. ``kinds`` limits which headings match."""
    if not text or not _heading_present(text, kinds):
        return text
    lines = text.split("\n")
    kept: list[str] = []
    index = 0
    while index < len(lines):
        fence = _fenced_block_end(lines, index, kinds)
        if fence is not None:
            index = fence
            continue
        if _is_heading(lines[index], kinds):
            index = _block_end(lines, index)
            continue
        kept.append(lines[index])
        index += 1
    return _collapse_blank_lines("\n".join(kept))


def _detail_blocks(recent: list[dict[str, Any]] | None) -> list[str]:
    found: list[str] = []
    for entry in recent or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("name") or "").strip() != "describe_media_model":
            continue
        body = str(entry.get("full_result") or "")
        for block in _extract_blocks(body, kinds=("image models", "video models")):
            if block not in found:
                found.append(block)
    return found


def _extract_blocks(text: str, *, kinds: tuple[str, ...] | None) -> list[str]:
    if not text:
        return []
    lines = text.split("\n")
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        if not _is_heading(lines[index], kinds):
            index += 1
            continue
        end = _block_end(lines, index)
        block = "\n".join(lines[index:end]).strip()
        if block and block not in blocks:
            blocks.append(block)
        index = end
    return blocks


def _heading_present(text: str, kinds: tuple[str, ...] | None) -> bool:
    return any(_is_heading(line, kinds) for line in text.split("\n"))


def _is_heading(line: str, kinds: tuple[str, ...] | None) -> bool:
    match = _HEADING_RE.match(line.strip())
    if match is None:
        return False
    if kinds is None:
        return True
    return match.group(1).lower() in {kind.lower() for kind in kinds}


def _is_block_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or _HEADING_RE.match(stripped):
        return True
    if _CARD_LINE_RE.match(stripped):
        return True
    if stripped.startswith("- ") and ("model=" in stripped or "(" in stripped):
        return True
    if line.startswith("  ") and ":" in stripped:
        return True
    return False


def _block_end(lines: list[str], heading_index: int) -> int:
    """Index of the first line that is not part of the model block."""
    index = heading_index + 1
    last_content = index
    while index < len(lines):
        if _FENCE_RE.match(lines[index]):
            break
        if lines[index].strip() == "":
            index += 1
            continue
        if _is_block_line(lines[index]):
            index += 1
            last_content = index
            continue
        break
    return last_content


def _fenced_block_end(
    lines: list[str],
    index: int,
    kinds: tuple[str, ...] | None,
) -> int | None:
    if not _FENCE_RE.match(lines[index]):
        return None
    body_start = index + 1
    while body_start < len(lines) and lines[body_start].strip() == "":
        body_start += 1
    if body_start >= len(lines) or not _is_heading(lines[body_start], kinds):
        return None
    end = body_start + 1
    while end < len(lines) and not _FENCE_RE.match(lines[end]):
        end += 1
    if end < len(lines):
        end += 1
    return end


def _collapse_blank_lines(text: str) -> str:
    collapsed = re.sub(r"\n{3,}", "\n\n", text)
    return collapsed.strip("\n")
