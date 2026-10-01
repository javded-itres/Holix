"""On-disk fragment index for long documents.

The chat turn stores a short card. The agent pulls matching fragments with
``search_document`` / ``read_document`` instead of pasting the whole file
into the model context. SQLite FTS5 is the index; a token scan is the fallback
when this SQLite build has no FTS5.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.documents.extract import extract_document_text
from core.paths import resolve_profile_data_dir

INLINE_LIMIT = 6_000
CHUNK_CHARS = 1_400
CHUNK_OVERLAP = 180
MAX_CHUNKS = 400


@dataclass(frozen=True)
class IndexedDocument:
    doc_id: str
    name: str
    path: str
    chars: int
    chunk_count: int
    preview: str


def chunk_text(text: str, *, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    body = (text or "").strip()
    if not body:
        return []
    step = max(1, size - overlap)
    chunks: list[str] = []
    start = 0
    while start < len(body) and len(chunks) < MAX_CHUNKS:
        piece = body[start : start + size].strip()
        if piece:
            chunks.append(piece)
        if start + size >= len(body):
            break
        start += step
    return chunks


def maybe_index_document(
    *,
    profile: str,
    path: Path | str,
    name: str,
    text: str,
    conversation_id: str,
    db_path: Path | None = None,
) -> str | None:
    """Index long text and return the chat card. Short text stays inline."""
    body = (text or "").strip()
    if len(body) < INLINE_LIMIT:
        return None
    stored = index_text(
        profile=profile,
        path=path,
        name=name,
        text=body,
        conversation_id=conversation_id,
        db_path=db_path,
    )
    return format_card(stored)


def index_text(
    *,
    profile: str,
    path: Path | str,
    name: str,
    text: str,
    conversation_id: str,
    db_path: Path | None = None,
) -> IndexedDocument:
    source = Path(path)
    body = (text or "").strip()
    task = _conversation(conversation_id)
    chunks = chunk_text(body)
    doc_id = _doc_id(source, task)
    preview = chunks[0][:500] if chunks else ""
    database = db_path or _database_path(profile)
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as db:
        _ensure(db)
        db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        _delete_fts(db, doc_id)
        db.execute(
            """INSERT INTO documents (id, conversation_id, name, path, chars, chunk_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (doc_id, task, name or source.name, str(source), len(body), len(chunks)),
        )
        for index, piece in enumerate(chunks):
            db.execute(
                "INSERT INTO chunks (doc_id, idx, text) VALUES (?, ?, ?)",
                (doc_id, index, piece),
            )
            _insert_fts(db, doc_id, index, piece)
        db.commit()
    return IndexedDocument(
        doc_id=doc_id,
        name=name or source.name,
        path=str(source),
        chars=len(body),
        chunk_count=len(chunks),
        preview=preview,
    )


def index_path(
    profile: str,
    path: Path | str,
    *,
    conversation_id: str,
    db_path: Path | None = None,
) -> IndexedDocument | None:
    source = Path(path)
    text = extract_document_text(source)
    if not text.strip():
        return None
    return index_text(
        profile=profile,
        path=source,
        name=source.name,
        text=text,
        conversation_id=conversation_id,
        db_path=db_path,
    )


def search_documents(
    profile: str,
    query: str,
    *,
    conversation_id: str,
    doc_id: str = "",
    limit: int = 5,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    database = db_path or _database_path(profile)
    if not database.is_file():
        return []
    task = _conversation(conversation_id)
    cap = max(1, min(int(limit), 8))
    with sqlite3.connect(database) as db:
        db.row_factory = sqlite3.Row
        _ensure(db)
        rows = _search_fts(db, query, conversation_id=task, doc_id=doc_id.strip(), limit=cap)
        if rows is None:
            rows = _search_scan(db, query, conversation_id=task, doc_id=doc_id.strip(), limit=cap)
        return [_hit(row) for row in rows]


def read_document_chunks(
    profile: str,
    *,
    conversation_id: str,
    doc_id: str = "",
    path: str = "",
    start: int = 0,
    count: int = 3,
    db_path: Path | None = None,
) -> list[dict[str, Any]] | None:
    """Fragments in this session, or None when that id belongs to another session."""
    database = db_path or _database_path(profile)
    if not database.is_file():
        return None
    task = _conversation(conversation_id)
    key = doc_id.strip() or (_doc_id(Path(path), task) if path else "")
    if not key:
        return None
    offset = max(0, int(start))
    take = max(1, min(int(count), 6))
    with sqlite3.connect(database) as db:
        db.row_factory = sqlite3.Row
        _ensure(db)
        owned = db.execute(
            "SELECT 1 FROM documents WHERE id = ? AND conversation_id = ?",
            (key, task),
        ).fetchone()
        if owned is None:
            return None
        rows = db.execute(
            """SELECT c.doc_id, c.idx, c.text, d.name
               FROM chunks c
               JOIN documents d ON d.id = c.doc_id
               WHERE c.doc_id = ? AND d.conversation_id = ? AND c.idx >= ?
               ORDER BY c.idx
               LIMIT ?""",
            (key, task, offset, take),
        ).fetchall()
    return [_hit(row) for row in rows]


def list_session_documents(
    profile: str,
    conversation_id: str,
    *,
    limit: int = 12,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Short cards for one session. Previews are openings, not the whole file."""
    task = _conversation(conversation_id)
    database = db_path or _database_path(profile)
    if not database.is_file():
        return []
    cap = max(1, min(int(limit), 20))
    with sqlite3.connect(database) as db:
        db.row_factory = sqlite3.Row
        _ensure(db)
        rows = db.execute(
            """SELECT id, name, path, chars, chunk_count
               FROM documents
               WHERE conversation_id = ?
               ORDER BY rowid DESC
               LIMIT ?""",
            (task, cap),
        ).fetchall()
        listed: list[dict[str, Any]] = []
        for row in rows:
            preview_row = db.execute(
                "SELECT text FROM chunks WHERE doc_id = ? AND idx = 0",
                (row["id"],),
            ).fetchone()
            preview = ""
            if preview_row is not None:
                preview = " ".join(str(preview_row["text"] or "").split())[:180]
            listed.append(
                {
                    "doc_id": row["id"],
                    "name": row["name"],
                    "path": row["path"],
                    "chars": int(row["chars"] or 0),
                    "chunk_count": int(row["chunk_count"] or 0),
                    "preview": preview,
                }
            )
    return listed


def format_session_documents_prompt(
    profile: str,
    conversation_id: str,
    *,
    db_path: Path | None = None,
) -> str:
    """Catalog a parent can hand to a sub-agent. Empty when this session has none."""
    rows = list_session_documents(profile, conversation_id, db_path=db_path)
    if not rows:
        return ""
    lines = [
        "## Session documents",
        "The parent session indexed these long documents. Do not paste or "
        "`read_file` a whole file. Call `search_document` with the question and "
        "`doc_id`, then `read_document` for a few fragments, and quote the fragment. "
        "Each id is a separate document.",
    ]
    for row in rows:
        lines.append(
            f"- {row['name']} id={row['doc_id']} "
            f"fragments={row['chunk_count']} chars={row['chars']}"
        )
        if row["path"]:
            lines.append(f"  path: {row['path']}")
        if row["preview"]:
            lines.append(f"  opening: {row['preview']}")
    return "\n".join(lines)


def delete_conversation_documents(
    profile: str,
    conversation_id: str,
    *,
    db_path: Path | None = None,
) -> None:
    """Drop every document indexed for one session."""
    task = (conversation_id or "").strip()
    if not task:
        return
    database = db_path or _database_path(profile)
    if not database.is_file():
        return
    with sqlite3.connect(database) as db:
        _ensure(db)
        ids = [
            str(row[0])
            for row in db.execute(
                "SELECT id FROM documents WHERE conversation_id = ?",
                (task,),
            )
        ]
        for doc_id in ids:
            db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            _delete_fts(db, doc_id)
        db.execute("DELETE FROM documents WHERE conversation_id = ?", (task,))
        db.commit()


def format_card(document: IndexedDocument) -> str:
    return (
        "Документ проиндексирован в этой сессии и в контекст целиком не входит. "
        f"id={document.doc_id}, фрагментов: {document.chunk_count}, "
        f"символов: {document.chars}. "
        f'Искать: search_document(query, doc_id="{document.doc_id}"). '
        f'Читать по порядку: read_document(doc_id="{document.doc_id}", start=0).\n'
        f"Начало:\n{document.preview}"
    )


def _database_path(profile: str) -> Path:
    return resolve_profile_data_dir(profile) / "documents.db"


def _conversation(conversation_id: str) -> str:
    return (conversation_id or "").strip() or "default"


def _doc_id(path: Path, conversation_id: str) -> str:
    task = _conversation(conversation_id)
    try:
        stat = path.stat()
        stamp = f"{task}|{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    except OSError:
        stamp = f"{task}|{path}"
    return hashlib.sha256(stamp.encode("utf-8", errors="replace")).hexdigest()[:12]


def _ensure(db: sqlite3.Connection) -> None:
    db.execute(
        """CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL DEFAULT '',
            name TEXT,
            path TEXT,
            chars INTEGER,
            chunk_count INTEGER
        )"""
    )
    columns = {str(row[1]) for row in db.execute("PRAGMA table_info(documents)")}
    if "conversation_id" not in columns:
        db.execute("ALTER TABLE documents ADD COLUMN conversation_id TEXT NOT NULL DEFAULT ''")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_conversation ON documents(conversation_id)"
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS chunks (
            doc_id TEXT,
            idx INTEGER,
            text TEXT,
            PRIMARY KEY (doc_id, idx)
        )"""
    )
    try:
        db.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                doc_id UNINDEXED,
                idx UNINDEXED,
                text,
                tokenize='unicode61'
            )"""
        )
    except sqlite3.OperationalError:
        pass


def _fts_ready(db: sqlite3.Connection) -> bool:
    row = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chunks_fts'"
    ).fetchone()
    return row is not None


def _delete_fts(db: sqlite3.Connection, doc_id: str) -> None:
    if not _fts_ready(db):
        return
    try:
        db.execute("DELETE FROM chunks_fts WHERE doc_id = ?", (doc_id,))
    except sqlite3.OperationalError:
        pass


def _insert_fts(db: sqlite3.Connection, doc_id: str, index: int, text: str) -> None:
    if not _fts_ready(db):
        return
    try:
        db.execute(
            "INSERT INTO chunks_fts (doc_id, idx, text) VALUES (?, ?, ?)",
            (doc_id, index, text),
        )
    except sqlite3.OperationalError:
        pass


def _match_query(query: str) -> str:
    words = re.findall(r"[\w]{3,}", query or "", flags=re.UNICODE)[:12]
    return " AND ".join(f'"{word}"' for word in words)


def _search_fts(
    db: sqlite3.Connection,
    query: str,
    *,
    conversation_id: str,
    doc_id: str,
    limit: int,
) -> list[sqlite3.Row] | None:
    if not _fts_ready(db):
        return None
    match = _match_query(query)
    if not match:
        return []
    sql = """SELECT f.doc_id AS doc_id, f.idx AS idx, f.text AS text, d.name AS name
             FROM chunks_fts f
             JOIN documents d ON d.id = f.doc_id
             WHERE chunks_fts MATCH ? AND d.conversation_id = ?"""
    params: list[Any] = [match, conversation_id]
    if doc_id:
        sql += " AND f.doc_id = ?"
        params.append(doc_id)
    sql += " LIMIT ?"
    params.append(limit)
    try:
        return db.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return None


def _search_scan(
    db: sqlite3.Connection,
    query: str,
    *,
    conversation_id: str,
    doc_id: str,
    limit: int,
) -> list[sqlite3.Row]:
    words = [word.lower() for word in re.findall(r"[\w]{3,}", query or "", flags=re.UNICODE)]
    sql = """SELECT c.doc_id, c.idx, c.text, d.name
             FROM chunks c JOIN documents d ON d.id = c.doc_id
             WHERE d.conversation_id = ?"""
    params: list[Any] = [conversation_id]
    if doc_id:
        sql += " AND c.doc_id = ?"
        params.append(doc_id)
    ranked: list[tuple[int, sqlite3.Row]] = []
    for row in db.execute(sql, params):
        hay = str(row["text"] or "").lower()
        score = sum(1 for word in words if word in hay)
        if score:
            ranked.append((score, row))
    ranked.sort(key=lambda item: (-item[0], int(item[1]["idx"])))
    return [row for _score, row in ranked[:limit]]


def _hit(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "doc_id": row["doc_id"],
        "name": row["name"],
        "index": int(row["idx"]),
        "text": row["text"],
    }
