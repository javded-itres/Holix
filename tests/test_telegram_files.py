"""Telegram file attachments: save, extract, prompt building."""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integrations.telegram.file_handler import (
    SavedTelegramFile,
    _extract_docx_text,
    _extract_pdf_text,
    _safe_filename,
    build_agent_prompt,
    enrich_saved_file,
    profile_files_dir,
    resolve_vision_config,
)


def test_resolve_vision_config_uses_env_when_model_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import settings

    monkeypatch.setenv("LITELLM_API_KEY", "sk-test-key")
    monkeypatch.setenv("LITELLM_API_BASE", "http://localhost:4000/v1")
    monkeypatch.setattr(settings, "telegram_vision_model", "vision-smart")

    class _Mgr:
        def load_profile(self, _profile: str):
            raise RuntimeError("skip profile")

    monkeypatch.setattr("cli.core.get_profile_manager", lambda: _Mgr())

    cfg = resolve_vision_config(profile="default")
    assert cfg.model == "vision-smart"
    assert cfg.api_key == "sk-test-key"
    assert cfg.base_url.endswith("/v1")


def test_resolve_vision_config_requires_api_when_only_model_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import settings

    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_API_BASE", raising=False)
    monkeypatch.setattr(settings, "telegram_vision_model", "vision-smart")
    monkeypatch.setattr(settings, "openai_api_key", "")

    class _Mgr:
        def load_profile(self, _profile: str):
            raise RuntimeError("no profile")

    monkeypatch.setattr("cli.core.get_profile_manager", lambda: _Mgr())

    with pytest.raises(RuntimeError, match="API"):
        resolve_vision_config(profile="default")


def test_safe_filename_sanitizes() -> None:
    assert _safe_filename("report (1).pdf") == "report (1).pdf"
    assert _safe_filename("../../../etc/passwd") == "passwd"


def test_profile_files_dir_under_data(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from cli.core import ProfileManager, init_profile

    profile = "default"
    pdir = tmp_path / "profiles" / profile
    pdir.mkdir(parents=True)
    (pdir / "config.yaml").write_text("profile_name: default\n", encoding="utf-8")

    monkeypatch.setattr(
        ProfileManager,
        "get_profile_dir",
        lambda self, name: pdir,
    )

    dest = profile_files_dir(profile, 12345)
    assert dest == pdir / "data" / "files" / "telegram" / "12345"
    assert dest.is_dir()


def test_build_agent_prompt_includes_path_and_description() -> None:
    saved = SavedTelegramFile(
        path=Path("/tmp/profile/data/files/telegram/1/report.pdf"),
        original_name="report.pdf",
        mime_type="application/pdf",
        kind="document",
        size_bytes=1024,
        description="Summary text",
    )
    prompt = build_agent_prompt("Сделай краткое резюме", [saved])
    assert "Сделай краткое резюме" in prompt
    assert "report.pdf" in prompt
    assert "Summary text" in prompt
    assert "/tmp/profile/data/files/telegram/1/report.pdf" in prompt


def test_extract_pdf_text(tmp_path: Path) -> None:
    from pypdf import PdfWriter

    pdf = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with pdf.open("wb") as fh:
        writer.write(fh)
    # blank page has no text — ensure extractor runs without error
    assert _extract_pdf_text(pdf) == ""


def test_extract_docx_text(tmp_path: Path) -> None:
    docx = tmp_path / "sample.docx"
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>Hello DOCX</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(docx, "w") as zf:
        zf.writestr("word/document.xml", xml)
    assert "Hello DOCX" in _extract_docx_text(docx)


@pytest.mark.asyncio
async def test_enrich_text_file(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("line one\nline two", encoding="utf-8")
    saved = SavedTelegramFile(
        path=path,
        original_name="notes.txt",
        mime_type="text/plain",
        kind="document",
        size_bytes=path.stat().st_size,
    )
    enriched = await enrich_saved_file(saved, profile="default")
    assert "line one" in enriched.description


@pytest.mark.asyncio
async def test_save_telegram_attachment_downloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from integrations.telegram import file_handler

    dest_root = tmp_path / "files"
    monkeypatch.setattr(
        file_handler,
        "profile_files_dir",
        lambda profile, chat_id: dest_root,
    )

    async def fake_download(bot, file_id, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"hello")
        return 5

    monkeypatch.setattr(file_handler, "download_telegram_file_to_path", fake_download)
    monkeypatch.setattr(file_handler, "enrich_saved_file", AsyncMock(side_effect=lambda s, **k: s))

    bot = MagicMock()
    saved = await file_handler.save_telegram_attachment(
        bot,
        "file123",
        profile="default",
        chat_id=1,
        file_name="test.txt",
        mime_type="text/plain",
    )
    assert saved.path.exists()
    assert saved.original_name == "test.txt"