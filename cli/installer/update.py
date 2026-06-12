"""Universal Holix updater (git source, uv tool, pip / PyPI)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from cli import __version__
from cli.installer.manifest import InstallManifest, load_manifest, save_manifest
from cli.installer.system import (
    InstallOptions,
    _has_uv,
    detect_repo_root,
    install_holix,
)

PYPI_PACKAGE = "Holix"
_VERSION_RE = re.compile(r"^v?(\d+\.\d+\.\d+)")


@dataclass(frozen=True, slots=True)
class UpdateOptions:
    check_only: bool = False
    channel: str = "auto"  # auto | git | pypi
    repo: Path | None = None
    force: bool = False
    no_fetch: bool = False


@dataclass(frozen=True, slots=True)
class UpdateResult:
    success: bool
    message: str
    current_version: str
    target_version: str | None = None
    updated: bool = False
    behind_commits: int | None = None


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _git_available(repo: Path) -> bool:
    return (repo / ".git").is_dir() and shutil.which("git") is not None


def _git_meta(repo: Path) -> tuple[str | None, str | None]:
    remote = _run(["git", "remote", "get-url", "origin"], cwd=repo)
    branch = _run(["git", "branch", "--show-current"], cwd=repo)
    return (
        remote.stdout.strip() if remote.returncode == 0 else None,
        branch.stdout.strip() if branch.returncode == 0 else None,
    )


def _git_behind(repo: Path, *, fetch: bool) -> tuple[int, str]:
    if fetch:
        fetch_r = _run(["git", "fetch", "--quiet"], cwd=repo, timeout=180)
        if fetch_r.returncode != 0:
            return 0, (fetch_r.stderr or fetch_r.stdout or "git fetch failed").strip()

    upstream = _run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        cwd=repo,
    )
    if upstream.returncode != 0:
        return 0, "no upstream branch (set upstream or use --repo)"

    count_r = _run(
        ["git", "rev-list", "--count", f"HEAD..{upstream.stdout.strip()}"],
        cwd=repo,
    )
    if count_r.returncode != 0:
        return 0, count_r.stderr.strip() or "cannot compare with upstream"

    try:
        behind = int(count_r.stdout.strip())
    except ValueError:
        behind = 0
    return behind, ""


def _git_pull(repo: Path) -> tuple[bool, str]:
    r = _run(["git", "pull", "--ff-only"], cwd=repo, timeout=300)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "git pull failed").strip()
    return True, r.stdout.strip() or "git pull ok"


def _read_project_version(repo: Path) -> str:
    text = (repo / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    return match.group(1) if match else __version__


def _pypi_latest_version(package: str = PYPI_PACKAGE) -> str | None:
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return str(data["info"]["version"])
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError):
        return None


def _parse_version(version: str) -> tuple[int, ...]:
    match = _VERSION_RE.match(version.strip())
    if not match:
        return (0,)
    return tuple(int(x) for x in match.group(1).split("."))


def _version_lt(a: str, b: str) -> bool:
    return _parse_version(a) < _parse_version(b)


def _infer_repo_from_package() -> Path | None:
    try:
        import cli

        return detect_repo_root(Path(cli.__file__).resolve())
    except (FileNotFoundError, ImportError):
        return None


def resolve_update_context(opts: UpdateOptions) -> tuple[InstallManifest, Path | None]:
    """Return manifest + repo path to use for this update."""
    manifest = load_manifest()
    repo: Path | None = opts.repo

    if repo is None and manifest and manifest.repo_root:
        candidate = Path(manifest.repo_root)
        if candidate.is_dir():
            repo = candidate

    if repo is None:
        repo = _infer_repo_from_package()

    if manifest is None:
        source = "git" if repo and _git_available(repo) else "pypi"
        manifest = InstallManifest(
            version=__version__,
            method="uv-tool" if _has_uv() else "pip",
            scope="user",
            source=source,
            extras=[],
            installed_at="",
            repo_root=str(repo) if repo else None,
        )
        if repo and _git_available(repo):
            remote, branch = _git_meta(repo)
            manifest = InstallManifest(
                version=__version__,
                method=manifest.method,
                scope="user",
                source="git",
                extras=[],
                installed_at="",
                repo_root=str(repo),
                git_remote=remote,
                git_branch=branch,
            )

    return manifest, repo


def _channel(manifest: InstallManifest, opts: UpdateOptions) -> str:
    if opts.channel != "auto":
        return opts.channel
    if manifest.source == "git":
        return "git"
    if manifest.source == "pypi":
        return "pypi"
    if manifest.repo_root and Path(manifest.repo_root).is_dir() and _git_available(Path(manifest.repo_root)):
        return "git"
    return "pypi"


def update_holix(opts: UpdateOptions) -> UpdateResult:
    """Check for or apply a Holix update."""
    manifest, repo = resolve_update_context(opts)
    current = __version__
    channel = _channel(manifest, opts)

    if channel == "git":
        return _update_from_git(manifest, repo, opts, current)
    return _update_from_pypi(manifest, opts, current)


def _update_from_git(
    manifest: InstallManifest,
    repo: Path | None,
    opts: UpdateOptions,
    current: str,
) -> UpdateResult:
    if repo is None or not repo.is_dir():
        return UpdateResult(
            False,
            "Git update requires a local repository. "
            "Re-clone Holix or run `holix install --repo /path/to/Holix`.",
            current_version=current,
        )

    if not _git_available(repo):
        return UpdateResult(
            False,
            f"{repo} is not a git repository.",
            current_version=current,
        )

    behind, err = _git_behind(repo, fetch=not opts.no_fetch)
    target_version = _read_project_version(repo)
    remote_configured = not err

    if err and opts.check_only:
        local_newer = _version_lt(current, target_version)
        msg = (
            f"Remote tracking not configured ({err}). "
            f"Local tree version: {target_version}."
        )
        if local_newer:
            msg += f" Reinstall recommended: {current} → {target_version}."
        else:
            msg += " Run `holix update --force` to reinstall from the current tree."
        return UpdateResult(
            True,
            msg,
            current_version=current,
            target_version=target_version,
            updated=False,
            behind_commits=None,
        )

    if err:
        behind = 0

    if opts.check_only:
        if remote_configured and (behind > 0 or _version_lt(current, target_version)):
            return UpdateResult(
                True,
                f"Update available: {behind} commit(s) on upstream, "
                f"version {current} → {target_version}",
                current_version=current,
                target_version=target_version,
                updated=False,
                behind_commits=behind,
            )
        return UpdateResult(
            True,
            f"Already up to date ({current}, branch clean vs upstream).",
            current_version=current,
            target_version=target_version,
            updated=False,
            behind_commits=behind if remote_configured else None,
        )

    needs_reinstall = opts.force or behind > 0 or _version_lt(current, target_version)
    if not needs_reinstall:
        return UpdateResult(
            True,
            f"Already up to date ({current}).",
            current_version=current,
            target_version=target_version,
            updated=False,
            behind_commits=0,
        )

    if behind > 0:
        ok, pull_msg = _git_pull(repo)
        if not ok:
            return UpdateResult(False, pull_msg, current_version=current)
        target_version = _read_project_version(repo)
    elif not remote_configured:
        pull_msg = "skipped git pull (no upstream); reinstalling from local tree"
    else:
        pull_msg = "skipped git pull (already aligned with upstream)"

    install_opts = InstallOptions(
        repo_root=repo,
        scope=manifest.scope,
        update_path=False,
        extras=tuple(manifest.extras),
    )
    install_result = install_holix(install_opts)
    if not install_result.success:
        return UpdateResult(
            False,
            install_result.message,
            current_version=current,
            target_version=target_version,
        )

    from cli.installer.system import record_install

    record_install(
        install_result,
        InstallOptions(
            repo_root=repo,
            scope=manifest.scope,
            update_path=False,
            extras=tuple(manifest.extras),
        ),
        repo_root=repo,
    )

    msg = (
        f"{pull_msg}\n"
        f"Reinstalled via {install_result.method}\n"
        f"Version: {current} → {target_version}\n"
        f"{install_result.message.strip()}"
    )
    return UpdateResult(
        True,
        msg,
        current_version=current,
        target_version=target_version,
        updated=True,
        behind_commits=behind,
    )


def _update_from_pypi(
    manifest: InstallManifest,
    opts: UpdateOptions,
    current: str,
) -> UpdateResult:
    latest = _pypi_latest_version()
    if latest is None:
        if manifest.repo_root and Path(manifest.repo_root).is_dir():
            return _update_from_git(manifest, Path(manifest.repo_root), opts, current)
        return UpdateResult(
            False,
            "Could not reach PyPI and no local git repository is configured. "
            "Use `holix install --repo /path/to/Holix` or set channel to git.",
            current_version=current,
        )

    if opts.check_only:
        if _version_lt(current, latest):
            return UpdateResult(
                True,
                f"PyPI update available: {current} → {latest}",
                current_version=current,
                target_version=latest,
                updated=False,
            )
        return UpdateResult(
            True,
            f"Already latest on PyPI ({current}).",
            current_version=current,
            target_version=latest,
            updated=False,
        )

    if not opts.force and not _version_lt(current, latest):
        return UpdateResult(
            True,
            f"Already latest ({current}).",
            current_version=current,
            target_version=latest,
            updated=False,
        )

    python = shutil.which("python3") or shutil.which("python")
    if not python:
        return UpdateResult(False, "Python not found", current_version=current)

    spec = PYPI_PACKAGE
    if manifest.extras:
        spec = f"{PYPI_PACKAGE}[{','.join(manifest.extras)}]"

    if _has_uv():
        cmd = [_has_uv(), "pip", "install", "--upgrade", "--python", python, spec]
        method = "uv pip"
    else:
        cmd = [python, "-m", "pip", "install", "--upgrade"]
        if manifest.scope == "user":
            cmd.append("--user")
        cmd.append(spec)
        method = "pip"

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        return UpdateResult(
            False,
            (r.stderr or r.stdout or "upgrade failed").strip(),
            current_version=current,
            target_version=latest,
        )

    from cli.installer.manifest import build_manifest

    save_manifest(
        build_manifest(
            version=latest,
            method=method,
            scope=manifest.scope,
            source="pypi",
            extras=tuple(manifest.extras),
            repo_root=None,
            holix_path=Path(shutil.which("holix") or ""),
            bin_dir=None,
        )
    )

    return UpdateResult(
        True,
        f"Upgraded via {method}: {current} → {latest}",
        current_version=current,
        target_version=latest,
        updated=True,
    )