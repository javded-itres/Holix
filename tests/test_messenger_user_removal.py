"""Full messenger user removal (Telegram and MAX)."""

from __future__ import annotations

import os

import pytest
from integrations.max.access_requests import get_access_request, register_access_request
from integrations.max.allowlist import add_allowed_user, load_allowed_user_ids
from integrations.max.user_profiles import resolve_user_profile, set_user_profile
from integrations.max.user_removal import list_known_user_ids as max_list_users
from integrations.max.user_removal import remove_max_user
from integrations.telegram.access_requests import (
    get_access_request as tg_get_access_request,
)
from integrations.telegram.access_requests import register_access_request as tg_register
from integrations.telegram.admin import set_admin_user
from integrations.telegram.allowlist import (
    add_allowed_user as tg_add_allowed,
)
from integrations.telegram.allowlist import (
    load_allowed_user_ids as tg_load_allowed,
)
from integrations.telegram.user_profiles import (
    resolve_user_profile as tg_resolve_profile,
)
from integrations.telegram.user_profiles import (
    set_user_profile as tg_set_profile,
)
from integrations.telegram.user_removal import list_known_user_ids as tg_list_users
from integrations.telegram.user_removal import remove_telegram_user


@pytest.fixture
def holix_home(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import cli.core as cli_core
    from cli.core import ProfileManager

    root = tmp_path / "holix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HOLIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HOLIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)
    ProfileManager().create_profile("usr-rm")
    prev_profile = os.environ.get("HOLIX_PROFILE")
    yield root
    if prev_profile is None:
        os.environ.pop("HOLIX_PROFILE", None)
    else:
        os.environ["HOLIX_PROFILE"] = prev_profile


_BOT = "usr-rm"


def test_remove_telegram_user_clears_all(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile=_BOT)
    tg_register(_BOT, user_id=42, username="alice")
    tg_add_allowed(_BOT, 42)
    tg_set_profile(_BOT, 42, "alice")

    notified: list[int] = []
    monkeypatch.setattr(
        "integrations.telegram.notify.notify_access_revoked_sync",
        lambda _bp, uid: notified.append(uid),
    )

    result = remove_telegram_user(_BOT, 42)
    assert result.ok
    assert result.removed_allowlist
    assert result.removed_mapping
    assert result.removed_access_request
    assert tg_load_allowed(_BOT) == set()
    assert tg_resolve_profile(_BOT, 42) is None
    assert tg_get_access_request(_BOT, 42) is None
    assert notified == [42]
    assert 42 not in tg_list_users(_BOT)


def test_remove_max_user_clears_all(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.max.env_store import save_max_env

    save_max_env({"MAX_ACCESS_TOKEN": "a" * 32}, profile=_BOT)
    register_access_request(_BOT, user_id=99, first_name="Bob")
    add_allowed_user(_BOT, 99)
    set_user_profile(_BOT, 99, "bob99")

    monkeypatch.setattr(
        "integrations.max.notify.notify_access_revoked_sync",
        lambda *_a, **_k: None,
    )

    result = remove_max_user(_BOT, 99, notify=False)
    assert result.ok
    assert result.removed_allowlist
    assert result.removed_mapping
    assert result.removed_access_request
    assert load_allowed_user_ids(_BOT) == set()
    assert resolve_user_profile(_BOT, 99) is None
    assert get_access_request(_BOT, 99) is None


def test_remove_blocks_admin_without_force(holix_home) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile=_BOT)
    set_admin_user(_BOT, 900)
    tg_add_allowed(_BOT, 900)

    with pytest.raises(ValueError, match="administrator"):
        remove_telegram_user(_BOT, 900, notify=False)


def test_remove_admin_with_force(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.admin import load_admin_user_id
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile=_BOT)
    set_admin_user(_BOT, 900)
    tg_add_allowed(_BOT, 900)
    monkeypatch.setattr(
        "integrations.telegram.notify.notify_access_revoked_sync",
        lambda *_a, **_k: None,
    )

    result = remove_telegram_user(_BOT, 900, notify=False, force_admin=True)
    assert result.cleared_admin
    assert load_admin_user_id(_BOT) is None


def test_list_known_users(holix_home) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile=_BOT)
    tg_register(_BOT, user_id=5, username="x")
    tg_add_allowed(_BOT, 5)
    tg_set_profile(_BOT, 5, "worker")

    users = tg_list_users(_BOT)
    assert users[5]["allowlist"] == "yes"
    assert users[5]["profile"] == "worker"
    assert users[5]["request_status"] == "pending"


def test_reapprove_after_removal_issues_new_key(
    holix_home,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from integrations.max.access_approval import approve_access_request
    from integrations.max.env_store import save_max_env

    save_max_env({"MAX_ACCESS_TOKEN": "a" * 32}, profile=_BOT)
    register_access_request(_BOT, user_id=225116274, first_name="Ann")
    monkeypatch.setattr(
        "integrations.max.notify.notify_access_approved_sync",
        lambda *_a, **_k: None,
    )
    first = approve_access_request(_BOT, 225116274, create_profile="user_225116274")
    assert first.access_key
    first_key = first.access_key

    monkeypatch.setattr(
        "integrations.max.notify.notify_access_revoked_sync",
        lambda *_a, **_k: None,
    )
    remove_max_user(_BOT, 225116274, notify=False)
    register_access_request(_BOT, user_id=225116274, first_name="Ann")

    second = approve_access_request(_BOT, 225116274, create_profile="user_225116274")
    assert second.access_key
    assert second.access_key.startswith("hp_")
    assert second.access_key != first_key
    assert "Ключ отправлен" in second.message or second.access_key


def test_removed_user_can_reapply(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.max.env_store import save_max_env

    save_max_env({"MAX_ACCESS_TOKEN": "a" * 32}, profile=_BOT)
    register_access_request(_BOT, user_id=77, first_name="Eve")
    add_allowed_user(_BOT, 77)
    monkeypatch.setattr(
        "integrations.max.notify.notify_access_revoked_sync",
        lambda *_a, **_k: None,
    )
    remove_max_user(_BOT, 77, notify=False)

    req, created = register_access_request(_BOT, user_id=77, first_name="Eve")
    assert created is True
    assert req.status == "pending"
    assert max_list_users(_BOT)[77]["request_status"] == "pending"