"""Cosine similarity of caller-supplied texts. Not profile memory search."""

from __future__ import annotations

import json
from typing import Any

from core.tools.base import BaseTool


class TextSimilarityTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "text_similarity"
        self.description = (
            "Cosine similarity of texts you pass in. "
            "Compare a pair or up to eight passages. "
            "Not profile memory search and not a classifier."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "text_a": {"type": "string", "description": "First text, with text_b."},
                "text_b": {"type": "string", "description": "Second text, with text_a."},
                "texts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Two to eight texts. Returns a cosine matrix.",
                },
            },
        }

    async def execute(
        self,
        text_a: str | None = None,
        text_b: str | None = None,
        texts: list[str] | None = None,
        **_: Any,
    ) -> str:
        try:
            from core.decision.config import resolve_embeddings
            from core.decision.embeddings import cosine, embed_texts
            from core.profile.service import ProfileManager
            from core.tools.execution_context import get_profile_name

            if texts:
                rows = [str(item) for item in texts]
            elif text_a is not None and text_b is not None:
                rows = [str(text_a), str(text_b)]
            else:
                return "Embeddings error: pass text_a and text_b, or texts."
            raw = None
            name = str(get_profile_name() or "").strip()
            if name:
                raw = getattr(ProfileManager().load_profile(name), "embeddings", None)
            embedded = await embed_texts(resolve_embeddings(raw), rows)
            if isinstance(embedded, str):
                return embedded
            if len(embedded) == 2 and not texts:
                return json.dumps({"cosine": round(cosine(embedded[0], embedded[1]), 4)})
            matrix = [[round(cosine(left, right), 4) for right in embedded] for left in embedded]
            return json.dumps({"vectors": len(embedded), "cosine": matrix})
        except Exception:
            return "Embeddings error: request failed."
