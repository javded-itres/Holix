"""Build and deliver user-confirmed support tickets to Telegram admins."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from typing import Any

REQUEST_ADMIN_SUPPORT_TOOL = "request_admin_support"
EXTRA_ADMIN_IDS_ENV = "HOLIX_TELEGRAM_ADMIN_EXTRA_USER_IDS"
PRIMARY_ADMIN_ID_ENV = "HOLIX_TELEGRAM_ADMIN_USER_ID"

_ID_SPLIT = re.compile(r"[,\s;]+")
_SECRET_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "token",
        "password",
        "secret",
        "authorization",
        "access_token",
        "refresh_token",
        "bot_token",
    }
)


def parse_telegram_user_ids(raw: str | None) -> list[int]:
    """Parse comma/space-separated Telegram numeric user ids."""
    out: list[int] = []
    seen: set[int] = set()
    for part in _ID_SPLIT.split(raw or ""):
        text = part.strip().strip("'\"")
        if not text.isdigit():
            continue
        uid = int(text)
        if uid <= 0 or uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
    return out


def admin_ids_from_env() -> list[int]:
    """Fallback when the Telegram hook is not registered (tests / CLI)."""
    ids = parse_telegram_user_ids(os.getenv(PRIMARY_ADMIN_ID_ENV, ""))
    ids.extend(parse_telegram_user_ids(os.getenv(EXTRA_ADMIN_IDS_ENV, "")))
    return list(dict.fromkeys(ids))


def infer_surface(conversation_id: str) -> str:
    cid = (conversation_id or "").strip().lower()
    if cid.startswith("tg_"):
        return "telegram"
    if cid.startswith("max_"):
        return "max"
    if cid.startswith("subagent:"):
        return "subagent"
    if cid.startswith("cron"):
        return "cron"
    if cid in {"", "default"}:
        return "local"
    return "studio_or_tui"


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            folded = str(key).strip().lower().replace("-", "_")
            if folded in _SECRET_KEYS or "api_key" in folded:
                out[str(key)] = "***"
            else:
                out[str(key)] = _redact(item)
        return out
    if isinstance(value, list):
        return [_redact(v) for v in value[:40]]
    if isinstance(value, str) and len(value) > 800:
        return value[:799] + "…"
    return value


def snapshot_system_settings(profile: str) -> dict[str, Any]:
    """Non-secret profile/runtime snapshot for an admin ticket."""
    name = (profile or "default").strip() or "default"
    snap: dict[str, Any] = {"profile": name}
    try:
        from core.profile import ProfileManager

        cfg = ProfileManager().load_profile(name)
    except Exception as exc:
        snap["error"] = str(exc)[:200]
        return snap
    providers = getattr(cfg, "providers", None) or {}
    provider_names = sorted(str(k) for k in providers.keys()) if isinstance(providers, dict) else []
    snap.update(
        {
            "model": str(getattr(cfg, "model", "") or ""),
            "default_provider": str(getattr(cfg, "default_provider", "") or ""),
            "providers": provider_names,
            "max_steps": getattr(cfg, "max_steps", None),
            "agent_pipeline": str(getattr(cfg, "agent_pipeline", "") or "") or None,
            "workspace_jail_enabled": bool(getattr(cfg, "workspace_jail_enabled", False)),
            "enable_subagents": getattr(cfg, "enable_subagents", None),
            "tools_presentation": str(getattr(cfg, "tools_presentation", "") or ""),
            "mcp_enabled": bool(getattr(cfg, "mcp_enabled", True)),
            "enable_meta_agent": getattr(cfg, "enable_meta_agent", None),
            "enable_self_refinement": getattr(cfg, "enable_self_refinement", None),
        }
    )
    return snap


def _escape_html(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_admin_html(payload: dict[str, Any]) -> str:
    """Compact HTML summary for Telegram (keep under ~3500 chars)."""
    session = payload.get("session") if isinstance(payload.get("session"), dict) else {}
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    analysis = str(payload.get("analysis") or "")[:1200]
    summary = str(payload.get("summary") or "")[:400]
    needed = str(payload.get("needed_settings") or "")[:400]
    cid = str(payload.get("conversation_id") or session.get("conversation_id") or "")
    profile = str(payload.get("profile") or settings.get("profile") or "")
    model = str(payload.get("model") or settings.get("model") or "")
    surface = str(payload.get("surface") or infer_surface(cid))
    lines = [
        "🆘 <b>Holix support ticket</b>",
        "",
        f"<b>Profile:</b> <code>{_escape_html(profile)}</code>",
        f"<b>Session:</b> <code>{_escape_html(cid)}</code>",
        f"<b>Where:</b> <code>{_escape_html(surface)}</code>",
        f"<b>Model:</b> <code>{_escape_html(model)}</code>",
    ]
    if summary:
        lines.extend(["", "<b>Summary</b>", _escape_html(summary)])
    if analysis:
        lines.extend(["", "<b>Analysis</b>", _escape_html(analysis)])
    if needed:
        lines.extend(["", "<b>Settings to review</b>", _escape_html(needed)])
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    if user:
        uname = str(user.get("display") or user.get("username") or user.get("id") or "")
        if uname:
            lines.extend(["", f"<b>User:</b> {_escape_html(uname)}"])
    lines.extend(
        [
            "",
            "<i>Full JSON (session excerpt, settings, logs) is attached when possible.</i>",
        ]
    )
    text = "\n".join(lines)
    if len(text) > 3500:
        return text[:3499] + "…"
    return text


def build_ticket_payload(
    *,
    summary: str,
    analysis: str,
    needed_settings: str = "",
    conversation_id: str = "",
    profile: str = "",
    model: str = "",
    surface: str = "",
    diagnose_report: dict[str, Any] | None = None,
    logs: list[dict[str, Any]] | None = None,
    user: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cid = (conversation_id or "").strip()
    prof = (profile or "").strip() or "default"
    report = diagnose_report if isinstance(diagnose_report, dict) else {}
    if not cid:
        cid = str(report.get("conversation_id") or "")
    settings = snapshot_system_settings(prof)
    llm = report.get("llm") if isinstance(report.get("llm"), dict) else {}
    models = llm.get("models") if isinstance(llm.get("models"), dict) else {}
    inferred_model = (model or "").strip()
    if not inferred_model and models:
        inferred_model = str(next(iter(models.keys())))
    if not inferred_model:
        inferred_model = str(settings.get("model") or "")
    session_excerpt = report.get("session") if isinstance(report.get("session"), dict) else {}
    findings = report.get("findings") if isinstance(report.get("findings"), list) else []
    payload = {
        "kind": "holix_admin_support",
        "created_at": datetime.now(UTC).isoformat(),
        "summary": (summary or "").strip()[:800],
        "analysis": (analysis or "").strip()[:4000],
        "needed_settings": (needed_settings or "").strip()[:1500],
        "conversation_id": cid,
        "profile": prof,
        "model": inferred_model,
        "surface": (surface or "").strip() or infer_surface(cid),
        "settings": settings,
        "findings": _redact(findings[:12]),
        "session": _redact(
            {
                "conversation_id": cid,
                "last_real_ask": session_excerpt.get("last_real_ask"),
                "user_turns": session_excerpt.get("user_turns"),
                "tools": (session_excerpt.get("tools") or [])[-24:],
                "failed_tools": session_excerpt.get("failed_tools") or [],
                "timeline": (session_excerpt.get("timeline") or [])[-20:],
                "recent_user": session_excerpt.get("recent_user") or [],
            }
        ),
        "llm": _redact(llm) if llm else {},
        "logs": _redact(list(logs or [])[-40:]),
        "user": _redact(user or {}),
    }
    return payload


def ticket_json_bytes(payload: dict[str, Any]) -> bytes:
    blob = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if len(blob) > 60_000:
        blob = blob[:59_999] + "\n…\n"
    return blob.encode("utf-8")


async def deliver_admin_support_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    """Send HTML + JSON document to every configured Telegram admin.

    Delivery uses ``core.plugins`` notify hooks so core never imports integrations.
    """
    from core.plugins.hooks import notify_hooks

    html = format_admin_html(payload)
    document = ticket_json_bytes(payload)
    filename = "holix-support.json"
    cid = str(payload.get("conversation_id") or "session")
    safe_cid = re.sub(r"[^a-zA-Z0-9._-]+", "_", cid)[:40] or "session"
    filename = f"holix-support-{safe_cid}.json"

    list_fn = getattr(notify_hooks, "list_telegram_admins", None)
    targets: list[dict[str, Any]] = []
    if callable(list_fn):
        try:
            raw_targets = list_fn(str(payload.get("profile") or "default"))
        except Exception as exc:
            return {
                "ok": False,
                "code": "admin_lookup_failed",
                "error": str(exc)[:240],
                "sent": 0,
            }
        if isinstance(raw_targets, list):
            for item in raw_targets:
                if isinstance(item, dict):
                    uid = item.get("user_id") or item.get("id")
                    bot_profile = str(item.get("profile") or item.get("bot_profile") or "")
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    bot_profile, uid = str(item[0]), item[1]
                else:
                    uid, bot_profile = item, ""
                try:
                    user_id = int(uid)
                except (TypeError, ValueError):
                    continue
                if user_id > 0:
                    targets.append({"profile": bot_profile or "default", "user_id": user_id})

    if not targets:
        env_ids = admin_ids_from_env()
        prof = str(payload.get("profile") or "default")
        targets = [{"profile": prof, "user_id": uid} for uid in env_ids]

    if not targets:
        return {
            "ok": False,
            "code": "no_telegram_admin",
            "error": (
                "No Telegram admin is configured. Set HOLIX_TELEGRAM_ADMIN_USER_ID "
                "(and optional HOLIX_TELEGRAM_ADMIN_EXTRA_USER_IDS) or assign an "
                "admin with `holix telegram requests approve --set-admin`."
            ),
            "sent": 0,
        }

    send_text = notify_hooks.send_telegram
    send_doc = getattr(notify_hooks, "send_telegram_document", None)
    delivered: list[int] = []
    failed: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for target in targets:
        bot_profile = str(target.get("profile") or "default")
        user_id = int(target["user_id"])
        key = (bot_profile, user_id)
        if key in seen:
            continue
        seen.add(key)
        ok_text = False
        if callable(send_text):
            try:
                ok_text = bool(
                    await send_text(
                        user_id,
                        html,
                        profile=bot_profile,
                        parse_mode="HTML",
                    )
                )
            except Exception as exc:
                failed.append({"user_id": user_id, "error": str(exc)[:200]})
                continue
        ok_doc = False
        if callable(send_doc):
            try:
                ok_doc = bool(
                    await send_doc(
                        user_id,
                        filename=filename,
                        content=document,
                        caption="Holix support ticket (JSON)",
                        profile=bot_profile,
                    )
                )
            except Exception:
                ok_doc = False
        if ok_text or ok_doc:
            delivered.append(user_id)
        else:
            failed.append({"user_id": user_id, "error": "send_failed"})

    if not delivered:
        return {
            "ok": False,
            "code": "delivery_failed",
            "error": "Could not deliver the ticket to any Telegram admin.",
            "failed": failed,
            "sent": 0,
        }
    return {
        "ok": True,
        "sent": len(delivered),
        "admin_ids": delivered,
        "failed": failed,
        "document": filename,
    }
