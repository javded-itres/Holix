"""Optional language-server helpers (Python via jedi; otherwise a structured stub)."""

from __future__ import annotations

from typing import Any

from core.tools.base import BaseTool
from core.tools.result import tool_err, tool_ok
from core.workspace import WorkspaceJailError, display_path_for_user, resolve_tool_path

_UNAVAILABLE = tool_err(
    "lsp_unavailable",
    "No language server is configured. Use grep to find symbols.",
    fallback="grep",
)


class LspTool(BaseTool):
    """Go-to-definition / references / hover when a language server is available."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "lsp"
        self.description = (
            "Language-server queries: definition, references, implementation, "
            "hover, diagnostics, symbols. Python-only via jedi when installed; "
            "otherwise returns lsp_unavailable and suggests grep."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "additionalProperties": False,
            "required": ["action", "path"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "definition",
                        "references",
                        "implementation",
                        "hover",
                        "diagnostics",
                        "symbols",
                    ],
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
        path: str,
        line: int = 1,
        character: int = 0,
        query: str = "",
        language: str = "",
        **_: Any,
    ) -> str:
        act = str(action or "").strip().lower()
        if act not in {
            "definition",
            "references",
            "implementation",
            "hover",
            "diagnostics",
            "symbols",
        }:
            return tool_err("invalid_action", f"unknown action {action!r}", fallback="grep")
        try:
            file_path = resolve_tool_path(path)
        except WorkspaceJailError as exc:
            return tool_err("jail", str(exc), fallback="grep")
        display = display_path_for_user(file_path, input_path=path)
        lang = (language or file_path.suffix.lstrip(".")).lower()
        if lang not in {"py", "python", ""} and file_path.suffix.lower() != ".py":
            return _UNAVAILABLE

        try:
            import jedi
        except ImportError:
            return _UNAVAILABLE

        if not file_path.is_file():
            return tool_err("not_found", f"file '{display}' does not exist", fallback="grep")
        try:
            source = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            return tool_err("io", str(exc), fallback="grep")

        script = jedi.Script(code=source, path=str(file_path))
        line_n = max(1, int(line or 1))
        col = max(0, int(character or 0))
        items: list[dict[str, Any]] = []

        try:
            if act == "hover":
                names = script.help(line=line_n, column=col) or script.infer(
                    line=line_n, column=col
                )
                for name in names[:8]:
                    items.append(
                        {
                            "name": str(getattr(name, "name", "") or ""),
                            "doc": str(getattr(name, "docstring", lambda: "")() or "")[:400],
                        }
                    )
            elif act == "definition" or act == "implementation":
                for name in script.goto(line=line_n, column=col, follow_imports=True)[:12]:
                    items.append(_jedi_loc(name))
            elif act == "references":
                for name in script.get_references(line=line_n, column=col)[:20]:
                    items.append(_jedi_loc(name))
            elif act in {"diagnostics", "symbols"}:
                needle = (query or "").strip().lower()
                for name in script.get_names(all_scopes=True, definitions=True)[:40]:
                    row = _jedi_loc(name)
                    if needle and needle not in str(row.get("name") or "").lower():
                        continue
                    items.append(row)
        except Exception as exc:
            return tool_err("lsp_error", str(exc), fallback="grep")

        return tool_ok(action=act, path=display, items=items)


def _jedi_loc(name: Any) -> dict[str, Any]:
    module_path = getattr(name, "module_path", None)
    return {
        "name": str(getattr(name, "name", "") or ""),
        "path": str(module_path) if module_path else "",
        "line": int(getattr(name, "line", 0) or 0),
        "column": int(getattr(name, "column", 0) or 0),
        "type": str(getattr(name, "type", "") or ""),
    }
