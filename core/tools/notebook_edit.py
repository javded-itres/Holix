"""Edit a cell in a Jupyter notebook (.ipynb) inside the workspace jail."""

from __future__ import annotations

import json
import uuid
from typing import Any

from core.crypto.profile_crypto import ProfileCryptoLockedError
from core.tools.base import BaseTool
from core.tools.execution_context import get_profile_name
from core.tools.result import tool_err, tool_ok
from core.workspace import WorkspaceJailError, display_path_for_user, resolve_tool_path
from core.workspace.quota import WorkspaceQuotaExceeded
from core.workspace.storage import format_quota_error, write_profile_file_text


class NotebookEditTool(BaseTool):
    """Replace, insert, or delete a cell in a .ipynb notebook."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "notebook_edit"
        self.description = (
            "Edit a Jupyter notebook (.ipynb) cell. Resolve by cell_id first, "
            "else cell_index. replace/insert require source. Preserves notebook "
            "metadata and other cell outputs unless that cell is replaced."
        )
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "additionalProperties": False,
            "required": ["path", "edit_mode"],
            "properties": {
                "path": {"type": "string"},
                "cell_id": {"type": "string"},
                "cell_index": {"type": "integer", "minimum": 0},
                "edit_mode": {
                    "type": "string",
                    "enum": ["replace", "insert", "delete"],
                },
                "cell_type": {
                    "type": "string",
                    "enum": ["code", "markdown", "raw"],
                },
                "source": {"type": "string"},
            },
        }

    async def execute(
        self,
        path: str,
        edit_mode: str,
        cell_id: str = "",
        cell_index: int | None = None,
        cell_type: str = "code",
        source: str = "",
        **_: Any,
    ) -> str:
        mode = str(edit_mode or "").strip().lower()
        if mode not in {"replace", "insert", "delete"}:
            return tool_err("invalid_mode", f"unknown edit_mode {edit_mode!r}")
        raw_path = (path or "").strip()
        if not raw_path:
            return tool_err("missing_path", "path is required")
        try:
            file_path = resolve_tool_path(raw_path)
        except WorkspaceJailError as exc:
            return tool_err("jail", str(exc))
        display = display_path_for_user(file_path, input_path=raw_path)
        if file_path.suffix.lower() != ".ipynb":
            return tool_err("not_notebook", "only .ipynb files are allowed", path=display)
        if not file_path.is_file():
            return tool_err("not_found", f"notebook '{display}' does not exist", path=display)

        try:
            text = file_path.read_text(encoding="utf-8")
            nb = json.loads(text)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return tool_err("invalid_notebook", f"could not parse notebook JSON: {exc}")
        if not isinstance(nb, dict) or not isinstance(nb.get("cells"), list):
            return tool_err("invalid_notebook", "notebook is missing a cells array")

        cells: list[Any] = nb["cells"]
        index: int | None = None
        cid = (cell_id or "").strip()
        if cid:
            for i, cell in enumerate(cells):
                if isinstance(cell, dict) and str(cell.get("id") or "") == cid:
                    index = i
                    break
            if index is None:
                return tool_err("not_found", f"cell_id '{cid}' not found", path=display)
        elif cell_index is not None:
            index = int(cell_index)
            if index < 0 or index > len(cells) or (mode != "insert" and index >= len(cells)):
                return tool_err(
                    "bad_index",
                    f"cell_index {index} out of range (n={len(cells)})",
                    path=display,
                )
        else:
            return tool_err("missing_cell", "pass cell_id or cell_index")

        if mode in {"replace", "insert"} and source is None:
            return tool_err("missing_source", "replace/insert require source")
        if mode in {"replace", "insert"} and not isinstance(source, str):
            return tool_err("missing_source", "replace/insert require source")

        ctype = str(cell_type or "code").strip().lower() or "code"
        if ctype not in {"code", "markdown", "raw"}:
            ctype = "code"

        if mode == "delete":
            if index is None or index >= len(cells):
                return tool_err("bad_index", "delete requires a valid cell index")
            cells.pop(index)
        elif mode == "insert":
            at = 0 if index is None else index
            at = max(0, min(at, len(cells)))
            new_cell = {
                "cell_type": ctype,
                "metadata": {},
                "source": _as_source_lines(source),
                "id": uuid.uuid4().hex[:8],
            }
            if ctype == "code":
                new_cell["outputs"] = []
                new_cell["execution_count"] = None
            cells.insert(at, new_cell)
            index = at
        else:
            if index is None or index >= len(cells):
                return tool_err("bad_index", "replace requires a valid cell index")
            cell = cells[index]
            if not isinstance(cell, dict):
                return tool_err("invalid_notebook", "cell is not an object")
            cell["source"] = _as_source_lines(source)
            if ctype:
                cell["cell_type"] = ctype
            if cell.get("cell_type") == "code":
                cell["outputs"] = []
                cell["execution_count"] = None

        try:
            dumped = json.dumps(nb, ensure_ascii=False, indent=1)
            json.loads(dumped)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return tool_err("invalid_notebook", f"notebook JSON invalid after edit: {exc}")

        try:
            write_profile_file_text(file_path, dumped + "\n", profile=get_profile_name())
        except WorkspaceQuotaExceeded as exc:
            return format_quota_error(exc)
        except WorkspaceJailError as exc:
            return tool_err("jail", str(exc))
        except ProfileCryptoLockedError as exc:
            return tool_err("crypto_locked", str(exc))
        except OSError as exc:
            return tool_err("io", str(exc))

        return tool_ok(
            path=display,
            edit_mode=mode,
            cell_index=index,
            cells=len(cells),
        )


def _as_source_lines(source: str) -> list[str]:
    text = source if source.endswith("\n") or source == "" else source + "\n"
    if not text:
        return []
    lines = text.splitlines(keepends=True)
    return lines
