"""Build chunked docs index and embedding vectors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.docs_chat.chunking import chunk_page, strip_markdown
from core.docs_chat.embeddings import embed_chunks, save_manifest, save_vectors


def build_chunk_entries(
    pages: list[dict[str, Any]],
    *,
    raw_by_file: dict[str, str],
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for page in pages:
        raw = raw_by_file.get(page["file"], "")
        if not raw:
            continue
        chunks.extend(
            chunk_page(
                raw,
                lang=str(page["lang"]),
                slug=str(page["slug"]),
                title=str(page["title"]),
                nav_order=int(page.get("nav_order", 999)),
            )
        )
    chunks.sort(key=lambda c: (c["lang"], c.get("nav_order", 999), c["slug"], c.get("section", "")))
    return chunks


def write_chunk_index(
    web_docs_dir: Path,
    *,
    pages: list[dict[str, Any]],
    raw_by_file: dict[str, str],
) -> list[dict[str, Any]]:
    chunks = build_chunk_entries(pages, raw_by_file=raw_by_file)
    chunks_path = web_docs_dir / "search-chunks.json"
    chunks_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")

    vectors_path = web_docs_dir / "search-vectors.npz"
    manifest_path = web_docs_dir / "search-vectors.manifest.json"
    if chunks:
        matrix = embed_chunks(chunks)
        chunk_ids = [str(c["id"]) for c in chunks]
        save_vectors(vectors_path, chunk_ids=chunk_ids, vectors=matrix)
        save_manifest(
            manifest_path,
            model="onnx-miniLM-l6-v2",
            dim=int(matrix.shape[1]) if matrix.size else 0,
            count=len(chunks),
        )
    return chunks


def make_page_entry(
    *,
    lang: str,
    stem: str,
    slug: str,
    title: str,
    heading: str,
    file_rel: str,
    raw: str,
    nav_order: int,
) -> dict[str, Any]:
    return {
        "id": f"{lang}/{slug}",
        "lang": lang,
        "slug": slug,
        "file": file_rel,
        "title": title,
        "heading": heading,
        "body": strip_markdown(raw)[:8000],
        "nav_order": nav_order,
    }