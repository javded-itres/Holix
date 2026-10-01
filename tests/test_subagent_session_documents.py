"""Sub-agents receive the parent session's document cards, not the whole file."""

from __future__ import annotations

from core.documents.index import INLINE_LIMIT, maybe_index_document
from core.subagents.base import SubAgentConfig
from core.subagents.prompt import build_subagent_system_prompt


def _index(tmp_path, monkeypatch, *, conversation_id: str, name: str, tail: str) -> None:
    monkeypatch.setattr(
        "core.documents.index._database_path",
        lambda profile: tmp_path / "documents.db",
    )
    filler = "обычный абзац. " * 500
    body = filler + "\n" + tail + "\n" + filler
    assert len(body) > INLINE_LIMIT
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    card = maybe_index_document(
        profile="default",
        path=path,
        name=name,
        text=body,
        conversation_id=conversation_id,
        db_path=tmp_path / "documents.db",
    )
    assert card is not None


def test_subagent_prompt_lists_session_documents_without_the_tail(tmp_path, monkeypatch) -> None:
    _index(
        tmp_path,
        monkeypatch,
        conversation_id="task-a",
        name="contract.txt",
        tail="Штраф за просрочку указан в приложении.",
    )
    cfg = SubAgentConfig(
        name="coder-1",
        agent_type="coder",
        system_prompt="You code.",
        tools=["read_file"],
        parent_conversation_id="task-a",
    )
    prompt = build_subagent_system_prompt(cfg, "Найди штраф", profile_name="default")
    assert "Session documents" in prompt
    assert "contract.txt" in prompt
    assert "search_document" in prompt
    assert "Штраф за просрочку" not in prompt
    assert "search_document" in cfg.tools
    assert "read_document" in cfg.tools


def test_subagent_does_not_see_another_sessions_documents(tmp_path, monkeypatch) -> None:
    _index(
        tmp_path,
        monkeypatch,
        conversation_id="task-a",
        name="contract.txt",
        tail="Штраф за просрочку указан в приложении.",
    )
    cfg = SubAgentConfig(
        name="coder-1",
        agent_type="coder",
        system_prompt="You code.",
        tools=["read_file"],
        parent_conversation_id="task-b",
    )
    prompt = build_subagent_system_prompt(cfg, "Найди штраф", profile_name="default")
    assert "Session documents" not in prompt
    assert "contract.txt" not in prompt
    assert cfg.tools == ["read_file"]


def test_page_analyst_does_not_gain_document_tools(tmp_path, monkeypatch) -> None:
    _index(
        tmp_path,
        monkeypatch,
        conversation_id="task-a",
        name="contract.txt",
        tail="Штраф за просрочку указан в приложении.",
    )
    cfg = SubAgentConfig(
        name="page-1",
        agent_type="page_analyst",
        system_prompt="One page.",
        tools=["fetch_url"],
        parent_conversation_id="task-a",
    )
    prompt = build_subagent_system_prompt(cfg, "URL: https://example.com", profile_name="default")
    assert "Session documents" not in prompt
    assert cfg.tools == ["fetch_url"]
