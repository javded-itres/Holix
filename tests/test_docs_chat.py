"""Tests for documentation-site chat assistant."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.docs_chat.retrieval import DocsSearchHit, search_docs
from core.docs_chat.service import (
    build_context,
    extract_doc_slugs,
    is_conversational_message,
    pick_open_slug,
    sanitize_assistant_text,
)


@pytest.fixture
def search_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    index = [
        {
            "lang": "ru",
            "slug": "installation",
            "title": "Установка",
            "heading": "",
            "body": "Установите Helix через pipx install HelixAgentAi",
        },
        {
            "lang": "en",
            "slug": "installation",
            "title": "Installation",
            "heading": "",
            "body": "Install Helix with pipx install HelixAgentAi",
        },
    ]
    web_docs = tmp_path / "web-docs"
    web_docs.mkdir()
    (web_docs / "index.html").write_text("<html></html>")
    (web_docs / "search-index.json").write_text(json.dumps(index))
    monkeypatch.setattr(
        "cli.services.docs_site.resolve_web_docs_dir",
        lambda: web_docs,
    )
    return web_docs


def test_search_docs_finds_matching_language(search_index: Path) -> None:
    hits = search_docs("pipx", lang="ru")
    assert len(hits) == 1
    assert hits[0].slug == "installation"
    assert hits[0].title == "Установка"


def test_search_docs_ignores_other_language(search_index: Path) -> None:
    hits = search_docs("pipx", lang="en")
    assert len(hits) == 1
    assert hits[0].title == "Installation"


def test_build_context_includes_page_slug(search_index: Path) -> None:
    hits = search_docs("Helix", lang="en")
    ctx = build_context(hits, page_slug="gateway")
    assert "gateway" in ctx
    assert "Installation" in ctx


def test_sanitize_strips_paths_and_keys() -> None:
    raw = "Key: sk-abcdefghijklmnopqrstuvwx Path: /Users/alice/.helix/profiles/default/.env"
    cleaned = sanitize_assistant_text(raw)
    assert "sk-" not in cleaned
    assert "/Users/" not in cleaned
    assert "[скрыто]" in cleaned
    assert "[путь скрыт]" in cleaned


def test_extract_doc_slugs_from_response() -> None:
    text = "See /docs/installation and /docs/cli for details."
    assert extract_doc_slugs(text) == ["installation", "cli"]


def test_pick_open_slug_uses_first_response_link() -> None:
    hits = [
        DocsSearchHit(title="PyPI", slug="pypi", snippet="", score=10),
        DocsSearchHit(title="Telegram", slug="telegram", snippet="", score=80),
    ]
    text = "См. также /docs/pypi. Настройка в /docs/telegram."
    assert pick_open_slug(hits, text, current_slug=None) == "pypi"


def test_pick_open_slug_ignores_search_hits_without_links() -> None:
    hits = [DocsSearchHit(title="Installation", slug="installation", snippet="", score=10)]
    assert pick_open_slug(hits, "Install with pipx", current_slug=None) is None


def test_pick_open_slug_skips_current_page() -> None:
    hits = [DocsSearchHit(title="Installation", slug="installation", snippet="", score=10)]
    assert pick_open_slug(hits, "", current_slug="installation") is None


def test_is_conversational_message_detects_greeting_and_meta() -> None:
    assert is_conversational_message("Привет!")
    assert is_conversational_message("Who are you?")
    assert is_conversational_message("Что ты умеешь?")
    assert not is_conversational_message("How do I install Helix?")


def test_sanitize_blocks_directory_listing() -> None:
    raw = "drwxr-xr-x  5 alice  staff  160 Jun  9 12:00 profiles\n-rw-r--r--  1 alice  staff  220 Jun  9 12:00 .env"
    cleaned = sanitize_assistant_text(raw)
    assert "drwx" not in cleaned
    assert "документации Helix" in cleaned


def test_docs_chat_config_endpoint_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    import api.gateway as gw

    monkeypatch.setattr(gw.settings, "docs_chat_enabled", False)
    client = TestClient(gw.app)
    res = client.get("/v1/docs/chat/config")
    assert res.status_code == 200
    assert res.json()["enabled"] is False


def test_docs_chat_requires_token_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    import api.gateway as gw

    monkeypatch.setattr(gw.settings, "docs_chat_enabled", True)
    monkeypatch.setattr(gw.settings, "docs_chat_token", "secret-token")
    client = TestClient(gw.app)
    res = client.post(
        "/v1/docs/chat",
        json={
            "message": "hello",
            "lang": "en",
            "client_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        },
    )
    assert res.status_code == 401