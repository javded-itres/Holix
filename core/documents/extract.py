"""Pull plain text out of documents the user attaches or names by path."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

MAX_EXTRACT_CHARS = 400_000

_TEXT_SUFFIXES = frozenset(
    {
        ".txt",
        ".md",
        ".markdown",
        ".csv",
        ".tsv",
        ".json",
        ".xml",
        ".html",
        ".htm",
        ".yaml",
        ".yml",
        ".py",
        ".js",
        ".ts",
        ".sql",
        ".log",
        ".rst",
        ".ini",
        ".cfg",
        ".env",
        ".rtf",
    }
)


def extract_document_text(path: Path, *, max_chars: int = MAX_EXTRACT_CHARS) -> str:
    """Return extracted text, or empty when the format has no text layer."""
    suffix = path.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        text = read_text_file(path, max_chars=max_chars)
        if suffix in {".html", ".htm"}:
            text = _strip_tags(text)
        return text
    if suffix == ".pdf":
        return extract_pdf_text(path, max_chars=max_chars)
    if suffix == ".docx":
        return extract_docx_text(path, max_chars=max_chars)
    if suffix == ".odt":
        return extract_odt_text(path, max_chars=max_chars)
    return ""


def read_text_file(path: Path, *, max_chars: int = MAX_EXTRACT_CHARS) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
        try:
            text = path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError:
            return ""
        return _cap(text, max_chars)
    return ""


def extract_pdf_text(path: Path, *, max_chars: int = MAX_EXTRACT_CHARS) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(str(path))
        parts: list[str] = []
        total = 0
        for page in reader.pages[:80]:
            piece = page.extract_text() or ""
            parts.append(piece)
            total += len(piece)
            if total >= max_chars:
                break
        return _cap("\n".join(parts).strip(), max_chars)
    except Exception:
        return ""


def extract_docx_text(path: Path, *, max_chars: int = MAX_EXTRACT_CHARS) -> str:
    return _office_xml_text(path, "word/document.xml", max_chars=max_chars)


def extract_odt_text(path: Path, *, max_chars: int = MAX_EXTRACT_CHARS) -> str:
    return _office_xml_text(path, "content.xml", max_chars=max_chars)


def _office_xml_text(path: Path, member: str, *, max_chars: int) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml_bytes = archive.read(member)
        root = ElementTree.fromstring(xml_bytes)
        texts = [node.text for node in root.iter() if node.text]
        return _cap(" ".join(texts).strip(), max_chars)
    except Exception:
        return ""


def _strip_tags(text: str) -> str:
    plain = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", plain).strip()


def _cap(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars]
