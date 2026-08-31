"""Studio product change ids: {task_prefix}-{n} not free-form slugs."""

from __future__ import annotations

import json
from pathlib import Path

from core.sdd.product_change_id import (
    allocate_product_change_id,
    ensure_studio_board_task,
    normalize_task_prefix,
)


def _write_project(
    tmp: Path, *, prefix: str = "", seq: int = 3, name: str = "LiteLLM Key Bot"
) -> Path:
    root = tmp / "projects" / "litellm-key-bot"
    meta = root / ".holix" / "project.json"
    meta.parent.mkdir(parents=True)
    (root / "openspec" / "changes").mkdir(parents=True)
    (root / "openspec" / "changes" / "litellmkeybot-1").mkdir()
    data = {
        "id": "proj_x",
        "name": name,
        "slug": "litellm-key-bot",
        "workspace_rel": "projects/litellm-key-bot",
        "settings": {"task_prefix": prefix, "task_seq": seq},
        "repos": [{"id": "r1", "name": "bot", "path": "projects/litellm-key-bot"}],
        "tasks": [
            {"id": "task_old", "change_id": "litellmkeybot-1", "title": "old"},
        ],
    }
    meta.write_text(json.dumps(data), encoding="utf-8")
    return root


def test_normalize_prefix_from_name() -> None:
    assert normalize_task_prefix("", project_name="LiteLLM Key Bot") == "litellmkeybot"


def test_allocate_rewrites_slug(tmp_path: Path) -> None:
    root = _write_project(tmp_path, prefix="", seq=3)
    out = allocate_product_change_id(root, requested="stars-key-for-non-members")
    assert out is not None
    assert out["change_id"] == "litellmkeybot-4"
    assert out["rewritten_from"] == "stars-key-for-non-members"
    saved = json.loads((root / ".holix" / "project.json").read_text(encoding="utf-8"))
    assert saved["settings"]["task_prefix"] == "litellmkeybot"
    assert saved["settings"]["task_seq"] == 4


def test_allocate_keeps_matching_prefix_id(tmp_path: Path) -> None:
    root = _write_project(tmp_path, prefix="litellmkeybot", seq=3)
    out = allocate_product_change_id(root, requested="litellmkeybot-4")
    assert out is not None
    assert out["change_id"] == "litellmkeybot-4"
    assert not out.get("rewritten_from")


def test_no_product_json_returns_none(tmp_path: Path) -> None:
    (tmp_path / "openspec").mkdir()
    assert allocate_product_change_id(tmp_path, requested="oauth-login") is None


def test_ensure_board_task_appends(tmp_path: Path) -> None:
    root = _write_project(tmp_path, prefix="litellmkeybot", seq=4)
    meta = root / ".holix" / "project.json"
    data = json.loads(meta.read_text(encoding="utf-8"))
    task = ensure_studio_board_task(
        meta_path=meta,
        data=data,
        change_id="litellmkeybot-4",
        title="Stars for non-members",
        request="buy with stars",
        worktree_rel="projects/litellm-key-bot/.holix/worktrees/litellmkeybot-4",
    )
    assert task is not None
    assert task["change_id"] == "litellmkeybot-4"
    again = ensure_studio_board_task(
        meta_path=meta,
        data=json.loads(meta.read_text(encoding="utf-8")),
        change_id="litellmkeybot-4",
        title="dup",
        request="dup",
    )
    assert again is not None
    assert again["id"] == task["id"]
