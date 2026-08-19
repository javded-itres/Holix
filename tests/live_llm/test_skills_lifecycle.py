"""Live LLM: skill loop stages or auto-approves with a notice, never a silent dump."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from core.agent_events import SkillProposalRejectedEvent, SkillProposedEvent
from core.plugins.hooks import notify_hooks
from core.skills.lifecycle import format_skill_notice_text
from core.skills.proposal import SkillProposalStore
from core.skills.self_improve import maybe_propose_skill

from tests.live_llm.provider import soft_contains

REPORT_DIR = Path("/tmp/holix-live-skills-last")


def _dump_report(
    *,
    hello_tools: list[str],
    hello_text: str,
    rec: dict | None,
    pending: list[dict],
    live_files: list[Path],
    notices: list[dict],
    rejected: list,
    skills_dir: Path,
) -> None:
    if REPORT_DIR.exists():
        shutil.rmtree(REPORT_DIR)
    REPORT_DIR.mkdir(parents=True)
    dest_skills = REPORT_DIR / "skills"
    dest_skills.mkdir()
    for src in live_files:
        shutil.copy2(src, dest_skills / src.name)
    pending_dir = skills_dir / "_pending"
    if pending_dir.is_dir():
        shutil.copytree(pending_dir, REPORT_DIR / "_pending")
    summary = {
        "hello_tools": hello_tools,
        "hello_text": (hello_text or "")[:400],
        "proposal": rec,
        "pending": pending,
        "live_files": [p.name for p in live_files],
        "notices": notices,
        "rejected": [
            {"skill_name": getattr(e, "skill_name", ""), "reason": getattr(e, "reason", "")}
            for e in rejected
        ],
    }
    (REPORT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print("\n===== LIVE SKILL REPORT =====")
    print(f"hello tools: {hello_tools}")
    print(f"hello text: {(hello_text or '')[:200]!r}")
    if rec:
        tier = rec.get("tier") or {}
        print(
            f"proposal: {rec.get('name')}  action={rec.get('action')}  "
            f"score={rec.get('quality_score')}  tier={tier.get('id')}/{tier.get('label_ru')}  "
            f"auto_applied={rec.get('auto_applied')}  status={rec.get('status')}"
        )
        print(f"description: {rec.get('description')}")
    else:
        print("proposal: <none>")
    print(f"pending: {len(pending)}  live_md: {[p.name for p in live_files]}")
    if notices:
        print("--- notice ---")
        print(format_skill_notice_text({**notices[-1], "locale": "ru"}))
    for path in live_files:
        print(f"\n----- LIVE {path.name} -----")
        print(path.read_text(encoding="utf-8")[:2500])
    for item in pending:
        body = item.get("content") or ""
        print(f"\n----- PENDING {item.get('name')} ({item.get('id')}) -----")
        print(body[:2500])
    print(f"\nreport dir: {REPORT_DIR}")
    print("===== END LIVE SKILL REPORT =====\n")


pytestmark = [pytest.mark.live_llm, pytest.mark.llm]


def _rich_session() -> list[dict]:
    """Passes should_create_skill: ≥4 user/assistant, ≥4 tools, ≥2 tool names."""
    return [
        {
            "role": "user",
            "content": (
                "Собери FastAPI каталог адресов с Dishka и pytest. "
                "Сверься с Context7, пиши файлы, прогони тесты."
            ),
        },
        {
            "role": "assistant",
            "content": "Сначала сверюсь с официальными доками Context7 и импортами.",
        },
        {"role": "tool", "name": "mcp_context7_resolve-library-id", "content": "/tiangolo/fastapi"},
        {
            "role": "assistant",
            "content": "Беру официальный FastAPI, читаю Depends, APIRouter и Dishka lifespan.",
        },
        {
            "role": "tool",
            "name": "mcp_context7_query-docs",
            "content": "APIRouter, Depends, provide, FromComponent",
        },
        {"role": "assistant", "content": "Пишу app/main.py, container.py и tests/test_catalog.py."},
        {"role": "tool", "name": "write_file", "content": "wrote app/main.py"},
        {"role": "tool", "name": "write_file", "content": "wrote tests/test_catalog.py"},
        {"role": "tool", "name": "run_terminal_command", "content": "pytest 3 passed"},
        {
            "role": "assistant",
            "content": "Готово: CRUD каталога и тесты зелёные. Dishka контейнер в lifespan.",
        },
    ]


@pytest.mark.asyncio
async def test_live_60_skill_loop_after_multi_tool_task(live_harness):
    """Trivial hello.py must not dump a skill; a rich session must go through the live generator."""
    notices: list[dict] = []
    notify_hooks.skill_notice_listeners.append(notices.append)
    try:
        prompt = (
            "In the current workspace create a tiny Python helper:\n"
            "1) write hello.py that prints HELLO_SKILL_OK\n"
            "2) read the file back\n"
            "3) list the directory\n"
            "4) run it with the terminal if allowed\n"
            "Use tools. When done, say HELLO_SKILL_OK in the final reply."
        )
        r = await live_harness.run(
            prompt,
            conversation_id="live_60_skills",
            timeout_s=480,
            retries=1,
        )
        assert live_harness.exists("hello.py") or soft_contains(
            r.text, "HELLO_SKILL_OK", "hello.py"
        ), f"task did not land, text={r.text!r} tools={r.tool_names()}"

        skills_dir = Path(live_harness.config.skills_dir)
        store = SkillProposalStore(skills_dir)
        live_md = list(skills_dir.glob("*.md")) if skills_dir.is_dir() else []
        proposed = [e for e in r.events if isinstance(e, SkillProposedEvent)]

        # A one-off hello.py must not land as a live skill without a notice.
        if live_md:
            assert notices or proposed, f"silent skill write: {[p.name for p in live_md]}"

        agent = live_harness.agent
        assert agent is not None
        extra: list = []

        def _cap(event) -> None:
            extra.append(event)

        agent.events.subscribe(_cap)
        try:
            rec = await maybe_propose_skill(
                agent,
                "live_60_rich",
                _rich_session(),
                "Готово: CRUD каталога и тесты зелёные. Dishka контейнер в lifespan.",
            )
        finally:
            agent.events.unsubscribe(_cap)

        rejected_live = [e for e in extra if isinstance(e, SkillProposalRejectedEvent)]
        proposed_live = [e for e in extra if isinstance(e, SkillProposedEvent)]
        pending = store.list_pending()
        live_after = list(skills_dir.glob("*.md")) if skills_dir.is_dir() else []
        _dump_report(
            hello_tools=r.tool_names(),
            hello_text=r.text,
            rec=rec,
            pending=pending,
            live_files=live_after,
            notices=notices,
            rejected=rejected_live,
            skills_dir=skills_dir,
        )
        if rec is None:
            # Explicit refuse is allowed; a silent live write is not.
            assert not live_after or notices or proposed or proposed_live, (
                "generator refused but a skill file appeared without a notice"
            )
            if not pending and not rejected_live:
                pytest.skip("live generator refused a reusable FastAPI session")
            return

        assert pending or live_after or notices, (
            f"proposal {rec!r} did not stage, persist, or notify"
        )
        if rec.get("auto_applied"):
            assert int(rec.get("quality_score") or 0) >= 60
            assert live_after
            assert not pending
        else:
            assert pending
            assert rec.get("name")
        if notices:
            payload = notices[-1]
            assert "quality_score" in payload
            assert payload.get("settings_path")
            if payload.get("auto_applied"):
                assert int(payload["quality_score"]) >= 60
    finally:
        notify_hooks.skill_notice_listeners[:] = [
            fn for fn in notify_hooks.skill_notice_listeners if fn is not notices.append
        ]
