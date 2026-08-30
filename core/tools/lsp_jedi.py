"""In-process Python LSP-like queries via jedi."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def query_jedi(
    file_path: Path,
    source: str,
    *,
    action: str,
    line: int,
    character: int,
    query: str = "",
) -> dict[str, Any]:
    import jedi

    script = jedi.Script(code=source, path=str(file_path))
    line_n = max(1, int(line or 1))
    col = max(0, int(character or 0))
    items: list[dict[str, Any]] = []

    if action == "hover":
        names = script.help(line=line_n, column=col) or script.infer(line=line_n, column=col)
        for name in names[:8]:
            items.append(
                {
                    "name": str(getattr(name, "name", "") or ""),
                    "doc": str(getattr(name, "docstring", lambda: "")() or "")[:400],
                }
            )
    elif action in {"definition", "implementation"}:
        for name in script.goto(line=line_n, column=col, follow_imports=True)[:12]:
            items.append(_jedi_loc(name))
    elif action == "references":
        for name in script.get_references(line=line_n, column=col)[:20]:
            items.append(_jedi_loc(name))
    elif action in {"diagnostics", "symbols"}:
        needle = (query or "").strip().lower()
        for name in script.get_names(all_scopes=True, definitions=True)[:40]:
            row = _jedi_loc(name)
            if needle and needle not in str(row.get("name") or "").lower():
                continue
            items.append(row)
    else:
        raise ValueError(f"unsupported action {action}")
    return {"items": items}


def _jedi_loc(name: Any) -> dict[str, Any]:
    module_path = getattr(name, "module_path", None)
    return {
        "name": str(getattr(name, "name", "") or ""),
        "path": str(module_path) if module_path else "",
        "line": int(getattr(name, "line", 0) or 0),
        "column": int(getattr(name, "column", 0) or 0),
        "type": str(getattr(name, "type", "") or ""),
    }
