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
            "Start image generation in the background and return immediately. "
            "No timeout: a 502 from the provider is retried until the image is saved. "
            "Do not wait, poll, switch models, or tell the user it failed. "
            "You are woken with the file when it is ready. "
            "Do not call send_chat_files in TUI. If that tool errors, do not generate again. "
            "Before the first call, use describe_media_model and set only parameters it lists. "
            "When editing an existing image, pass that file in references and only the new "
            "change in prompt. The tool appends that change to the saved prompt and keeps the seed. "
            "Do not rewrite the previous scene. Change size only if the user asks."
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
                "seed": {
                    "type": "integer",
                    "description": (
                        "Keep the seed from describe_media_model or the reference file "
                        "when editing. Omit only for a brand-new picture."
                    ),
                },
                "references": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Paths to reference photos or the previous generated image. "
                        "Required when the user wants to change an existing picture."
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
        seed: int | None = None,
        send: bool | None = None,
        references: list[str] | None = None,
        **_: Any,
    ) -> str:
        text = (prompt or "").strip()
        if not text:
            return "Error: prompt is required"
        cfg = _live_config(self._config)
        if not cfg.enabled:
            return "Error: media extension is disabled"
        from holix_media.select import choose_provider

        spec, problem = choose_provider(
            cfg.image_providers,
            prompt=text,
            has_references=bool(references),
            provider_id=provider,
        )
        if problem:
            return problem
        if spec is None:
            return (
                "Error: no image provider configured. "
                "Add image_providers in extension settings or HOLIX_MEDIA_IMAGE_* env."
            )
        try:
            refs = load_references(references, agent=self._agent)
        except ReferenceError as exc:
            return f"Error: {exc}"
        from holix_media.params import choose_seed, compose_edit_prompt, previous_generation_field

        text = compose_edit_prompt(text, refs)
        chosen_seed = choose_seed(seed, refs)
        chosen_size = size or previous_generation_field(refs, "size") or spec.size or "1024x1024"
        auto = cfg.auto_send if send is None else bool(send)
        agent = self._agent
        subdir = cfg.output_subdir

        async def _run() -> str:
            blob = await generate_image(
                spec,
                text,
                size=chosen_size,
                seed=chosen_seed,
                references=refs,
            )
            path = save_blob(blob, agent=agent, subdir=subdir)
            _remember_generation(
                path,
                kind="image",
                spec=spec,
                prompt=text,
                seed=chosen_seed,
                size=blob.size or chosen_size,
                references=refs,
            )
            extra = await _maybe_send(str(path), "", auto_send=auto)
            return _format_saved("image", path, spec, blob, extra)

        return await _start_media_task("image", text, _run)


class GenerateVideoTool(BaseTool):
    def __init__(self, *, config: MediaConfig, agent: Any | None = None) -> None:
        super().__init__()
        self._config = config
        self._agent = agent
        self.name = "generate_video"
        self.description = (
            "Start video generation in the background and return immediately. "
            "No timeout: Hailuo and similar models can take many minutes, and "
            "HTTP 502/503/504 are retried until the clip is saved. "
            "Do not wait, poll, switch models, or tell the user the backend is down. "
            "You are woken with the file when it is ready. "
            "Do not stitch images, install ffmpeg, or encode video in the shell."
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
                "seed": {
                    "type": "integer",
                    "description": "Keep the previous seed when revising the same clip.",
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
        seed: int | None = None,
        send: bool | None = None,
        references: list[str] | None = None,
        **_: Any,
    ) -> str:
        text = (prompt or "").strip()
        if not text:
            return "Error: prompt is required"
        cfg = _live_config(self._config)
        if not cfg.enabled:
            return "Error: media extension is disabled"
        from holix_media.select import choose_provider

        spec, problem = choose_provider(
            cfg.video_providers,
            prompt=text,
            has_references=bool(references),
            provider_id=provider,
        )
        if problem:
            return problem
        if spec is None:
            return (
                "Error: no video provider configured. "
                "Add video_providers in extension settings or HOLIX_MEDIA_VIDEO_* env."
            )
        try:
            refs = load_references(references, agent=self._agent)
        except ReferenceError as exc:
            return f"Error: {exc}"
        from holix_media.params import choose_seed, compose_edit_prompt

        text = compose_edit_prompt(text, refs)
        chosen_seed = choose_seed(seed, refs)
        auto = cfg.auto_send if send is None else bool(send)
        agent = self._agent
        subdir = cfg.output_subdir

        async def _run() -> str:
            blob = await generate_video(
                spec,
                text,
                duration_s=duration_s,
                seed=chosen_seed,
                references=refs,
            )
            path = save_blob(blob, agent=agent, subdir=subdir)
            _remember_generation(
                path,
                kind="video",
                spec=spec,
                prompt=text,
                seed=chosen_seed,
                size="",
                references=refs,
            )
            extra = await _maybe_send(str(path), "", auto_send=auto)
            return _format_saved("video", path, spec, blob, extra)

        return await _start_media_task("video", text, _run)


async def _start_media_task(kind: str, prompt: str, runner) -> str:
    try:
        from core.runtime.agent_tasks import get_agent_task_registry
        from core.tools.execution_context import get_conversation_id, get_profile_name
    except ImportError:
        try:
            return await runner()
        except Exception as exc:
            return f"Error: {exc}"
    profile = get_profile_name() or "default"
    conversation_id = get_conversation_id() or "default"
    duplicate = _existing_same_prompt(prompt, profile, conversation_id)
    if duplicate:
        return duplicate
    from integrations.messenger.generation_details import media_task_label

    description = media_task_label(kind, profile)
    launched = await get_agent_task_registry().launch_async(
        description=description,
        command=prompt,
        profile=profile,
        conversation_id=conversation_id,
        runner=runner,
    )
    if isinstance(launched, str):
        return launched
    return (
        f"Background task started: id={launched.task_id} — {launched.description}. "
        "Когда изображение или видео будет готово, оно придёт в чат."
    )


def _existing_same_prompt(prompt: str, profile: str, conversation_id: str) -> str | None:
    """Block a second generation of the same prompt after a TUI send failure."""
    from core.runtime.agent_tasks import get_agent_task_registry

    needle = (prompt or "").strip()
    if not needle:
        return None
    for task in get_agent_task_registry().list_for(
        profile=profile, conversation_id=conversation_id
    ):
        if (task.command or "").strip() != needle:
            continue
        if task.status == "failed":
            continue
        if not task.is_running() and task.status != "completed":
            continue
        saved = (task.output or "").strip()
        tail = f"\n{saved}" if saved else ""
        return (
            f"Already generated this prompt: id={task.task_id} status={task.status}. "
            "Do not start another image or video. "
            "send_chat_files failing in TUI does not mean generation failed. "
            "Tell the user the existing file path. The Open link is in the transcript." + tail
        )
    return None


def _live_config(fallback: MediaConfig) -> MediaConfig:
    """Re-read extension settings so a Studio save applies without restarting the agent.

    If the profile has no media.yaml yet, keep the config the tool was registered with.
    """
    try:
        from core.tools.execution_context import get_profile_name

        from holix_media.profile_files import (
            active_profile_name,
            load_media_settings,
            media_settings_path,
        )

        profile = get_profile_name() or active_profile_name()
        path = media_settings_path(profile)
        if path is None or not path.is_file():
            return fallback
        return load_media_config(load_media_settings(profile))
    except Exception:
        return fallback


def _format_saved(kind: str, path: Path, spec: Any, blob: Any, extra: str) -> str:
    if "Sent " in (extra or "") and "Error" not in (extra or ""):
        return (
            f"Saved {kind}: {path}\n"
            "Delivered to the chat. Do not send another message about the file."
        )
    uri = Path(path).resolve().as_uri()
    label = "Open image" if kind == "image" else "Open video"
    lines = [
        f"Saved {kind}: {path}",
        f"[{label}]({uri})",
        f"Open: {uri}",
        f"provider={spec.id} type={spec.type} model={spec.model} bytes={len(blob.data)}",
    ]
    if getattr(blob, "seed", None) is not None:
        lines.append(f"seed={blob.seed}")
    if getattr(blob, "size", None):
        lines.append(f"size={blob.size}")
    if extra:
        lines.append(extra.strip())
    lines.append(
        "In TUI the link is already in the transcript. Do not call send_chat_files "
        "and do not generate this prompt again if sending fails. "
        "In Telegram/MAX the file is sent when auto_send is on."
    )
    return "\n".join(lines)


class DescribeMediaModelTool(BaseTool):
    def __init__(self, *, config: MediaConfig, agent: Any | None = None) -> None:
        super().__init__()
        self._config = config
        self._agent = agent
        self.name = "describe_media_model"
        self.description = (
            "Read the configured image or video models and what each one is for. "
            "Call this before generate_image or generate_video. "
            "Leave provider empty: the tool picks the text-only model or the "
            "reference model from these notes and from the prompt. "
            "When the user edits an existing result, pass its path in references."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["image", "video"],
                    "description": "image or video",
                },
            },
            "required": ["kind"],
        }

    async def execute(self, kind: str = "image", **_: Any) -> str:
        from holix_media.http import HttpxTransport
        from holix_media.params import format_model_card, read_last_job
        from holix_media.providers import _auth_headers
        from holix_media.store import workspace_root

        wanted = "video" if str(kind).strip().lower() == "video" else "image"
        cfg = _live_config(self._config)
        pool = cfg.video_providers if wanted == "video" else cfg.image_providers
        spec = pool[0] if pool else None
        if spec is None:
            return f"Error: no {wanted} provider configured"
        from holix_media.select import format_provider_menu

        menu = format_provider_menu(pool)
        record: dict[str, Any] = {}
        base = spec.resolved_base_url or spec.base_url
        if base and spec.api_key:
            try:
                data = await HttpxTransport().get_json(
                    base.rstrip("/") + "/models",
                    headers=_auth_headers(spec),
                    timeout=30,
                )
                for item in data.get("data") or []:
                    if isinstance(item, dict) and item.get("id") == spec.model:
                        record = item
                        break
            except Exception as exc:
                record = {"error": str(exc)[:200]}
        directory = workspace_root(self._agent) / (cfg.output_subdir or "media")
        card = format_model_card(
            spec,
            kind=wanted,
            record=record,
            last_job=read_last_job(directory, wanted),
        )
        return f"Configured {wanted} models:\n{menu}\n\n{card}"


def _remember_generation(
    path: Path,
    *,
    kind: str,
    spec: Any,
    prompt: str,
    seed: int,
    size: str,
    references: list[Any],
) -> None:
    from holix_media.params import write_generation_meta, write_last_job

    meta = {
        "kind": kind,
        "path": str(path),
        "provider": getattr(spec, "id", ""),
        "model": getattr(spec, "model", ""),
        "prompt": prompt,
        "seed": seed,
        "size": size,
        "references": [str(getattr(ref, "path", ref)) for ref in references],
    }
    write_generation_meta(path, meta)
    write_last_job(path.parent, kind, meta)


def all_tools(*, config: MediaConfig | None = None, agent: Any | None = None) -> list[Any]:
    cfg = config or load_media_config()
    return [
        DescribeMediaModelTool(config=cfg, agent=agent),
        GenerateImageTool(config=cfg, agent=agent),
        GenerateVideoTool(config=cfg, agent=agent),
    ]
