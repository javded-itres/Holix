"""Install Holix from PyPI via pipx or uv tool."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MIN_PYTHON = (3, 12)


@dataclass(frozen=True, slots=True)
class PyPIInstallResult:
    success: bool
    message: str
    holix_path: str | None = None
    method: str = ""


def _python_ok(exe: str) -> bool:
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
    for exe in (sys.executable, *(shutil.which(n) for n in ("python3.14", "python3.13", "python3.12", "python3", "python"))):
        if exe and _python_ok(exe):
            return exe
    raise RuntimeError(
        f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required. "
        "Install from https://www.python.org/downloads/"
    )


def ensure_pipx(python: str) -> str | None:
    pipx = shutil.which("pipx")
    if pipx:
        return pipx
    print("Installing pipx…")
    subprocess.run(
        [python, "-m", "pip", "install", "--user", "pipx"],
        check=True,
        timeout=300,
    )
    subprocess.run([python, "-m", "pipx", "ensurepath"], check=False, timeout=60)
    return shutil.which("pipx") or str(Path.home() / ".local" / "bin" / "pipx")


def _holix_candidates() -> list[Path]:
    home = Path.home()
    if platform.system() == "Windows":
        return [
            home / ".local" / "bin" / "holix.exe",
            home / "AppData" / "Roaming" / "Python" / "Python312" / "Scripts" / "holix.exe",
        ]
    return [
        home / ".local" / "bin" / "holix",
        home / ".local" / "pipx" / "venvs" / "holix" / "bin" / "holix",
    ]


def locate_holix() -> str | None:
    found = shutil.which("holix")
    if found:
        return found
    for path in _holix_candidates():
        if path.is_file():
            return str(path)
    return None


def install_from_pypi(*, full: bool = False, force: bool = True) -> PyPIInstallResult:
    """Install Holix package from PyPI."""
    spec = "Holix[all]" if full else "Holix"
    try:
        python = find_python()
    except RuntimeError as exc:
        return PyPIInstallResult(False, str(exc))

    uv = shutil.which("uv")
    if uv:
        cmd = [uv, "tool", "install", spec]
        if force:
            cmd.insert(3, "--force")
        method = "uv tool"
    else:
        pipx = ensure_pipx(python)
        if not pipx:
            return PyPIInstallResult(False, "pipx not found after install attempt")
        cmd = [pipx, "install", spec]
        if force:
            cmd.append("--force")
        method = "pipx"

    env = os.environ.copy()
    local_bin = str(Path.home() / ".local" / "bin")
    env["PATH"] = f"{local_bin}{os.pathsep}{env.get('PATH', '')}"

    try:
        subprocess.run(cmd, check=True, timeout=900, env=env)
    except subprocess.CalledProcessError as exc:
        return PyPIInstallResult(False, f"Install failed ({exc})")
    except OSError as exc:
        return PyPIInstallResult(False, f"Install failed: {exc}")

    holix = locate_holix()
    if not holix:
        return PyPIInstallResult(
            False,
            f"Installed via {method}, but holix not found. "
            f"Add {local_bin} to PATH and open a new terminal.",
            method=method,
        )

    return PyPIInstallResult(
        True,
        f"Holix installed via {method}\n  package: {spec}\n  binary: {holix}",
        holix_path=holix,
        method=method,
    )