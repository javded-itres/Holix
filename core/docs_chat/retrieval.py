"""Hybrid keyword + semantic retrieval for docs chat."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from core.docs_chat.embeddings import embed_query, load_vectors
from core.docs_chat.keywords import content_terms, expand_query_terms, slug_keyword_terms

logger = logging.getLogger(__name__)

_KEYWORD_WEIGHT = 0.45
_SEMANTIC_WEIGHT = 0.55
_PAGE_BOOST = 0.12
_CANDIDATE_POOL = 24


@dataclass(frozen=True, slots=True)
class DocsSearchHit:
    title: str
    slug: str
    snippet: str
    score: float
    section: str = ""
    heading: str = ""


def _web_docs_dir() -> Path:
    from cli.services.docs_site import resolve_web_docs_dir

    return resolve_web_docs_dir()


def chunks_path() -> Path:
    return _web_docs_dir() / "search-chunks.json"


def vectors_path() -> Path:
    return _web_docs_dir() / "search-vectors.npz"


_chunks_cache: list[dict[str, Any]] | None = None
_vectors_cache: tuple[list[str], np.ndarray] | None = None


def clear_retrieval_cache() -> None:
    global _chunks_cache, _vectors_cache
    _chunks_cache = None
    _vectors_cache = None


def load_chunks(*, reload: bool = False) -> list[dict[str, Any]]:
    global _chunks_cache
    if _chunks_cache is not None and not reload:
        return _chunks_cache
    path = chunks_path()
    if not path.is_file():
        _chunks_cache = []
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        _chunks_cache = data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("docs chat: could not load chunks: %s", exc)
        _chunks_cache = []
    return _chunks_cache


def _load_vectors_cached() -> tuple[list[str], np.ndarray] | None:
    global _vectors_cache
    if _vectors_cache is not None:
        return _vectors_cache
    _vectors_cache = load_vectors(vectors_path())
    return _vectors_cache


def _keyword_score(chunk: dict[str, Any], *, query: str, terms: list[str], content: list[str]) -> float:
    title = str(chunk.get("title", "")).lower()
    heading = str(chunk.get("heading", "")).lower()
    body = str(chunk.get("body", "")).lower()
    slug = str(chunk.get("slug", "")).lower()
    slug_spaced = slug.replace("-", " ")
    keywords = [str(k).lower() for k in chunk.get("keywords") or []]
    score = 0.0

    if title.find(query) >= 0:
        score += 50
    if heading.find(query) >= 0:
        score += 40
    if slug.find(query) >= 0 or slug_spaced.find(query) >= 0:
        score += 70

    for term in terms:
        if term == slug or term in slug_spaced:
            score += 140
        if term in keywords:
            score += 90
        if term in title:
            score += 24
        if term in heading:
            score += 18

    for term in content:
        if term in keywords:
            score += 50
        if term in heading:
            score += 16
        if term in title:
            score += 20
        if term in body:
            score += 5
        if term == slug or term in slug_spaced:
            score += 100

    for term in slug_keyword_terms(slug):
        if term in terms or term in content:
            score += 35

    return score


def _semantic_scores(chunks: list[dict[str, Any]], query: str) -> dict[str, float]:
    loaded = _load_vectors_cached()
    query_vec = embed_query(query)
    if loaded is None or query_vec is None:
        return {}
    ids, matrix = loaded
    id_to_idx = {chunk_id: idx for idx, chunk_id in enumerate(ids)}
    scores: dict[str, float] = {}
    for chunk in chunks:
        chunk_id = str(chunk.get("id", ""))
        idx = id_to_idx.get(chunk_id)
        if idx is None:
            continue
        similarity = float(np.dot(matrix[idx], query_vec))
        if similarity > 0:
            scores[chunk_id] = similarity
    return scores


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    max_score = max(scores.values())
    if max_score <= 0:
        return scores
    return {key: value / max_score for key, value in scores.items()}


def _make_hit(chunk: dict[str, Any], score: float) -> DocsSearchHit:
    heading = str(chunk.get("heading") or chunk.get("title") or chunk.get("slug", ""))
    title = str(chunk.get("title") or chunk.get("slug", ""))
    if heading and heading.lower() != title.lower():
        display_title = f"{title} — {heading}"
    else:
        display_title = title
    return DocsSearchHit(
        title=display_title,
        slug=str(chunk.get("slug", "")),
        snippet=str(chunk.get("body", "")).strip(),
        score=score,
        section=str(chunk.get("section", "")),
        heading=heading,
    )


def search_docs(
    query: str,
    *,
    lang: str,
    limit: int = 5,
    page_slug: str | None = None,
) -> list[DocsSearchHit]:
    q = query.lower().strip()
    if not q:
        return []

    chunks = [c for c in load_chunks() if c.get("lang") == lang]
    if not chunks:
        return _legacy_page_search(query, lang=lang, limit=limit)

    terms = expand_query_terms(q)
    content = content_terms(terms) or terms

    keyword_raw: dict[str, float] = {}
    for chunk in chunks:
        chunk_id = str(chunk.get("id", ""))
        score = _keyword_score(chunk, query=q, terms=terms, content=content)
        if score > 0:
            keyword_raw[chunk_id] = score

    semantic_raw = _semantic_scores(chunks, q)
    keyword = _normalize(keyword_raw)
    semantic = _normalize(semantic_raw)

    combined: dict[str, float] = {}
    for chunk in chunks:
        chunk_id = str(chunk.get("id", ""))
        kw = keyword.get(chunk_id, 0.0)
        sem = semantic.get(chunk_id, 0.0)
        if kw <= 0 and sem <= 0:
            continue
        score = _KEYWORD_WEIGHT * kw + _SEMANTIC_WEIGHT * sem
        if page_slug and str(chunk.get("slug")) == page_slug:
            score += _PAGE_BOOST
        combined[chunk_id] = score

    if not combined:
        return []

    chunk_by_id = {str(c.get("id", "")): c for c in chunks}
    ranked = sorted(combined.items(), key=lambda item: item[1], reverse=True)

    hits: list[DocsSearchHit] = []
    per_slug: dict[str, int] = {}
    for chunk_id, score in ranked[:_CANDIDATE_POOL]:
        chunk = chunk_by_id.get(chunk_id)
        if not chunk:
            continue
        slug = str(chunk.get("slug", ""))
        if per_slug.get(slug, 0) >= 2:
            continue
        per_slug[slug] = per_slug.get(slug, 0) + 1
        hits.append(_make_hit(chunk, score))
        if len(hits) >= limit:
            break
    return hits


def _load_page_index() -> list[dict[str, Any]]:
    path = _web_docs_dir() / "search-index.json"
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _legacy_page_search(query: str, *, lang: str, limit: int) -> list[DocsSearchHit]:
    """Fallback when chunk index is missing."""
    q = query.lower().strip()
    terms = expand_query_terms(q)
    content = content_terms(terms) or terms
    hits: list[DocsSearchHit] = []
    for entry in _load_page_index():
        if entry.get("lang") != lang:
            continue
        slug = str(entry.get("slug", "")).lower()
        title = str(entry.get("title", "")).lower()
        heading = str(entry.get("heading", "")).lower()
        body = str(entry.get("body", "")).lower()
        score = 0.0
        for term in content:
            if term == slug:
                score += 80
            if term in title:
                score += 20
            if term in heading:
                score += 12
            if term in body:
                score += 4
        if score <= 0:
            continue
        hits.append(
            DocsSearchHit(
                title=str(entry.get("title", entry.get("slug", ""))),
                slug=str(entry.get("slug", "")),
                snippet=str(entry.get("body", ""))[:320],
                score=score,
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]