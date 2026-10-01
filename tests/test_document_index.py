"""Long documents stay out of the prompt and are searched by fragment."""

from __future__ import annotations

import json

import pytest
from core.documents.index import (
    INLINE_LIMIT,
    chunk_text,
    delete_conversation_documents,
    maybe_index_document,
    read_document_chunks,
    search_documents,
)
from core.tools.documents import ReadDocumentTool, SearchDocumentTool
from core.tools.lazy_schema import CORE_TOOL_NAMES
from core.tools.slot_policy import PLAN_MODE_ALLOWED


def test_short_text_is_not_indexed(tmp_path) -> None:
    card = maybe_index_document(
        profile="default",
        path=tmp_path / "note.txt",
        name="note.txt",
        text="short note",
        conversation_id="task-a",
        db_path=tmp_path / "documents.db",
    )
    assert card is None


def test_long_text_card_hides_the_tail_but_search_finds_it(tmp_path) -> None:
    filler = "обычный абзац договора. " * 400
    body = filler + "\nСрок оплаты 10 дней. Штраф за просрочку указан в приложении.\n" + filler
    assert len(body) > INLINE_LIMIT
    db = tmp_path / "documents.db"
    path = tmp_path / "contract.txt"
    path.write_text(body, encoding="utf-8")
    card = maybe_index_document(
        profile="default",
        path=path,
        name="contract.txt",
        text=body,
        conversation_id="task-a",
        db_path=db,
    )
    assert card is not None
    assert "Штраф за просрочку" not in card
    assert "search_document" in card
    assert len(card) < 1200
    hits = search_documents(
        "default",
        "штраф просрочку",
        conversation_id="task-a",
        db_path=db,
    )
    assert hits
    assert any("Штраф" in hit["text"] for hit in hits)
    doc_id = hits[0]["doc_id"]
    page = read_document_chunks(
        "default",
        conversation_id="task-a",
        doc_id=doc_id,
        start=0,
        count=1,
        db_path=db,
    )
    assert page
    assert page[0]["index"] == 0
    assert "Штраф" not in page[0]["text"]


def test_sessions_do_not_see_each_others_documents(tmp_path) -> None:
    filler = "абзац договора. " * 500
    db = tmp_path / "documents.db"
    contract = tmp_path / "contract.txt"
    report = tmp_path / "report.txt"
    shared = tmp_path / "shared.txt"
    contract.write_text(filler + "\nШтраф за просрочку.\n" + filler, encoding="utf-8")
    report.write_text(filler + "\nВыручка за квартал.\n" + filler, encoding="utf-8")
    shared.write_text(filler + "\nОбщий пункт поставки.\n" + filler, encoding="utf-8")
    card_a = maybe_index_document(
        profile="default",
        path=contract,
        name="contract.txt",
        text=contract.read_text(encoding="utf-8"),
        conversation_id="task-a",
        db_path=db,
    )
    card_b = maybe_index_document(
        profile="default",
        path=report,
        name="report.txt",
        text=report.read_text(encoding="utf-8"),
        conversation_id="task-b",
        db_path=db,
    )
    shared_a = maybe_index_document(
        profile="default",
        path=shared,
        name="shared.txt",
        text=shared.read_text(encoding="utf-8"),
        conversation_id="task-a",
        db_path=db,
    )
    shared_b = maybe_index_document(
        profile="default",
        path=shared,
        name="shared.txt",
        text=shared.read_text(encoding="utf-8"),
        conversation_id="task-b",
        db_path=db,
    )
    assert card_a and card_b and shared_a and shared_b
    assert shared_a != shared_b
    leaked = search_documents(
        "default",
        "штраф просрочку",
        conversation_id="task-b",
        db_path=db,
    )
    assert leaked == []
    own = search_documents(
        "default",
        "штраф просрочку",
        conversation_id="task-a",
        db_path=db,
    )
    assert own
    assert (
        read_document_chunks(
            "default",
            conversation_id="task-b",
            doc_id=own[0]["doc_id"],
            db_path=db,
        )
        is None
    )
    both = search_documents(
        "default",
        "пункт поставки",
        conversation_id="task-a",
        db_path=db,
    )
    assert both
    assert {hit["name"] for hit in both} == {"shared.txt"}
    assert len({hit["doc_id"] for hit in both}) == 1
    delete_conversation_documents("default", "task-a", db_path=db)
    assert (
        search_documents(
            "default",
            "штраф просрочку",
            conversation_id="task-a",
            db_path=db,
        )
        == []
    )
    kept = search_documents(
        "default",
        "выручка квартал",
        conversation_id="task-b",
        db_path=db,
    )
    assert kept
    assert kept[0]["name"] == "report.txt"


def test_chunks_overlap_and_stop() -> None:
    parts = chunk_text("a" * 5000, size=1000, overlap=100)
    assert len(parts) >= 5
    assert parts[0][:50] == "a" * 50


@pytest.mark.asyncio
async def test_tools_index_a_path_and_do_not_return_the_whole_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "core.documents.index._database_path",
        lambda profile: tmp_path / "documents.db",
    )
    monkeypatch.setattr("core.tools.documents._profile", lambda: "default")
    path = tmp_path / "notes.md"
    path.write_text(
        "начало.\n" + ("слово " * 2000) + "\nUNIQUE_PENALTY_CLAUSE конец.", encoding="utf-8"
    )
    found = json.loads(
        await SearchDocumentTool().execute(query="UNIQUE_PENALTY_CLAUSE", path=str(path))
    )
    assert found["ok"] is True
    assert found["count"] >= 1
    blob = json.dumps(found, ensure_ascii=False)
    assert "UNIQUE_PENALTY_CLAUSE" in blob
    assert path.read_text(encoding="utf-8") not in blob
    assert all(len(hit["text"]) < 2000 for hit in found["fragments"])
    doc_id = found["doc_id"]
    opened = json.loads(await ReadDocumentTool().execute(doc_id=doc_id, start=0, count=1))
    assert opened["fragments"][0]["index"] == 0
    from core.tools.execution_context import conversation_scope, reset_conversation_scope

    other = conversation_scope("task-b")
    try:
        missed = json.loads(await SearchDocumentTool().execute(query="UNIQUE_PENALTY_CLAUSE"))
        denied = json.loads(await ReadDocumentTool().execute(doc_id=doc_id, start=0, count=1))
    finally:
        reset_conversation_scope(other)
    assert missed["ok"] is True
    assert missed["count"] == 0
    assert denied["ok"] is False
    assert denied["code"] == "not_found"
    assert "search_document" in CORE_TOOL_NAMES
    assert "read_document" in CORE_TOOL_NAMES
    assert "search_document" in PLAN_MODE_ALLOWED
