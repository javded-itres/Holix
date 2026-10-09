"""Format shell tool results; honor pytest failures even when a pipe hid rc."""

from __future__ import annotations

import re

from core.platform_compat import IS_WINDOWS
from core.runtime.test_run_signals import is_red_test_output, is_test_command, is_test_log_dump

# grep/rg exit 1 means "no selected lines", not a crashed command.
_SEARCH_MISS_RE = re.compile(
    r"(?:^|[;&|(\n]|&&|\|\|)\s*(?:grep|egrep|fgrep|rg|ag|ack|git\s+grep)\b"
)
# CLI usage, not a Python traceback. Those stay Error so the agent can fix them.
_USAGE_RE = re.compile(
    r"(?i)(no such command|unknown command|unrecognized arguments|invalid choice|^usage:)"
)

# dash (Debian/Ubuntu /bin/sh) treats a failed `set` as fatal (special builtin),
# so we must not invoke `set -o pipefail` unless this is actually bash.
_PIPEFAIL_PREFIX = '[ -n "${BASH_VERSION:-}" ] && set -o pipefail; '


def rewrite_bash_source(command: str) -> str:
    """Turn a command-word ``source`` into POSIX ``.``.

    Holix runs shell tools with ``/bin/sh``. On Debian that is dash, which
    has no ``source`` and exits 127. ``. file`` is the same operation.
    """
    text = str(command or "")
    if "source" not in text:
        return text
    out: list[str] = []
    i = 0
    quote = ""
    while i < len(text):
        ch = text[i]
        if quote:
            out.append(ch)
            if ch == quote and not (quote == '"' and i > 0 and text[i - 1] == "\\"):
                quote = ""
            i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            out.append(ch)
            i += 1
            continue
        if text.startswith("source", i) and _source_word(text, i) and _command_position(text, i):
            out.append(".")
            i += len("source")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _source_word(text: str, index: int) -> bool:
    before = text[index - 1] if index else ""
    after_at = index + len("source")
    after = text[after_at] if after_at < len(text) else ""
    if before and (before.isalnum() or before == "_"):
        return False
    if after and (after.isalnum() or after == "_"):
        return False
    return True


def _command_position(text: str, index: int) -> bool:
    """True when ``source`` is the command, not an argument (``grep source``)."""
    j = index - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    if j < 0:
        return True
    return text[j] in ";|&(\n{"


def with_pipefail(command: str) -> str:
    """Prefix bash so ``pytest | tail`` keeps pytest's exit code.

    Debian/Ubuntu ``/bin/sh`` is dash and rejects ``pipefail``. Skip ``set``
    unless ``BASH_VERSION`` is set. Red pytest output is still reported as
    Error by ``format_process_result`` when a pipe hid the exit code.
    A bash-only ``source`` is rewritten to ``.`` so the same shell can run it.
    """
    text = rewrite_bash_source(str(command or ""))
    if not text.strip() or IS_WINDOWS:
        return text
    stripped = text.lstrip()
    if stripped.startswith('[ -n "${BASH_VERSION:-}" ]') or stripped.startswith("set -o pipefail"):
        return text
    return _PIPEFAIL_PREFIX + text


def format_process_result(
    *,
    returncode: int,
    output: str,
    error: str = "",
    command: str = "",
) -> str:
    """Human-readable terminal tool payload.

    ``pytest … | tail`` often returns 0 because ``tail`` succeeded. If the
    combined output still looks like a red test run, report Error.
    """
    out = output or ""
    err = error or ""
    blob = f"{out}\n{err}"
    rc = int(returncode or 0)
    tests_lied_ok = (
        rc == 0
        and bool(command)
        and is_test_command(command)
        and (is_red_test_output(blob) or is_test_log_dump(blob))
    )
    if tests_lied_ok:
        body = out if out.strip() else err
        return f"Error (exit code 0, tests failed in output):\n{body}"
    if rc == 0:
        return f"Success (exit code 0):\n{out}" if out else "Success (no output)"
    if _search_miss(command, rc):
        body = out.strip() or err.strip()
        return f"No matches:\n{body}" if body else "No matches."
    if _usage_only(rc, out, err):
        body = (err or out).strip()
        return f"Unrecognized command:\n{body}" if body else "Unrecognized command."
    return f"Error (exit code {rc}):\nSTDOUT:\n{out}\nSTDERR:\n{err}"


def _search_miss(command: str, returncode: int) -> bool:
    return returncode == 1 and bool(_SEARCH_MISS_RE.search(command or ""))


def _usage_only(returncode: int, output: str, error: str) -> bool:
    if returncode != 2:
        return False
    blob = f"{output}\n{error}"
    if "Traceback" in blob:
        return False
    return bool(_USAGE_RE.search(blob))
