"""Search and read fragments of a long document without loading the whole file."""

from __future__ import annotations

from typing import Any

from core.documents.index import index_path, read_document_chunks, search_documents
from core.tools.base import BaseTool
from core.tools.execution_context import get_conversation_id, get_profile_name
from core.tools.result import tool_err, tool_ok


def _profile() -> str:
    return (get_profile_name() or "default").strip() or "default"


def _conversation() -> str:
    return (get_conversation_id() or "default").strip() or "default"


class SearchDocumentTool(BaseTool):
    """Find fragments inside an indexed document."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "search_document"
        self.description = (
            "Search fragments of a long document in the current session "
            "(pdf, docx, md, txt, and other text). Documents from another "
            "session are not visible. Pass doc_id from the attachment card, "
            "or path to index that file into this session first. Returns a few "
            "matching fragments, not the whole document."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "additionalProperties": False,
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "description": "What to find in the document."},
                "doc_id": {
                    "type": "string",
                    "description": "Id from the attachment card. Empty searches all indexed docs.",
                },
                "path": {
                    "type": "string",
                    "description": "File path. Indexed first when it is not already in the store.",
                },
                "limit": {"type": "integer", "description": "How many fragments to return, max 8."},
            },
        }

    async def execute(
        self,
        query: str = "",
        doc_id: str = "",
        path: str = "",
        limit: int = 5,
        **_: Any,
    ) -> str:
        text = (query or "").strip()
        if not text:
            return tool_err("bad_query", "query is required")
        profile = _profile()
        conversation_id = _conversation()
        if path.strip():
            indexed = index_path(profile, path.strip(), conversation_id=conversation_id)
            if indexed is None:
                return tool_err("empty", "No text extracted from that path.", path=path)
            doc_id = doc_id or indexed.doc_id
        hits = search_documents(
            profile,
            text,
            conversation_id=conversation_id,
            doc_id=doc_id,
            limit=limit,
        )
        return tool_ok(query=text, doc_id=doc_id, count=len(hits), fragments=hits)


class ReadDocumentTool(BaseTool):
    """Read a few consecutive fragments of an indexed document."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "read_document"
        self.description = (
            "Read a few consecutive fragments of a document indexed in this "
            "session. start is the fragment index (0 is the beginning). "
            "Another session's doc_id is not readable here. "
            "Do not request the whole file; search_document first, then read around a hit."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "doc_id": {"type": "string", "description": "Id from the attachment card."},
                "path": {"type": "string", "description": "File path if doc_id is unknown."},
                "start": {"type": "integer", "description": "First fragment index. Default 0."},
                "count": {"type": "integer", "description": "How many fragments, max 6."},
            },
        }

    async def execute(
        self,
        doc_id: str = "",
        path: str = "",
        start: int = 0,
        count: int = 3,
        **_: Any,
    ) -> str:
        profile = _profile()
        conversation_id = _conversation()
        key = (doc_id or "").strip()
        file_path = (path or "").strip()
        if not key and file_path:
            indexed = index_path(profile, file_path, conversation_id=conversation_id)
            if indexed is None:
                return tool_err("empty", "No text extracted from that path.", path=file_path)
            key = indexed.doc_id
        if not key:
            return tool_err("bad_target", "doc_id or path is required")
        chunks = read_document_chunks(
            profile,
            conversation_id=conversation_id,
            doc_id=key,
            start=start,
            count=count,
        )
        if chunks is None:
            return tool_err(
                "not_found",
                "No document with that id in this session.",
                doc_id=key,
            )
        return tool_ok(doc_id=key, start=start, count=len(chunks), fragments=chunks)
