"""Plan save reuses plan_id; list_plans collapses orphan drafts."""

from __future__ import annotations

import json

from core.plan_review.plan_storage import list_plans, save_plan


def test_save_plan_reuses_file_for_same_plan_id(tmp_path, monkeypatch) -> None:
    import core.plan_review.plan_storage as ps

    monkeypatch.setattr(ps, "get_plan_dir", lambda config=None: tmp_path)
    monkeypatch.setattr(ps, "_plan_search_dirs", lambda config=None: [tmp_path])

    steps = [{"step": 1, "description": "A", "status": "pending"}]
    p1 = save_plan(
        steps,
        "studio",
        plan_status="pending_review",
        plan_id="plan_same1",
        user_input="Do thing",
    )
    p2 = save_plan(
        steps + [{"step": 2, "description": "B", "status": "pending"}],
        "studio",
        plan_status="confirmed",
        plan_id="plan_same1",
        user_input="Do thing",
    )
    assert p1 == p2
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["status"] == "confirmed"
    assert data["plan_id"] == "plan_same1"
    assert len(data["steps"]) == 2


def test_save_plan_mints_id_when_empty(tmp_path, monkeypatch) -> None:
    import core.plan_review.plan_storage as ps

    monkeypatch.setattr(ps, "get_plan_dir", lambda config=None: tmp_path)
    p = save_plan(
        [{"step": 1, "description": "x"}],
        "studio",
        plan_status="confirmed",
        plan_id="",
        user_input="t",
    )
    assert p.name.startswith("plan_")
    assert not p.name[:8].isdigit()  # not YYYYMMDD_ timestamp style


def test_list_plans_prefers_confirmed_over_drafts(tmp_path, monkeypatch) -> None:
    import core.plan_review.plan_storage as ps

    monkeypatch.setattr(ps, "get_plan_dir", lambda config=None: tmp_path)
    monkeypatch.setattr(ps, "_plan_search_dirs", lambda config=None: [tmp_path])

    save_plan(
        [{"step": 1, "description": "A"}],
        "studio",
        plan_status="pending_review",
        plan_id="plan_a1",
        user_input="Index products in elasticsearch",
    )
    save_plan(
        [{"step": 1, "description": "A"}, {"step": 2, "description": "B"}],
        "studio",
        plan_status="pending_review",
        plan_id="plan_a2",
        user_input="Index products in elasticsearch",
    )
    save_plan(
        [{"step": 1, "description": "A"}, {"step": 2, "description": "B"}],
        "studio",
        plan_status="confirmed",
        plan_id="plan_a3",
        user_input="Index products in elasticsearch",
    )

    listed = list_plans(limit=20)
    assert len(listed) == 1
    assert listed[0]["status"] == "confirmed"
    assert listed[0]["plan_id"] == "plan_a3"
