"""OS-level filesystem sandbox for shell / background processes.

Modes affect filesystem writes only (same contract as DeepSeek Harness):
read-only, workspace-write, danger-full-access.

If a restricted mode is requested and no backend is usable, the spawn is
refused (fail-closed) instead of running unconfined.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from core.platform_compat import IS_LINUX, IS_MACOS, IS_WINDOWS

SANDBOX_MODES = ("read-only", "workspace-write", "danger-full-access")


class SandboxUnavailable(RuntimeError):
    """Restricted sandbox mode was requested but cannot be enforced."""


def normalize_sandbox_mode(value: str | None) -> str:
    raw = str(value or "").strip().lower().replace("_", "-")
    if raw in SANDBOX_MODES:
        return raw
    if raw in {"danger", "full", "off", "none"}:
        return "danger-full-access"
    if raw in {"write", "workspace"}:
        return "workspace-write"
    if raw in {"ro", "readonly"}:
        return "read-only"
    return "danger-full-access"


def sandbox_backend() -> str | None:
    """Installed backend name, or None if this host cannot confine."""
    if os.environ.get("HOLIX_OS_SANDBOX", "").strip().lower() in {"0", "off", "false", "no"}:
        return None
    if IS_MACOS and shutil.which("sandbox-exec"):
        return "sandbox-exec"
    if IS_LINUX and shutil.which("bwrap"):
        return "bwrap"
    return None


def _writable_roots(workspace_root: str | None) -> list[str]:
    roots: list[str] = []
    if workspace_root:
        try:
            roots.append(str(Path(workspace_root).expanduser().resolve()))
        except OSError:
            roots.append(str(workspace_root))
        try:
            from core.runtime.git_worktree import extra_sandbox_write_roots

            for extra_git in extra_sandbox_write_roots(workspace_root):
                if extra_git and extra_git not in roots:
                    roots.append(extra_git)
        except Exception:
            pass
    for extra in ("/tmp", "/private/tmp"):
        if Path(extra).exists():
            roots.append(extra)
    try:
        tmp = str(Path(tempfile.gettempdir()).resolve())
        if tmp not in roots:
            roots.append(tmp)
    except OSError:
        pass
    out: list[str] = []
    seen: set[str] = set()
    for root in roots:
        if root and root not in seen:
            seen.add(root)
            out.append(root)
    return out


def _sbpl_subpath(path: str) -> str:
    escaped = path.replace("\\", "\\\\").replace('"', '\\"')
    return f'(subpath "{escaped}")'


def _seatbelt_profile(mode: str, workspace_root: str | None) -> str:
    lines = [
        "(version 1)",
        "(allow default)",
        "(deny file-write*)",
        '(allow file-write-data (literal "/dev/null"))',
        '(allow file-write-data (literal "/dev/dtracehelper"))',
    ]
    if mode == "workspace-write":
        for root in _writable_roots(workspace_root):
            lines.append(f"(allow file-write* {_sbpl_subpath(root)})")
    return "\n".join(lines) + "\n"


def confine_argv(
    argv: list[str],
    *,
    mode: str,
    workspace_root: str | None,
    cwd: str | None = None,
) -> list[str]:
    """Wrap *argv* so the process (and children) stay in *mode*.

    ``danger-full-access`` returns argv unchanged. Restricted modes raise
    :class:`SandboxUnavailable` when no backend can enforce them.
    """
    del cwd  # backends chdir via spawn cwd=
    wanted = normalize_sandbox_mode(mode)
    if wanted == "danger-full-access" or not argv:
        return list(argv)
    backend = sandbox_backend()
    if backend is None:
        hint = (
            "Install bubblewrap (Linux), ensure sandbox-exec is usable (macOS), "
            "or `/permission danger-full-access`."
        )
        if IS_WINDOWS:
            hint = "Windows OS sandbox is not available; `/permission danger-full-access`."
        raise SandboxUnavailable(
            f'sandbox mode "{wanted}" was requested but no sandbox backend is usable '
            f"on this host; refusing to run unconfined. {hint}"
        )
    if backend == "sandbox-exec":
        profile = _seatbelt_profile(wanted, workspace_root)
        return ["sandbox-exec", "-p", profile, *argv]
    # bwrap: whole OS read-only, then overlay writable roots
    wrapped = [
        "bwrap",
        "--die-with-parent",
        "--ro-bind",
        "/",
        "/",
        "--dev-bind",
        "/dev",
        "/dev",
        "--proc",
        "/proc",
    ]
    if wanted == "workspace-write":
        for root in _writable_roots(workspace_root):
            if Path(root).exists():
                wrapped.extend(["--bind", root, root])
    wrapped.append("--")
    wrapped.extend(argv)
    return wrapped


def confine_shell_command(
    command: str,
    *,
    mode: str,
    workspace_root: str | None,
    cwd: str | None = None,
) -> list[str]:
    """Return argv that runs *command* via bash/cmd inside the sandbox."""
    if IS_WINDOWS:
        inner = ["cmd", "/c", command.strip()]
    else:
        inner = ["/bin/bash", "-lc", command.strip()]
    return confine_argv(inner, mode=mode, workspace_root=workspace_root, cwd=cwd)
