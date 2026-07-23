"""Messenger bot public URLs."""

from integrations.messenger.bot_links import max_bot_url, normalize_bot_username, telegram_bot_url


def test_telegram_bot_url() -> None:
    assert telegram_bot_url("holix_bot") == "https://t.me/holix_bot"
    assert telegram_bot_url("@holix_bot") == "https://t.me/holix_bot"
    assert telegram_bot_url("bad name") is None
    assert normalize_bot_username("") is None


def test_max_bot_url() -> None:
    assert max_bot_url("id123") == "https://max.ru/id123"
