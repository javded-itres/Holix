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


def test_parse_raz_v_n_minut():
    assert parse_schedule_to_cron("раз в 5 минут") == "*/5 * * * *"
    assert parse_schedule_to_cron("каждые 5 минут") == "*/5 * * * *"


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


def test_detect_ignores_build_console_service_every_n_minutes():
    """App/worker briefs must not become Holix cron (false positive «в 5» → 05:00)."""
    msg = (
        "Создай консольный сервис, который будет запускать job раз в 5 минут "
        "с задачей ходить на сервис пользователей и проверять наличие новых "
        "пользователей, если новый пользователь появился писать его данные в лог"
    )
    assert detect_cron_intent(msg) is None


def test_detect_ignores_create_service_kazhdye_n_minut():
    msg = "Создай сервис который каждые 5 минут проверяет API пользователей"
    assert detect_cron_intent(msg) is None


def test_detect_ignores_interval_without_holix_schedule_intent():
    assert detect_cron_intent("Раз в 5 минут ходи на /users и логируй новых") is None


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


@pytest.mark.asyncio
async def test_auto_dispatch_disabled() -> None:
    from cli.shared.cron_auto_dispatch import try_cron_auto_dispatch

    host = MagicMock()
    host.profile = "x"
    assert (
        await try_cron_auto_dispatch(
            host,
            "Присылай сводку новостей каждый день в 10 утра",
        )
        is False
    )
