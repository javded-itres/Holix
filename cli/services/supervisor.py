"""Start API gateway together with all configured companion services."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from typing import NoReturn

from core.platform_compat import popen_background

from cli.services.docs_site import docs_url, resolve_web_docs_dir
from cli.services.gateway_state import update_docs_info, update_telegram_pid
from cli.utils.ports import resolve_listen_port
from cli.utils.rich_console import print_info, print_success, print_warning
from integrations.telegram.config import load_telegram_settings, telegram_aiogram_available


def telegram_enabled(profile: str = "default") -> bool:
    """True when a Telegram bot token is configured."""
    return bool(load_telegram_settings(profile).bot_token.strip())


def telegram_should_start(profile: str = "default") -> bool:
    """True when token is set and optional aiogram dependency is installed."""
    return telegram_enabled(profile) and telegram_aiogram_available()


def docs_should_start() -> bool:
    """True when web-docs/ is available in this install."""
    try:
        resolve_web_docs_dir()
        return True
    except FileNotFoundError:
        return False


async def _run_telegram(profile: str) -> None:
    if not telegram_enabled(profile):
        print_warning(
            "Telegram bot skipped (set TELEGRAM_BOT_TOKEN or HELIX_TELEGRAM_BOT_TOKEN to enable)"
        )
        return

    if not telegram_aiogram_available():
        print_warning("Telegram bot skipped: aiogram is not installed")
        print_info("Install: uv sync --extra telegram")
        return

    try:
        from integrations.telegram.bot import HelixTelegramBot
    except ImportError as e:
        print_warning(f"Telegram bot skipped: {e}")
        print_info("Install: uv sync --extra telegram")
        return

    print_success(f"Telegram bot starting (profile={profile})")
    bot = HelixTelegramBot(profile=profile)
    try:
        await bot.run_polling()
    except ImportError as e:
        print_warning(f"Telegram bot stopped: {e}")
        print_info("Install: uv sync --extra telegram")
    except asyncio.CancelledError:
        if bot._dp is not None:
            await bot._dp.stop_polling()
        raise


async def _run_gateway_uvicorn(host: str, port: int) -> None:
    import uvicorn

    config = uvicorn.Config(
        "api.gateway:app",
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def _run_cron_scheduler(profile: str) -> None:
    from core.cron.scheduler import CronScheduler

    await CronScheduler(profile).run_forever()


def _terminate_proc(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def _docs_subprocess(host: str, port: int, profile: str) -> subprocess.Popen[bytes] | None:
    if not docs_should_start():
        print_warning("Documentation site skipped (web-docs/ not found)")
        return None

    listen_port = resolve_listen_port(host, port)
    if listen_port != port:
        print_warning(f"Docs port {port} is in use; using {listen_port} instead")
        port = listen_port

    print_success(f"Documentation site starting on {docs_url(host, port)}")
    proc = popen_background(
        [sys.executable, "-m", "cli.services.docs_worker", "--host", host, "--port", str(port)],
    )
    if proc.pid:
        update_docs_info(pid=proc.pid, host=host, port=port, profile=profile)
    return proc


async def _run_supervisor_async(
    host: str,
    port: int,
    profile: str,
    *,
    with_docs: bool = False,
    docs_host: str = "127.0.0.1",
    docs_port: int = 8080,
) -> None:
    print_info(f"Starting Helix API Gateway on {host}:{port}")
    companions = ["cron"]
    if with_docs:
        companions.append("docs" if docs_should_start() else "docs (unavailable)")
    if telegram_should_start(profile):
        companions.append("telegram")
    elif telegram_enabled(profile):
        companions.append("telegram (needs: uv sync --extra telegram)")
    else:
        companions.append("telegram (disabled)")
    print_info(f"Companion services: {', '.join(companions)}")

    docs_proc = _docs_subprocess(docs_host, docs_port, profile) if with_docs else None
    gateway_task = asyncio.create_task(_run_gateway_uvicorn(host, port), name="gateway")
    telegram_task = asyncio.create_task(_run_telegram(profile), name="telegram")
    cron_task = asyncio.create_task(_run_cron_scheduler(profile), name="cron")
    tasks = (gateway_task, telegram_task, cron_task)

    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for task, result in zip(tasks, results):
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                print_warning(f"{task.get_name()} failed: {result}")
    except asyncio.CancelledError:
        pass
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        _terminate_proc(docs_proc)
        print_info("All services stopped.")


def _cron_subprocess(profile: str) -> subprocess.Popen[bytes] | None:
    env = os.environ.copy()
    env["HELIX_PROFILE"] = profile
    print_success(f"Cron scheduler starting in subprocess (profile={profile})")
    return popen_background(
        [sys.executable, "-m", "cli.services.cron_worker", "--profile", profile],
        env=env,
    )


def _telegram_subprocess(profile: str) -> subprocess.Popen[bytes] | None:
    if not telegram_enabled(profile):
        print_warning(
            "Telegram bot skipped (set TELEGRAM_BOT_TOKEN or HELIX_TELEGRAM_BOT_TOKEN to enable)"
        )
        return None

    if not telegram_aiogram_available():
        print_warning("Telegram bot skipped: aiogram is not installed")
        print_info("Install: uv sync --extra telegram")
        return None

    env = os.environ.copy()
    print_success(f"Telegram bot starting in subprocess (profile={profile})")
    proc = popen_background(
        [sys.executable, "-m", "integrations.telegram.main"],
        env=env,
    )
    if proc.pid:
        update_telegram_pid(proc.pid, profile=profile)
    return proc


def _start_with_reload(
    host: str,
    port: int,
    profile: str,
    *,
    with_docs: bool = False,
    docs_host: str = "127.0.0.1",
    docs_port: int = 8080,
) -> NoReturn:
    """Gateway with uvicorn reload; companions run in sibling OS processes."""
    import uvicorn

    print_info(f"Starting Helix API Gateway on {host}:{port}")
    print_info("Auto-reload enabled (companions run in separate processes)")

    tg_proc = _telegram_subprocess(profile)
    cron_proc = _cron_subprocess(profile)
    docs_proc = _docs_subprocess(docs_host, docs_port, profile) if with_docs else None

    try:
        uvicorn.run(
            "api.gateway:app",
            host=host,
            port=port,
            reload=True,
            log_level="info",
        )
    except KeyboardInterrupt:
        print_info("\nShutting down gateway...")
    finally:
        for proc in (tg_proc, cron_proc, docs_proc):
            _terminate_proc(proc)


def run_gateway_supervisor(
    host: str,
    port: int,
    *,
    reload: bool = False,
    profile: str = "default",
    with_docs: bool = False,
    docs_host: str = "127.0.0.1",
    docs_port: int = 8080,
) -> None:
    """Start gateway and all companion services (Telegram, docs, …)."""
    from core.env_loader import bootstrap_profile_env

    bootstrap_profile_env(profile)
    if reload:
        _start_with_reload(
            host,
            port,
            profile,
            with_docs=with_docs,
            docs_host=docs_host,
            docs_port=docs_port,
        )
        return

    try:
        asyncio.run(
            _run_supervisor_async(
                host,
                port,
                profile,
                with_docs=with_docs,
                docs_host=docs_host,
                docs_port=docs_port,
            )
        )
    except KeyboardInterrupt:
        print_info("\nShutting down…")