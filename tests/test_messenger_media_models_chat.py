"""Messenger opt-in for Configured image/video models in chat."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from cli.core import ProfileManager
from integrations.messenger.media_models_chat import (
    filter_media_model_tool_notice,
    media_models_visible_for_profile,
    set_media_models_visible_for_host,
    shape_media_models_chat,
)

_DUMP = (
    "Configured image models:\n"
    "- mikrollm model=image-z-image-turbo: (no note) (text prompt only)\n"
    "\n"
    "kind: image\n"
    "provider: mikrollm\n"
    "type: openai_images\n"
    "model: image-z-image-turbo\n"
    "parameters:\n"
    "- size (string, optional)\n"
    "hub model card: not listed for this key\n"
)


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_media_models_default_off_and_persist(holix_home: Path) -> None:
    ProfileManager().create_profile("alice", inherit_global=False)
    host = SimpleNamespace(profile="alice", agent=None)
    assert media_models_visible_for_profile("alice") is False

    assert set_media_models_visible_for_host(host, True) is True
    assert media_models_visible_for_profile("alice") is True
    assert ProfileManager().load_profile("alice").show_media_models_in_chat is True

    set_media_models_visible_for_host(host, False)
    assert media_models_visible_for_profile("alice") is False
    assert ProfileManager().load_profile("alice").show_media_models_in_chat is False


def test_shape_hides_model_list_until_opt_in() -> None:
    answer = f"Запускаю генерацию.\n\n{_DUMP}"
    hidden = shape_media_models_chat(answer, visible=False)
    assert hidden == "Запускаю генерацию."
    assert "Configured image models:" not in hidden

    shown = shape_media_models_chat(answer, visible=True)
    assert shown.startswith("Запускаю генерацию.")
    assert "Configured image models:" in shown
    assert shown.count("Configured image models:") == 1


def test_shape_appends_tool_list_when_the_model_omitted_it() -> None:
    recent = [{"name": "describe_media_model", "full_result": _DUMP}]
    shown = shape_media_models_chat(
        "Готово, файл в пути.",
        visible=True,
        recent_tool_results=recent,
    )
    assert shown.startswith("Готово, файл в пути.")
    assert "Configured image models:" in shown

    hidden = shape_media_models_chat(
        "Готово, файл в пути.",
        visible=False,
        recent_tool_results=recent,
    )
    assert hidden == "Готово, файл в пути."


def test_shape_is_idempotent_when_visible() -> None:
    recent = [{"name": "describe_media_model", "full_result": _DUMP}]
    once = shape_media_models_chat("Ок.", visible=True, recent_tool_results=recent)
    twice = shape_media_models_chat(once, visible=True, recent_tool_results=recent)
    assert twice == once
    assert twice.count("Configured image models:") == 1


def test_fenced_dump_is_removed_when_hidden() -> None:
    text = f"Ок.\n\n```\n{_DUMP}```\n"
    assert shape_media_models_chat(text, visible=False) == "Ок."


def test_describe_tool_notice_never_leaks_mid_run() -> None:
    assert filter_media_model_tool_notice("describe_media_model", _DUMP, visible=False) == ""
    assert filter_media_model_tool_notice("describe_media_model", _DUMP, visible=True) == ""


def test_other_tool_notice_drops_configured_models_when_hidden() -> None:
    body = "This prompt needs a reference.\nConfigured models:\n- mikrollm model=image: note (text prompt only)\n"
    hidden = filter_media_model_tool_notice("generate_image", body, visible=False)
    assert "Configured models:" not in hidden
    assert "reference" in hidden
    kept = filter_media_model_tool_notice("generate_image", body, visible=True)
    assert "Configured models:" in kept


def test_status_menu_includes_extended_button() -> None:
    pytest.importorskip("aiogram.types")
    from integrations.telegram.keyboards import (
        extended_mode_picker_keyboard,
        parse_callback,
        status_menu_keyboard,
    )

    kb = status_menu_keyboard("ru", is_admin=False)
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "Расширенный" in labels
    payloads = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "hx:r:extended" in payloads

    picker = extended_mode_picker_keyboard(False, "ru")
    picker_payloads = [btn.callback_data for row in picker.inline_keyboard for btn in row]
    assert "hx:xv:1" in picker_payloads
    assert parse_callback("hx:xv:0") == ("xv", "0")


def test_status_menu_includes_extended_button_max() -> None:
    from integrations.max.keyboards import (
        extended_mode_picker_keyboard,
        parse_callback,
        status_menu_keyboard,
    )

    kb = status_menu_keyboard("en", is_admin=True)
    labels = [btn["text"] for row in kb["payload"]["buttons"] for btn in row]
    assert "Extended" in labels

    picker = extended_mode_picker_keyboard(True, "en")
    payloads = [btn["payload"] for row in picker["payload"]["buttons"] for btn in row]
    assert "hx:xv:1" in payloads
    assert parse_callback("hx:xv:1") == ("xv", "1")
