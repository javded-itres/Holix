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


def _prompt_language(profile: str) -> str:
    """Name of the profile default language, for the generation prompt."""
    loc = "ru"
    try:
        from integrations.messenger.locale import messenger_locale

        if profile:
            loc = messenger_locale(profile)
    except Exception:
        loc = "ru"
    if loc.lower().startswith("en"):
        return "English"
    return "Russian"


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

    def _active_cfg(self):
        """Providers the agent can call. The API key is read again at execute time."""
        cfg = self._cfg()
        if not cfg.enabled:
            return None
        providers = (*cfg.image_providers, *cfg.video_providers)
        if not any((item.model or item.base_url) for item in providers):
            return None
        return cfg

    def register_tools(self, registry: Any, agent: Any) -> None:
        cfg = self._active_cfg()
        if cfg is None:
            logger.info("holix-media idle: no configured image or video provider")
            return
        for tool in all_tools(config=cfg, agent=agent):
            registry.register(tool)
        if self.settings.get("install_skill", True):
            self._install_skill(agent)

    def register_slash_commands(self, commands: list[SlashCommandSpec]) -> None:
        if self._active_cfg() is None:
            return
        commands.append(
            SlashCommandSpec(command="/imagine", description="Generate an image from a prompt")
        )
        commands.append(
            SlashCommandSpec(command="/video", description="Generate a short video from a prompt")
        )

    def augment_system_prompt(self, profile: str) -> str | None:
        cfg = self._active_cfg()
        if cfg is None:
            return None
        from holix_media.select import format_provider_menu

        imgs = format_provider_menu(cfg.image_providers)
        vids = format_provider_menu(cfg.video_providers)
        try:
            from core.tools.lazy_schema import messenger_delivery_available

            messenger = messenger_delivery_available()
        except Exception:
            messenger = False
        language = _prompt_language(profile)
        return (
            "## Media generation\n"
            "Tools `generate_image` and `generate_video` start a background task and "
            "return immediately. There is no timeout. HTTP 502/503/504 is retried "
            "inside that task. Do not poll, do not switch models, and do not tell "
            "the user the backend is down. Say that generation is running; the file "
            "arrives in the chat on its own. Do not send another message after it. "
            "Files land in workspace `media/`.\n"
            "Image models:\n"
            f"{imgs}\n"
            "Video models:\n"
            f"{vids}\n"
            "Leave `provider` empty. The tool reads these notes and the prompt. "
            "A plain «generate an image/video» uses the text-only model. "
            "If the user attached a file or asks to change, add, or interact with an "
            "existing picture or clip, pass that file in `references`; the tool then "
            "uses the model marked as accepting a reference. Do not pick a text-only "
            "model for that.\n"
            "Before generating, call `describe_media_model` and use only parameters it lists. "
            "Do not paste `Configured image models:` or `Configured video models:` into the "
            "user-visible reply. Telegram and MAX add that list only when the user turned "
            "on extended mode in the menu.\n"
            f"Write the generation prompt predominantly in {language}. "
            "Keep a name or a word the user wrote in another language as they wrote it.\n"
            "To change an existing image, pass that file in `references` and put only the new "
            "change in `prompt`. The tool appends it to the saved prompt and keeps the seed. "
            "Do not rewrite the previous scene. Change `size` only when the user asks.\n"
            "Workflow: the user may **first send photos**, then say what to do "
            "(edit, combine, restyle, «оживи», make a video). Pass those disk paths "
            "in `references` (from «Вложения» / previous turns). Do not ask to re-upload.\n"
            + (
                "In Telegram or MAX the file is sent when auto_send is on; otherwise call "
                "`send_chat_files`. Do not claim the user received the file unless that "
                "tool returned `Sent N file(s)`.\n"
                if messenger
                else "This run is not Telegram or MAX. Do not try to send the file to a "
                "messenger. The Open link is written into the TUI transcript when the "
                "file is saved.\n"
            )
            + "Hard rule: never assemble video yourself (no ffmpeg, moviepy, "
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
