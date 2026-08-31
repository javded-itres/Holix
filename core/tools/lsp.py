"""Language-server queries for the coding agent (multi-language)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.tools.base import BaseTool
from core.tools.execution_context import get_workspace_root
from core.tools.lsp_servers import (
    hints_for_path,
    language_id_for,
    ready_titles,
    resolve_lsp,
    status_rows,
)
from core.tools.result import tool_err, tool_ok
from core.workspace import WorkspaceJailError, display_path_for_user, resolve_tool_path

_ACTIONS = {
    "definition",
    "references",
    "implementation",
    "hover",
    "diagnostics",
    "symbols",
    "status",
}


class LspTool(BaseTool):
    """Go-to-definition / references / hover via installed language servers."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "lsp"
        self.description = (
            "Navigate code via the language server. For architecture / how code "
            "connects use symbols, hover, definition, references, implementation "
            "(path + line + character). Do not substitute a diagnostics sweep or "
            "read_file dumps. diagnostics is for one known file after navigation. "
            "status lists ready servers. Python: Pyright, then basedpyright/pylsp/"
            "jedi; also JS/TS, Go, Rust, JSON/HTML/CSS, YAML, Bash, …. Missing "
            "server → lsp_unavailable with install hints; fall back to grep. "
            "Run holix lsp setup / holix doctor to install packages."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "additionalProperties": False,
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": sorted(_ACTIONS),
                },
                "path": {"type": "string"},
                "line": {"type": "integer", "minimum": 1},
                "character": {"type": "integer", "minimum": 0},
                "query": {"type": "string"},
                "language": {"type": "string"},
            },
        }

    async def execute(
        self,
        action: str,
        path: str = "",
        line: int = 1,
        character: int = 0,
        query: str = "",
        language: str = "",
        **_: Any,
    ) -> str:
        act = str(action or "").strip().lower()
        if act not in _ACTIONS:
            return tool_err("invalid_action", f"unknown action {action!r}", fallback="grep")
        if act == "status":
            rows = status_rows()
            return tool_ok(
                action="status",
                ready=[r["title"] for r in rows if r["ready"]],
                servers=rows,
            )

        raw_path = (path or "").strip()
        if not raw_path:
            return tool_err("missing_path", "path is required", fallback="grep")
        try:
            file_path = resolve_tool_path(raw_path)
        except WorkspaceJailError as exc:
            return tool_err("jail", str(exc), fallback="grep")
        display = display_path_for_user(file_path, input_path=raw_path)
        if not file_path.is_file():
            return tool_err(
                "not_found",
                f"file '{display}' does not exist",
                fallback="grep",
            )
        try:
            source = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            return tool_err("io", str(exc), fallback="grep")

        resolved = resolve_lsp(file_path, language)
        lang = language_id_for(file_path, language)
        if resolved is None:
            return tool_err(
                "lsp_unavailable",
                "No language server is configured for this file. "
                "Install packages via: holix lsp setup",
                fallback="grep",
                language=lang,
                install=hints_for_path(file_path, language),
                ready=ready_titles(),
            )

        try:
            if resolved.kind == "jedi":
                from core.tools.lsp_jedi import query_jedi

                payload = query_jedi(
                    file_path,
                    source,
                    action=act,
                    line=line,
                    character=character,
                    query=query,
                )
            else:
                from core.tools.lsp_rpc import query_language_server

                root = _workspace_root(file_path)
                payload = await query_language_server(
                    resolved,
                    root=root,
                    file_path=file_path,
                    source=source,
                    action=act,
                    line=line,
                    character=character,
                    query=query,
                )
        except Exception as exc:
            err = str(exc).strip() or type(exc).__name__
            return tool_err(
                "lsp_error",
                err,
                fallback="grep",
                language=lang,
                server=resolved.spec.id,
            )
        return tool_ok(
            action=act,
            path=display,
            language=lang,
            server=resolved.spec.id,
            **payload,
        )


def _workspace_root(file_path: Path) -> Path:
    raw = (get_workspace_root() or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return file_path.parent.resolve()
