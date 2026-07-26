"""Cron SQLite history store."""

from __future__ import annotations

from core.cron.history import list_runs, record_run


def test_record_and_list_runs(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path / "holix"))
    from core.profile import ProfileManager

    ProfileManager().ensure_directories()
    # profile dir under HOLIX_HOME
    record_run(
        "default",
        job_id="abc123",
        job_name="Daily",
        status="success",
        duration_s=1.5,
        result_preview="ok done",
        trigger="manual",
    )
    record_run(
        "default",
        job_id="abc123",
        job_name="Daily",
        status="error",
        error="boom",
        trigger="schedule",
    )
    all_runs = list_runs("default", limit=10)
    assert len(all_runs) >= 2
    job_runs = list_runs("default", job_id="abc123", limit=10)
    assert all(r["job_id"] == "abc123" for r in job_runs)
    assert job_runs[0]["status"] in {"success", "error"}
