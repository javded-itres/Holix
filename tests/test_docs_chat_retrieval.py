"""Tests for docs chat chunking and hybrid retrieval."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from core.docs_chat.chunking import chunk_page
from core.docs_chat.embeddings import save_vectors
from core.docs_chat.retrieval import search_docs


@pytest.fixture
def chunk_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    web_docs = tmp_path / "web-docs"
    web_docs.mkdir()
    (web_docs / "index.html").write_text("<html></html>")

    telegram_raw = """# Telegram

## Setup
Configure Telegram bot token and allowlist for each profile.

## Voice messages
Helix transcribes Telegram voice notes via Whisper API.
"""
    pypi_raw = """# PyPI

## Publishing
How to configure package metadata and publish to PyPI.
"""

    chunks = [
        *chunk_page(telegram_raw, lang="ru", slug="telegram", title="Telegram", nav_order=11),
        *chunk_page(pypi_raw, lang="ru", slug="pypi", title="PyPI", nav_order=18),
    ]
    (web_docs / "search-chunks.json").write_text(json.dumps(chunks), encoding="utf-8")

    vectors = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.9, 0.1],
        ],
        dtype=np.float32,
    )
    save_vectors(
        web_docs / "search-vectors.npz",
        chunk_ids=[c["id"] for c in chunks],
        vectors=vectors,
    )

    from core.docs_chat.retrieval import clear_retrieval_cache

    clear_retrieval_cache()
    monkeypatch.setattr("core.docs_chat.retrieval.embed_query", lambda _q: np.array([0.95, 0.05, 0.0]))
    monkeypatch.setattr("cli.services.docs_site.resolve_web_docs_dir", lambda: web_docs)
    clear_retrieval_cache()
    return web_docs


def test_chunk_page_splits_sections() -> None:
    raw = (
        "# Title\n\n"
        "Intro text here long enough to count as a standalone chunk for retrieval.\n\n"
        "## Section A\n\n"
        "Alpha content here with enough words to pass the minimum chunk length threshold.\n\n"
        "## Section B\n\n"
        "Beta content here with enough words to pass the minimum chunk length threshold easily."
    )
    chunks = chunk_page(raw, lang="en", slug="demo", title="Demo", nav_order=1)
    assert len(chunks) >= 2
    assert {"section-a", "section-b"} <= {c["section"] for c in chunks}


def test_search_docs_finds_telegram_chunk(chunk_index: Path) -> None:
    hits = search_docs("Как настроить телеграм", lang="ru")
    assert hits
    assert hits[0].slug == "telegram"
    assert "allowlist" in hits[0].snippet.lower() or "token" in hits[0].snippet.lower()


def test_search_docs_prefers_telegram_over_pypi(chunk_index: Path) -> None:
    hits = search_docs("настроить telegram бот", lang="ru")
    slugs = [h.slug for h in hits]
    assert slugs[0] == "telegram"
    if len(slugs) > 1:
        assert "pypi" not in slugs[:1]