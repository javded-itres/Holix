"""Flatten MAX reposts (`link.type=forward`) into body text + attachments."""

from __future__ import annotations

from typing import Any


def is_max_forward(message: dict[str, Any] | None) -> bool:
    if not isinstance(message, dict):
        return False
    if message.get("_is_forward"):
        return True
    link = message.get("link")
    if not isinstance(link, dict):
        return False
    return str(link.get("type") or "").strip().lower() == "forward"


def _sender_label(sender: Any) -> str:
    if not isinstance(sender, dict):
        return ""
    name = str(sender.get("name") or "").strip()
    if name:
        return name
    first = str(sender.get("first_name") or "").strip()
    last = str(sender.get("last_name") or "").strip()
    full = " ".join(p for p in (first, last) if p)
    if full:
        return full
    username = str(sender.get("username") or "").strip()
    if username:
        return f"@{username.lstrip('@')}"
    return ""


def _as_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _expand_nested_attachments(
    attachments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Unwrap type=link/share nested media; collect share URLs as extra text."""
    media: list[dict[str, Any]] = []
    urls: list[str] = []
    for att in attachments:
        kind = str(att.get("type") or "").strip().lower()
        if kind in {"link", "share"}:
            payload = att.get("payload") if isinstance(att.get("payload"), dict) else {}
            inner_msg = payload.get("message")
            if isinstance(inner_msg, dict):
                nested, nested_urls = _expand_nested_attachments(
                    _as_list(inner_msg.get("attachments"))
                )
                media.extend(nested)
                urls.extend(nested_urls)
            nested_atts, nested_urls = _expand_nested_attachments(
                _as_list(payload.get("attachments"))
            )
            media.extend(nested_atts)
            urls.extend(nested_urls)
            url = str(payload.get("url") or "").strip()
            title = str(payload.get("title") or "").strip()
            if url:
                urls.append(f"{title} {url}".strip() if title else url)
            continue
        media.append(att)
    return media, urls


def flatten_max_forward(message: dict[str, Any]) -> dict[str, Any]:
    """Merge forwarded body/attachments into the outer message.

    MAX reposts leave ``body.text`` empty (or only the user's comment) and put
    the original content in ``link.message`` and/or ``attachments[].type=link``.
    """
    if not isinstance(message, dict) or not is_max_forward(message):
        return message

    link = message.get("link") if isinstance(message.get("link"), dict) else {}
    nested = link.get("message") if isinstance(link.get("message"), dict) else {}
    outer_body = message.get("body") if isinstance(message.get("body"), dict) else {}

    comment = str(outer_body.get("text") or "").strip()
    forwarded = str(nested.get("text") or "").strip()
    origin = _sender_label(link.get("sender"))

    attachments, extra_urls = _expand_nested_attachments(
        _as_list(outer_body.get("attachments")) + _as_list(nested.get("attachments"))
    )
    if extra_urls:
        extra = "\n".join(extra_urls)
        forwarded = f"{forwarded}\n{extra}".strip() if forwarded else extra

    from integrations.messenger.forwards import combine_forward_text

    has_media = bool(attachments)
    text = combine_forward_text(
        forwarded=forwarded,
        comment=comment,
        origin=origin,
        locale="ru",
        has_media=has_media,
    )

    new_body = dict(outer_body)
    new_body["text"] = text
    new_body["attachments"] = attachments
    out = dict(message)
    out["body"] = new_body
    out["_is_forward"] = True
    return out
