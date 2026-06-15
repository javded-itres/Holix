"""Work status replies for status / what-are-you-doing questions."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import cli.core as cli_core
import pytest
from core.direct_dispatch import (
    build_work_status_reply,
    is_work_activity_request,
    should_answer_work_status,
)
from core.i18n import LocaleStore


def _patch_holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "holix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HOLIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HOLIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)


def test_work_activity_patterns() -> None:
    assert is_work_activity_request("что делаешь?")
    assert is_work_activity_request("что ты делаешь")
    assert should_answer_work_status("какой статус?")


def test_build_work_status_ru_no_subagents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_holix_home(tmp_path, monkeypatch)
    LocaleStore("default").set("ru")

    mgr = MagicMock()
    mgr.get_status_summary.return_value = {
        "total": 0,
        "running": 0,
        "agents": [],
    }

    agent = SimpleNamespace(
        config=SimpleNamespace(enable_subagents=True),
        subagents=mgr,
        _event_context=None,
    )

    body = build_work_status_reply(
        agent,
        profile_name="default",
        last_user_message="Доделай AI CMS",
        last_assistant_message="Запускаю субагента-кодера.",
        recent_user_tasks=["Доделай AI CMS"],
    )

    assert "Статус работы" in body
    assert "Доделай AI CMS" in body
    assert "Запускаю субагента-кодера" in body
    assert "нет запущенных" in body.lower()