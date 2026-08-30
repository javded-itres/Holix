"""Install language-server packages and required toolchains for holix lsp setup."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.platform_compat import IS_WINDOWS
from core.tools.lsp_servers import (
    CATALOG,
    LspServerSpec,
    extra_bin_dirs,
    jedi_available,
    pyright_available,
    spec_ready,
)

OnProgress = Callable[[str], None] | None

# Friendly names → catalog id (in addition to spec.id and the status table number).
_ALIASES: dict[str, str] = {
    "python": "python-pyright",
    "py": "python-pyright",
    "pyright": "python-pyright",
    "basedpyright": "python-basedpyright",
    "pylsp": "python-pylsp",
    "jedi": "python-jedi",
    "js": "typescript",
    "ts": "typescript",
    "javascript": "typescript",
    "typescript": "typescript",
    "json": "json",
    "html": "html",
    "css": "css",
    "yaml": "yaml",
    "yml": "yaml",
    "bash": "bash",
    "shell": "bash",
    "sh": "bash",
    "zsh": "bash",
    "docker": "dockerfile",
    "dockerfile": "dockerfile",
    "go": "go",
    "golang": "go",
    "gopls": "go",
    "rust": "rust",
    "rs": "rust",
    "rust-analyzer": "rust",
    "c": "clangd",
    "cpp": "clangd",
    "c++": "clangd",
    "cxx": "clangd",
    "clangd": "clangd",
    "llvm": "clangd",
    "lua": "lua",
    "php": "php",
    "intelephense": "php",
    "ruby": "ruby",
    "rb": "ruby",
    "solargraph": "ruby",
    "vue": "vue",
    "md": "markdown",
    "markdown": "markdown",
    "marksman": "markdown",
    "toml": "toml",
    "taplo": "toml",
}

_KEYWORD_RECOMMENDED = frozenset({"recommended", "default", "y", "yes"})
_KEYWORD_ALL = frozenset({"all", "*"})
_KEYWORD_MISSING = frozenset({"missing", "not-ready", "pending"})
_KEYWORD_OPTIONAL = frozenset({"optional"})

_TOOLCHAIN_LABELS = {
    "npm": "Node.js (npm) — Homebrew install if missing",
    "go": "Go toolchain — Homebrew install if missing, then gopls",
    "rustup": "rustup — Homebrew/rustup-init if missing, then rust-analyzer",
    "cargo": "Rust cargo (crate install)",
    "gem": "RubyGems — Homebrew Ruby if missing",
    "brew": "Homebrew formulae",
    "pip": "Python packages (uv/pip into this Holix interpreter)",
    "apt": "apt (Linux; command is printed, not run with sudo)",
}


def _run(
    cmd: list[str],
    *,
    timeout: int = 180,
    env: dict[str, str] | None = None,
    visible: bool = False,
) -> tuple[bool, str]:
    merged = dict(os.environ)
    merged.setdefault("NONINTERACTIVE", "1")
    merged.setdefault("HOMEBREW_NO_AUTO_UPDATE", "1")
    if env:
        merged.update(env)
    try:
        if visible:
            proc = subprocess.run(cmd, check=False, timeout=timeout, env=merged)
            if proc.returncode != 0:
                return False, f"exit {proc.returncode}: {' '.join(cmd)}"
            return True, " ".join(cmd)
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    text = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, text.strip() or f"exit {proc.returncode}"
    return True, text.strip()


def prepend_bin_dirs_to_path() -> None:
    """So a server installed this session is visible to holix lsp status / the agent."""
    parts = [str(p) for p in extra_bin_dirs() if p.is_dir()]
    current = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join([*parts, current]) if parts else current


def _which(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for directory in extra_bin_dirs():
        for extra in (name, f"{name}.exe", f"{name}.cmd"):
            candidate = directory / extra
            if candidate.is_file():
                return str(candidate)
    return None


def _note(on_progress: OnProgress, message: str) -> None:
    if on_progress:
        on_progress(message)


def _pip_install(package: str, on_progress: OnProgress = None) -> tuple[bool, str]:
    commands = [
        [sys.executable, "-m", "pip", "install", package],
    ]
    uv = shutil.which("uv")
    if uv:
        commands.insert(0, [uv, "pip", "install", "--python", sys.executable, package])
        commands.insert(1, [uv, "pip", "install", package])
    last_err = "pip/uv not available"
    _note(on_progress, f"pip/uv install {package}")
    for cmd in commands:
        ok, out = _run(cmd, timeout=300)
        if ok:
            prepend_bin_dirs_to_path()
            return True, f"Installed {package}"
        last_err = out or last_err
    return False, last_err


def _ensure_brew(on_progress: OnProgress = None) -> tuple[bool, str]:
    if _which("brew"):
        return True, "brew ready"
    _note(on_progress, "Homebrew not found")
    return False, "Homebrew not found. Install from https://brew.sh then re-run holix lsp setup"


def _brew_link_prefix(formula: str) -> None:
    brew = _which("brew")
    if not brew:
        return
    ok, out = _run([brew, "--prefix", formula], timeout=30)
    if not ok or not out:
        return
    bin_dir = Path(out.splitlines()[-1].strip()) / "bin"
    if bin_dir.is_dir():
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
    prepend_bin_dirs_to_path()


def _ensure_node(on_progress: OnProgress = None) -> tuple[bool, str]:
    prepend_bin_dirs_to_path()
    if _which("npm") and _which("node"):
        return True, "node/npm ready"
    ok_b, msg_b = _ensure_brew(on_progress)
    if not ok_b:
        return (
            False,
            "Node.js/npm not found. Install Node 22+ (nvm, brew install node) then re-run.",
        )
    brew = _which("brew") or "brew"
    _note(on_progress, "Installing Node.js via Homebrew (may take a few minutes)…")
    ok, out = _run([brew, "install", "node"], timeout=900, visible=True)
    prepend_bin_dirs_to_path()
    if _which("npm"):
        return True, "Installed Node.js via Homebrew"
    return False, out or msg_b


def _ensure_go(on_progress: OnProgress = None) -> tuple[bool, str]:
    prepend_bin_dirs_to_path()
    if _which("go"):
        return True, "go ready"
    ok_b, msg_b = _ensure_brew(on_progress)
    if not ok_b:
        return False, "Go not found. Install from https://go.dev/dl/ or: brew install go"
    brew = _which("brew") or "brew"
    _note(on_progress, "Installing Go via Homebrew (may take a few minutes)…")
    ok, out = _run([brew, "install", "go"], timeout=900, visible=True)
    prepend_bin_dirs_to_path()
    if _which("go"):
        return True, "Installed Go via Homebrew"
    return False, out or msg_b


def _ensure_rustup(on_progress: OnProgress = None) -> tuple[bool, str]:
    prepend_bin_dirs_to_path()
    if _which("rustup") and _which("cargo"):
        return True, "rustup ready"
    ok_b, msg_b = _ensure_brew(on_progress)
    if ok_b:
        brew = _which("brew") or "brew"
        _note(on_progress, "Installing rustup via Homebrew…")
        _run([brew, "install", "rustup"], timeout=900, visible=True)
        rustup_init = _which("rustup-init")
        if rustup_init:
            _note(on_progress, "Running rustup-init -y…")
            _run([rustup_init, "-y", "--no-modify-path"], timeout=400, visible=True)
        prepend_bin_dirs_to_path()
        if _which("rustup"):
            return True, "Installed rustup via Homebrew"
    if _which("rustup"):
        return True, "rustup ready"
    return False, msg_b if not ok_b else "rustup not found. Install: curl https://sh.rustup.rs | sh"


def _refresh_gem_bins() -> None:
    ruby = _which("ruby")
    if ruby:
        ok, out = _run(
            [ruby, "-e", "require 'rubygems'; print Gem.user_dir"],
            timeout=20,
        )
        if ok and out.strip():
            bin_dir = Path(out.strip()) / "bin"
            if bin_dir.is_dir():
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
    prepend_bin_dirs_to_path()


def _ensure_ruby_gem(on_progress: OnProgress = None) -> tuple[bool, str]:
    prepend_bin_dirs_to_path()
    if _which("gem"):
        return True, "gem ready"
    ok_b, msg_b = _ensure_brew(on_progress)
    if not ok_b:
        return False, "RubyGems not found. Install Ruby, then: gem install solargraph"
    brew = _which("brew") or "brew"
    _note(on_progress, "Installing Ruby via Homebrew…")
    ok, out = _run([brew, "install", "ruby"], timeout=900, visible=True)
    prepend_bin_dirs_to_path()
    if _which("gem"):
        _refresh_gem_bins()
        return True, "Installed Ruby via Homebrew"
    return False, out or msg_b


def install_pyright() -> tuple[bool, str]:
    if pyright_available():
        return True, "Pyright already installed"
    ok, msg = _pip_install("pyright")
    prepend_bin_dirs_to_path()
    if ok and pyright_available():
        return True, "Installed Pyright (pyright-langserver)"
    if ok:
        return (
            True,
            "Installed Pyright package (restart the shell if pyright-langserver is not on PATH)",
        )
    ok_n, _ = _ensure_node()
    npm = _which("npm")
    if ok_n and npm:
        ok2, out_n = _run([npm, "install", "-g", "pyright"], timeout=180, visible=True)
        prepend_bin_dirs_to_path()
        if ok2:
            return True, "Installed Pyright via npm"
        return False, out_n or msg
    return False, msg


def install_jedi() -> tuple[bool, str]:
    if jedi_available():
        return True, "jedi already installed"
    return _pip_install("jedi")


def _npm_install(packages: list[str], on_progress: OnProgress = None) -> tuple[bool, str]:
    ok_n, msg_n = _ensure_node(on_progress)
    if not ok_n:
        return False, msg_n
    npm = _which("npm")
    if not npm:
        return False, "npm not found after Node install"
    unique: list[str] = []
    for pkg in packages:
        if pkg and pkg not in unique:
            unique.append(pkg)
    if not unique:
        return True, "no npm packages"
    _note(on_progress, "npm install -g " + " ".join(unique))
    ok, out = _run([npm, "install", "-g", *unique], timeout=400, visible=True)
    prepend_bin_dirs_to_path()
    if ok:
        return True, "Installed npm packages: " + ", ".join(unique)
    return False, out


def _try_kind(kind: str, value: str, on_progress: OnProgress = None) -> tuple[bool, str]:
    tokens = value.split()
    if kind == "extra":
        return False, "skip extra (use pip/npm packages from the spec)"
    if kind == "pip":
        pkg = tokens[0] if tokens else value
        return _pip_install(pkg, on_progress)
    if kind == "npm":
        return _npm_install(tokens, on_progress)
    if kind == "brew":
        ok_b, msg_b = _ensure_brew(on_progress)
        if not ok_b:
            return False, msg_b
        brew = _which("brew") or "brew"
        _note(on_progress, "brew install " + " ".join(tokens))
        ok, out = _run([brew, "install", *tokens], timeout=900, visible=True)
        prepend_bin_dirs_to_path()
        for formula in tokens:
            if not formula.startswith("-"):
                _brew_link_prefix(formula)
        return (True, f"brew install {' '.join(tokens)}") if ok else (False, out)
    if kind == "apt":
        if IS_WINDOWS or sys.platform == "darwin":
            return False, "apt skipped on this OS"
        apt = _which("apt-get") or _which("apt")
        if not apt:
            return False, "apt-get not found"
        return False, f"Run as admin: sudo apt install {' '.join(tokens)}"
    if kind == "go":
        ok_g, msg_g = _ensure_go(on_progress)
        if not ok_g:
            return False, msg_g
        go = _which("go") or "go"
        gobin = Path.home() / "go" / "bin"
        gobin.mkdir(parents=True, exist_ok=True)
        _note(on_progress, f"go install {value}")
        ok, out = _run(
            [go, "install", value],
            timeout=600,
            env={"GOBIN": str(gobin)},
            visible=True,
        )
        prepend_bin_dirs_to_path()
        return (True, f"go install {value}") if ok else (False, out)
    if kind == "rustup":
        ok_r, msg_r = _ensure_rustup(on_progress)
        if not ok_r:
            return False, msg_r
        rustup = _which("rustup") or "rustup"
        if not tokens:
            cmd = [rustup, "component", "add", "rust-analyzer"]
        elif tokens[0] == "component" or "component" in tokens:
            cmd = [rustup, *tokens]
        else:
            cmd = [rustup, "component", "add", *tokens]
        _note(on_progress, " ".join(cmd))
        ok, out = _run(cmd, timeout=400, visible=True)
        prepend_bin_dirs_to_path()
        return (True, " ".join(cmd)) if ok else (False, out)
    if kind == "cargo":
        ok_r, msg_r = _ensure_rustup(on_progress)
        if not ok_r and not _which("cargo"):
            return False, msg_r
        cargo = _which("cargo") or "cargo"
        _note(on_progress, "cargo install " + " ".join(tokens))
        ok, out = _run([cargo, "install", *tokens], timeout=900, visible=True)
        prepend_bin_dirs_to_path()
        return (True, f"cargo install {' '.join(tokens)}") if ok else (False, out)
    if kind == "gem":
        ok_g, msg_g = _ensure_ruby_gem(on_progress)
        if not ok_g:
            return False, msg_g
        gem = _which("gem") or "gem"
        _note(on_progress, "gem install --user-install " + " ".join(tokens))
        ok, out = _run([gem, "install", "--user-install", *tokens], timeout=400, visible=True)
        _refresh_gem_bins()
        return (True, f"gem install {' '.join(tokens)}") if ok else (False, out)
    return False, f"unknown install kind {kind}"


def install_spec(spec: LspServerSpec, on_progress: OnProgress = None) -> list[str]:
    """Install one catalog entry and whatever toolchain it needs."""
    prepend_bin_dirs_to_path()
    if spec_ready(spec):
        return [f"ok: {spec.title} already installed"]
    lines: list[str] = []
    last_err = ""
    _note(on_progress, f"Installing {spec.title}…")
    for kind, value in spec.install:
        if kind == "extra":
            continue
        ok, msg = _try_kind(kind, value, on_progress)
        if ok:
            lines.append(f"ok: {msg}")
        else:
            last_err = msg
            lines.append(f"skip: {kind}: {msg}")
        if spec_ready(spec):
            lines.append(f"ok: {spec.title} ready")
            return lines
    if spec_ready(spec):
        lines.append(f"ok: {spec.title} ready")
        return lines
    lines.append(f"error: could not install {spec.title}" + (f" ({last_err})" if last_err else ""))
    return lines


def install_specs(specs: list[LspServerSpec], on_progress: OnProgress = None) -> list[str]:
    prepend_bin_dirs_to_path()
    lines: list[str] = []
    pending: list[LspServerSpec] = []
    for spec in specs:
        if spec_ready(spec):
            lines.append(f"ok: {spec.title} already installed")
        else:
            pending.append(spec)

    npm_pkgs: list[str] = []
    for spec in pending:
        first = next((kind for kind, _value in spec.install if kind != "extra"), None)
        if first != "npm":
            continue
        for kind, value in spec.install:
            if kind == "npm":
                npm_pkgs.extend(value.split())
    if npm_pkgs:
        ok, msg = _npm_install(npm_pkgs, on_progress)
        lines.append(("ok: " if ok else "error: ") + msg)
        prepend_bin_dirs_to_path()

    for spec in pending:
        if spec_ready(spec):
            lines.append(f"ok: {spec.title} ready")
            continue
        lines.extend(install_spec(spec, on_progress))
    return lines


def parse_selection(
    raw: str, catalog: tuple[LspServerSpec, ...] | None = None
) -> list[LspServerSpec]:
    """Parse 'recommended' / 'all' / 'missing' / 'optional' / ids / numbers / aliases.

    Tokens can be mixed: ``recommended,go,rust`` or ``12 15 vue``.
    """
    items = catalog or CATALOG
    text = (raw or "").strip().lower()
    if not text:
        return [s for s in items if s.recommended]
    tokens = [t for t in text.replace(";", " ").replace(",", " ").split() if t]
    if len(tokens) == 1 and tokens[0] in _KEYWORD_ALL:
        return list(items)
    if len(tokens) == 1 and tokens[0] in _KEYWORD_RECOMMENDED:
        return [s for s in items if s.recommended]
    if len(tokens) == 1 and tokens[0] in _KEYWORD_MISSING:
        return [s for s in items if not spec_ready(s)]
    if len(tokens) == 1 and tokens[0] in _KEYWORD_OPTIONAL:
        return [s for s in items if not s.recommended]

    by_id = {s.id.lower(): s for s in items}
    by_num = {str(i): s for i, s in enumerate(items, start=1)}
    picked: list[LspServerSpec] = []
    seen: set[str] = set()

    def add(spec: LspServerSpec) -> None:
        if spec.id not in seen:
            seen.add(spec.id)
            picked.append(spec)

    for token in tokens:
        if token in _KEYWORD_ALL:
            return list(items)
        if token in _KEYWORD_RECOMMENDED:
            for spec in items:
                if spec.recommended:
                    add(spec)
            continue
        if token in _KEYWORD_OPTIONAL:
            for spec in items:
                if not spec.recommended:
                    add(spec)
            continue
        if token in _KEYWORD_MISSING:
            for spec in items:
                if not spec_ready(spec):
                    add(spec)
            continue
        spec = by_num.get(token) or by_id.get(token)
        if spec is None:
            alias = _ALIASES.get(token)
            if alias:
                spec = by_id.get(alias)
        if spec is None:
            raise ValueError(f"unknown language server: {token}")
        add(spec)
    if not picked:
        raise ValueError("nothing selected")
    return picked


def toolchain_labels(specs: list[LspServerSpec]) -> list[str]:
    """Human-readable toolchains that will be ensured for the given servers."""
    seen: set[str] = set()
    labels: list[str] = []
    for spec in specs:
        if spec_ready(spec):
            continue
        for kind, _value in spec.install:
            if kind in {"extra"} or kind in seen:
                continue
            seen.add(kind)
            labels.append(_TOOLCHAIN_LABELS.get(kind, kind))
    return labels


def install_recommended(*, npm: bool = True, on_progress: OnProgress = None) -> list[str]:
    """Install the default Python + (if Node) web language servers."""
    specs = [s for s in CATALOG if s.recommended]
    if not npm:
        specs = [s for s in specs if s.id.startswith("python")]
    return install_specs(specs, on_progress)


def setup_summary() -> dict[str, Any]:
    from core.tools.lsp_servers import status_rows

    rows = status_rows()
    return {
        "ready": [r for r in rows if r["ready"]],
        "missing_recommended": [r for r in rows if r["recommended"] and not r["ready"]],
        "optional": [r for r in rows if not r["recommended"] and not r["ready"]],
        "has_npm": bool(_which("npm")),
        "has_node": bool(_which("node")),
        "rows": rows,
    }


def catalog_choices() -> list[tuple[int, LspServerSpec, bool]]:
    return [(i, spec, spec_ready(spec)) for i, spec in enumerate(CATALOG, start=1)]
