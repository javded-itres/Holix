"""Gather project handbook + openspec specs for plan generation.

Plan mode is **read-only** for SDD / OpenSpec:
1. Load ``.holix/HOLIX.md`` (if any) and **read** ``openspec/specs`` (if any).
2. If HOLIX.md is missing/empty → run the same pre-scan as ``/init``
   (``scan_project_for_init`` + ``write_init_skeleton``), then re-read HOLIX.md.
   That is the **only** write allowed while building a plan.
3. **Never** call ``sdd_init`` / propose / apply / archive from planning context.
4. Build a single markdown block for the plan prompt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.project.holix_md import (
    DEFAULT_MAX_CHARS,
    holix_md_exists,
    load_holix_md,
    planning_context_note,
    resolve_holix_md_read_path,
)
from core.project.init_scan import (
    format_init_scan_report,
    scan_project_for_init,
    write_init_skeleton,
)
from core.project.instruction_files import format_instruction_files_block

logger = logging.getLogger(__name__)

_SPECS_MAX_CHARS = 16_000
_SPEC_FILE_MAX = 4_000
_SKIP_DIRS = frozenset(
    {
        ".git",
        ".holix",
        ".helix",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".next",
        ".turbo",
        "coverage",
        "target",
        "vendor",
    }
)


@dataclass
class PlanningContext:
    """Result of ensure_planning_context()."""

    handbook_block: str
    holix_present: bool = False
    holix_path: str = ""
    specs_present: bool = False
    specs_paths: list[str] = field(default_factory=list)
    init_ran: bool = False
    scan_summary: str = ""

    def to_meta(self) -> dict[str, Any]:
        return {
            "holix_present": self.holix_present,
            "holix_path": self.holix_path,
            "specs_present": self.specs_present,
            "specs_paths": list(self.specs_paths),
            "init_ran": self.init_ran,
        }


def _workspace_root(cwd: str | Path | None = None) -> Path:
    return (Path(cwd) if cwd else Path.cwd()).expanduser().resolve()


def _is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def discover_openspec_roots(cwd: str | Path | None = None) -> list[Path]:
    """openspec/ at workspace root and one level of subprojects."""
    root = _workspace_root(cwd)
    found: list[Path] = []
    root_os = root / "openspec"
    if _is_dir(root_os):
        found.append(root_os)
    try:
        children = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        children = []
    for child in children:
        if not _is_dir(child):
            continue
        name = child.name
        if name in _SKIP_DIRS or name.startswith("."):
            continue
        nested = child / "openspec"
        if _is_dir(nested):
            found.append(nested)
    return found


def load_openspec_specs_context(
    cwd: str | Path | None = None,
    *,
    max_chars: int = _SPECS_MAX_CHARS,
) -> tuple[str, list[str]]:
    """Load main domain specs under openspec/specs/** as markdown.

    Returns (markdown_block_or_empty, list_of_relative_paths).
    """
    root = _workspace_root(cwd)
    paths: list[Path] = []
    for os_root in discover_openspec_roots(cwd):
        specs_dir = os_root / "specs"
        if not _is_dir(specs_dir):
            continue
        try:
            for path in sorted(specs_dir.rglob("*")):
                if not _is_file(path):
                    continue
                if path.suffix.lower() not in {".md", ".markdown", ".txt"}:
                    continue
                paths.append(path)
        except OSError:
            continue

    if not paths:
        return "", []

    chunks: list[str] = []
    rels: list[str] = []
    used = 0
    for path in paths:
        try:
            rel = str(path.resolve().relative_to(root)).replace("\\", "/")
        except ValueError:
            rel = str(path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if not text:
            continue
        if len(text) > _SPEC_FILE_MAX:
            text = text[:_SPEC_FILE_MAX] + "\n… [truncated]"
        piece = f"### `{rel}`\n\n{text}\n"
        if used + len(piece) > max_chars:
            remaining = max_chars - used
            if remaining > 200:
                chunks.append(piece[:remaining] + "\n… [specs truncated]")
            break
        chunks.append(piece)
        rels.append(rel)
        used += len(piece)

    if not chunks:
        return "", []
    header = (
        "## Project specs (openspec) — read-only reference\n"
        "Treat these as product/requirements source of truth when planning. "
        "Align architecture and steps with them; do not invent conflicting APIs. "
        "Do **not** run `sdd_init` or rewrite openspec during plan generation.\n\n"
    )
    return header + "\n".join(chunks), rels


def load_openspec_layout_summary(cwd: str | Path | None = None) -> str:
    """Short read-only inventory of existing ``openspec/`` trees (no init)."""
    root = _workspace_root(cwd)
    roots = discover_openspec_roots(cwd)
    if not roots:
        return ""
    lines: list[str] = [
        "## OpenSpec layout (read-only)\n",
        "Existing `openspec/` directories found. Plan mode **only reads** this tree; "
        "it does not create or modify SDD layout.\n",
    ]
    for os_root in roots:
        try:
            rel_root = str(os_root.resolve().relative_to(root)).replace("\\", "/")
        except ValueError:
            rel_root = str(os_root)
        lines.append(f"- `{rel_root}/`")
        for sub in ("config.yaml", "specs", "changes"):
            p = os_root / sub
            if sub == "config.yaml":
                if _is_file(p):
                    lines.append("  - config.yaml present")
                continue
            if not _is_dir(p):
                continue
            try:
                children = sorted(c.name for c in p.iterdir() if not c.name.startswith("."))[:12]
            except OSError:
                children = []
            if children:
                shown = ", ".join(f"`{n}`" for n in children)
                more = "" if len(children) < 12 else ", …"
                lines.append(f"  - `{sub}/`: {shown}{more}")
            else:
                lines.append(f"  - `{sub}/` (empty)")
    lines.append("")
    return "\n".join(lines)


def _holix_is_usable(text: str | None) -> bool:
    if not text or not text.strip():
        return False
    # Very thin skeleton still counts as present — we still attach scan if we just created it.
    return len(text.strip()) >= 40


def _run_init_prescan(
    cwd: str | Path | None = None,
    *,
    locale: str = "en",
) -> tuple[bool, str]:
    """Same first half of `/init`: scan repo + seed HOLIX.md skeleton.

    Returns (ran, scan_report_markdown).
    """
    from core.i18n.messages import t
    from core.project.init_prompt import _holix_md_rel_path

    try:
        scan = scan_project_for_init(cwd=cwd)
    except Exception:
        logger.warning("planning_context: init scan failed", exc_info=True)
        return False, ""

    loc = locale if locale in ("en", "ru") else "en"
    try:
        template = t("init.holix_template", loc)
    except Exception:
        template = "# Project handbook\n\n## Overview\n\n"

    holix_rel = _holix_md_rel_path(None)
    try:
        # Only write skeleton if file still missing at workspace root.
        if not holix_md_exists(cwd):
            write_init_skeleton(
                scan,
                holix_rel_path=holix_rel,
                template=template,
                locale=loc,
            )
            logger.info("planning_context: wrote HOLIX.md skeleton via /init pre-scan")
        report = format_init_scan_report(scan, locale=loc)
        return True, report
    except Exception:
        logger.warning("planning_context: write_init_skeleton failed", exc_info=True)
        try:
            return True, format_init_scan_report(scan, locale=loc)
        except Exception:
            return False, ""


def ensure_planning_context(
    cwd: str | Path | None = None,
    *,
    locale: str = "en",
    max_holix_chars: int = DEFAULT_MAX_CHARS,
    agent: object | None = None,
    config: object | None = None,
) -> PlanningContext:
    """Load HOLIX.md + openspec specs; auto-run /init pre-scan when handbook missing.

    Prefer explicit ``cwd`` or agent ``workspace_root`` over process CWD.
    """
    if cwd is None:
        from core.project.workspace_root import resolve_project_root

        root = resolve_project_root(agent=agent, config=config)
        cwd = root
    else:
        root = _workspace_root(cwd)
        cwd = root
    init_ran = False
    scan_summary = ""

    holix_body = load_holix_md(cwd, max_chars=max_holix_chars)
    holix_path_obj = resolve_holix_md_read_path(cwd)

    if not _holix_is_usable(holix_body):
        logger.info(
            "planning_context: HOLIX.md missing/empty under %s — running /init pre-scan",
            root,
        )
        init_ran, scan_summary = _run_init_prescan(cwd, locale=locale)
        # Re-check after /init skeleton
        holix_body = load_holix_md(cwd, max_chars=max_holix_chars)
        holix_path_obj = resolve_holix_md_read_path(cwd)

    specs_block, specs_paths = load_openspec_specs_context(cwd)
    layout_summary = load_openspec_layout_summary(cwd)
    instruction_block = format_instruction_files_block(cwd)

    parts: list[str] = [planning_context_note(), ""]

    if holix_body and holix_path_obj is not None:
        try:
            rel = str(holix_path_obj.resolve().relative_to(root)).replace("\\", "/")
        except ValueError:
            rel = str(holix_path_obj)
        parts.append(f"## Project knowledge (`{rel}`)")
        if init_ran:
            parts.append(
                "_HOLIX.md was missing — ran `/init` pre-scan and re-loaded the handbook. "
                "Base the plan on this document and the scan summary below. "
                "This is not SDD init._"
            )
        else:
            parts.append(
                "_Use this handbook as the primary source of truth for architecture, "
                "modules, APIs, and conventions._"
            )
        parts.append("")
        parts.append(holix_body)
        parts.append("")
    elif scan_summary:
        parts.append("## Project knowledge")
        parts.append(
            "_No HOLIX.md was available even after `/init` pre-scan. "
            "Use the scan summary as the project map._"
        )
        parts.append("")

    if instruction_block:
        parts.append(instruction_block)
        parts.append("")

    if scan_summary:
        parts.append("## `/init` project scan")
        parts.append(
            "_Deterministic repo survey (same data `/init` uses before filling HOLIX.md). "
            "No `openspec/` layout was created by this step._"
        )
        parts.append("")
        parts.append(scan_summary)
        parts.append("")

    if specs_block:
        parts.append(specs_block)
        parts.append("")
    elif layout_summary:
        parts.append(layout_summary)
        parts.append(
            "_No domain specs under `openspec/specs/` yet. Continue planning from "
            "HOLIX.md / task only. **Do not** call `sdd_init` from plan mode._\n"
        )
    else:
        parts.append(
            "## Project specs (openspec)\n"
            "_No `openspec/` tree found. Plan from HOLIX.md and the task only. "
            "**Do not** call `sdd_init` during plan mode. SDD/Specs setup is a "
            "separate user action outside plan generation._\n"
        )

    handbook = "\n".join(parts).strip()
    return PlanningContext(
        handbook_block=handbook,
        holix_present=bool(holix_body),
        holix_path=(
            str(holix_path_obj.resolve().relative_to(root)).replace("\\", "/")
            if holix_path_obj is not None
            else ""
        ),
        specs_present=bool(specs_paths),
        specs_paths=specs_paths,
        init_ran=init_ran,
        scan_summary=scan_summary,
    )
