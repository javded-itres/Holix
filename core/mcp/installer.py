"""Helpers to 'install' (prepare) MCP servers from popular list or git repositories.

For git repos:
- Clones into ~/.holix/mcp-servers/<name>/
- Attempts to detect the best stdio command (node, uv, python, etc.)
- Can run npm install / uv sync automatically.
- Returns a suggested MCPServerConfig dict ready for profile.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.mcp.popular import PopularMCPServer
from core.platform_compat import resolve_holix_home

logger = logging.getLogger(__name__)

MCP_SERVERS_ROOT = resolve_holix_home() / "mcp-servers"
_TARGET_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")
_GIT_URL_RE = re.compile(r"^(https://|git@|ssh://)[^\s]+$")


def _validate_subprocess_argv(cmd: list[str]) -> list[str]:
    if not cmd or not all(isinstance(arg, str) and arg for arg in cmd):
        raise ValueError("Invalid subprocess command")
    if any("\0" in arg for arg in cmd):
        raise ValueError("Invalid subprocess command")
    return list(cmd)


def _validate_target_name(name: str) -> str:
    if not _TARGET_NAME_RE.fullmatch(name):
        raise ValueError(f"Invalid MCP server name: {name!r}")
    return name


def _validate_git_url(url: str) -> str:
    value = url.strip()
    if not value or value.startswith("-") or not _GIT_URL_RE.fullmatch(value):
        raise ValueError(f"Invalid git URL: {url!r}")
    return value


def ensure_mcp_servers_root() -> Path:
    MCP_SERVERS_ROOT.mkdir(parents=True, exist_ok=True)
    return MCP_SERVERS_ROOT


def _run(cmd: list[str], cwd: Path | None = None, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a command, optionally capturing output."""
    argv = _validate_subprocess_argv(cmd)
    kwargs: dict[str, Any] = {"cwd": str(cwd) if cwd else None, "shell": False}
    if capture:
        kwargs.update({"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True})
    return subprocess.run(argv, check=check, **kwargs)


def clone_or_update_git(url: str, target_name: str, depth: int = 1) -> Path:
    """Clone a git repo into ~/.holix/mcp-servers/<target_name>."""
    safe_url = _validate_git_url(url)
    safe_name = _validate_target_name(target_name)
    root = ensure_mcp_servers_root()
    dest = root / safe_name
    if dest.exists():
        # try to pull latest (best effort)
        try:
            _run(["git", "-C", str(dest), "pull", "--ff-only"], check=False)
            return dest
        except Exception:
            shutil.rmtree(dest, ignore_errors=True)
    cmd = ["git", "clone"]
    if depth > 0:
        cmd += ["--depth", str(depth)]
    cmd += [safe_url, str(dest)]
    _run(cmd)
    return dest


def _detect_js_entry(cloned: Path) -> tuple[str, list[str]] | None:
    pkg_file = cloned / "package.json"
    if not pkg_file.exists():
        return None
    try:
        pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
    except Exception:
        return None

    # Prefer pre-built dist
    candidates = [
        cloned / "dist" / "index.js",
        cloned / "build" / "index.js",
        cloned / "dist" / "server.js",
    ]
    for c in candidates:
        if c.exists():
            return "node", [str(c)]

    # From package.json
    main = pkg.get("main")
    if main:
        main_path = cloned / main
        if main_path.exists():
            return "node", [str(main_path)]

    # Common for many MCP TS servers
    if (cloned / "src" / "index.ts").exists() or (cloned / "index.ts").exists():
        # Will need build later
        return "node", [str(cloned / "dist" / "index.js")]

    return None


def _detect_python_entry(cloned: Path) -> tuple[str, list[str]] | None:
    if (cloned / "pyproject.toml").exists() or (cloned / "setup.py").exists() or (cloned / "setup.cfg").exists():
        # Try common patterns
        # Many python MCP use "mcp" or "server" module
        for mod in ["mcp_server", "server", "main", "app"]:
            if (cloned / f"{mod}.py").exists() or (cloned / f"{mod}" / "__init__.py").exists():
                return "uv", ["--directory", str(cloned), "run", "python", "-m", mod]
        # Fallback generic
        return "uv", ["--directory", str(cloned), "run", "python", "-m", "server"]
    return None


def _try_readme_hints(cloned: Path) -> tuple[str, list[str]] | None:
    for readme_name in ("README.md", "README", "readme.md"):
        p = cloned / readme_name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore").lower()
        # Look for common one-liners
        if "npx -y" in text:
            # crude extraction
            for line in text.splitlines():
                if "npx -y" in line and ("mcp" in line or "server" in line):
                    # take the first npx command-ish
                    parts = line.strip().split()
                    if parts[0] == "npx" or parts[0].startswith("npx"):
                        idx = parts.index("npx") if "npx" in parts else 0
                        return parts[idx], parts[idx+1:idx+6]  # rough
        if "node " in text and ".js" in text:
            for line in text.splitlines():
                if "node " in line and ".js" in line:
                    parts = line.strip().split()
                    try:
                        i = parts.index("node")
                        return "node", parts[i+1:i+3]
                    except ValueError:
                        pass
    return None


def detect_command(cloned: Path) -> tuple[str, list[str], str]:
    """Return (command, args, notes). Best effort detection."""
    notes = ""

    # 1. JS / TS
    js = _detect_js_entry(cloned)
    if js:
        cmd, args = js
        # Check if dist exists, otherwise suggest build
        if not any((cloned / d / "index.js").exists() for d in ("dist", "build")):
            notes = "Run `npm install && npm run build` (or `bun install && bun run build`) inside the cloned dir first."
        return cmd, args, notes

    # 2. Python
    py = _detect_python_entry(cloned)
    if py:
        return py[0], py[1], "Make sure uv is installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)."

    # 3. README hints
    hints = _try_readme_hints(cloned)
    if hints:
        return hints[0], hints[1], ""

    # 4. Last resort generic
    if (cloned / "index.js").exists():
        return "node", [str(cloned / "index.js")], "You may need to run `npm install` first."

    if (cloned / "main.py").exists():
        return "python", [str(cloned / "main.py")], ""

    return "node", [str(cloned / "dist" / "index.js")], "Please inspect the README and adjust command/args manually after clone."


def auto_prepare(cloned: Path, cmd: str) -> None:
    """Run install/build steps for common ecosystems (best effort, non-fatal)."""
    try:
        if (cloned / "package.json").exists():
            # Prefer bun if present, else npm
            if shutil.which("bun"):
                _run(["bun", "install"], cwd=cloned, check=False)
                if (cloned / "package.json").exists():  # build if script exists
                    _run(["bun", "run", "build"], cwd=cloned, check=False)
            else:
                _run(["npm", "install", "--no-audit", "--no-fund"], cwd=cloned, check=False)
                pkg = cloned / "package.json"
                if pkg.exists():
                    data = json.loads(pkg.read_text())
                    if "build" in (data.get("scripts") or {}):
                        _run(["npm", "run", "build"], cwd=cloned, check=False)
        elif (cloned / "pyproject.toml").exists() or (cloned / "uv.lock").exists():
            if shutil.which("uv"):
                _run(["uv", "sync", "--directory", str(cloned)], check=False)
    except Exception as e:
        logger.warning("Auto-prepare step failed (non-fatal): %s", e)


def build_config_from_popular(pop: PopularMCPServer, provided_params: dict[str, str]) -> dict[str, Any]:
    """Turn a popular entry + user params into a raw dict suitable for MCPServerConfig."""
    from core.mcp.validate import normalize_allowed_paths

    params = {**pop.default_params, **provided_params}
    if pop.key == "filesystem":
        raw_paths = params.get("allowed_paths", "")
        if not (raw_paths or "").strip():
            from pathlib import Path

            raw_paths = str(Path.cwd().resolve())
            params["allowed_paths"] = raw_paths
        valid, errs = normalize_allowed_paths(raw_paths)
        if errs:
            raise ValueError(
                "Filesystem MCP path error:\n  - " + "\n  - ".join(errs)
                + "\nUse existing directories (e.g. current project path)."
            )
        params["allowed_paths"] = " ".join(valid)

    args = []
    for a in pop.args_template:
        if a.startswith("{") and a.endswith("}"):
            key = a[1:-1]
            val = params.get(key, "")
            if val:
                if key == "allowed_paths" and pop.key == "filesystem":
                    args.extend(val.split())
                elif " " in val or "," in val:
                    parts = [p.strip() for p in val.replace(",", " ").split() if p.strip()]
                    args.extend(parts)
                else:
                    args.append(val)
        else:
            args.append(a)

    data: dict[str, Any] = {
        "transport": pop.transport,
        "command": pop.command,
        "args": args,
    }
    if pop.env:
        data["env"] = pop.env
    if pop.notes:
        data["_notes"] = pop.notes
    return data


def install_from_git(git_url: str, suggested_name: str | None = None, auto_prepare_steps: bool = True) -> dict[str, Any]:
    """Clone a git-based MCP server and return a suggested config dict.

    The caller (CLI) is responsible for letting user review/edit the returned command/args/env
    before saving to profile.
    """
    name = suggested_name or git_url.rstrip("/").split("/")[-1].removesuffix(".git")
    name = "".join(c if c.isalnum() or c in "-_" else "-" for c in name).strip("-")[:40] or "custom-mcp"

    cloned = clone_or_update_git(git_url, name)

    if auto_prepare_steps:
        auto_prepare(cloned, "")

    cmd, args, notes = detect_command(cloned)

    data: dict[str, Any] = {
        "transport": "stdio",
        "command": cmd,
        "args": args,
        "_source": "git",
        "_cloned_path": str(cloned),
    }
    if notes:
        data["_notes"] = notes

    # Try to inject a README note
    readme = cloned / "README.md"
    if readme.exists():
        data["_readme"] = str(readme)

    return data
