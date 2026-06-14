"""Send generated files back to the user in the active chat (Telegram or MAX)."""

from __future__ import annotations

from typing import Any

from core.tools.base import BaseTool
from core.tools.execution_context import get_chat_delivery_bridge


class SendChatFilesTool(BaseTool):
    """Deliver local files to the user in Telegram or MAX chat."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "send_chat_files"
        self.description = (
            "Send files to the user in chat (Telegram or MAX). Use after creating or "
            "generating documents, images, or videos. Pass one path or 2–10 paths. "
            "On Telegram, compatible files are sent as albums; on MAX, each file is "
            "sent as a separate message. Optional caption applies to the first item."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Absolute or relative paths to files to send",
                    "minItems": 1,
                    "maxItems": 10,
                },
                "caption": {
                    "type": "string",
                    "description": "Optional caption for the file or album",
                },
            },
            "required": ["paths"],
        }

    async def execute(
        self,
        paths: list[str],
        caption: str = "",
        **_: Any,
    ) -> str:
        bridge = get_chat_delivery_bridge()
        if bridge is None:
            return (
                "Error: send_chat_files is only available in Telegram or MAX chat. "
                "Tell the user the file paths instead."
            )

        cleaned = [str(p).strip() for p in (paths or []) if str(p).strip()]
        if not cleaned:
            return "Error: paths must contain at least one file"

        return await bridge.send_files(cleaned, caption=(caption or "").strip())