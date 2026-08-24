"""Track long-running project processes started by the agent (per chat session)."""

from __future__ import annotations

import asyncio
import logging
import shlex
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.platform_compat import (
    IS_POSIX,
    IS_WINDOWS,
    is_process_alive,
    popen_background,
    terminate_process,
)
from core.runtime.background_process_health import (
    ProcessHealthReport,
    build_health_report,
    tail_log_file,
)

logger = logging.getLogger(__name__)

_process_stop_hooks: list[Any] = []


def register_process_stop_hook(hook: Any) -> None:
    """Notify messengers when a background process is stopped (any registry)."""
    if hook not in _process_stop_hooks:
        _process_stop_hooks.append(hook)


def unregister_process_stop_hook(hook: Any) -> None:
    try:
        _process_stop_hooks.remove(hook)
    except ValueError:
        pass


def _notify_process_stopped(rec: BackgroundProcessRecord) -> None:
    for hook in list(_process_stop_hooks):
        try:
            hook(rec)
        except Exception:
            logger.debug("background process stop hook failed", exc_info=True)


@dataclass(slots=True)
class BackgroundProcessRecord:
    process_id: str
    label: str
    command: str
    pid: int
    conversation_id: str
    profile: str
    chat_id: str | None = None
    log_path: str = ""
    started_at: float = field(default_factory=time.time)
    _popen: Any = field(default=None, repr=False)

    def is_running(self) -> bool:
        return is_process_alive(self.pid)

    def display_line(self) -> str:
        status = "running" if self.is_running() else "stopped"
        return f"▶ {self.label} · pid {self.pid} · {status}\n`{self.command}`"


class BackgroundProcessRegistry:
    """In-memory registry keyed by profile + conversation."""

    def __init__(self) -> None:
        self._records: dict[str, BackgroundProcessRecord] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _scope_key(profile: str, conversation_id: str) -> str:
        return f"{profile}:{conversation_id}"

    def _records_for_profile(self, profile: str) -> list[BackgroundProcessRecord]:
        return [rec for rec in self._records.values() if rec.profile == profile]

    def _ports_for_record(self, rec: BackgroundProcessRecord) -> list[int]:
        from core.runtime.port_utils import extract_listen_ports_from_log, parse_listen_ports

        ports = parse_listen_ports(rec.command)
        if rec.log_path:
            log_tail = tail_log_file(rec.log_path, max_lines=40)
            for port in extract_listen_ports_from_log(log_tail):
                if port not in ports:
                    ports.append(port)
        return ports

    async def cleanup_before_start(
        self,
        *,
        profile: str,
        command: str,
        conversation_id: str | None = None,
    ) -> list[BackgroundProcessRecord]:
        """Stop profile processes that hold ports the new command needs."""
        from core.runtime.port_utils import force_free_ports, parse_listen_ports

        # Include processes started by Telegram/other Holix OS processes.
        self.hydrate_from_disk(profile)
        async with self._lock:
            candidates = list(self._records_for_profile(profile))
        candidates.sort(key=lambda r: r.started_at, reverse=True)

        target_ports = set(parse_listen_ports(command))
        to_stop: list[BackgroundProcessRecord] = []
        seen_ids: set[str] = set()
        for rec in candidates:
            if rec.process_id in seen_ids:
                continue
            port_conflict = bool(target_ports and set(self._ports_for_record(rec)) & target_ports)
            if port_conflict:
                to_stop.append(rec)
                seen_ids.add(rec.process_id)

        stopped: list[BackgroundProcessRecord] = []
        all_ports: list[int] = list(target_ports)
        for rec in to_stop:
            await self._stop_record(rec)
            stopped.append(rec)
            for port in self._ports_for_record(rec):
                if port not in all_ports:
                    all_ports.append(port)

        if all_ports:
            await asyncio.to_thread(force_free_ports, all_ports)
        return stopped

    async def start(
        self,
        *,
        command: str,
        label: str,
        conversation_id: str,
        profile: str,
        chat_id: str | None = None,
        cwd: str | None = None,
    ) -> BackgroundProcessRecord:
        from core.runtime.background_paths import (
            background_log_dir,
            build_background_spawn_env,
            command_needs_shell,
            resolve_argv_executable,
            resolve_background_process_root,
        )

        await self.cleanup_before_start(
            profile=profile,
            command=command,
            conversation_id=conversation_id,
        )

        from core.runtime.port_utils import find_busy_ports, format_port_conflict_message

        busy_ports = await asyncio.to_thread(find_busy_ports, command)
        if busy_ports:
            raise ValueError(format_port_conflict_message(busy_ports))

        try:
            argv = shlex.split(command, posix=not IS_WINDOWS)
        except ValueError as exc:
            raise ValueError(f"Invalid command syntax: {exc}") from exc
        if not argv:
            raise ValueError("Empty command")

        if cwd and str(cwd).strip():
            project_root = Path(cwd).expanduser().resolve()
        else:
            project_root = resolve_background_process_root()
        root = str(project_root)

        log_dir = background_log_dir(project_root)
        log_dir.mkdir(parents=True, exist_ok=True)
        process_id = f"proc_{uuid.uuid4().hex[:10]}"
        log_path = log_dir / f"{process_id}.log"

        spawn_env = build_background_spawn_env(project_root)
        spawn_argv = resolve_argv_executable(argv, project_root)

        # Optional Studio/admin resource limits (CPU/RAM) for multi-tenant hosts.
        preexec = None
        try:
            from core.runtime.resource_limits import (
                load_resource_limits,
                process_preexec_fn,
                wrap_process_argv,
            )

            _limits = load_resource_limits()
            preexec = process_preexec_fn(_limits)
            spawn_argv = wrap_process_argv(spawn_argv, _limits)
        except Exception:
            preexec = None

        def _spawn() -> tuple[Any, str]:
            log_handle = open(log_path, "ab")  # noqa: SIM115
            try:
                if command_needs_shell(command):
                    shell_argv = (
                        ["/bin/bash", "-lc", command.strip()]
                        if IS_POSIX
                        else ["cmd", "/c", command.strip()]
                    )
                    try:
                        from core.runtime.resource_limits import (
                            load_resource_limits,
                            wrap_process_argv,
                        )

                        shell_argv = wrap_process_argv(shell_argv, load_resource_limits())
                    except Exception:
                        pass
                    popen = popen_background(
                        shell_argv,
                        stdout=log_handle,
                        stderr=log_handle,
                        cwd=root,
                        env=spawn_env,
                        preexec_fn=preexec,
                    )
                else:
                    popen = popen_background(
                        spawn_argv,
                        stdout=log_handle,
                        stderr=log_handle,
                        cwd=root,
                        env=spawn_env,
                        preexec_fn=preexec,
                    )
            finally:
                log_handle.close()
            return popen, str(log_path.resolve())

        popen, resolved_log = await asyncio.to_thread(_spawn)
        display_label = (label or argv[0]).strip()[:120]

        async with self._lock:
            record = BackgroundProcessRecord(
                process_id=process_id,
                label=display_label,
                command=command.strip(),
                pid=int(popen.pid),
                conversation_id=conversation_id,
                profile=profile,
                chat_id=chat_id,
                log_path=resolved_log,
                _popen=popen,
            )
            self._records[process_id] = record

        # Persist so Studio (separate OS process) sees Telegram/CLI starts.
        try:
            from core.runtime.background_process_store import upsert_record

            await asyncio.to_thread(upsert_record, record)
        except Exception as exc:
            logger.warning("Failed to persist background process index: %s", exc)

        logger.info(
            "Background process started id=%s pid=%s profile=%s cmd=%s",
            process_id,
            record.pid,
            profile,
            command[:200],
        )
        return record

    async def stop(self, process_id: str) -> BackgroundProcessRecord | None:
        async with self._lock:
            rec = self._records.get(process_id)
        if rec is None:
            # May only exist on disk (started by another Holix process).
            rec = self.get(process_id)
        if rec is None:
            return None
        await self._stop_all_records([rec])
        return rec

    async def stop_for_scope(
        self, *, profile: str, conversation_id: str
    ) -> BackgroundProcessRecord | None:
        """Stop the newest running process in this chat session (or most recent if all stopped)."""
        rec = self.active_for_scope(profile=profile, conversation_id=conversation_id)
        if rec is None:
            records = self.list_for_scope(profile=profile, conversation_id=conversation_id)
            rec = records[0] if records else None
        if rec is None:
            return None
        from core.runtime.port_utils import force_free_ports

        ports = self._ports_for_record(rec)
        await self._stop_record(rec)
        if ports:
            await asyncio.to_thread(force_free_ports, ports)
        return rec

    async def stop_for_profile(self, *, profile: str) -> BackgroundProcessRecord | None:
        """Stop all background processes for a profile (any conversation)."""
        async with self._lock:
            candidates = list(self._records_for_profile(profile))
        if not candidates:
            return None
        return await self._stop_all_records(candidates)

    async def _stop_all_records(
        self,
        candidates: list[BackgroundProcessRecord],
    ) -> BackgroundProcessRecord | None:
        from core.runtime.port_utils import force_free_ports

        if not candidates:
            return None
        candidates = sorted(candidates, key=lambda r: r.started_at, reverse=True)
        all_ports: list[int] = []
        for rec in candidates:
            await self._stop_record(rec)
            for port in self._ports_for_record(rec):
                if port not in all_ports:
                    all_ports.append(port)
        if all_ports:
            await asyncio.to_thread(force_free_ports, all_ports)
        return candidates[0]

    def active_for_scope(
        self, *, profile: str, conversation_id: str
    ) -> BackgroundProcessRecord | None:
        for rec in self.list_for_scope(profile=profile, conversation_id=conversation_id):
            if rec.is_running():
                return rec
        return None

    def _exit_code(self, rec: BackgroundProcessRecord) -> int | None:
        if rec._popen is None:
            return None
        try:
            return rec._popen.poll()
        except Exception:
            return None

    async def check_health(
        self,
        *,
        process_id: str | None = None,
        profile: str,
        conversation_id: str,
        wait_s: float = 2.0,
    ) -> ProcessHealthReport:
        if wait_s > 0:
            await asyncio.sleep(wait_s)

        rec: BackgroundProcessRecord | None
        if process_id:
            rec = self.get(process_id)
        else:
            rec = self.active_for_scope(profile=profile, conversation_id=conversation_id)
            if rec is None:
                records = self.list_for_scope(profile=profile, conversation_id=conversation_id)
                rec = records[0] if records else None

        if rec is None:
            return ProcessHealthReport(
                status="not_found",
                recommendation="No process to check. Start one with start_background_process.",
            )

        log_tail = await asyncio.to_thread(tail_log_file, rec.log_path)
        running = rec.is_running()
        exit_code = self._exit_code(rec)
        report = build_health_report(
            process_id=rec.process_id,
            label=rec.label,
            pid=rec.pid,
            log_path=rec.log_path,
            running=running,
            exit_code=exit_code,
            log_tail=log_tail,
        )
        expected_ports = self._ports_for_record(rec)
        if expected_ports:
            from core.runtime.background_process_health import apply_port_checks
            from core.runtime.port_verify import verify_expected_ports

            port_checks = await asyncio.to_thread(
                verify_expected_ports,
                expected_ports=expected_ports,
                root_pid=rec.pid,
                root_running=running,
                expected_command=rec.command,
            )
            report = apply_port_checks(
                report,
                port_checks=port_checks,
                expected_ports=expected_ports,
            )
        return report

    async def restart(
        self,
        *,
        command: str,
        label: str,
        conversation_id: str,
        profile: str,
        chat_id: str | None = None,
        cwd: str | None = None,
    ) -> BackgroundProcessRecord:
        """Stop profile processes, free ports, and start the same command again."""
        return await self.start(
            command=command,
            label=label,
            conversation_id=conversation_id,
            profile=profile,
            chat_id=chat_id,
            cwd=cwd,
        )

    async def _stop_record(self, rec: BackgroundProcessRecord) -> None:
        try:
            await asyncio.to_thread(terminate_process, rec.pid, grace=2.0)
        except Exception as exc:
            logger.warning(
                "Failed to stop process %s (pid=%s): %s",
                rec.process_id,
                rec.pid,
                exc,
            )
        if rec._popen is not None:
            try:
                await asyncio.to_thread(rec._popen.wait, timeout=1)
            except Exception:
                pass
        try:
            from core.runtime.background_process_store import remove_record

            await asyncio.to_thread(remove_record, rec.profile, rec.process_id)
        except Exception as exc:
            logger.warning("Failed to remove background process from index: %s", exc)
        async with self._lock:
            self._records.pop(rec.process_id, None)
        _notify_process_stopped(rec)

    def hydrate_from_disk(self, profile: str | None = None) -> int:
        """Load process rows started by other Holix processes (Telegram/Studio/CLI).

        Returns number of records newly merged into memory.
        """
        from core.runtime.background_process_store import (
            iter_profile_names_with_index,
            load_index,
            prune_dead_records,
        )

        profiles: set[str] = set()
        if profile:
            profiles.add((profile or "").strip() or "default")
        else:
            profiles.update(
                (rec.profile or "default").strip() or "default" for rec in self._records.values()
            )
            if not profiles:
                profiles.update(iter_profile_names_with_index())

        added = 0
        for prof in profiles:
            rows = prune_dead_records(prof, is_alive=is_process_alive)
            if not rows:
                rows = load_index(prof)
            for row in rows:
                pid_key = str(row.get("process_id") or "")
                if not pid_key or pid_key in self._records:
                    continue
                try:
                    pid = int(row.get("pid") or 0)
                except (TypeError, ValueError):
                    continue
                if pid <= 0 or not is_process_alive(pid):
                    continue
                rec = BackgroundProcessRecord(
                    process_id=pid_key,
                    label=str(row.get("label") or pid_key)[:120],
                    command=str(row.get("command") or ""),
                    pid=pid,
                    conversation_id=str(row.get("conversation_id") or ""),
                    profile=str(row.get("profile") or prof),
                    chat_id=(str(row["chat_id"]) if row.get("chat_id") else None),
                    log_path=str(row.get("log_path") or ""),
                    started_at=float(row.get("started_at") or time.time()),
                    _popen=None,
                )
                self._records[pid_key] = rec
                added += 1
        return added

    def get(self, process_id: str) -> BackgroundProcessRecord | None:
        rec = self._records.get(process_id)
        if rec is not None:
            return rec
        # Cross-process: scan profile indexes
        self.hydrate_from_disk()
        return self._records.get(process_id)

    def list_for_profile(self, *, profile: str) -> list[BackgroundProcessRecord]:
        """All background processes for a profile (any conversation + disk index)."""
        self.hydrate_from_disk(profile)
        return sorted(self._records_for_profile(profile), key=lambda r: r.started_at, reverse=True)

    def list_running_for_profile(self, *, profile: str) -> list[BackgroundProcessRecord]:
        """OS-alive processes only — dead/crashed records are omitted."""
        return [rec for rec in self.list_for_profile(profile=profile) if rec.is_running()]


PROCESS_EXIT_WAKE_MAX = 3


def vanished_process_ids(previous: list[str], current: list[str]) -> list[str]:
    """Ids that were listed as running and are gone now."""
    alive = {str(x).strip() for x in current if str(x).strip()}
    out: list[str] = []
    seen: set[str] = set()
    for raw in previous:
        pid = str(raw).strip()
        if not pid or pid in alive or pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
    return out


def format_process_exit_wakeup(
    *,
    label: str,
    process_id: str,
    pid: int = 0,
    reason: str = "stopped",
) -> str:
    """User-turn text so the agent can react without busy-polling."""
    name = (label or process_id or "process").strip() or "process"
    extra = f" pid={pid}" if pid else ""
    why = (reason or "stopped").strip() or "stopped"
    return (
        f"Background process `{name}` (id={process_id}{extra}) is no longer running "
        f"({why}). If that was unexpected, read the process log, fix if needed, and "
        "restart only if the user still wants the server. Do not busy-poll with "
        "check_background_process; you will be notified again if it dies."
    )

    def list_for_scope(
        self, *, profile: str, conversation_id: str
    ) -> list[BackgroundProcessRecord]:
        self.hydrate_from_disk(profile)
        scope = self._scope_key(profile, conversation_id)
        out: list[BackgroundProcessRecord] = []
        for rec in self._records.values():
            if self._scope_key(rec.profile, rec.conversation_id) == scope:
                out.append(rec)
        return sorted(out, key=lambda r: r.started_at, reverse=True)


_default_registry: BackgroundProcessRegistry | None = None
_profile_registries: dict[str, BackgroundProcessRegistry] = {}


def bind_background_process_registry(
    registry: BackgroundProcessRegistry,
    profile_name: str,
) -> None:
    """Associate a registry with a profile (set during agent initialize)."""
    key = (profile_name or "default").strip() or "default"
    _profile_registries[key] = registry
    try:
        registry.hydrate_from_disk(key)
    except Exception:
        pass


def unbind_background_process_registry(profile_name: str) -> None:
    key = (profile_name or "default").strip() or "default"
    _profile_registries.pop(key, None)


def get_background_process_registry(profile_name: str | None = None) -> BackgroundProcessRegistry:
    """Return the registry for a Holix profile (never share one bag across profiles).

    Agent initialize binds its instance via :func:`bind_background_process_registry`.
    When unbound, create/reuse a per-profile registry so Studio HTTP listing and
    tools cannot mix process records between users.

    Always hydrates from the shared on-disk index so Telegram-started processes
    appear in Studio for the same profile.
    """
    from core.tools.execution_context import get_profile_name

    key = (profile_name or get_profile_name() or "default").strip() or "default"
    bound = _profile_registries.get(key)
    if bound is not None:
        try:
            bound.hydrate_from_disk(key)
        except Exception:
            pass
        return bound
    # Isolate by profile key. Keep a process-wide default only for the
    # literal ``default`` key used by single-user / tests without a profile.
    if key == "default":
        global _default_registry
        if _default_registry is None:
            _default_registry = BackgroundProcessRegistry()
        _profile_registries.setdefault("default", _default_registry)
        try:
            _default_registry.hydrate_from_disk("default")
        except Exception:
            pass
        return _default_registry
    reg = BackgroundProcessRegistry()
    try:
        reg.hydrate_from_disk(key)
    except Exception:
        pass
    _profile_registries[key] = reg
    return reg
