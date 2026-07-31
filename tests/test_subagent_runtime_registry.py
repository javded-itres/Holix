"""Profile-scoped sub-agent runtime registry (cross-host visibility)."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.subagents import runtime_registry as rr
from core.subagents.base import (
    ProcessMode,
    SubAgentConfig,
    SubAgentHandle,
    SubAgentStatus,
)


@pytest.fixture()
def profile_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setattr(
        rr,
        "profile_dir_for_name",
        lambda name, default="default": tmp_path / "profiles" / (name or default),
    )
    return "saas"


def _running_handle(name: str = "coder") -> SubAgentHandle:
    h = SubAgentHandle(
        name=name,
        config=SubAgentConfig(name=name, process_mode=ProcessMode.ASYNC, max_steps=10),
        status=SubAgentStatus.RUNNING,
        agent_type="coder",
        task_preview="Implement feature X",
        max_steps=10,
        steps_taken=2,
        current_activity="writing files",
        last_tool="write_file",
    )
    h.started_at_wall = 1_700_000_000.0
    return h


def test_publish_and_list_across_owners(profile_home: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_MESSENGER_HOST", "telegram")
    owner_tg = rr.owner_key(source="telegram", pid=111)
    published = rr.publish_handle(
        profile_home,
        _running_handle("coder"),
        owner=owner_tg,
        source="telegram",
    )
    assert published is not None
    assert published["id"] == f"{owner_tg}::coder"
    assert published["source"] == "telegram"

    monkeypatch.delenv("HOLIX_MESSENGER_HOST", raising=False)
    monkeypatch.setenv("HOLIX_STUDIO", "1")
    owner_studio = rr.owner_key(source="studio", pid=222)
    rr.publish_handle(
        profile_home,
        _running_handle("researcher"),
        owner=owner_studio,
        source="studio",
    )

    jobs = rr.list_jobs(profile_home, include_done=True)
    names = {j["name"] for j in jobs}
    assert names == {"coder", "researcher"}
    sources = {j["name"]: j["source"] for j in jobs}
    assert sources["coder"] == "telegram"
    assert sources["researcher"] == "studio"


def test_merge_local_wins(profile_home: str) -> None:
    owner = "studio-1"
    local = [
        {
            "name": "coder",
            "id": f"{owner}::coder",
            "status": "running",
            "running": True,
            "done": False,
            "elapsed_ms": 50,
            "local": True,
        }
    ]
    remote = [
        {
            "name": "coder",
            "id": f"{owner}::coder",
            "status": "running",
            "running": True,
            "done": False,
            "elapsed_ms": 10,
            "source": "studio",
            "owner": owner,
        },
        {
            "name": "coder",
            "id": "telegram-9::coder",
            "status": "running",
            "running": True,
            "done": False,
            "elapsed_ms": 20,
            "source": "telegram",
            "owner": "telegram-9",
        },
    ]
    merged = rr.merge_local_and_profile(local, remote, local_owner=owner)
    assert len(merged) == 2
    by_id = {m["id"]: m for m in merged}
    assert by_id[f"{owner}::coder"]["local"] is True
    assert by_id[f"{owner}::coder"]["elapsed_ms"] == 50
    assert by_id["telegram-9::coder"]["source"] == "telegram"


def test_cancel_request_roundtrip(profile_home: str) -> None:
    owner = rr.owner_key(source="telegram", pid=333)
    rr.publish_handle(
        profile_home,
        _running_handle("worker"),
        owner=owner,
        source="telegram",
    )
    assert rr.request_cancel(profile_home, f"{owner}::worker") is True
    pending = rr.take_cancel_requests(profile_home, owner)
    assert pending == ["worker"]
    assert rr.take_cancel_requests(profile_home, owner) == []


def test_get_job_by_id(profile_home: str) -> None:
    owner = "max-44"
    rr.publish_handle(
        profile_home,
        _running_handle("reviewer"),
        owner=owner,
        source="max",
    )
    job = rr.get_job(profile_home, f"{owner}::reviewer", include_activity=True)
    assert job is not None
    assert job["name"] == "reviewer"
    assert job["source"] == "max"


def test_delete_job_removes_snapshot(profile_home: str) -> None:
    owner = "studio-7"
    rr.publish_handle(
        profile_home,
        _running_handle("coder"),
        owner=owner,
        source="studio",
    )
    assert rr.get_job(profile_home, f"{owner}::coder") is not None
    result = rr.delete_job(profile_home, f"{owner}::coder")
    assert result["ok"] is True
    assert result["deleted"] >= 1
    assert rr.get_job(profile_home, f"{owner}::coder") is None
    assert rr.list_jobs(profile_home) == []


def test_delete_done_jobs_keeps_running(profile_home: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    owner = "studio-8"
    running = _running_handle("worker")
    rr.publish_handle(profile_home, running, owner=owner, source="studio")

    # Write a finished job snapshot directly (recent so retention keeps it).
    now = time.time()
    done_path = rr._job_path(profile_home, owner, "finished")
    done_path.parent.mkdir(parents=True, exist_ok=True)
    done_path.write_text(
        (
            '{"name":"finished","status":"completed","running":false,"done":true,'
            f'"owner":"{owner}","id":"{owner}::finished","updated_at":{now}'
            "}\n"
        ),
        encoding="utf-8",
    )
    jobs = rr.list_jobs(profile_home, include_done=True)
    names = {j["name"] for j in jobs}
    assert "worker" in names
    assert "finished" in names

    result = rr.delete_done_jobs(profile_home)
    assert result["ok"] is True
    assert result["deleted"] >= 1
    remaining = {j["name"] for j in rr.list_jobs(profile_home, include_done=True)}
    assert "finished" not in remaining
    assert "worker" in remaining
