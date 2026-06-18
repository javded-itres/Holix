"""Natural-language cron intent detection and auto-create."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from core.cron.auto_create import try_auto_create_cron
from core.cron.nl_intent import detect_cron_intent
from core.cron.schedule_parse import parse_schedule_to_cron
from core.cron.store import CronStore


def test_parse_every_day_at_10_am_not_five_field_false_positive():
    assert parse_schedule_to_cron("every day at 10 am") == "0 10 * * *"


def test_parse_russian_daily_morning():
    assert parse_schedule_to_cron("каждый день в 10 утра") == "0 10 * * *"


def test_parse_russian_evening():
    assert parse_schedule_to_cron("каждый день в 8 вечера") == "0 20 * * *"


def test_detect_news_digest_intent_ru():
    msg = "Присылай мне такие новости по этой теме каждый день в 10 утра"
    intent = detect_cron_intent(msg)
    assert intent is not None
    assert intent.cron_expression == "0 10 * * *"
    assert "новости" in intent.task.lower()


def test_detect_ignores_one_shot():
    assert detect_cron_intent("Сделай это один раз сейчас") is None


def test_detect_ignores_slash_cron():
    assert detect_cron_intent("/cron list") is None


def test_detect_english_daily():
    msg = "Send me a disk usage summary every day at 9"
    intent = detect_cron_intent(msg)
    assert intent is not None
    assert intent.cron_expression == "0 9 * * *"
    assert "disk" in intent.task.lower()


def test_auto_create_from_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from cli.core import ProfileManager

    profile = "cron_auto"

    def fake_dir(p: str) -> Path:
        d = tmp_path / p
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(ProfileManager, "get_profile_dir", lambda self, p: fake_dir(p))

    host = MagicMock()
    host.profile = profile
    host.conversation_id = "tg_test_1"
    session = MagicMock()
    session.chat_id = 12345
    session.conversation_id = "tg_test_1"
    host._session = session

    msg = "Присылай сводку новостей каждый день в 10 утра"
    job = try_auto_create_cron(host, msg)
    assert job is not None
    assert job.cron_expression == "0 10 * * *"
    assert job.notify_chat_id == 12345
    assert job.session_id == "tg_test_1"
    assert CronStore(profile).get(job.id) is not None