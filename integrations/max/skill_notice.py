"""MAX delivery of skill proposal notices (with approve/reject buttons)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.i18n import t
from core.plugins.hooks import register_skill_notice_listener
from core.skills.lifecycle import format_skill_notice_text

logger = logging.getLogger(__name__)


def register() -> None:
    register_skill_notice_listener(_on_notice)


def _on_notice(payload: dict[str, Any]) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_deliver(payload))
    except RuntimeError:
        logger.debug("max skill notice: no running loop")


def _targets(holix_profile: str) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    try:
        from core.profile import ProfileManager

        from integrations.max.config import load_max_settings
        from integrations.max.user_profiles import load_user_profiles

        for bot_name in ProfileManager().list_profiles():
            try:
                settings = load_max_settings(bot_name)
            except Exception:
                continue
            if not getattr(settings, "bot_token", ""):
                continue
            mapping = load_user_profiles(bot_name)
            for uid, prof in mapping.items():
                if str(prof) == holix_profile:
                    found.append((bot_name, int(uid)))
    except Exception:
        logger.debug("max skill targets failed", exc_info=True)
    try:
        from holix_studio.application.messenger_bindings import (
            get_messenger_bindings,
            resolve_bot_profile,
        )

        bot = resolve_bot_profile(serve_profile=None, user_profile=holix_profile)
        bindings = get_messenger_bindings(bot_profile=bot, holix_profile=holix_profile)
        uid = (bindings.get("max") or {}).get("user_id")
        if uid and (bot, int(uid)) not in found:
            found.append((bot, int(uid)))
    except Exception:
        pass
    return found


async def _deliver(payload: dict[str, Any]) -> None:
    profile = str(payload.get("profile") or "")
    if not profile:
        return
    text = format_skill_notice_text(payload)
    loc = str(payload.get("locale") or "en")
    pid = str(payload.get("proposal_id") or "")
    suffix = pid[-8:] if len(pid) >= 8 else pid
    auto = bool(payload.get("auto_applied"))
    from integrations.max.client import MaxClient
    from integrations.max.config import load_max_settings
    from integrations.max.keyboards import _callback_btn, inline_keyboard

    attachments = None
    if not auto and suffix:
        attachments = [
            inline_keyboard(
                [
                    [
                        _callback_btn(t("skill.btn.approve", loc), f"sk:a:{suffix}"),
                        _callback_btn(t("skill.btn.reject", loc), f"sk:r:{suffix}"),
                    ]
                ]
            )
        ]
    for bot_name, user_id in _targets(profile):
        try:
            settings = load_max_settings(bot_name)
            if not settings.bot_token:
                continue
            client = MaxClient(settings.bot_token)
            try:
                await client.send_message(
                    text,
                    user_id=user_id,
                    attachments=attachments,
                )
            finally:
                await client.close()
        except Exception:
            logger.warning("max skill notice send failed", exc_info=True)
