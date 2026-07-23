"""Start API gateway together with all configured companion services."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from typing import NoReturn

from core.platform_compat import popen_background
from integrations.max.gateway_routes import max_enabled, max_should_poll, max_should_webhook
from integrations.telegram.config import load_telegram_settings, telegram_aiogram_available

from cli.services.docs_site import docs_url, resolve_web_docs_dir
from cli.services.extension_sidecars import (
    sidecars_to_state,
    start_extension_sidecars,
    terminate_sidecars,
)
from cli.services.gateway_state import (
    update_docs_info,
    update_max_pid,
    update_sidecars,
    update_telegram_pid,
)
from cli.utils.ports import resolve_listen_port
from cli.utils.rich_console import print_info, print_success, print_warning


def telegram_enabled(profile: str = "default") -> bool:
    """True when a Telegram bot token is configured."""
    return bool(load_telegram_settings(profile).bot_token.strip())


def telegram_should_start(profile: str = "default") -> bool:
    """True when token is set and optional aiogram dependency is installed."""
    return telegram_enabled(profile) and telegram_aiogram_available()


def docs_should_start() -> bool:
    """True when holix-docs (or legacy web-docs/) is available."""
    try:
        resolve_web_docs_dir()
        return True
    except FileNotFoundError:
        return False


async def _run_telegram(profile: str) -> None:
    if not telegram_enabled(profile):
        print_warning(
            "Telegram bot skipped (set TELEGRAM_BOT_TOKEN or HOLIX_TELEGRAM_BOT_TOKEN to enable)"
        )
        return

    if not telegram_aiogram_available():
        print_warning("Telegram bot skipped: aiogram is not installed")
        print_info("Install: uv sync --extra telegram")
        return

    try:
        from integrations.telegram.bot import HolixTelegramBot
    except ImportError as e:
        print_warning(f"Telegram bot skipped: {e}")
        print_info("Install: uv sync --extra telegram")
        return

    print_success(f"Telegram bot starting (profile={profile})")
    bot = HolixTelegramBot(profile=profile)
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


async def _run_cron_scheduler(_profile: str) -> None:
    from core.cron.scheduler import GlobalCronScheduler

    await GlobalCronScheduler().run_forever()


async def _run_max(profile: str) -> None:
    if not max_should_poll(profile):
        if max_enabled(profile) and max_should_webhook(profile):
            print_info("MAX webhook handled inside gateway process")
        elif not max_enabled(profile):
            print_warning(
                "MAX bot skipped (set MAX_ACCESS_TOKEN or HOLIX_MAX_ACCESS_TOKEN to enable)"
            )
        return

    from integrations.max.config import load_max_settings
    from integrations.max.polling import run_polling

    print_success(f"MAX bot starting (polling, profile={profile})")
    try:
        await run_polling(load_max_settings(profile), profile=profile)
    except RuntimeError as exc:
        print_warning(f"MAX bot stopped: {exc}")
    except asyncio.CancelledError:
        raise


def _terminate_proc(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


async def _watch_os_companions(
    profile: str,
    *,
    procs: dict[str, subprocess.Popen[bytes] | None],
    interval_sec: float = 5.0,
    restart_backoff_sec: float = 3.0,
    max_consecutive_failures: int = 5,
) -> None:
    """Restart Telegram/MAX OS companions if they exit (zombies / crashes).

    Permanent config failures (e.g. MAX profile misconfiguration) use
    exponential backoff and stop after *max_consecutive_failures* so a
    broken companion cannot busy-loop the host.
    """
    failures: dict[str, int] = {"telegram": 0, "max": 0}
    while True:
        await asyncio.sleep(interval_sec)
        for name, start_fn in (
            ("telegram", lambda: _telegram_subprocess(profile)),
            ("max", lambda: _max_subprocess(profile)),
        ):
            proc = procs.get(name)
            if proc is None or proc.poll() is None:
                if proc is not None and proc.poll() is None:
                    failures[name] = 0
                continue
            code = proc.returncode
            failures[name] = failures.get(name, 0) + 1
            n = failures[name]
            if n > max_consecutive_failures:
                print_warning(
                    f"{name} companion exited (code={code}) {n} times; "
                    f"giving up auto-restart (profile={profile})"
                )
                procs[name] = None
                continue
            backoff = restart_backoff_sec * (2 ** min(n - 1, 4))
            print_warning(
                f"{name} companion exited (code={code}); "
                f"restarting in {backoff:.0f}s "
                f"(try {n}/{max_consecutive_failures}, profile={profile})"
            )
            await asyncio.sleep(backoff)
            procs[name] = start_fn()


def _docs_subprocess(
    host: str,
    port: int,
    profile: str,
    *,
    gateway_host: str,
    gateway_port: int,
) -> subprocess.Popen[bytes] | None:
    if not docs_should_start():
        print_warning("Documentation site skipped (holix-docs not found; set HOLIX_WEB_DOCS_DIR)")
        return None

    listen_port = resolve_listen_port(host, port, wait_timeout=8.0)
    if listen_port != port:
        print_warning(f"Docs port {port} is in use; using {listen_port} instead")
        port = listen_port

    print_success(f"Documentation site starting on {docs_url(host, port)}")
    docs_env = os.environ.copy()
    docs_env["HOLIX_GATEWAY_HOST"] = gateway_host
    docs_env["HOLIX_GATEWAY_PORT"] = str(gateway_port)
    proc = popen_background(
        [
            sys.executable,
            "-m",
            "cli.services.docs_worker",
            "--host",
            host,
            "--port",
            str(port),
            "--profile",
            profile,
        ],
        env=docs_env,
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
    print_info(f"Starting Holix API Gateway on {host}:{port}")
    companions = ["cron"]
    if with_docs:
        companions.append("docs" if docs_should_start() else "docs (unavailable)")
    if telegram_should_start(profile):
        companions.append("telegram")
    elif telegram_enabled(profile):
        companions.append("telegram (needs: uv sync --extra telegram)")
    else:
        companions.append("telegram (disabled)")
    if max_should_webhook(profile):
        companions.append("max (webhook)")
    elif max_should_poll(profile):
        companions.append("max (polling)")
    elif max_enabled(profile):
        companions.append("max (disabled)")
    else:
        companions.append("max (disabled)")
    print_info(f"Companion services: {', '.join(companions)}")

    os.environ["HOLIX_GATEWAY_SUPERVISOR"] = "1"

    docs_proc = (
        _docs_subprocess(
            docs_host,
            docs_port,
            profile,
            gateway_host=host,
            gateway_port=port,
        )
        if with_docs
        else None
    )
    tg_proc = _telegram_subprocess(profile)
    # MAX must run as a separate OS process (like Telegram). In-process polling
    # races gateway agent warm-up on the same profile and can hang forever in
    # create_agent — bot never reaches Long Polling and appears dead.
    max_proc = _max_subprocess(profile)
    companion_procs: dict[str, subprocess.Popen[bytes] | None] = {
        "telegram": tg_proc,
        "max": max_proc,
    }
    sidecar_procs = start_extension_sidecars(
        profile, gateway_host=host, gateway_port=port
    )
    if sidecar_procs:
        update_sidecars(sidecars_to_state(sidecar_procs), profile=profile)
        companions_extra = ", ".join(s.label for s in sidecar_procs)
        print_info(f"Extension sidecars: {companions_extra}")
    gateway_task = asyncio.create_task(_run_gateway_uvicorn(host, port), name="gateway")
    cron_task = asyncio.create_task(_run_cron_scheduler(profile), name="cron")
    companion_watch = asyncio.create_task(
        _watch_os_companions(profile, procs=companion_procs),
        name="companion-watch",
    )
    tasks = (gateway_task, cron_task, companion_watch)

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
        terminate_sidecars(sidecar_procs)
        _terminate_proc(docs_proc)
        _terminate_proc(companion_procs.get("telegram"))
        _terminate_proc(companion_procs.get("max"))
        print_info("All services stopped.")


def _cron_subprocess(profile: str) -> subprocess.Popen[bytes] | None:
    env = os.environ.copy()
    env["HOLIX_PROFILE"] = profile
    print_success("Cron scheduler starting in subprocess (all profiles)")
    return popen_background(
        [sys.executable, "-m", "cli.services.cron_worker"],
        env=env,
    )


def _max_subprocess(profile: str) -> subprocess.Popen[bytes] | None:
    if max_should_webhook(profile):
        return None
    if not max_should_poll(profile):
        if max_enabled(profile):
            print_warning("MAX bot skipped (webhook mode requires gateway)")
        else:
            print_warning(
                "MAX bot skipped (set MAX_ACCESS_TOKEN or HOLIX_MAX_ACCESS_TOKEN to enable)"
            )
        return None

    _terminate_stray_module_workers("integrations.max.main", profile)
    env = os.environ.copy()
    env["HOLIX_PROFILE"] = profile
    print_success(f"MAX bot starting in subprocess (polling, profile={profile})")
    proc = popen_background(
        [sys.executable, "-m", "integrations.max.main", "--profile", profile],
        env=env,
    )
    if proc.pid:
        update_max_pid(proc.pid, profile=profile)
    return proc


def _terminate_stray_module_workers(module: str, profile: str) -> None:
    """Stop other OS processes for the same companion module+profile (avoid dual poll)."""
    from core.platform_compat import is_process_alive, terminate_process

    profile_flag = f"--profile {profile}"
    profile_flag_eq = f"--profile={profile}"
    try:
        import pathlib

        for proc_dir in pathlib.Path("/proc").iterdir():
            if not proc_dir.name.isdigit():
                continue
            pid = int(proc_dir.name)
            if pid == os.getpid() or not is_process_alive(pid):
                continue
            try:
                cmd = (proc_dir / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                    errors="replace"
                )
            except (OSError, PermissionError):
                continue
            if module not in cmd:
                continue
            # Require explicit profile flag so multi-profile hosts are not disrupted.
            if profile_flag not in cmd and profile_flag_eq not in cmd:
                continue
            print_warning(f"Stopping stray {module} pid={pid} (profile={profile})")
            terminate_process(pid, grace=3.0)
    except Exception:
        pass


def _telegram_subprocess(profile: str) -> subprocess.Popen[bytes] | None:
    if not telegram_enabled(profile):
        print_warning(
            "Telegram bot skipped (set TELEGRAM_BOT_TOKEN or HOLIX_TELEGRAM_BOT_TOKEN to enable)"
        )
        return None

    if not telegram_aiogram_available():
        print_warning("Telegram bot skipped: aiogram is not installed")
        print_info("Install: uv sync --extra telegram")
        return None

    _terminate_stray_module_workers("integrations.telegram.main", profile)
    env = os.environ.copy()
    env["HOLIX_PROFILE"] = profile
    print_success(f"Telegram bot starting in subprocess (profile={profile})")
    proc = popen_background(
        [sys.executable, "-m", "integrations.telegram.main", "--profile", profile],
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

    print_info(f"Starting Holix API Gateway on {host}:{port}")
    print_info("Auto-reload enabled (companions run in separate processes)")

    tg_proc = _telegram_subprocess(profile)
    max_proc = _max_subprocess(profile)
    cron_proc = _cron_subprocess(profile)
    docs_proc = (
        _docs_subprocess(
            docs_host,
            docs_port,
            profile,
            gateway_host=host,
            gateway_port=port,
        )
        if with_docs
        else None
    )
    sidecar_procs = start_extension_sidecars(
        profile, gateway_host=host, gateway_port=port
    )
    if sidecar_procs:
        update_sidecars(sidecars_to_state(sidecar_procs), profile=profile)

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
        terminate_sidecars(sidecar_procs)
        for proc in (tg_proc, max_proc, cron_proc, docs_proc):
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
    from cli.core import bootstrap_profile_unlock_from_env

    bootstrap_profile_unlock_from_env(profile)
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