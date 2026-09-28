"""Host extension: `holix media` CLI."""

from __future__ import annotations

import asyncio
from typing import Any

from holix_media.config import load_media_config
from holix_media.providers import generate_image, generate_video
from holix_media.refs import load_references
from holix_media.store import save_blob


class MediaHostExtension:
    name = "media"
    version = "0.1.5"
    requires_holix = ">=1.1.0"
    description = "Generate images and video; send to Telegram/MAX chats"
    capabilities = frozenset({"cli"})
    permissions = frozenset({"network", "filesystem", "tools"})

    def register_cli(self, app: Any) -> None:
        try:
            import typer
        except ImportError:
            return
        cli = typer.Typer(help="Media generation (images / video)")

        @cli.command("providers")
        def providers() -> None:
            from core.extensions.settings import load_extension_settings

            try:
                from core.env_loader import active_profile_name

                profile = active_profile_name() or "default"
                settings = load_extension_settings(profile, "media")
            except Exception:
                settings = {}
            cfg = load_media_config(settings)
            typer.echo(f"enabled={cfg.enabled} auto_send={cfg.auto_send}")
            typer.echo("images:")
            for p in cfg.image_providers:
                typer.echo(f"  - {p.id}: {p.type} model={p.model or '-'} url={p.base_url}")
            typer.echo("videos:")
            for p in cfg.video_providers:
                typer.echo(f"  - {p.id}: {p.type} model={p.model or '-'} url={p.base_url}")
            if not cfg.image_providers and not cfg.video_providers:
                typer.echo("  (none — edit extension settings or HOLIX_MEDIA_* env)")

        @cli.command("imagine")
        def imagine(
            prompt: str = typer.Argument(..., help="Image prompt"),
            provider: str = typer.Option("", "--provider", "-p"),
            ref: list[str] | None = typer.Option(
                None,
                "--ref",
                help="Reference image path (repeatable)",
            ),
        ) -> None:
            cfg = _cfg()
            spec = cfg.provider("image", provider or None)
            if spec is None:
                raise typer.BadParameter("No image provider configured")
            refs = load_references(ref)
            blob = asyncio.run(generate_image(spec, prompt, references=refs))
            path = save_blob(blob, agent=None, subdir=cfg.output_subdir)
            typer.echo(str(path))

        @cli.command("video")
        def video_cmd(
            prompt: str = typer.Argument(..., help="Video prompt"),
            provider: str = typer.Option("", "--provider", "-p"),
            ref: list[str] | None = typer.Option(
                None,
                "--ref",
                help="Still photo to animate (repeatable)",
            ),
        ) -> None:
            cfg = _cfg()
            spec = cfg.provider("video", provider or None)
            if spec is None:
                raise typer.BadParameter("No video provider configured")
            refs = load_references(ref)
            blob = asyncio.run(generate_video(spec, prompt, references=refs))
            path = save_blob(blob, agent=None, subdir=cfg.output_subdir)
            typer.echo(str(path))

        app.add_typer(cli, name="media")

    def mount_gateway(self, app: Any) -> None:
        return None

    def on_startup(self, ctx: Any) -> None:
        return None

    def on_shutdown(self) -> None:
        return None


def _cfg():
    try:
        from core.env_loader import active_profile_name
        from core.extensions.settings import load_extension_settings

        return load_media_config(
            load_extension_settings(active_profile_name() or "default", "media")
        )
    except Exception:
        return load_media_config({})


def get_extension() -> MediaHostExtension:
    return MediaHostExtension()
