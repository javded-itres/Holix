"""Generate the Python SDK block shown to the model in Code mode."""

from __future__ import annotations

from typing import Any

from core.tools.code_mode.policy import RUN_CODE_NAME, is_forbidden_in_program

_INSTRUCTIONS = """## Writing code for run_code

`run_code` takes two required arguments: `code` (the body of a Python function; \
type comments are ignored) and `description` (short summary for the UI).

Inside the program:

- Call tools as `tools.name(arg=value)` — quoted access for exotic names: \
`tools["my-tool"](arg=value)`. The name `tools` is already bound; do not \
pip-install it. `import tools` / `from tools import name` alias the same \
object. Calls are synchronous. Failed tools raise \
`ToolCallError` with `.tool_name` and `.message` — catch to continue.
- Sequence dependent work with ordinary Python. Independent read-only tools \
may run together: `tools.parallel(("read_file", {"path": "a"}), \
("grep", {"pattern": "TODO", "path": "."}))` returns a list of results. \
Writes and other mutating calls stay one-at-a-time.
- Edit existing files with `tools.patch_file(path=..., old_string=..., \
new_string=...)` or `replacements=[{"old_string": "...", "new_string": \
"..."}]`. Use `tools.write_file` only to create a new file or replace the \
entire contents — do not rewrite a module to change a few lines.
- Emit results with `return` and/or `print(...)`. ONLY what you print or return \
comes back — intermediate tool results are not added to the conversation, so \
extract just what you need.
- Relative paths (`.`, `src/foo`) and `run_terminal_command` start in the \
profile workspace (see the path below). Use an absolute path only when you \
mean a different tree. Persistent servers go through \
`tools.start_background_process(...)`, not `run_terminal_command`.
- Do not `import os`, `subprocess`, `pathlib`, `sys`, `socket`, or HTTP \
clients. File and shell work goes through `tools.*`. Probe a local server \
with `tools.run_terminal_command(command="curl -sS http://127.0.0.1:PORT/...")` \
— `fetch_url` / browser tools reject localhost. `2>/dev/null` redirects are allowed.

The available tools:"""


def _schema_signature(schema: dict[str, Any]) -> str:
    fn = schema.get("function") if isinstance(schema, dict) else None
    if not isinstance(fn, dict):
        return ""
    name = str(fn.get("name") or "").strip()
    if not name:
        return ""
    desc = str(fn.get("description") or "").strip().replace("\n", " ")
    params = fn.get("parameters") if isinstance(fn.get("parameters"), dict) else {}
    props = params.get("properties") if isinstance(params.get("properties"), dict) else {}
    required = {str(x) for x in (params.get("required") or []) if str(x).strip()}
    parts: list[str] = []
    for key in sorted(props):
        spec = props[key] if isinstance(props[key], dict) else {}
        typ = str(spec.get("type") or "any")
        if key in required:
            parts.append(f"{key}: {typ}")
        else:
            parts.append(f"{key}: {typ} | None = None")
    sig = ", ".join(parts)
    line = f"- **{name}**({sig})"
    if desc:
        line += f": {desc[:240]}"
    return line


def end_tool_schemas(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Schemas the SDK may bind — never `run_code` or forbidden tools."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for schema in schemas:
        fn = schema.get("function") if isinstance(schema, dict) else None
        if not isinstance(fn, dict):
            continue
        name = str(fn.get("name") or "").strip()
        if not name or name in seen:
            continue
        if name == RUN_CODE_NAME or is_forbidden_in_program(name):
            continue
        seen.add(name)
        out.append(schema)
    out.sort(key=lambda s: str((s.get("function") or {}).get("name") or ""))
    return out


def build_sdk_text(schemas: list[dict[str, Any]]) -> str:
    lines = [_schema_signature(s) for s in end_tool_schemas(schemas)]
    body = "\n".join(line for line in lines if line) or "- (no tools visible in this scope)"
    return body


def build_code_mode_prompt_section(
    schemas: list[dict[str, Any]],
    *,
    workspace_root: str | None = None,
) -> str:
    extra = ""
    root = str(workspace_root or "").strip()
    if root:
        extra = f"\nProfile workspace: `{root}`.\n"
    marker = "The available tools:"
    if marker in _INSTRUCTIONS:
        head, tail = _INSTRUCTIONS.rsplit(marker, 1)
        return head + extra + marker + tail + "\n\n" + build_sdk_text(schemas)
    return _INSTRUCTIONS + extra + "\n\n" + build_sdk_text(schemas)
