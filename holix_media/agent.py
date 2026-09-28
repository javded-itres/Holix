"""Agent extension entry: tools, slash commands, prompt, skill."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from holix_media.config import load_media_config
from holix_media.tools import all_tools

logger = logging.getLogger(__name__)

try:
    from core.extensions.agent_base import AgentExtensionBase
    from holix_sdk.agent import SlashCommandSpec
except ImportError:  # pragma: no cover
    try:
        from holix_sdk.agent import AgentExtensionBase, SlashCommandSpec  # type: ignore[no-redef]
    except ImportError:
        from dataclasses import dataclass

        @dataclass(frozen=True, slots=True)
        class SlashCommandSpec:  # type: ignore[no-redef]
            command: str
            description: str

        class AgentExtensionBase:  # type: ignore[no-redef]
            name = ""
            version = "0.0.0"
            requires_holix = ">=0.1.0"
            permissions: frozenset[str] = frozenset()
            settings: dict[str, Any] = {}

            def register_tools(self, registry: Any, agent: Any) -> None:
                return None

            def register_slash_commands(self, commands: list) -> None:
                return None

            def augment_system_prompt(self, profile: str) -> str | None:
                return None


_SKILL_SRC = Path(__file__).resolve().parent / "skill" / "media-gen"


class MediaAgentExtension(AgentExtensionBase):
    name = "media"
    version = "0.1.5"
    requires_holix = ">=1.1.0"
    permissions = frozenset({"tools", "network", "filesystem"})

    def __init__(self) -> None:
        self.settings: dict[str, Any] = {}

    def default_settings(self) -> dict[str, Any]:
        # No providers until the user writes extension settings or HOLIX_MEDIA_* env.
        # An empty dict also skips writing a default media.yaml on first start.
        return {}

    def on_settings_loaded(self, settings: dict[str, Any]) -> None:
        self.settings = dict(settings or {})

    def _cfg(self):
        return load_media_config(self.settings)

    def register_tools(self, registry: Any, agent: Any) -> None:
        cfg = self._cfg()
        if not cfg.ready:
            logger.info("holix-media idle: no configured image or video provider")
            return
        for tool in all_tools(config=cfg, agent=agent):
            registry.register(tool)
        if self.settings.get("install_skill", True):
            self._install_skill(agent)

    def register_slash_commands(self, commands: list[SlashCommandSpec]) -> None:
        if not self._cfg().ready:
            return
        commands.append(
            SlashCommandSpec(command="/imagine", description="Generate an image from a prompt")
        )
        commands.append(
            SlashCommandSpec(command="/video", description="Generate a short video from a prompt")
        )

    def augment_system_prompt(self, profile: str) -> str | None:
        cfg = self._cfg()
        if not cfg.ready:
            return None
        imgs = ", ".join(f"{p.id} ({p.model or p.type})" for p in cfg.image_providers) or "none"
        vids = ", ".join(f"{p.id} ({p.model or p.type})" for p in cfg.video_providers) or "none"
        return (
            "## Media generation\n"
            "Tools `generate_image` and `generate_video` create files in workspace `media/`.\n"
            f"Image providers: {imgs}. Video providers: {vids}.\n"
            "Workflow: the user may **first send photos**, then say what to do "
            "(edit, combine, restyle, «оживи», make a video). Pass those disk paths "
            "in `references` (from «Вложения» / previous turns). Do not ask to re-upload.\n"
            "In TUI, put the markdown Open link from the tool result in the reply "
            "(`[Open image](file://…)`). In Telegram or MAX the file is sent when "
            "auto_send is on; otherwise call `send_chat_files`. "
            "Do not paste base64. Do not claim the user received the file unless "
            "send_chat_files returned Sent N file(s).\n"
            "Hard rule: never assemble video yourself (no ffmpeg, moviepy, "
            "frame-stitching, or encoding scripts). Return only the file "
            "`generate_video` saved. If that tool fails, report the error."
        )

    def _install_skill(self, agent: Any) -> None:
        if not _SKILL_SRC.is_dir():
            return
        try:
            cfg = getattr(agent, "config", None)
            skills_dir = getattr(cfg, "skills_dir", None) if cfg is not None else None
            dest_root = Path(str(skills_dir)) if skills_dir else None
            if dest_root is None:
                from core.env_loader import active_profile_name, profile_dir_path

                dest_root = profile_dir_path(active_profile_name() or "default") / "data" / "skills"
            dest = dest_root / "media-gen"
            dest.mkdir(parents=True, exist_ok=True)
            for src in _SKILL_SRC.rglob("*"):
                if src.is_file():
                    rel = src.relative_to(_SKILL_SRC)
                    target = dest / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, target)
        except Exception:
            logger.exception("holix-media skill install failed")


def get_agent_extension() -> MediaAgentExtension:
    return MediaAgentExtension()
