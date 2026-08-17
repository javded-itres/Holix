"""Restricted Python execution for agent tools.

Primary isolation boundary is a **subprocess** (own process, killable on timeout).
In-process restricted builtins are defense-in-depth only — not a security sandbox.
"""

from __future__ import annotations

import asyncio
import builtins as _builtins
import json
import os
import sys
import textwrap
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from config import settings
from core.tools.base import BaseTool

# Modules allowed via ``import`` / ``from … import`` inside execute_python.
_SAFE_MODULES: frozenset[str] = frozenset(
    {
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
        "struct",
        "numbers",
        "cmath",
        "time",
        "calendar",
        "pprint",
        "pathlib",
    }
)

_SAFE_BUILTIN_NAMES: tuple[str, ...] = (
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
    "EOFError",
    "ImportError",
    "IndexError",
    "KeyError",
    "LookupError",
    "MemoryError",
    "NameError",
    "OSError",
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

# Worker script: runs in a child process; reads one JSON line from stdin.
_WORKER_SOURCE = textwrap.dedent(
    r"""
    import builtins as _builtins
    import json
    import sys
    from contextlib import redirect_stderr, redirect_stdout
    from io import StringIO

    ALLOWED = set(%(allowed)s)

    SAFE_BUILTIN_NAMES = %(builtin_names)s

    def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level != 0:
            raise ImportError("Relative imports are not allowed in execute_python")
        root = (name or "").split(".", 1)[0]
        if root not in ALLOWED:
            raise ImportError(
                "Import of %%r is not allowed. Allowed modules: %%s"
                %% (name, ", ".join(sorted(ALLOWED)))
            )
        return _builtins.__import__(name, globals, locals, fromlist, level)

    def _build_builtins():
        mapping = {
            "__import__": _safe_import,
            "__name__": "__main__",
            "__build_class__": _builtins.__build_class__,
        }
        for n in SAFE_BUILTIN_NAMES:
            if hasattr(_builtins, n):
                mapping[n] = getattr(_builtins, n)
        return mapping

    def run_code(code: str) -> dict:
        stdout_c = StringIO()
        stderr_c = StringIO()
        result_value = None
        g = {"__builtins__": _build_builtins(), "__name__": "__main__"}
        for mod in sorted(ALLOWED):
            try:
                g[mod] = _builtins.__import__(mod)
            except ImportError:
                pass
        loc = {}
        try:
            with redirect_stdout(stdout_c), redirect_stderr(stderr_c):
                try:
                    result_value = eval(code, g, loc)
                except SyntaxError:
                    exec(code, g, loc)
            out = {
                "ok": True,
                "stdout": stdout_c.getvalue(),
                "stderr": stderr_c.getvalue(),
                "result": None if result_value is None else repr(result_value),
            }
        except Exception as e:
            out = {
                "ok": False,
                "error_type": type(e).__name__,
                "error": str(e),
                "stdout": stdout_c.getvalue(),
                "stderr": stderr_c.getvalue(),
            }
        return out

    def main() -> int:
        try:
            raw = sys.stdin.read()
            payload = json.loads(raw) if raw.strip() else {}
            code = payload.get("code") or ""
            out = run_code(code)
        except Exception as e:
            out = {
                "ok": False,
                "error_type": type(e).__name__,
                "error": str(e),
                "stdout": "",
                "stderr": "",
            }
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
        sys.stdout.flush()
        return 0 if out.get("ok") else 1

    if __name__ == "__main__":
        raise SystemExit(main())
    """
) % {
    "allowed": repr(sorted(_SAFE_MODULES)),
    "builtin_names": repr(_SAFE_BUILTIN_NAMES),
}


def _format_worker_result(data: dict) -> str:
    if data.get("ok"):
        parts: list[str] = []
        if data.get("stdout"):
            parts.append(f"STDOUT:\n{data['stdout']}")
        if data.get("stderr"):
            parts.append(f"STDERR:\n{data['stderr']}")
        if data.get("result") is not None:
            parts.append(f"RESULT: {data['result']}")
        if not parts:
            return "Code executed successfully (no output)"
        return "\n\n".join(parts)
    err_type = data.get("error_type") or "Error"
    err = data.get("error") or "unknown error"
    extra = ""
    if data.get("stderr"):
        extra = f"\n\nSTDERR:\n{data['stderr']}"
    return f"Error: {err_type}: {err}{extra}"


def _build_safe_builtins(allowed_modules: frozenset[str]) -> dict:
    """In-process restricted builtins (fallback path only)."""

    def _safe_import(
        name: str,
        globals: dict | None = None,  # noqa: A002
        locals: dict | None = None,  # noqa: A002
        fromlist: tuple = (),
        level: int = 0,
    ):
        if level != 0:
            raise ImportError("Relative imports are not allowed in execute_python")
        root = (name or "").split(".", 1)[0]
        if root not in allowed_modules:
            allowed = ", ".join(sorted(allowed_modules))
            raise ImportError(f"Import of '{name}' is not allowed. Allowed modules: {allowed}")
        return _builtins.__import__(name, globals, locals, fromlist, level)

    mapping: dict = {
        "__import__": _safe_import,
        "__name__": "__main__",
        "__build_class__": _builtins.__build_class__,
    }
    for name in _SAFE_BUILTIN_NAMES:
        if hasattr(_builtins, name):
            mapping[name] = getattr(_builtins, name)
    return mapping


class PythonExecutorTool(BaseTool):
    """Execute Python in a killable child process with restricted imports."""

    # Kill subprocess this many seconds after the soft timeout if still alive.
    _KILL_GRACE_S = 1.0

    def __init__(self):
        super().__init__()
        self.name = "execute_python"
        self.description = (
            "Execute Python code safely in a restricted subprocess. "
            "Returns stdout, stderr, and result. Use for calculations and data "
            "processing. Filesystem/network modules (os, subprocess, socket) are "
            "blocked — use list_directory / run_terminal_command for the workspace."
        )
        self.risk_level = "high"
        self.parameters = {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 10)",
                    "default": 10,
                },
            },
            "required": ["code"],
        }
        self.safe_modules = set(_SAFE_MODULES)

    async def execute(self, code: str, timeout: int = 10) -> str:
        if not settings.enable_code_executor:
            return "Error: Code executor is disabled (HOLIX_ENABLE_CODE_EXECUTOR=false)"
        from core.runtime.introspect_signals import INTROSPECT_REFUSAL, is_introspect_code

        if is_introspect_code(code):
            return INTROSPECT_REFUSAL
        try:
            timeout_s = max(1, int(timeout or 10))
        except (TypeError, ValueError):
            timeout_s = 10
        try:
            return await self._run_in_subprocess(code, timeout_s)
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"

    async def _run_in_subprocess(self, code: str, timeout_s: int) -> str:
        """Primary path: separate process, hard-killed on timeout."""
        env = os.environ.copy()
        # Avoid inheriting agent secrets into the worker when possible.
        for key in list(env):
            if key.startswith("HOLIX_") and key not in {
                "HOLIX_HOME",
                "HOLIX_PROFILE",
            }:
                # Keep home/profile for path resolution if needed; drop API keys etc.
                if any(s in key.upper() for s in ("KEY", "TOKEN", "SECRET", "PASSWORD", "PEPPER")):
                    env.pop(key, None)

        # Own process group so killpg reaps nested children.
        kwargs: dict = {
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "env": env,
            "cwd": str(Path.cwd()),
        }
        if os.name == "posix":
            kwargs["start_new_session"] = True

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",  # isolate: no user site, no PYTHON* path influence
            "-c",
            _WORKER_SOURCE,
            **kwargs,
        )
        payload = json.dumps({"code": code}, ensure_ascii=False).encode("utf-8")
        try:
            # Poll cancel while waiting (same pattern as terminal tool).
            from core.tools.execution_context import is_run_cancelled

            comm = asyncio.create_task(proc.communicate(payload))
            loop = asyncio.get_running_loop()
            deadline = loop.time() + float(timeout_s)
            while not comm.done():
                if is_run_cancelled():
                    await self._kill_process(proc)
                    comm.cancel()
                    return "Error: Run cancelled — code execution terminated."
                remaining = deadline - loop.time()
                if remaining <= 0:
                    await self._kill_process(proc)
                    comm.cancel()
                    return f"Error: Code execution timed out after {timeout_s} seconds"
                try:
                    stdout, stderr = await asyncio.wait_for(
                        asyncio.shield(comm), timeout=min(0.2, remaining)
                    )
                    break
                except TimeoutError:
                    continue
            else:
                stdout, stderr = await comm
        except TimeoutError:
            await self._kill_process(proc)
            return f"Error: Code execution timed out after {timeout_s} seconds"

        if stderr and not stdout:
            err = stderr.decode("utf-8", errors="replace").strip()
            return f"Error: Worker failed: {err or 'unknown stderr'}"

        raw = (stdout or b"").decode("utf-8", errors="replace").strip()
        if not raw:
            err = (stderr or b"").decode("utf-8", errors="replace").strip()
            if proc.returncode and err:
                return f"Error: Worker exited {proc.returncode}: {err}"
            return "Error: Empty response from code worker"

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return f"Error: Invalid worker response: {raw[:400]}"
        if not isinstance(data, dict):
            return "Error: Invalid worker response type"
        return _format_worker_result(data)

    async def _kill_process(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        try:
            if os.name == "posix" and proc.pid:
                try:
                    os.killpg(proc.pid, 9)
                except (ProcessLookupError, PermissionError, OSError):
                    proc.kill()
            else:
                proc.kill()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=self._KILL_GRACE_S)
        except (TimeoutError, ProcessLookupError):
            pass

    # ---- in-process fallback (tests / platforms without subprocess) ----

    def _make_globals(self) -> dict:
        allowed = frozenset(self.safe_modules)
        safe_globals: dict = {
            "__builtins__": _build_safe_builtins(allowed),
            "__name__": "__main__",
        }
        for module in sorted(allowed):
            try:
                safe_globals[module] = _builtins.__import__(module)
            except ImportError:
                pass
        return safe_globals

    async def _run_code_inprocess(self, code: str) -> str:
        """Legacy in-process path (not a security boundary)."""
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        result_value = None
        safe_globals = self._make_globals()
        safe_locals: dict = {}
        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                try:
                    result_value = eval(code, safe_globals, safe_locals)
                except SyntaxError:
                    exec(code, safe_globals, safe_locals)
            data = {
                "ok": True,
                "stdout": stdout_capture.getvalue(),
                "stderr": stderr_capture.getvalue(),
                "result": None if result_value is None else repr(result_value),
            }
            return _format_worker_result(data)
        except Exception as e:
            data = {
                "ok": False,
                "error_type": type(e).__name__,
                "error": str(e),
                "stdout": stdout_capture.getvalue(),
                "stderr": stderr_capture.getvalue(),
            }
            return _format_worker_result(data)


class MathCalculatorTool(BaseTool):
    """Tool for mathematical calculations using Python's math module."""

    def __init__(self):
        super().__init__()
        self.name = "calculate"
        self.description = (
            "Perform mathematical calculations. Supports basic arithmetic, trigonometry, "
            "logarithms, etc. Examples: '2+2', 'sqrt(16)', 'sin(pi/2)'"
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate",
                }
            },
            "required": ["expression"],
        }

    async def execute(self, expression: str) -> str:
        import math

        try:
            safe_globals = {
                "__builtins__": {},
                "abs": abs,
                "round": round,
                "min": min,
                "max": max,
                "sum": sum,
                "pow": pow,
                "sqrt": math.sqrt,
                "sin": math.sin,
                "cos": math.cos,
                "tan": math.tan,
                "asin": math.asin,
                "acos": math.acos,
                "atan": math.atan,
                "log": math.log,
                "log10": math.log10,
                "exp": math.exp,
                "pi": math.pi,
                "e": math.e,
                "ceil": math.ceil,
                "floor": math.floor,
                "factorial": math.factorial,
            }
            result = eval(expression, safe_globals, {})
            return f"Result: {result}"
        except Exception as e:
            return f"Error: {type(e).__name__}: {str(e)}"
