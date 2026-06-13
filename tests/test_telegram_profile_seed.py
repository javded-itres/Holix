"""Telegram-created user profiles must inherit LLM settings from the bot profile."""

from __future__ import annotations

import pytest
import yaml
from cli.core import ProfileManager
from core.env_loader import profile_env_path
from core.global_config import global_config_path, global_env_path
from core.models.manager import ModelManager
from integrations.telegram.access_approval import approve_access_request
from integrations.telegram.access_requests import register_access_request
from integrations.telegram.profile_seed import seed_telegram_user_profile_from_bot


@pytest.fixture
def holix_home(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import cli.core as cli_core

    root = tmp_path / "holix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HOLIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HOLIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)
    cli_core._unlocked_profiles.clear()
    yield root
    cli_core._unlocked_profiles.clear()


def _write_bot_profile_with_litellm(manager: ProfileManager, name: str) -> None:
    manager.create_profile(name, inherit_global=True)
    bot_dir = manager.get_profile_dir(name)
    (bot_dir / "config.yaml").write_text(
        yaml.dump(
            {
                "profile_name": name,
                "default_provider": "litellm",
                "providers": {
                    "litellm": {
                        "base_url": "http://127.0.0.1:4000/v1",
                        "api_key": "${LITELLM_API_KEY}",
                        "default_model": "gpt-4o-mini",
                    },
                },
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    (bot_dir / ".env").write_text(
        "LITELLM_API_KEY=sk-bot-test\nLITELLM_API_BASE=http://127.0.0.1:4000/v1\n",
        encoding="utf-8",
    )


def test_seed_copies_model_settings_from_bot_profile(holix_home) -> None:
    global_config_path().parent.mkdir(parents=True, exist_ok=True)
    global_config_path().write_text("profile_name: _global\n", encoding="utf-8")
    global_env_path().write_text("# empty global env\n", encoding="utf-8")

    manager = ProfileManager()
    _write_bot_profile_with_litellm(manager, "shared")
    manager.create_profile("lain", with_access_key=True, inherit_global=True)

    lain_before = manager.load_profile("lain")
    assert lain_before.default_provider is None
    assert not lain_before.providers

    seeded = seed_telegram_user_profile_from_bot(
        manager,
        bot_profile="shared",
        user_profile="lain",
    )
    assert seeded is True

    user_cfg = manager.load_profile("lain")
    mc = ModelManager(user_cfg).get_default_model_config()
    assert mc is not None
    assert mc.model == "gpt-4o-mini"
    assert mc.base_url == "http://127.0.0.1:4000/v1"

    user_env = profile_env_path("lain").read_text(encoding="utf-8")
    assert "LITELLM_API_KEY=sk-bot-test" in user_env


def test_approve_seeds_llm_for_new_profile(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.env_store import save_telegram_env

    global_config_path().parent.mkdir(parents=True, exist_ok=True)
    global_config_path().write_text("profile_name: _global\n", encoding="utf-8")

    manager = ProfileManager()
    _write_bot_profile_with_litellm(manager, "shared")

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="shared")
    register_access_request("shared", user_id=77, username="lain")
    monkeypatch.setattr(
        "integrations.telegram.notify.notify_access_approved_sync",
        lambda *args, **kwargs: None,
    )

    result = approve_access_request("shared", 77, create_profile="lain")
    assert result.holix_profile == "lain"

    user_cfg = manager.load_profile("lain")
    mc = ModelManager(user_cfg).get_default_model_config()
    assert mc is not None
    assert mc.model == "gpt-4o-mini"