"""Global cron scheduler and profile discovery."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from core.cron.discovery import CronProfileIndex, invalidate_profile
from core.cron.scheduler import GlobalCronScheduler
from core.cron.store import CronStore


def _fake_profile_dir(tmp_path: Path, profile: str) -> Path:
    d = tmp_path / profile
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.yaml").write_text(f"profile_name: {profile}\n", encoding="utf-8")
    return d


@pytest.fixture(autouse=True)
def _reset_profile_index() -> None:
    import core.cron.discovery as discovery

    discovery._index = None
    yield
    discovery._index = None


@pytest.fixture
def profiles_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from cli.core import ProfileManager

    def fake_dir(self, profile: str) -> Path:
        return _fake_profile_dir(tmp_path, profile)

    monkeypatch.setattr(ProfileManager, "get_profile_dir", fake_dir)
    monkeypatch.setattr("cli.core.profiles_dir", lambda: tmp_path)
    return tmp_path


def test_index_discovers_multiple_profiles(profiles_root: Path) -> None:
    CronStore("alice").add(task="task a", cron_expression="0 9 * * *")
    CronStore("bob").add(task="task b", cron_expression="0 10 * * *")

    index = CronProfileIndex(discovery_interval_s=0)
    profiles = index.scan_profiles_with_jobs()
    assert profiles == ["alice", "bob"]

    by_profile = dict(index.iter_enabled_jobs())
    assert set(by_profile) == {"alice", "bob"}
    assert len(by_profile["alice"]) == 1
    assert len(by_profile["bob"]) == 1


def test_index_uses_mtime_cache(profiles_root: Path) -> None:
    store = CronStore("alice")
    store.add(task="cached", cron_expression="0 9 * * *")
    index = CronProfileIndex(discovery_interval_s=9999)

    first = dict(index.iter_enabled_jobs())
    second = dict(index.iter_enabled_jobs())
    assert first == second
    assert "alice" in index._cache


def test_invalidate_profile_refreshes_after_save(profiles_root: Path) -> None:
    from core.cron.discovery import get_profile_index

    index = get_profile_index()
    assert dict(index.iter_enabled_jobs()) == {}

    CronStore("alice").add(task="new job", cron_expression="0 * * * *")
    invalidate_profile("alice")

    jobs = dict(index.iter_enabled_jobs())
    assert "alice" in jobs
    assert jobs["alice"][0].task == "new job"


@pytest.mark.asyncio
async def test_global_scheduler_dispatches_due_jobs_from_any_profile(
    profiles_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    past = datetime(2020, 1, 1, tzinfo=UTC).isoformat()
    CronStore("alice").add(task="run a", cron_expression="0 9 * * *")
    CronStore("bob").add(task="run b", cron_expression="0 10 * * *")
    for profile in ("alice", "bob"):
        store = CronStore(profile)
        data = store.load()
        data.jobs[0].next_run_at = past
        store.save(data)

    run_mock = AsyncMock()
    monkeypatch.setattr("core.cron.scheduler.run_cron_job", run_mock)

    scheduler = GlobalCronScheduler(tick_seconds=30, max_concurrent=2)
    await scheduler.tick()
    for _ in range(100):
        if run_mock.await_count >= 2:
            break
        await asyncio.sleep(0.01)

    assert run_mock.await_count == 2
    profiles_run = {call.args[0].profile for call in run_mock.await_args_list}
    assert profiles_run == {"alice", "bob"}