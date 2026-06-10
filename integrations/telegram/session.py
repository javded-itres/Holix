"""Per-chat Telegram session state."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.presenters.live_buffer import LiveTranscriptBuffer

if TYPE_CHECKING:
    from integrations.telegram.file_handler import SavedTelegramFile
from cli.tui.shared.transcript_store import TranscriptStore


@dataclass
class ChatSession:
    chat_id: int
    user_id: int
    profile: str
    conversation_id: str
    execution_modes: list[str] = field(
        default_factory=lambda: ["react", "plan_and_execute", "hybrid", "auto"]
    )
    execution_mode_index: int = 0
    streaming_enabled: bool = False
    session_display_name: str = "main"
    known_sessions: list[dict] = field(default_factory=list)
    session_names: dict[str, str] = field(default_factory=dict)
    _memory_search_query: str = ""
    _memory_search_results: list[dict] = field(default_factory=list)
    _recent_tool_results: list[dict] = field(default_factory=list)
    _transcript_store: TranscriptStore = field(default_factory=TranscriptStore)
    live_message_id: int | None = None
    live_buffer: LiveTranscriptBuffer | None = None
    run_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    pending_plan_review_id: str | None = None
    pending_confirmation_message_id: int | None = None
    pending_plan_message_ids: list[int] = field(default_factory=list)
    agent: Any = None
    profile_manual_override: bool = False
    ui_profiles: list[str] = field(default_factory=list)
    ui_sessions: list[dict] = field(default_factory=list)
    ui_sessions_page: int = 0
    ui_model_presets: list = field(default_factory=list)
    ui_providers: list = field(default_factory=list)
    ui_providers_page: int = 0
    ui_models_provider_idx: int | None = None
    ui_models_page: int = 0
    ui_skills: list[str] = field(default_factory=list)
    ui_skills_page: int = 0
    active_model_slot: str = "main"
    active_model_label: str = ""
    _model_synced_for: str | None = None
    pending_files: list[SavedTelegramFile] = field(default_factory=list)

    @property
    def execution_mode(self) -> str:
        return self.execution_modes[self.execution_mode_index]

    def bump_live_buffer(self) -> LiveTranscriptBuffer:
        buf = LiveTranscriptBuffer(
            profile=self.profile,
            mode=self.execution_mode,
            session_label=self.session_display_name,
        )
        self.live_buffer = buf
        return buf