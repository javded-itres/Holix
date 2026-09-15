"""Studio product layout: dedicated spec repo vs code clones."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.sdd.product_change_id import find_product_project_json

_SPEC_ROLES = frozenset({"spec", "specs", "openspec", "sdd"})
_CODE_ROLES = frozenset({"code", "app", "service", "repo"})


@dataclass(frozen=True, slots=True)
class ProductLayout:
    meta_path: Path
    project_root: Path
    data: dict[str, Any]
    spec_root: Path | None = None
    code_roots: tuple[Path, ...] = ()
    spec_rel: str = ""

    @property
    def has_dedicated_spec(self) -> bool:
        if self.spec_root is None:
            return False
        if self.code_roots:
            return True
        return self.spec_root.resolve() != self.project_root.resolve()

    @property
    def is_multi(self) -> bool:
        repos = [r for r in (self.data.get("repos") or []) if isinstance(r, dict)]
        return len(repos) > 1

    def inferred_openspec_root(self) -> Path | None:
        """Clone that already contains openspec/ when no role=spec is set.

        Dedicated spec repo always wins. Otherwise only directories that
        already have ``openspec/config.yaml`` — never invent a new root.
        """
        if self.has_dedicated_spec:
            return self.spec_root
        found: list[Path] = []
        for repo in self.data.get("repos") or []:
            if not isinstance(repo, dict):
                continue
            abs_p = _resolve_repo_path(self.project_root, repo)
            if (abs_p / "openspec" / "config.yaml").is_file():
                found.append(abs_p)
        if found:
            return found[0]
        if not self.is_multi:
            cfg = self.project_root / "openspec" / "config.yaml"
            if cfg.is_file():
                return self.project_root
        return None


def _repo_role(repo: dict[str, Any]) -> str:
    raw = str(repo.get("role") or repo.get("kind") or "").strip().lower()
    if raw in _SPEC_ROLES:
        return "spec"
    if raw in _CODE_ROLES:
        return "code"
    return ""


def _resolve_repo_path(project_root: Path, repo: dict[str, Any]) -> Path:
    raw = str(repo.get("path") or repo.get("name") or "").strip().replace("\\", "/").strip("/")
    if not raw:
        return project_root
    p = Path(raw)
    if p.is_absolute():
        return p.expanduser().resolve()
    direct = (project_root / raw).resolve()
    try:
        direct.relative_to(project_root)
        if direct.is_dir() or not (project_root / p.name).is_dir():
            return direct
    except ValueError:
        pass
    named = (project_root / p.name).resolve()
    try:
        named.relative_to(project_root)
        return named
    except ValueError:
        return direct


def load_product_layout(start: Path | str) -> ProductLayout | None:
    """Walk parents for ``.holix/project.json`` and resolve spec/code clones."""
    meta = find_product_project_json(Path(start))
    if meta is None:
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    project_root = meta.parent.parent
    repos = data.get("repos") if isinstance(data.get("repos"), list) else []
    explicit = [_repo_role(r) for r in repos if isinstance(r, dict)]
    has_roles = any(explicit)
    spec_root: Path | None = None
    spec_rel = ""
    code: list[Path] = []
    if has_roles:
        for repo in repos:
            if not isinstance(repo, dict):
                continue
            role = _repo_role(repo)
            abs_p = _resolve_repo_path(project_root, repo)
            if role == "spec" and spec_root is None:
                spec_root = abs_p
                spec_rel = str(repo.get("path") or repo.get("name") or abs_p.name).strip()
            elif role == "code" or role == "":
                if spec_root is None or abs_p != spec_root:
                    code.append(abs_p)
    return ProductLayout(
        meta_path=meta,
        project_root=project_root,
        data=data,
        spec_root=spec_root,
        code_roots=tuple(code),
        spec_rel=spec_rel,
    )


def is_under_code_repo(layout: ProductLayout, path: Path) -> bool:
    try:
        resolved = path.expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    for root in layout.code_roots:
        try:
            rr = root.resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if resolved == rr or resolved.is_relative_to(rr):
            if layout.spec_root is not None:
                try:
                    sr = layout.spec_root.resolve()
                    if resolved == sr or resolved.is_relative_to(sr):
                        return False
                except (OSError, RuntimeError, ValueError):
                    pass
            return True
    return False


def sdd_workspace_for_layout(layout: ProductLayout | None, fallback: Path) -> Path:
    """Directory that owns ``openspec/`` for this product, else *fallback*."""
    if layout is None:
        return fallback
    if layout.spec_root is not None:
        return layout.spec_root
    inferred = layout.inferred_openspec_root()
    if inferred is not None:
        return inferred
    return fallback
