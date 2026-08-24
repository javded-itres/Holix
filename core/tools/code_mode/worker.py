#!/usr/bin/env python3
"""Standalone Code mode worker. Stdlib only. Host launches with ``python -I``."""

from __future__ import annotations

import io
import json
import sys
import tokenize

_SAFE_MODULES = (
    "math",
    "random",
    "datetime",
    "json",
    "collections",
    "re",
    "itertools",
    "functools",
    "statistics",
    "decimal",
    "fractions",
    "string",
    "textwrap",
    "unicodedata",
    "copy",
    "hashlib",
    "base64",
    "uuid",
    "typing",
    "dataclasses",
    "operator",
    "heapq",
    "bisect",
    "array",
    "numbers",
    "cmath",
    "time",
    "calendar",
    "pprint",
)

_IMPORT_HINTS = {
    "os": "Use tools.list_directory / read_file / write_file / run_terminal_command instead of os.",
    "subprocess": "Use tools.run_terminal_command or tools.start_background_process.",
    "pathlib": "Use tools for file I/O; pathlib is blocked in run_code.",
    "sys": "sys is blocked in run_code.",
    "socket": "Talk to a local server with tools.run_terminal_command (curl), not socket.",
    "requests": "Use tools.run_terminal_command with curl, or tools.web_fetch for public URLs.",
    "httpx": "Use tools.run_terminal_command with curl, or tools.web_fetch for public URLs.",
    "urllib": "Use tools.run_terminal_command with curl, or tools.web_fetch for public URLs.",
    "shutil": "Use tools.write_file / delete_file / run_terminal_command instead of shutil.",
}


def _import_refusal(name: str, root: str) -> str:
    hint = _IMPORT_HINTS.get(root, "")
    msg = f"Import of {name!r} is not allowed"
    return f"{msg}. {hint}" if hint else msg


def _format_user_exception(exc: BaseException) -> str:
    """Short error for the model — no Holix worker internals."""
    line = None
    tb = getattr(exc, "__traceback__", None)
    while tb is not None:
        filename = tb.tb_frame.f_code.co_filename
        if filename in {"<string>", "<stdin>"}:
            n = tb.tb_lineno
            if tb.tb_frame.f_code.co_name == "__holix_user":
                n = max(1, n - 1)
            line = n
        tb = tb.tb_next
    prefix = f"{type(exc).__name__}: {exc}"
    if line is not None:
        return f"{prefix} (run_code line {line})"
    return prefix


_SAFE_BUILTIN_NAMES = (
    "abs",
    "all",
    "any",
    "ascii",
    "bin",
    "bool",
    "bytearray",
    "bytes",
    "callable",
    "chr",
    "complex",
    "dict",
    "divmod",
    "enumerate",
    "filter",
    "float",
    "format",
    "frozenset",
    "getattr",
    "hasattr",
    "hash",
    "hex",
    "id",
    "int",
    "isinstance",
    "issubclass",
    "iter",
    "len",
    "list",
    "map",
    "max",
    "min",
    "next",
    "object",
    "oct",
    "ord",
    "pow",
    "print",
    "range",
    "repr",
    "reversed",
    "round",
    "set",
    "slice",
    "sorted",
    "str",
    "sum",
    "tuple",
    "type",
    "zip",
    "BaseException",
    "Exception",
    "ArithmeticError",
    "AssertionError",
    "AttributeError",
    "IndexError",
    "KeyError",
    "LookupError",
    "MemoryError",
    "NameError",
    "OverflowError",
    "RuntimeError",
    "StopIteration",
    "SyntaxError",
    "TypeError",
    "ValueError",
    "ZeroDivisionError",
    "True",
    "False",
    "None",
)


def _send(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def _recv() -> dict:
    line = sys.stdin.readline()
    if not line:
        raise EOFError("host closed")
    data = json.loads(line)
    if not isinstance(data, dict):
        raise TypeError("host reply must be an object")
    return data


class ToolCallError(Exception):
    def __init__(self, tool_name: str, message: str) -> None:
        self.tool_name = tool_name
        self.message = message
        super().__init__(f"{tool_name}: {message}")


class _Log:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write(self, text: str) -> None:
        if not text:
            return
        self.lines.append(text if text.endswith("\n") else text + "\n")

    def flush(self) -> None:
        return


class _Tools:
    def __init__(self, log: _Log) -> None:
        self._seq = 0
        self._log = log

    def _call(self, name: str, kwargs: dict) -> object:
        self._seq += 1
        cid = self._seq
        _send({"t": "call", "id": cid, "name": name, "args": kwargs})
        reply = _recv()
        if reply.get("id") != cid:
            raise ToolCallError(name, "host reply id mismatch")
        if reply.get("ok"):
            return reply.get("value")
        raise ToolCallError(name, str(reply.get("error") or "tool failed"))

    def __getattr__(self, name: str):
        def _fn(**kwargs):
            return self._call(name, kwargs)

        _fn.__name__ = name
        return _fn

    def __getitem__(self, name: str):
        return getattr(self, str(name))

    def parallel(self, *items):
        """Run independent read-only tool calls as one host batch."""
        calls = []
        for item in items:
            if isinstance(item, dict):
                name = item.get("name") or item.get("tool") or ""
                args = item.get("args") if isinstance(item.get("args"), dict) else {}
                if not args and isinstance(item.get("arguments"), dict):
                    args = item.get("arguments")
            elif isinstance(item, (tuple, list)) and item:
                name = item[0]
                args = item[1] if len(item) > 1 and isinstance(item[1], dict) else {}
            else:
                raise TypeError("tools.parallel() expects (name, kwargs) or {name, args} items")
            calls.append({"name": str(name), "args": dict(args or {})})
        if not calls:
            return []
        self._seq += 1
        cid = self._seq
        _send({"t": "batch", "id": cid, "calls": calls})
        reply = _recv()
        if reply.get("id") != cid:
            raise ToolCallError("parallel", "host reply id mismatch")
        if reply.get("ok"):
            values = reply.get("values")
            return list(values) if isinstance(values, list) else []
        raise ToolCallError("parallel", str(reply.get("error") or "batch failed"))


def _make_safe_import(tools_obj: _Tools):
    def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        if level != 0:
            raise ImportError("Relative imports are not allowed")
        root = (name or "").split(".", 1)[0]
        # Models often write `import tools` / `from tools import grep`. The SDK
        # object is already injected; alias it instead of rejecting the import.
        if root == "tools":
            if (name or "") != "tools":
                raise ImportError(f"Import of {name!r} is not allowed")
            return tools_obj
        if root not in _SAFE_MODULES:
            raise ImportError(_import_refusal(name, root))
        return __import__(name, globals, locals, fromlist, level)

    return _safe_import


def _build_builtins(log: _Log, tools_obj: _Tools) -> dict:
    import builtins as _builtins

    def _print(*args, **kwargs):
        buf = _Log()
        kwargs = dict(kwargs)
        kwargs["file"] = buf
        _builtins.print(*args, **kwargs)
        log.write("".join(buf.lines))

    mapping = {
        "__import__": _make_safe_import(tools_obj),
        "__name__": "__main__",
        "__build_class__": _builtins.__build_class__,
        "print": _print,
    }
    for n in _SAFE_BUILTIN_NAMES:
        if n == "print":
            continue
        if hasattr(_builtins, n):
            mapping[n] = getattr(_builtins, n)
    return mapping


def _multiline_string_continuation_lines(code: str) -> set[int]:
    """Physical lines that continue a string / f-string / t-string (1-based)."""
    lines: set[int] = set()
    start_types = []
    end_types = []
    for name in ("FSTRING_START", "TSTRING_START"):
        tok = getattr(tokenize, name, None)
        if tok is not None:
            start_types.append(tok)
    for name in ("FSTRING_END", "TSTRING_END"):
        tok = getattr(tokenize, name, None)
        if tok is not None:
            end_types.append(tok)
    stack: list[int] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(code).readline):
            if tok.type in start_types:
                stack.append(tok.start[0])
            elif tok.type in end_types:
                start = stack.pop() if stack else tok.start[0]
                lines.update(range(start + 1, tok.end[0] + 1))
            elif tok.type == tokenize.STRING:
                lines.update(range(tok.start[0] + 1, tok.end[0] + 1))
    except (tokenize.TokenError, IndentationError):
        return set()
    return lines


def _indent_as_function_body(code: str, prefix: str = "    ") -> str:
    """Indent a function body without rewriting interiors of multiline strings.

    ``textwrap.indent`` would add spaces *inside* ``\"\"\"...\"\"\"`` values, so
    ``write_file(content=\"\"\"a\\nb\"\"\")`` wrote ``b`` with a leading indent.
    Continuation lines of a string stay at column 0; the parser is still inside
    the quotes, so the function does not end.
    """
    src = code.replace("\r\n", "\n").replace("\r", "\n")
    if not src.strip():
        return prefix + "pass\n"
    if not src.endswith("\n"):
        src += "\n"
    skip = _multiline_string_continuation_lines(src)
    out: list[str] = []
    for i, line in enumerate(src.splitlines(True), start=1):
        if i in skip or not line.strip():
            out.append(line)
        else:
            out.append(prefix + line)
    return "".join(out)


def _run_user(code: str, g: dict) -> object:
    loc: dict = {}
    try:
        wrapped = "def __holix_user():\n" + _indent_as_function_body(code)
        exec(wrapped, g, loc)  # noqa: S102 — worker executes model code by design
        return loc["__holix_user"]()
    except SyntaxError:
        exec(code, g, loc)  # noqa: S102
        return loc.get("result")


def main() -> int:
    raw = sys.stdin.readline()
    if not raw.strip():
        _send({"t": "error", "error": "empty request", "logs": []})
        return 1
    try:
        req = json.loads(raw)
    except json.JSONDecodeError as exc:
        _send({"t": "error", "error": f"invalid request: {exc}", "logs": []})
        return 1
    code = str(req.get("code") or "")
    log = _Log()
    tools_obj = _Tools(log)
    g = {
        "__builtins__": _build_builtins(log, tools_obj),
        "__name__": "__main__",
        "ToolCallError": ToolCallError,
        "tools": tools_obj,
    }
    for mod in _SAFE_MODULES:
        try:
            g[mod] = __import__(mod)
        except ImportError:
            pass
    try:
        value = _run_user(code, g)
        result = None if value is None else value
        _send({"t": "done", "result": result, "logs": log.lines})
        return 0
    except ToolCallError as exc:
        _send(
            {
                "t": "error",
                "error": str(exc),
                "logs": log.lines,
            }
        )
        return 1
    except Exception as exc:
        _send(
            {
                "t": "error",
                "error": _format_user_exception(exc),
                "logs": log.lines,
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
