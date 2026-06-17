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
    ) -> list[BackgroundProcessRecord]:
        """Stop every Holix-tracked process for profile and free target ports."""
        from core.runtime.port_utils import force_free_ports, parse_listen_ports

        async with self._lock:
            candidates = list(self._records_for_profile(profile))
        candidates.sort(key=lambda r: r.started_at, reverse=True)

        stopped: list[BackgroundProcessRecord] = []
        all_ports: list[int] = list(parse_listen_ports(command))
        for rec in candidates:
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
        from core.workspace import get_effective_workspace_root

        await self.cleanup_before_start(profile=profile, command=command)

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

        root = cwd
        if root is None:
            ws = get_effective_workspace_root()
            root = str(ws) if ws is not None else None

        log_dir = Path(root or ".") / ".holix" / "process-logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        process_id = f"proc_{uuid.uuid4().hex[:10]}"
        log_path = log_dir / f"{process_id}.log"

        def _spawn() -> tuple[Any, str]:
            log_handle = open(log_path, "ab")  # noqa: SIM115
            try:
                if IS_WINDOWS or not any(
                    token in command for token in ("&&", "||", "|", ";")
                ):
                    popen = popen_background(
                        argv,
                        stdout=log_handle,
                        stderr=log_handle,
                        cwd=root,
                    )
                else:
                    shell_cmd = f"exec {command}" if IS_POSIX else command
                    shell_argv = (
                        ["/bin/sh", "-c", shell_cmd]
                        if IS_POSIX
                        else ["cmd", "/c", shell_cmd]
                    )
                    popen = popen_background(
                        shell_argv,
                        stdout=log_handle,
                        stderr=log_handle,
                        cwd=root,
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

        logger.info(
            "Background process started id=%s pid=%s cmd=%s",
            process_id,
            record.pid,
            command[:200],
        )
        return record

    async def stop(self, process_id: str) -> BackgroundProcessRecord | None:
        async with self._lock:
            rec = self._records.get(process_id)
        if rec is None:
            return None
        await self._stop_all_records([rec])
        return rec

    async def stop_for_scope(self, *, profile: str, conversation_id: str) -> BackgroundProcessRecord | None:
        scope = self._scope_key(profile, conversation_id)
        async with self._lock:
            candidates = [
                rec
                for rec in self._records.values()
                if self._scope_key(rec.profile, rec.conversation_id) == scope
            ]
        if not candidates:
            return None
        return await self._stop_all_records(candidates)

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

    def get(self, process_id: str) -> BackgroundProcessRecord | None:
        return self._records.get(process_id)

    def list_for_scope(self, *, profile: str, conversation_id: str) -> list[BackgroundProcessRecord]:
        scope = self._scope_key(profile, conversation_id)
        out: list[BackgroundProcessRecord] = []
        for rec in self._records.values():
            if self._scope_key(rec.profile, rec.conversation_id) == scope:
                out.append(rec)
        return sorted(out, key=lambda r: r.started_at, reverse=True)

    def active_for_scope(self, *, profile: str, conversation_id: str) -> BackgroundProcessRecord | None:
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


_registry: BackgroundProcessRegistry | None = None


def get_background_process_registry() -> BackgroundProcessRegistry:
    global _registry
    if _registry is None:
        _registry = BackgroundProcessRegistry()
    return _registry