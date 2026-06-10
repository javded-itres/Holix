"""Cron expression parsing, store, and scheduler due checks."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from core.cron.expressions import compute_next_run, validate_cron_expression
from core.cron.models import CronJob
from core.cron.schedule_parse import parse_schedule_to_cron
from core.cron.scheduler import _job_is_due
from core.cron.store import CronStore


def test_validate_five_field_cron():
    assert validate_cron_expression("0 9 * * *") == "0 9 * * *"


def test_parse_natural_daily():
    assert parse_schedule_to_cron("every day at 9") == "0 9 * * *"


def test_parse_every_minutes():
    assert parse_schedule_to_cron("every 15 minutes") == "*/15 * * * *"


def test_job_is_due_when_next_in_past():
    past = datetime(2020, 1, 1, tzinfo=UTC).isoformat()
    job = CronJob(task="t", cron_expression="0 9 * * *", enabled=True, next_run_at=past)
    now = datetime.now(UTC)
    assert _job_is_due(job, now=now) is True


def test_job_not_due_when_next_in_future():
    future = compute_next_run("0 9 * * *").isoformat()
    job = CronJob(task="t", cron_expression="0 9 * * *", enabled=True, next_run_at=future)
    now = datetime.now(UTC)
    assert _job_is_due(job, now=now) is False


def test_cron_store_roundtrip(tmp_path: Path, monkeypatch):
    from cli.core import ProfileManager

    profile = "cron_test"

    def fake_dir(p: str) -> Path:
        d = tmp_path / p
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(ProfileManager, "get_profile_dir", lambda self, p: fake_dir(p))

    store = CronStore(profile)
    job = store.add(task="check logs", cron_expression="0 9 * * *", name="daily")
    assert job.id
    assert store.get(job.id) is not None

    store.set_enabled(job.id, False)
    assert store.get(job.id).enabled is False

    assert store.remove(job.id)
    assert store.get(job.id) is None


def test_parse_add_arguments():
    from cli.shared.commands.cron_commands import parse_add_arguments

    expr, task = parse_add_arguments("every hour :: ping")
    assert expr == "0 * * * *"
    assert task == "ping"

    expr2, task2 = parse_add_arguments("0 9 * * * :: backup")
    assert expr2 == "0 9 * * *"
    assert task2 == "backup"