"""Resolve cwd and log directory for background project processes."""

from __future__ import annotations

import os
import re
from pathlib import Path


def resolve_background_process_root(working_directory: str = "") -> Path:
    """Pick the directory where a background dev server should run.

    Priority:
    1. Explicit ``working_directory`` from the tool call
    2. Workspace jail root (when jail is enabled)
    3. Profile workspace root from tool execution context
    4. Process current working directory
    """
    if working_directory and str(working_directory).strip():
        return Path(working_directory).expanduser().resolve()

    from core.tools.execution_context import get_workspace_root, is_workspace_jail_enabled
    from core.workspace import get_effective_workspace_root

    jail_root = get_effective_workspace_root()
    if jail_root is not None:
        return jail_root

    raw = get_workspace_root()
    if raw and str(raw).strip():
        candidate = Path(raw).expanduser()
        if candidate.is_dir():
            return candidate.resolve()

    if is_workspace_jail_enabled():
        raise ValueError(
            "Workspace jail is enabled but no workspace root is configured. "
            "Set workspace_root on the profile or pass working_directory."
        )

    return Path.cwd().resolve()


def background_log_dir(project_root: Path) -> Path:
    return project_root / ".holix" / "process-logs"


def project_venv_bin(project_root: Path) -> Path | None:
    """Return the project venv executable directory (Scripts on Windows, else bin)."""
    for rel in (".venv/Scripts", ".venv/bin"):
        candidate = project_root / rel
        if candidate.is_dir():
            return candidate
    return None


def build_background_spawn_env(project_root: Path) -> dict[str, str]:
    """Environment for detached dev servers: unbuffered logs + project venv on PATH."""
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    venv_bin = project_venv_bin(project_root)
    if venv_bin is not None:
        prefix = str(venv_bin)
        path = env.get("PATH", "")
        if prefix not in path.split(os.pathsep):
            env["PATH"] = f"{prefix}{os.pathsep}{path}" if path else prefix

    pythonpath = env.get("PYTHONPATH", "")
    root = str(project_root)
    if root not in [p for p in pythonpath.split(os.pathsep) if p]:
        env["PYTHONPATH"] = f"{root}{os.pathsep}{pythonpath}" if pythonpath else root

    return env


def resolve_argv_executable(argv: list[str], project_root: Path) -> list[str]:
    """Prefer project ``.venv/bin/<name>`` when the command uses a bare tool name."""
    if not argv:
        return argv
    venv_bin = project_venv_bin(project_root)
    if venv_bin is None:
        return argv

    first = argv[0]
    name = Path(first).name
    if first != name and not first.startswith(".venv/"):
        return argv

    candidate = venv_bin / name
    if candidate.is_file():
        return [str(candidate), *argv[1:]]
    return argv


_SHELL_OPERATORS = ("&&", "||", "|", ";", "\n")
_SHELL_PREFIXES = ("source ", "export ", ". ")


def command_needs_shell(command: str) -> bool:
    """True when the command relies on shell builtins or compound syntax."""
    text = (command or "").strip()
    if not text:
        return False
    if any(op in text for op in _SHELL_OPERATORS):
        return True
    return any(text.startswith(prefix) for prefix in _SHELL_PREFIXES)


_CD_RE = re.compile(
    r"(?P<pre>(?:^|&&|\|\||;|\n)[ \t]*cd[ \t]+)"
    r"(?P<path>\"[^\"]+\"|'[^']+'|[^\s;&|]+)"
)
_SKIP_LISTING = frozenset(
    {".git", ".holix", "node_modules", ".venv", "__pycache__", "dist", "build"}
)


def is_holix_linked_worktree(path: Path) -> bool:
    """True for ``<clone>/.holix/worktrees/<id>``."""
    return path.parent.name == "worktrees" and path.parent.parent.name == ".holix"


def prepare_worktree_project_launch(
    command: str,
    working_directory: str = "",
    workspace_root: Path | str | None = None,
    *,
    change_id: str = "",
) -> tuple[str, str]:
    """Point a dev-server launch at the change worktree.

    A session pinned to ``<clone>/.holix/worktrees/<id>`` already has that
    directory as its cwd. ``cd projects/<name>`` is a profile-workspace path
    and does not exist there, so the server never starts. Rewrite those
    paths (and ``working_directory``) onto the worktree.

    When the session jail is a product root and ``change_id`` is set, a
    ``cd`` into a member clone is rewritten to that clone's change worktree
    when the directory exists.
    """
    try:
        from core.runtime.git_worktree import worktrees_enabled

        if not worktrees_enabled():
            return command, working_directory
    except Exception:
        pass
    if workspace_root is None:
        return command, working_directory
    try:
        root = Path(workspace_root).expanduser().resolve()
    except OSError:
        return command, working_directory
    if not root.is_dir():
        return command, working_directory

    if is_holix_linked_worktree(root):
        return _prepare_inside_worktree(command, working_directory, root)

    change = (change_id or "").strip()
    if not change:
        return command, working_directory
    return _prepare_at_product_root(command, working_directory, root, change)


def _prepare_inside_worktree(
    command: str,
    working_directory: str,
    worktree: Path,
) -> tuple[str, str]:
    spawn = worktree
    wd = (working_directory or "").strip()
    if wd:
        mapped = _map_into_worktree(wd, worktree, worktree)
        if mapped is None:
            raise ValueError(_missing_worktree_dir(wd, worktree))
        spawn = mapped

    def _resolve(token: str) -> Path | None:
        if token.startswith("-"):
            return None
        return _map_into_worktree(token, worktree, spawn)

    rewritten = _rewrite_cd_commands(command, _resolve, spawn, strict=True, worktree=worktree)
    out_wd = str(spawn) if wd else working_directory
    return rewritten, out_wd


def _prepare_at_product_root(
    command: str,
    working_directory: str,
    product: Path,
    change_id: str,
) -> tuple[str, str]:
    spawn = product
    wd = (working_directory or "").strip()
    if wd:
        mapped = _map_into_change_worktree(wd, product, change_id, product)
        if mapped is not None:
            spawn = mapped

    def _resolve(token: str) -> Path | None:
        if token.startswith("-"):
            return None
        return _map_into_change_worktree(token, product, change_id, spawn)

    rewritten = _rewrite_cd_commands(
        command,
        _resolve,
        spawn,
        strict=False,
        worktree=product,
    )
    out_wd = str(spawn) if wd and spawn != product else working_directory
    if not wd and "cd " not in rewritten and spawn == product:
        only = _sole_change_worktree(product, change_id)
        if only is not None:
            out_wd = str(only)
    return rewritten, out_wd


def _rewrite_cd_commands(
    command: str,
    resolve_token,
    spawn: Path,
    *,
    strict: bool,
    worktree: Path,
) -> str:
    missing: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        raw = match.group("path")
        token = raw[1:-1] if len(raw) >= 2 and raw[0] in "\"'" and raw[0] == raw[-1] else raw
        if token.startswith("-") or token in {"", "."}:
            return match.group(0)
        mapped = resolve_token(token)
        if mapped is None:
            if strict and not _exists_under(token, spawn):
                missing.append(token)
            return match.group(0)
        shown = _cd_target(mapped, spawn)
        if shown == token.replace("\\", "/").strip("/"):
            return match.group(0)
        quoted = f"'{shown}'" if " " in shown else shown
        return f"{match.group('pre')}{quoted}"

    rewritten = _CD_RE.sub(_sub, command or "")
    if missing:
        raise ValueError(_missing_worktree_dir(missing[0], worktree))
    return rewritten


def _cd_target(mapped: Path, spawn: Path) -> str:
    try:
        rel = mapped.resolve().relative_to(spawn.resolve())
    except ValueError:
        return mapped.resolve().as_posix()
    if not rel.parts:
        return "."
    return rel.as_posix()


def _exists_under(token: str, spawn: Path) -> bool:
    path = Path(token).expanduser()
    if path.is_absolute():
        try:
            resolved = path.resolve()
        except OSError:
            return False
        return resolved.is_dir() and _is_under(resolved, spawn)
    try:
        return (spawn / path).is_dir()
    except OSError:
        return False


def _map_into_worktree(token: str, worktree: Path, spawn: Path) -> Path | None:
    """Map a workspace or clone path onto this change worktree."""
    raw = (token or "").strip().strip("\"'")
    if not raw or raw.startswith("-"):
        return None
    worktree = worktree.resolve()
    spawn = spawn.resolve()
    if raw in {".", "./"}:
        return spawn
    clone = worktree.parent.parent.parent
    anchor = _workspace_anchor(clone)
    cand = Path(raw).expanduser()

    if not cand.is_absolute():
        direct = _dir_under(spawn / cand, worktree)
        if direct is not None:
            return direct

    targets: list[Path] = []
    if cand.is_absolute():
        targets.append(cand)
    else:
        if anchor is not None:
            targets.append(anchor / cand)
        targets.append(clone / cand)

    for target in targets:
        mapped = _translate_clone_path(target, clone, worktree)
        if mapped is not None:
            return mapped

    rel = raw.replace("\\", "/").strip("/")
    prefixes: list[str] = []
    if anchor is not None:
        try:
            prefixes.append(clone.relative_to(anchor).as_posix())
        except ValueError:
            pass
    prefixes.append(clone.name)
    seen: set[str] = set()
    for prefix in prefixes:
        if not prefix or prefix in seen:
            continue
        seen.add(prefix)
        if rel == prefix:
            return worktree
        head = prefix + "/"
        if rel.startswith(head):
            dest = _dir_under(worktree / rel[len(head) :], worktree)
            if dest is not None:
                return dest

    if rel.startswith("projects/"):
        rest = rel[len("projects/") :]
        if rest and rest != clone.name:
            dest = _dir_under(worktree / rest, worktree)
            if dest is not None:
                return dest
    return None


def _map_into_change_worktree(
    token: str,
    product: Path,
    change_id: str,
    spawn: Path,
) -> Path | None:
    """Map ``cd <member>`` to ``<member>/.holix/worktrees/<change_id>``."""
    raw = (token or "").strip().strip("\"'")
    if not raw or raw.startswith("-"):
        return None
    product = product.resolve()
    if raw in {".", "./"}:
        only = _sole_change_worktree(product, change_id)
        return only
    cand = Path(raw).expanduser()
    if cand.is_absolute():
        try:
            rel = cand.resolve().relative_to(product)
        except (OSError, ValueError):
            return None
    else:
        rel = Path(raw.replace("\\", "/"))
        if any(part == ".." for part in rel.parts):
            return None
    return _walk_change_worktree(product, rel, change_id, spawn)


def _walk_change_worktree(
    product: Path,
    rel: Path,
    change_id: str,
    spawn: Path,
) -> Path | None:
    parts = rel.parts
    if not parts or any(part in {".", ".."} for part in parts):
        return None
    del spawn
    cursor = product
    for index, part in enumerate(parts):
        nxt = cursor / part
        worktree = nxt / ".holix" / "worktrees" / change_id
        if nxt.is_dir() and worktree.is_dir():
            rest = Path(*parts[index + 1 :]) if index + 1 < len(parts) else None
            if rest is None:
                return worktree.resolve()
            dest = worktree / rest
            if dest.is_dir() and _is_under(dest.resolve(), product.resolve()):
                return dest.resolve()
            raise ValueError(_missing_worktree_dir(rel.as_posix(), worktree.resolve()))
        if not nxt.is_dir():
            return None
        cursor = nxt
    return None


def _sole_change_worktree(product: Path, change_id: str) -> Path | None:
    found = _find_change_worktrees(product, change_id)
    if len(found) == 1:
        return found[0]
    return None


def _find_change_worktrees(product: Path, change_id: str, max_depth: int = 4) -> list[Path]:
    found: list[Path] = []

    def _walk(directory: Path, depth: int) -> None:
        if depth > max_depth or len(found) > 1:
            return
        try:
            children = list(directory.iterdir())
        except OSError:
            return
        for child in children:
            if not child.is_dir() or child.name in _SKIP_LISTING or child.name.startswith("."):
                if child.name == ".holix" and child.is_dir():
                    worktree = child / "worktrees" / change_id
                    if worktree.is_dir():
                        found.append(worktree.resolve())
                continue
            _walk(child, depth + 1)

    _walk(product, 0)
    return found


def _translate_clone_path(target: Path, clone: Path, worktree: Path) -> Path | None:
    try:
        resolved = target.expanduser().resolve()
    except OSError:
        return None
    if _is_under(resolved, worktree) and resolved.is_dir():
        return resolved
    try:
        rel = resolved.relative_to(clone.resolve())
    except ValueError:
        return None
    if rel.parts[:2] == (".holix", "worktrees"):
        if resolved == worktree:
            return worktree
        return None
    if not rel.parts:
        return worktree
    return _dir_under(worktree / rel, worktree)


def _workspace_anchor(clone: Path) -> Path | None:
    for parent in (clone, *clone.parents):
        if parent.name == "workspace":
            return parent
    if clone.parent.name == "projects":
        return clone.parent.parent
    return None


def _dir_under(path: Path, root: Path) -> Path | None:
    try:
        resolved = path.resolve()
    except OSError:
        return None
    if resolved.is_dir() and _is_under(resolved, root.resolve()):
        return resolved
    return None


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _missing_worktree_dir(token: str, worktree: Path) -> str:
    return (
        f"This session runs in the git worktree `{worktree}`. "
        f"`{token}` is not in this worktree, so the server stays on this change "
        f"and does not start from the main clone. "
        f"Use `.` or an existing directory: {_child_dir_names(worktree)}."
    )


def _child_dir_names(root: Path) -> str:
    names: list[str] = []
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError:
        return "(unavailable)"
    for entry in entries:
        if entry.name.startswith(".") or entry.name in _SKIP_LISTING:
            continue
        if entry.is_dir():
            names.append(entry.name)
        if len(names) >= 12:
            break
    if not names:
        return "(no project directories)"
    return ", ".join(f"`{name}`" for name in names)
