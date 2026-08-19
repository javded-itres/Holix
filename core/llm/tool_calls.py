"""Parse tool calls leaked as assistant text (Qwen / Hermes / XML).

Local Qwen backends often emit ``<tool_call>…`` (or the bare word
``tool_call``) in ``message.content`` instead of OpenAI ``tool_calls``.
Holix only executes structured calls — recover them here.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

LEAKED_TOOL_NUDGE = (
    "STOP. You printed a textual <tool_call> block. That is not executed. "
    "Do not write XML, JSON fences, or </tool_call>. "
    "Call the tool through the function-calling API on this turn "
    "(the next request forces a native tool call). "
    "If the work is already done, reply in plain text with no tool_call markup."
)

_TOOL_BLOCK_RE = re.compile(
    r"<tool_call\b[^>]*>([\s\S]*?)</tool_call>",
    re.IGNORECASE,
)
_FUNCTION_XML_RE = re.compile(
    r"<function\s*=\s*([^\s>]+)>([\s\S]*?)</function>",
    re.IGNORECASE,
)
_PARAM_XML_RE = re.compile(
    r"<parameter\s*=\s*([^>]+)>([\s\S]*?)</parameter>",
    re.IGNORECASE,
)
_ARG_KV_RE = re.compile(
    r"<arg_key>\s*([^<]+?)\s*</arg_key>\s*<arg_value>([\s\S]*?)</arg_value>",
    re.IGNORECASE,
)
_BARE_TOOL_LINE_RE = re.compile(r"(?im)^\s*<?/?tool_call>?\s*$")
_LEAK_MARKUP_RE = re.compile(
    r"(?is)(</?tool_call\b|<function\s*=|<parameter\s*=|\btool_calls?\b)",
)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-.]{0,80}$")


def looks_like_leaked_tool_markup(text: str | None) -> bool:
    """True when content contains a textual tool-call fence or token."""
    return bool(_LEAK_MARKUP_RE.search(text or ""))


def strip_tool_call_markup(text: str | None) -> str:
    """Remove tool-call fences so leftover prose can stay as assistant text."""
    if not text:
        return ""
    cleaned = _TOOL_BLOCK_RE.sub("", str(text))
    cleaned = re.sub(r"(?is)</?tool_call\b[^>]*>", "", cleaned)
    cleaned = re.sub(r"(?is)<function\s*=[^>]*>[\s\S]*?</function>", "", cleaned)
    cleaned = _BARE_TOOL_LINE_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


@dataclass(slots=True)
class TextualTurn:
    """How a sub-agent should treat assistant text that may leak tool XML."""

    kind: str  # tools | retry | final
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    final_text: str = ""
    nudge: str = ""


def resolve_textual_turn(
    content: str | None,
    *,
    tools: list[Any] | None = None,
    force_final: bool = False,
) -> TextualTurn:
    """Recover leaked Qwen/Hermes tool XML, or refuse to treat it as a finish.

    - ``tools``: parseable leaked calls — execute them (unless ``force_final``).
    - ``retry``: markup / degeneration without a usable call — do not finish.
    - ``final``: plain text that may be the sub-agent result.
    """
    text = str(content or "")
    calls = extract_textual_tool_calls(text, tools=tools)
    leak = looks_like_leaked_tool_markup(text)
    degenerate = False
    try:
        from core.llm.response_text import is_pathological_repetition

        degenerate = is_pathological_repetition(text, min_repeats=3)
    except Exception:
        degenerate = False

    if calls and not force_final:
        return TextualTurn(
            kind="tools",
            tool_calls=calls,
            final_text=strip_tool_call_markup(text),
        )
    if leak or degenerate:
        visible = strip_tool_call_markup(text)
        if (
            force_final
            and visible.strip()
            and not looks_like_leaked_tool_markup(visible)
            and not degenerate
        ):
            return TextualTurn(kind="final", final_text=visible)
        return TextualTurn(
            kind="retry",
            final_text=visible,
            nudge=LEAKED_TOOL_NUDGE,
        )
    return TextualTurn(kind="final", final_text=text or "No response")


def tool_call_objects(calls: list[dict[str, Any]]) -> list[Any]:
    """OpenAI-shaped objects so ``tools.execute`` can run recovered calls."""
    out: list[Any] = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        fn = call.get("function") if isinstance(call.get("function"), dict) else {}
        name = str((fn or {}).get("name") or "").strip()
        if not name:
            continue
        if not tool_call_has_required_args(call):
            continue
        args = (fn or {}).get("arguments")
        if not isinstance(args, str):
            args = json.dumps(args or {}, ensure_ascii=False)
        out.append(
            SimpleNamespace(
                id=str(call.get("id") or f"call_{uuid.uuid4().hex[:12]}"),
                type=str(call.get("type") or "function"),
                function=SimpleNamespace(name=name, arguments=args),
            )
        )
    return out


def extract_textual_tool_calls(
    text: str | None,
    *,
    tools: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Return OpenAI-shaped tool_calls parsed from assistant content.

    Supported shapes:
    - ``<tool_call>{"name": "...", "arguments": {...}}</tool_call>``
    - ``<tool_call>name\\n{...}</tool_call>``
    - Qwen3 XML ``<function=name><parameter=k>v</parameter></function>``
    - ``<arg_key>/<arg_value>`` pairs
    """
    raw = str(text or "")
    if not raw.strip():
        return []
    known = _known_tool_names(tools)
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    blocks = _TOOL_BLOCK_RE.findall(raw)
    if not blocks and looks_like_leaked_tool_markup(raw):
        # Unclosed / truncated fence — try the remainder after the marker.
        parts = re.split(r"(?is)</?tool_call\b[^>]*>|\btool_call\b", raw, maxsplit=1)
        if len(parts) == 2 and parts[1].strip():
            blocks = [parts[1]]

    for block in blocks:
        for call in _parse_tool_block(block, known=known):
            key = (call["function"]["name"], call["function"]["arguments"])
            if key in seen:
                continue
            seen.add(key)
            found.append(call)

    if not found:
        # Whole reply may be a single JSON / XML function without a wrapper.
        for call in _parse_tool_block(raw, known=known):
            key = (call["function"]["name"], call["function"]["arguments"])
            if key in seen:
                continue
            seen.add(key)
            found.append(call)

    if not found:
        for call in extract_truncated_tool_calls(raw, tools=tools):
            key = (call["function"]["name"], call["function"]["arguments"])
            if key in seen:
                continue
            seen.add(key)
            found.append(call)

    return [call for call in found if tool_call_has_required_args(call)]


_WRITE_TOOLS = frozenset({"write_file", "patch_file"})
_PATH_TOOLS = frozenset({"read_file", "list_directory", "delete_file"})
_SEARCH_TOOLS = frozenset({"grep", "glob"})
_SHELL_TOOLS = frozenset({"terminal", "run_terminal_command"})


def tool_call_has_required_args(call: dict[str, Any] | None) -> bool:
    """False for recovered ``write_file`` / path tools with empty arguments."""
    if not isinstance(call, dict):
        return False
    fn = call.get("function") if isinstance(call.get("function"), dict) else {}
    name = str((fn or {}).get("name") or "").strip()
    if not name:
        return False
    raw = (fn or {}).get("arguments")
    args: Any = {}
    if isinstance(raw, dict):
        args = raw
    elif isinstance(raw, str) and raw.strip():
        parsed = _load_json_blob(raw)
        args = parsed if isinstance(parsed, dict) else {}
    if name in _WRITE_TOOLS:
        return bool(str(args.get("path") or "").strip()) and "content" in args
    if name in _PATH_TOOLS:
        return any(str(args.get(k) or "").strip() for k in ("path", "file", "target_directory"))
    if name in _SEARCH_TOOLS:
        return bool(str(args.get("pattern") or args.get("query") or "").strip())
    if name in _SHELL_TOOLS:
        return bool(str(args.get("command") or "").strip())
    return True


_TRUNC_NAME_RE = re.compile(r'"name"\s*:\s*"([A-Za-z_][A-Za-z0-9_\-.]{0,80})"')
_TRUNC_STR_RE = re.compile(
    r'"(path|file|target_directory|command|query|pattern|url)"\s*:\s*"((?:\\.|[^"\\])*)"'
)
_TRUNC_CONTENT_RE = re.compile(r'"content"\s*:\s*"')


def extract_truncated_tool_calls(
    text: str | None,
    *,
    tools: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Best-effort recovery of an unclosed / degenerated ``<tool_call>`` JSON.

    Qwen often starts a valid ``write_file`` and then loops on the content.
    If we can still read ``name`` + ``path`` (and a content prefix), execute it
    instead of failing the job.
    """
    raw = str(text or "")
    if not raw.strip():
        return []
    known = _known_tool_names(tools)
    name_hit = _TRUNC_NAME_RE.search(raw)
    name = name_hit.group(1) if name_hit else _first_ident_line(raw, known=known)
    if not name or not _accept_name(name, known):
        return []

    args: dict[str, Any] = {}
    for key, value in _TRUNC_STR_RE.findall(raw):
        args[str(key)] = _unescape_json_string_prefix(value)

    content_hit = _TRUNC_CONTENT_RE.search(raw)
    if content_hit:
        content = _unescape_json_string_prefix(raw[content_hit.end() :])
        content = _cut_repeated_tail(content)
        args["content"] = content

    if name in {"write_file", "patch_file"}:
        if not args.get("path") or "content" not in args:
            return []
    elif name in {"read_file", "list_directory", "delete_file"}:
        if not any(args.get(k) for k in ("path", "file", "target_directory")):
            return []
    elif name in {"grep", "glob"}:
        if not args.get("pattern") and not args.get("query"):
            return []
    elif name in {"terminal", "run_terminal_command"}:
        if not args.get("command"):
            return []
    elif not args:
        return []
    return [_make_call(name, args)]


def _unescape_json_string_prefix(raw: str) -> str:
    """Decode a JSON string that may be missing its closing quote."""
    out: list[str] = []
    i = 0
    text = str(raw or "")
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            mapped = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/"}
            if nxt in mapped:
                out.append(mapped[nxt])
                i += 2
                continue
            if nxt == "u" and i + 6 <= len(text):
                try:
                    out.append(chr(int(text[i + 2 : i + 6], 16)))
                    i += 6
                    continue
                except ValueError:
                    pass
            out.append(nxt)
            i += 2
            continue
        if ch == '"':
            break
        out.append(ch)
        i += 1
    return "".join(out)


def _cut_repeated_tail(text: str) -> str:
    """Drop a Qwen-style repeated suffix (gitignore / comment loops)."""
    body = str(text or "")
    degenerate = False
    try:
        from core.llm.response_text import is_pathological_repetition

        degenerate = is_pathological_repetition(body, min_repeats=3)
    except Exception:
        degenerate = False
    if not degenerate:
        return body
    lines = body.splitlines(keepends=True)
    counts: dict[str, int] = {}
    for i, line in enumerate(lines):
        key = line.strip()
        if len(key) < 3 or len(key) > 64:
            continue
        counts[key] = counts.get(key, 0) + 1
        if counts[key] >= 3:
            return "".join(lines[:i]).rstrip() + "\n"
    return body.rstrip() + "\n"


def _known_tool_names(tools: list[Any] | None) -> set[str]:
    names: set[str] = set()
    for item in tools or []:
        if not isinstance(item, dict):
            continue
        fn = item.get("function") if isinstance(item.get("function"), dict) else {}
        name = (fn or {}).get("name") or item.get("name")
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
    return names


def _parse_tool_block(block: str, *, known: set[str]) -> list[dict[str, Any]]:
    text = (block or "").strip()
    if not text:
        return []

    xml_calls = list(_parse_qwen_xml_functions(text, known=known))
    if xml_calls:
        return xml_calls

    kv = dict(_ARG_KV_RE.findall(text))
    if kv:
        name = _first_ident_line(text, known=known)
        if name:
            return [_make_call(name, kv)]

    decoded = _load_json_blob(text)
    if isinstance(decoded, list):
        out: list[dict[str, Any]] = []
        for item in decoded:
            call = _call_from_mapping(item, known=known)
            if call:
                out.append(call)
        if out:
            return out
    if isinstance(decoded, dict):
        call = _call_from_mapping(decoded, known=known)
        if call:
            return [call]
        name = _first_ident_line(text, known=known)
        if name:
            return [_make_call(name, decoded)]

    name = _first_ident_line(text, known=known)
    if name:
        rest = text[len(name) :].strip() if text.startswith(name) else ""
        args = _load_json_blob(rest)
        if isinstance(args, dict):
            return [_make_call(name, args)]
        if not rest:
            return [_make_call(name, {})]
    return []


def _parse_qwen_xml_functions(text: str, *, known: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, body in _FUNCTION_XML_RE.findall(text):
        clean = str(name or "").strip().strip("'\"")
        if not _accept_name(clean, known):
            continue
        params: dict[str, Any] = {}
        for key, value in _PARAM_XML_RE.findall(body or ""):
            params[str(key).strip()] = _coerce_scalar((value or "").strip())
        out.append(_make_call(clean, params))
    return out


def _call_from_mapping(data: Any, *, known: set[str]) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    name = data.get("name") or data.get("function") or ""
    if isinstance(name, dict):
        name = name.get("name") or ""
        arguments = data.get("function", {}).get("arguments", data.get("arguments"))
    else:
        arguments = data.get("arguments", data.get("parameters", data.get("args")))
    name = str(name or "").strip()
    if not _accept_name(name, known):
        return None
    if isinstance(arguments, str):
        parsed = _load_json_blob(arguments)
        arguments = parsed if isinstance(parsed, dict) else {"raw": arguments}
    if arguments is None:
        arguments = {k: v for k, v in data.items() if k not in {"name", "function", "id", "type"}}
    if not isinstance(arguments, dict):
        arguments = {}
    return _make_call(name, arguments)


def _first_ident_line(text: str, *, known: set[str]) -> str:
    for line in (text or "").splitlines():
        token = line.strip().strip("`").strip("<>/")
        if not token or token.lower() in {"tool_call", "tool_calls", "function"}:
            continue
        # ``name\\n{json}`` on one line
        if "{" in token:
            token = token.split("{", 1)[0].strip()
        if _accept_name(token, known):
            return token
        if known:
            hit = _match_known(token, known)
            if hit:
                return hit
    return ""


def _accept_name(name: str, known: set[str]) -> bool:
    if not name or not _IDENT_RE.match(name):
        return False
    if not known:
        return True
    return name in known or _match_known(name, known) is not None


def _match_known(name: str, known: set[str]) -> str | None:
    if name in known:
        return name
    lowered = name.lower().replace("-", "_")
    for item in known:
        if item.lower().replace("-", "_") == lowered:
            return item
    return None


def _load_json_blob(text: str | None) -> Any:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", raw)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _coerce_scalar(value: str) -> Any:
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw[:1] in "{[":
        parsed = _load_json_blob(raw)
        if parsed is not None:
            return parsed
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
            return int(raw)
    except ValueError:
        pass
    return raw


def _make_call(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    payload = arguments if isinstance(arguments, dict) else {}
    return {
        "id": f"call_{uuid.uuid4().hex[:12]}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(payload, ensure_ascii=False),
        },
    }
