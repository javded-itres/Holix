"""Admin broadcast posts to MAX users (shared bot)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from integrations.max.admin import is_max_admin
from integrations.max.markdown import escape_html, split_max_html


@dataclass(frozen=True, slots=True)
class AdminBroadcastDraft:
    """Pending compose step: next plain message is sent to recipients."""

    target: str  # "all" or Holix profile name


@dataclass(slots=True)
class BroadcastDeliveryResult:
    sent: int = 0
    failed: list[str] = field(default_factory=list)
    skipped_admin: bool = False

    @property
    def ok(self) -> bool:
        return self.sent > 0 and not self.failed


def resolve_broadcast_recipients(
    bot_profile: str,
    target: str,
    *,
    exclude_user_id: int | None = None,
) -> list[tuple[int, str]]:
    """Return (max_user_id, holix_profile) pairs for a broadcast target."""
    from integrations.max.admin import load_admin_user_id
    from integrations.max.allowlist import load_allowed_user_ids
    from integrations.max.user_profiles import load_user_profiles

    bot_profile = (bot_profile or "default").strip() or "default"
    target = (target or "").strip()
    admin_id = load_admin_user_id(bot_profile)
    mapping = load_user_profiles(bot_profile)
    allowed = load_allowed_user_ids(bot_profile)

    recipients: dict[int, str] = {}
    for uid, profile in mapping.items():
        recipients[int(uid)] = profile.strip()

    for uid in allowed:
        uid = int(uid)
        if uid not in recipients:
            recipients[uid] = bot_profile

    exclude = {int(exclude_user_id)} if exclude_user_id is not None else set()
    if admin_id is not None:
        exclude.add(int(admin_id))

    pairs = [
        (uid, profile)
        for uid, profile in sorted(recipients.items())
        if uid not in exclude
    ]
    if target.lower() == "all":
        return pairs
    return [(uid, prof) for uid, prof in pairs if prof == target]


def format_broadcast_html(
    content: str,
    *,
    target: str,
    holix_profile: str | None = None,
) -> str:
    body = escape_html(content.strip())
    if target.lower() == "all":
        header = "📢 <b>Сообщение от администратора</b>"
    else:
        profile_esc = escape_html(holix_profile or target)
        header = f"📢 <b>Сообщение от администратора</b> · профиль <code>{profile_esc}</code>"
    return f"{header}\n\n{body}"


def format_delivery_report(
    result: BroadcastDeliveryResult,
    *,
    target: str,
    recipient_count: int,
) -> str:
    target_esc = escape_html(target)
    lines = [
        "✅ <b>Рассылка завершена</b>",
        f"Цель: <code>{target_esc}</code>",
        f"Доставлено: {result.sent} из {recipient_count}",
    ]
    if result.failed:
        lines.append("")
        lines.append("<b>Ошибки:</b>")
        for item in result.failed[:8]:
            lines.append(f"• {escape_html(item)}")
        if len(result.failed) > 8:
            lines.append(f"• … ещё {len(result.failed) - 8}")
    return "\n".join(lines)


async def deliver_broadcast(
    bot_profile: str,
    recipients: list[tuple[int, str]],
    content: str,
    *,
    target: str,
    client: Any | None = None,
) -> BroadcastDeliveryResult:
    """Send broadcast HTML to each MAX recipient."""
    from integrations.max.client import MaxClient
    from integrations.max.config import load_max_settings
    from integrations.max.env_store import load_max_env_files

    load_max_env_files(bot_profile)
    settings = load_max_settings(bot_profile)
    token = settings.access_token.strip()
    if not token:
        raise RuntimeError("MAX_ACCESS_TOKEN is not configured")

    result = BroadcastDeliveryResult()
    close_client = False
    max_client = client
    if max_client is None:
        max_client = MaxClient(token)
        await max_client._ensure_session()
        close_client = True

    try:
        for user_id, holix_profile in recipients:
            html = format_broadcast_html(
                content,
                target=target,
                holix_profile=holix_profile,
            )
            try:
                for chunk in split_max_html(html) or [html]:
                    await max_client.send_message(
                        chunk,
                        user_id=int(user_id),
                        fmt="html",
                    )
                    await asyncio.sleep(0.05)
                result.sent += 1
            except Exception as exc:
                result.failed.append(f"{user_id}: {exc}")
    finally:
        if close_client and max_client is not None:
            await max_client.close()

    return result


async def handle_admin_message_command(host: Any, command: str) -> None:
    """Parse ``/message`` and start compose mode or show help."""
    from core.i18n import host_locale, t

    session = host._session
    bot_profile = getattr(session, "bot_profile", "default")
    user_id = int(getattr(session, "user_id", 0))

    if not is_max_admin(bot_profile, user_id):
        await host._send_html(escape_html(t("tg.message_admin_only", host_locale(host))))
        return

    parts = command.strip().split()
    sub = parts[1].lower() if len(parts) > 1 else ""

    if sub in {"", "help"}:
        await host._send_html(t("tg.message_help", host_locale(host)))
        return

    if sub == "cancel":
        session.pending_admin_broadcast = None
        await host._send_html(escape_html(t("tg.message_cancelled", host_locale(host))))
        return

    target = parts[1]
    if target.lower() == "all":
        draft_target = "all"
    else:
        from cli.core import ProfileManager

        manager = ProfileManager()
        if not manager.profile_exists(target):
            recipients = resolve_broadcast_recipients(
                bot_profile,
                target,
                exclude_user_id=user_id,
            )
            if not recipients:
                await host._send_html(
                    escape_html(t("tg.message_unknown_profile", host_locale(host), name=target))
                )
                return
        draft_target = target

    recipients = resolve_broadcast_recipients(
        bot_profile,
        draft_target,
        exclude_user_id=user_id,
    )
    if not recipients:
        await host._send_html(escape_html(t("tg.message_no_recipients", host_locale(host))))
        return

    session.pending_admin_broadcast = AdminBroadcastDraft(target=draft_target)
    if draft_target.lower() == "all":
        hint = t("tg.message_compose_all", host_locale(host), count=len(recipients))
    else:
        hint = t(
            "tg.message_compose_profile",
            host_locale(host),
            profile=escape_html(draft_target),
            count=len(recipients),
        )
    await host._send_html(hint)


async def try_compose_admin_broadcast(host: Any, text: str) -> bool:
    """If admin is composing a broadcast, send it and consume the message."""
    session = host._session
    draft: AdminBroadcastDraft | None = getattr(session, "pending_admin_broadcast", None)
    if draft is None:
        return False

    bot_profile = getattr(session, "bot_profile", "default")
    user_id = int(getattr(session, "user_id", 0))
    if not is_max_admin(bot_profile, user_id):
        session.pending_admin_broadcast = None
        return False

    message = (text or "").strip()
    if not message:
        await host._send_text("Пустое сообщение не отправлено.")
        return True

    if message.startswith("/"):
        session.pending_admin_broadcast = None
        return False

    recipients = resolve_broadcast_recipients(
        bot_profile,
        draft.target,
        exclude_user_id=user_id,
    )
    session.pending_admin_broadcast = None

    if not recipients:
        await host._send_html(escape_html("Нет получателей для рассылки."))
        return True

    result = await deliver_broadcast(
        bot_profile,
        recipients,
        message,
        target=draft.target,
        client=getattr(host, "_client", None),
    )
    report = format_delivery_report(
        result,
        target=draft.target,
        recipient_count=len(recipients),
    )
    await host._send_html(report)
    return True