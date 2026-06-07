"""Install Helix CLI into the user or system PATH (macOS, Linux, Windows)."""

from __future__ import annotations

import os
import platform
import re
import shutil
import site
import subprocess
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path

MIN_PYTHON = (3, 14)


@dataclass(frozen=True, slots=True)
class InstallOptions:
    repo_root: Path
    scope: str = "user"  # "user" | "system"
    update_path: bool = True
    extras: tuple[str, ...] = ()  # e.g. ("telegram", "browser")


@dataclass(frozen=True, slots=True)
class InstallResult:
    success: bool
    message: str
    helix_path: Path | None = None
    bin_dir: Path | None = None
    path_updated: bool = False
    method: str = "pip"
    version: str = ""


def detect_repo_root(start: Path | None = None) -> Path:
    """Find repository root (directory containing pyproject.toml with helix)."""
    cur = (start or Path(__file__)).resolve()
    if cur.is_file():
        cur = cur.parent
    for parent in [cur, *cur.parents]:
        pyproject = parent / "pyproject.toml"
        if pyproject.is_file():
            text = pyproject.read_text(encoding="utf-8")
            if 'name = "helix-agent-ai"' in text or 'name = "helix-agent"' in text or 'name = "helix"' in text:
                return parent
    raise FileNotFoundError("Helix repository root not found (pyproject.toml)")


def _python_version_ok(exe: str) -> bool:
    try:
        out = subprocess.run(
            [exe, "-c", "import sys; print(sys.version_info[:2])"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        major, minor = map(int, out.stdout.strip().strip("()").split(","))
        return (major, minor) >= MIN_PYTHON
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def find_python() -> str:
    """Return a Python 3.14+ executable path."""
    candidates: list[str] = [sys.executable]
    for name in ("python3.14", "python3", "python", "py"):
        found = shutil.which(name)
        if found and found not in candidates:
            candidates.append(found)

    for exe in candidates:
        if _python_version_ok(exe):
            return exe

    raise RuntimeError(
        f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required. "
        "Install from https://www.python.org/downloads/ or use pyenv/uv."
    )


def _has_uv() -> str | None:
    return shutil.which("uv")


def scripts_bin_dir(python_exe: str, *, scope: str) -> Path:
    """Directory where console_scripts (helix) are installed."""
    if platform.system() == "Windows":
        if scope == "system":
            return Path(sysconfig.get_path("scripts"))
        user_base = Path(site.USER_BASE)
        return user_base / "Scripts"

    if scope == "system":
        return Path(sysconfig.get_path("scripts"))

    user_base = Path(site.getuserbase())
    return user_base / "bin"


def _helix_executable(bin_dir: Path) -> Path | None:
    if platform.system() == "Windows":
        for name in ("helix.exe", "helix.cmd", "helix"):
            path = bin_dir / name
            if path.is_file():
                return path
        return None
    path = bin_dir / "helix"
    return path if path.is_file() or path.is_symlink() else None


def _target_spec(opts: InstallOptions) -> str:
    if opts.extras:
        return f".[{','.join(opts.extras)}]"
    return "."


def _pip_install(python_exe: str, repo_root: Path, opts: InstallOptions) -> None:
    cmd = [python_exe, "-m", "pip", "install"]
    if opts.scope == "user":
        cmd.append("--user")
    elif platform.system() != "Windows":
        cmd.append("--break-system-packages")
    cmd.append(_target_spec(opts))
    subprocess.run(cmd, cwd=str(repo_root), check=True, timeout=600)


def _uv_tool_install(repo_root: Path) -> None:
    uv = _has_uv()
    if not uv:
        raise FileNotFoundError("uv not found")
    subprocess.run(
        [uv, "tool", "install", "--force", str(repo_root)],
        check=True,
        timeout=600,
        cwd=str(repo_root),
    )


def _uv_pip_install(python_exe: str, repo_root: Path, opts: InstallOptions) -> None:
    uv = _has_uv()
    if not uv:
        raise FileNotFoundError("uv not found")
    cmd = [uv, "pip", "install", "--python", python_exe]
    if opts.scope == "system":
        cmd.append("--system")
    cmd.append(_target_spec(opts))
    subprocess.run(cmd, cwd=str(repo_root), check=True, timeout=600)


def install_helix(opts: InstallOptions) -> InstallResult:
    """Install helix from *opts.repo_root* and optionally update PATH."""
    repo_root = opts.repo_root.resolve()
    if not (repo_root / "pyproject.toml").is_file():
        return InstallResult(False, f"Not a Helix repo: {repo_root}")

    try:
        python_exe = find_python()
    except RuntimeError as e:
        return InstallResult(False, str(e))

    method = "pip"
    bin_dir = scripts_bin_dir(python_exe, scope=opts.scope)
    try:
        if _has_uv() and opts.scope == "user":
            try:
                _uv_tool_install(repo_root)
                method = "uv tool"
                bin_dir = Path.home() / ".local" / "bin"
                if platform.system() == "Windows":
                    bin_dir = (
                        Path(os.environ.get("USERPROFILE", Path.home())) / ".local" / "bin"
                    )
            except subprocess.CalledProcessError:
                _uv_pip_install(python_exe, repo_root, opts)
                method = "uv pip"
                bin_dir = scripts_bin_dir(python_exe, scope=opts.scope)
        elif _has_uv():
            _uv_pip_install(python_exe, repo_root, opts)
            method = "uv pip"
            bin_dir = scripts_bin_dir(python_exe, scope=opts.scope)
        else:
            _pip_install(python_exe, repo_root, opts)
            bin_dir = scripts_bin_dir(python_exe, scope=opts.scope)
    except subprocess.CalledProcessError as e:
        return InstallResult(False, f"Install failed ({e})")
    except OSError as e:
        return InstallResult(False, f"Install failed: {e}")

    helix_path = _helix_executable(bin_dir)
    if helix_path is None:
        # uv tool may use different layout — scan common dirs
        for candidate in (
            bin_dir,
            Path.home() / ".local" / "bin",
            scripts_bin_dir(python_exe, scope=opts.scope),
        ):
            helix_path = _helix_executable(candidate)
            if helix_path:
                bin_dir = candidate
                break

    if helix_path is None:
        return InstallResult(
            False,
            f"Install finished via {method} but `helix` executable was not found. "
            f"Check {bin_dir}",
            bin_dir=bin_dir,
        )

    path_updated = False
    path_msg = ""
    if opts.update_path:
        path_updated, path_msg = ensure_path_in_shell(bin_dir)

    msg = (
        f"Helix installed via {method}\n"
        f"  binary: {helix_path}\n"
        f"  bin dir: {bin_dir}\n"
    )
    if path_msg:
        msg += f"  PATH: {path_msg}\n"
    if not path_updated and opts.update_path:
        msg += f"  Add to PATH: export PATH=\"{bin_dir}:$PATH\"\n"

    version = _read_installed_version(repo_root)

    return InstallResult(
        True,
        msg,
        helix_path=helix_path,
        bin_dir=bin_dir,
        path_updated=path_updated,
        method=method,
        version=version,
    )


def _path_contains(path_var: str, directory: str) -> bool:
    parts = path_var.split(os.pathsep) if platform.system() == "Windows" else path_var.split(":")
    norm = os.path.normcase(os.path.normpath(directory))
    return any(os.path.normcase(os.path.normpath(p)) == norm for p in parts if p)


def ensure_path_in_shell(bin_dir: Path) -> tuple[bool, str]:
    """Append *bin_dir* to the user PATH (shell rc or Windows user env)."""
    bin_str = str(bin_dir.resolve())
    system = platform.system()

    if system == "Windows":
        return _ensure_path_windows(bin_str)

    updated = False
    messages: list[str] = []
    export_line = f'export PATH="{bin_str}:$PATH"  # helix'
    marker = "# helix"

    for rc_name in (".zshrc", ".bashrc", ".profile"):
        rc = Path.home() / rc_name
        if not rc.exists():
            continue
        text = rc.read_text(encoding="utf-8", errors="replace")
        if bin_str in text or marker in text:
            messages.append(f"already in {rc_name}")
            updated = True
            continue
        with rc.open("a", encoding="utf-8") as f:
            f.write(f"\n{marker}\n{export_line}\n")
        messages.append(f"updated {rc_name}")
        updated = True

    return updated, "; ".join(messages) if messages else "add PATH manually"


def _ensure_path_windows(bin_str: str) -> tuple[bool, str]:
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Environment",
            0,
            winreg.KEY_READ | winreg.KEY_SET_VALUE,
        )
        try:
            current, _ = winreg.QueryValueEx(key, "Path")
        except OSError:
            current = ""
        if _path_contains(current, bin_str):
            winreg.CloseKey(key)
            return True, "already in user PATH"
        new_path = f"{bin_str};{current}" if current else bin_str
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
        winreg.CloseKey(key)
        os.environ["Path"] = f"{bin_str};{os.environ.get('Path', '')}"
        return True, "updated Windows user PATH (open a new terminal)"
    except Exception as e:
        return False, f"Windows PATH update failed: {e}"


def _install_source(repo_root: Path) -> tuple[str, str | None, str | None]:
    """Return (source, git_remote, git_branch)."""
    if not (repo_root / ".git").is_dir() or not shutil.which("git"):
        return "local", None, None
    remote = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return (
        "git",
        remote.stdout.strip() if remote.returncode == 0 else None,
        branch.stdout.strip() if branch.returncode == 0 else None,
    )


def record_install(
    result: InstallResult,
    opts: InstallOptions,
    *,
    repo_root: Path,
) -> None:
    """Persist install metadata for ``helix update``."""
    from cli import __version__
    from cli.installer.manifest import build_manifest, save_manifest

    source, git_remote, git_branch = _install_source(repo_root)
    version = result.version or _read_installed_version(repo_root) or __version__
    save_manifest(
        build_manifest(
            version=version,
            method=result.method,
            scope=opts.scope,
            source=source,
            extras=opts.extras,
            repo_root=repo_root,
            helix_path=result.helix_path,
            bin_dir=result.bin_dir,
            git_remote=git_remote,
            git_branch=git_branch,
        )
    )


def _read_installed_version(repo_root: Path) -> str:
    text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    return match.group(1) if match else ""


def verify_helix_on_path() -> tuple[bool, str]:
    """Check whether `helix` is invocable."""
    found = shutil.which("helix")
    if found:
        try:
            out = subprocess.run(
                [found, "version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if out.returncode == 0:
                return True, found
        except (OSError, subprocess.SubprocessError):
            return True, found
        return True, found
    return False, "helix not found on PATH"