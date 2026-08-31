"""Natural-language Holix init maps onto the /init prompt."""

from __future__ import annotations

from pathlib import Path

from core.project.init_intent import (
    expand_user_message_for_holix_init,
    looks_like_holix_init_request,
)


def test_detects_ru_and_en_init_phrases() -> None:
    assert looks_like_holix_init_request(
        "Проанализируй код используя lsp, проекта litellm-key-bot , "
        "архитектура поддерживается или нет сделай инициализацию Holix"
    )
    assert looks_like_holix_init_request("сделай инициализацию Holix")
    assert looks_like_holix_init_request("please initialize Holix for this repo")
    assert looks_like_holix_init_request("write HOLIX.md")
    assert not looks_like_holix_init_request("проанализируй архитектуру проекта")
    assert not looks_like_holix_init_request("init git repository")


def test_expand_pure_init_is_init_prompt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text("# App\n", encoding="utf-8")
    msg = expand_user_message_for_holix_init(
        "сделай инициализацию Holix",
        locale="en",
        cwd=str(tmp_path),
    )
    assert "update_holix_section" in msg
    assert (tmp_path / ".holix" / "HOLIX.md").is_file()
    assert "сделай инициализацию" not in msg


def test_expand_mixed_keeps_original(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pkg").mkdir()
    original = (
        "Проанализируй код используя lsp, проекта foo, "
        "архитектура поддерживается или нет сделай инициализацию Holix"
    )
    msg = expand_user_message_for_holix_init(original, locale="en", cwd=str(tmp_path))
    assert "update_holix_section" in msg
    assert original in msg
    assert "original request" in msg.lower() or "do this as well" in msg.lower()


def test_already_expanded_not_rewrapped() -> None:
    body = "Please fill HOLIX.md via update_holix_section one section at a time."
    assert looks_like_holix_init_request(body) is False
    assert expand_user_message_for_holix_init(body, locale="en") == body
