"""Agent tools: generate_image / generate_video."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from holix_media.config import MediaConfig, load_media_config
from holix_media.providers import generate_image, generate_video
from holix_media.refs import ReferenceError, load_references
from holix_media.store import save_blob

try:
    from core.tools.base import BaseTool
except ImportError:  # pragma: no cover

    class BaseTool:  # type: ignore[no-redef]
        def __init__(self) -> None:
            self.name = ""
            self.description = ""
            self.parameters: dict[str, Any] = {}
            self.risk_level = "medium"

        async def execute(self, **kwargs: Any) -> str:
            raise NotImplementedError


async def _maybe_send(path: str, caption: str, *, auto_send: bool) -> str:
    if not auto_send:
        return ""
    try:
        from core.tools.execution_context import get_chat_delivery_bridge
        from core.tools.send_chat_files import SendChatFilesTool
    except ImportError:
        return ""
    if get_chat_delivery_bridge() is None:
        return (
            "\nNot in Telegram/MAX chat — file is on disk. "
            "In messenger the agent should call send_chat_files with this path."
        )
    tool = SendChatFilesTool()
    result = await tool.execute(paths=[path], caption=caption)
    return f"\n{result}"


class GenerateImageTool(BaseTool):
    def __init__(self, *, config: MediaConfig, agent: Any | None = None) -> None:
        super().__init__()
        self._config = config
        self._agent = agent
        self.name = "generate_image"
        self.description = (
            "Generate or edit an image. Pass a text prompt. If the user uploaded "
            "photos (Telegram/MAX attachments already saved on disk, or files in "
            "workspace), pass their paths in `references` so the model uses them "
            "as source: restyle, combine several photos, or follow the prompt. "
            "Saves into workspace media/. Telegram/MAX: auto_send or send_chat_files."
        )
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Image description (what to generate)",
                },
                "provider": {
                    "type": "string",
                    "description": "Optional provider id from image_providers",
                },
                "size": {
                    "type": "string",
                    "description": "Optional size, e.g. 1024x1024",
                },
                "send": {
                    "type": "boolean",
                    "description": "Send to Telegram/MAX if available (default: auto_send setting)",
                },
                "references": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Paths to reference photos (user uploads). "
                        "Use when the user first sent images, then said what to do."
                    ),
                },
            },
            "required": ["prompt"],
        }

    async def execute(
        self,
        prompt: str = "",
        provider: str = "",
        size: str = "",
        send: bool | None = None,
        references: list[str] | None = None,
        **_: Any,
    ) -> str:
        text = (prompt or "").strip()
        if not text:
            return "Error: prompt is required"
        cfg = self._config
        if not cfg.enabled:
            return "Error: media extension is disabled"
        spec = cfg.provider("image", provider or None)
        if spec is None:
            return (
                "Error: no image provider configured. "
                "Add image_providers in extension settings or HOLIX_MEDIA_IMAGE_* env."
            )
        try:
            refs = load_references(references, agent=self._agent)
        except ReferenceError as exc:
            return f"Error: {exc}"
        try:
            blob = await generate_image(spec, text, size=size or None, references=refs)
        except Exception as exc:
            return f"Error: {exc}"
        path = save_blob(blob, agent=self._agent, subdir=cfg.output_subdir)
        auto = cfg.auto_send if send is None else bool(send)
        extra = await _maybe_send(str(path), text[:200], auto_send=auto)
        return _format_saved("image", path, spec, blob, extra)


class GenerateVideoTool(BaseTool):
    def __init__(self, *, config: MediaConfig, agent: Any | None = None) -> None:
        super().__init__()
        self._config = config
        self._agent = agent
        self.name = "generate_video"
        self.description = (
            "Ask the configured video model for a short clip (optionally from "
            "user photos via `references`). Return that model output only. "
            "Do not stitch images, install ffmpeg, or encode video in the shell. "
            "Saves mp4 in media/. Telegram/MAX: auto_send or send_chat_files."
        )
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Video description",
                },
                "provider": {
                    "type": "string",
                    "description": "Optional provider id from video_providers",
                },
                "duration_s": {
                    "type": "integer",
                    "description": "Optional duration in seconds",
                },
                "send": {
                    "type": "boolean",
                    "description": "Send to Telegram/MAX if available",
                },
                "references": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Paths to still photos to animate / use as the first frame "
                        "(user uploads already on disk)."
                    ),
                },
            },
            "required": ["prompt"],
        }

    async def execute(
        self,
        prompt: str = "",
        provider: str = "",
        duration_s: int | None = None,
        send: bool | None = None,
        references: list[str] | None = None,
        **_: Any,
    ) -> str:
        text = (prompt or "").strip()
        if not text:
            return "Error: prompt is required"
        cfg = self._config
        if not cfg.enabled:
            return "Error: media extension is disabled"
        spec = cfg.provider("video", provider or None)
        if spec is None:
            return (
                "Error: no video provider configured. "
                "Add video_providers in extension settings or HOLIX_MEDIA_VIDEO_* env."
            )
        try:
            refs = load_references(references, agent=self._agent)
        except ReferenceError as exc:
            return f"Error: {exc}"
        try:
            blob = await generate_video(spec, text, duration_s=duration_s, references=refs)
        except Exception as exc:
            return f"Error: {exc}"
        path = save_blob(blob, agent=self._agent, subdir=cfg.output_subdir)
        auto = cfg.auto_send if send is None else bool(send)
        extra = await _maybe_send(str(path), text[:200], auto_send=auto)
        return _format_saved("video", path, spec, blob, extra)


def _format_saved(kind: str, path: Path, spec: Any, blob: Any, extra: str) -> str:
    uri = Path(path).resolve().as_uri()
    label = "Open image" if kind == "image" else "Open video"
    lines = [
        f"Saved {kind}: {path}",
        f"[{label}]({uri})",
        f"Open: {uri}",
        f"provider={spec.id} type={spec.type} model={spec.model} bytes={len(blob.data)}",
    ]
    remote = getattr(blob, "source_url", None)
    if remote:
        lines.append(f"URL: {remote}")
    if extra:
        lines.append(extra.strip())
    lines.append(
        f"In TUI the {kind} link is clickable. In Telegram/MAX the file is sent "
        "when auto_send is on; otherwise call send_chat_files with this path. "
        f"Include [{label}]({uri}) in the user-visible reply."
    )
    return "\n".join(lines)


def all_tools(*, config: MediaConfig | None = None, agent: Any | None = None) -> list[Any]:
    cfg = config or load_media_config()
    return [
        GenerateImageTool(config=cfg, agent=agent),
        GenerateVideoTool(config=cfg, agent=agent),
    ]
