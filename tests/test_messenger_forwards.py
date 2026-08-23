"""Forwarded Telegram / MAX messages flattened for the agent."""

from __future__ import annotations

from types import SimpleNamespace

from integrations.max.file_handler import extract_media_attachments
from integrations.max.forwards import flatten_max_forward, is_max_forward
from integrations.messenger.forwards import combine_forward_text
from integrations.telegram.forwards import (
    compose_telegram_forward_prompt,
    is_telegram_forward,
    pending_attachment_from_message,
    telegram_forward_origin_label,
)


def test_combine_forward_includes_origin_and_instruction() -> None:
    ru = combine_forward_text(
        forwarded="Привет",
        origin="Иван",
        locale="ru",
    )
    assert "Переслано от: Иван" in ru
    assert "Привет" in ru
    empty = combine_forward_text(origin="Канал", locale="ru", has_media=True)
    assert "Переслано от: Канал" in empty
    assert "Обработай пересланное" in empty


def test_telegram_forward_origin_user_and_channel() -> None:
    user = SimpleNamespace(first_name="Анна", last_name="П.", username="anna", id=1)
    msg = SimpleNamespace(
        forward_origin=SimpleNamespace(
            sender_user=user,
            sender_user_name=None,
            chat=None,
            sender_chat=None,
            author_signature=None,
        ),
        forward_from=None,
        forward_from_chat=None,
        forward_sender_name=None,
        forward_date=None,
        text="hello",
        caption=None,
    )
    assert is_telegram_forward(msg)
    assert telegram_forward_origin_label(msg) == "Анна П."
    prompt = compose_telegram_forward_prompt(msg, locale="ru", has_media=False)
    assert "Переслано от: Анна П." in prompt
    assert "hello" in prompt

    channel = SimpleNamespace(
        forward_origin=SimpleNamespace(
            sender_user=None,
            sender_user_name=None,
            chat=SimpleNamespace(title="Новости", username="news"),
            sender_chat=None,
            author_signature="ред.",
        ),
        forward_from=None,
        forward_from_chat=None,
        forward_sender_name=None,
        forward_date=1,
        text=None,
        caption=None,
        photo=None,
        document=None,
        video=None,
        animation=None,
        video_note=None,
    )
    assert "Новости" in telegram_forward_origin_label(channel)
    photo = SimpleNamespace(
        file_id="aaa",
        file_unique_id="uid",
        file_size=12,
    )
    channel.photo = [photo]
    att = pending_attachment_from_message(channel)
    assert att is not None
    assert att.mime_type == "image/jpeg"


def test_telegram_video_attachment() -> None:
    msg = SimpleNamespace(
        photo=None,
        document=None,
        video=SimpleNamespace(
            file_id="vid",
            file_unique_id="v1",
            file_name="clip.mp4",
            mime_type="video/mp4",
            file_size=99,
        ),
        animation=None,
        video_note=None,
    )
    att = pending_attachment_from_message(msg)
    assert att is not None
    assert att.file_name == "clip.mp4"
    assert att.mime_type == "video/mp4"


def test_max_forward_merges_text_and_file() -> None:
    msg = {
        "sender": {"user_id": 7, "name": "User"},
        "body": {"text": "посмотри", "attachments": []},
        "link": {
            "type": "forward",
            "sender": {"name": "Канал MAX"},
            "message": {
                "text": "Счёт за март",
                "attachments": [
                    {
                        "type": "file",
                        "filename": "invoice.pdf",
                        "size": 10,
                        "payload": {"url": "https://cdn.example/invoice.pdf"},
                    }
                ],
            },
        },
    }
    assert is_max_forward(msg)
    flat = flatten_max_forward(msg)
    assert flat["_is_forward"] is True
    text = flat["body"]["text"]
    assert "Канал MAX" in text
    assert "Счёт за март" in text
    assert "посмотри" in text
    items = extract_media_attachments(flat)
    assert len(items) == 1
    assert items[0].file_name == "invoice.pdf"


def test_max_forward_link_attachment_nested_image() -> None:
    msg = {
        "body": {
            "text": "",
            "attachments": [
                {
                    "type": "link",
                    "payload": {
                        "message": {
                            "attachments": [
                                {
                                    "type": "image",
                                    "payload": {
                                        "photo_id": 5,
                                        "url": "https://cdn.example/p.jpg",
                                    },
                                }
                            ]
                        }
                    },
                }
            ],
        },
        "link": {"type": "forward", "sender": {"name": "Друг"}, "message": {"text": ""}},
    }
    flat = flatten_max_forward(msg)
    items = extract_media_attachments(flat)
    assert len(items) == 1
    assert items[0].attachment_type == "image"
    assert "Обработай пересланное" in flat["body"]["text"]


def test_max_reply_is_not_flattened() -> None:
    msg = {
        "body": {"text": "ответ", "attachments": []},
        "link": {
            "type": "reply",
            "message": {"text": "оригинал", "attachments": []},
        },
    }
    assert is_max_forward(msg) is False
    assert flatten_max_forward(msg) is msg
