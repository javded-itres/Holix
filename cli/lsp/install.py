"""Install language-server packages for the Holix lsp tool."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any

from core.tools.lsp_servers import (
    CATALOG,
    jedi_available,
    missing_recommended,
    pyright_available,
    spec_ready,
)

RECOMMENDED_NPM = (
    "typescript",
    "typescript-language-server",
    "vscode-langservers-extracted",
    "yaml-language-server",
    "bash-language-server",
    "dockerfile-language-server-nodejs",
)


def _run(cmd: list[str], *, timeout: int = 180) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    text = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, text.strip() or f"exit {proc.returncode}"
    return True, text.strip()


def _pip_install(package: str) -> tuple[bool, str]:
    commands = [
        [sys.executable, "-m", "pip", "install", package],
    ]
    uv = shutil.which("uv")
    if uv:
        commands.insert(0, [uv, "pip", "install", package])
    last_err = "pip/uv not available"
    for cmd in commands:
        ok, out = _run(cmd)
        if ok:
            return True, f"Installed {package}"
        last_err = out or last_err
    return False, last_err


def install_pyright() -> tuple[bool, str]:
    if pyright_available():
        return True, "Pyright already installed"
    ok, msg = _pip_install("pyright")
    if ok and pyright_available():
        return True, "Installed Pyright (pyright-langserver)"
    if ok:
        return (
            True,
            "Installed Pyright package (restart the shell if pyright-langserver is not on PATH)",
        )
    npm = shutil.which("npm")
    if npm:
        ok_n, out_n = _run([npm, "install", "-g", "pyright"], timeout=180)
        if ok_n:
            return True, "Installed Pyright via npm"
        return False, out_n or msg
    return False, msg


def install_jedi() -> tuple[bool, str]:
    if jedi_available():
        return True, "jedi already installed"
    return _pip_install("jedi")


def install_npm_recommended() -> tuple[bool, str]:
    npm = shutil.which("npm")
    if not npm:
        return False, "npm not found — install Node.js, then: holix lsp setup"
    ok, out = _run([npm, "install", "-g", *RECOMMENDED_NPM], timeout=300)
    if ok:
        return True, "Installed npm language servers (JS/TS, JSON/HTML/CSS, YAML, Bash, Dockerfile)"
    return False, out


def toolchain_optional_commands() -> list[str]:
    cmds: list[str] = []
    if shutil.which("go") and not spec_ready(next(s for s in CATALOG if s.id == "go")):
        cmds.append("go install golang.org/x/tools/gopls@latest")
    if (shutil.which("rustup") or shutil.which("cargo")) and not spec_ready(
        next(s for s in CATALOG if s.id == "rust")
    ):
        if shutil.which("rustup"):
            cmds.append("rustup component add rust-analyzer")
        else:
            cmds.append("brew install rust-analyzer")
    if not spec_ready(next(s for s in CATALOG if s.id == "clangd")):
        if shutil.which("brew"):
            cmds.append("brew install llvm")
        elif shutil.which("apt-get"):
            cmds.append("sudo apt install clangd")
    return cmds


def install_recommended(*, npm: bool = True) -> list[str]:
    """Install the default Python + (if Node) web language servers. Returns log lines."""
    lines: list[str] = []
    ok, msg = install_pyright()
    lines.append(("ok: " if ok else "error: ") + msg)
    ok_j, msg_j = install_jedi()
    lines.append(("ok: " if ok_j else "error: ") + msg_j)
    if npm and shutil.which("npm"):
        ok_n, msg_n = install_npm_recommended()
        lines.append(("ok: " if ok_n else "error: ") + msg_n)
    elif npm and not shutil.which("npm"):
        lines.append(
            "skip: Node.js/npm not on PATH — JS/TS/JSON/HTML/CSS/YAML/Bash servers not installed"
        )
    extra = toolchain_optional_commands()
    if extra:
        lines.append("optional (run yourself):")
        lines.extend(f"  {c}" for c in extra)
    missing = missing_recommended()
    still = [s.title for s in missing]
    if still:
        lines.append("still missing: " + ", ".join(still))
    return lines


def setup_summary() -> dict[str, Any]:
    from core.tools.lsp_servers import status_rows

    rows = status_rows()
    return {
        "ready": [r for r in rows if r["ready"]],
        "missing_recommended": [r for r in rows if r["recommended"] and not r["ready"]],
        "optional": [r for r in rows if not r["recommended"] and not r["ready"]],
        "has_npm": bool(shutil.which("npm")),
        "has_node": bool(shutil.which("node")),
    }
