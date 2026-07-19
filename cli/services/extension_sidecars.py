"""Discover and launch extension sidecar HTTP processes with the gateway supervisor.

Host extensions that declare capability ``sidecar`` may implement::

    def sidecar_spec(self, profile: str) -> SidecarSpec | dict | None:
        '''Return a listen spec, or None / omit to skip.'''

``SidecarSpec`` fields: ``id``, ``host``, ``port``, ``argv`` (list of strings;
if the first element is not absolute and not a known interpreter path, the
supervisor prepends ``sys.executable``), optional ``env``, ``label``, ``url_path``.

Permissions: extensions need ``network`` (or ``subprocess``) to start a sidecar.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import Any

from core.extensions.base import CAPABILITY_SIDECAR
from core.extensions.permissions import (
    PERMISSION_GATEWAY,
    PERMISSION_NETWORK,
    PERMISSION_SUBPROCESS,
    extension_permissions,
)
from core.platform_compat import popen_background
from cli.utils.ports import resolve_listen_port
from cli.utils.rich_console import print_info, print_success, print_warning

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SidecarSpec:
    """How to run one extension sidecar process."""

    id: str
    host: str
    port: int
    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)
    label: str = ""
    url_path: str = "/"

    def display_label(self) -> str:
        return self.label or self.id

    def public_url(self) -> str:
        bind = "127.0.0.1" if self.host in ("0.0.0.0", "::") else self.host
        path = self.url_path if self.url_path.startswith("/") else f"/{self.url_path}"
        return f"http://{bind}:{self.port}{path}"


@dataclass(slots=True)
class RunningSidecar:
    id: str
    host: str
    port: int
    pid: int
    label: str = ""
    url_path: str = "/"
    proc: subprocess.Popen[bytes] | None = field(default=None, repr=False)

    def public_url(self) -> str:
        bind = "127.0.0.1" if self.host in ("0.0.0.0", "::") else self.host
        path = self.url_path if self.url_path.startswith("/") else f"/{self.url_path}"
        return f"http://{bind}:{self.port}{path}"

    def to_state_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "host": self.host,
            "port": self.port,
            "pid": self.pid,
            "label": self.label,
            "url_path": self.url_path,
            "url": self.public_url(),
        }


def _coerce_spec(raw: Any, *, fallback_id: str) -> SidecarSpec | None:
    if raw is None:
        return None
    if isinstance(raw, SidecarSpec):
        return raw
    if not isinstance(raw, dict):
        return None
    sid = str(raw.get("id") or fallback_id).strip() or fallback_id
    host = str(raw.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int(raw.get("port") or 0)
    except (TypeError, ValueError):
        return None
    argv = raw.get("argv") or raw.get("command") or []
    if isinstance(argv, str):
        argv = argv.split()
    if not isinstance(argv, (list, tuple)) or not argv:
        return None
    env_raw = raw.get("env") or {}
    env = {str(k): str(v) for k, v in env_raw.items()} if isinstance(env_raw, dict) else {}
    return SidecarSpec(
        id=sid,
        host=host,
        port=port,
        argv=[str(a) for a in argv],
        env=env,
        label=str(raw.get("label") or raw.get("name") or sid),
        url_path=str(raw.get("url_path") or "/"),
    )


def collect_sidecar_specs(profile: str) -> list[SidecarSpec]:
    """Ask discovered host extensions for sidecar specs."""
    from core.extensions.registry import discover_extensions

    specs: list[SidecarSpec] = []
    seen: set[str] = set()
    for ext in discover_extensions(profile):
        caps = frozenset(getattr(ext, "capabilities", frozenset()) or ())
        # Capability optional: method presence is enough (older manifests).
        has_method = callable(getattr(ext, "sidecar_spec", None))
        if CAPABILITY_SIDECAR not in caps and not has_method:
            continue
        perms = extension_permissions(ext)
        # Need network, subprocess, or gateway — empty perms default to tools-only
        allowed = {PERMISSION_NETWORK, PERMISSION_SUBPROCESS, PERMISSION_GATEWAY}
        if perms and not (perms & allowed):
            logger.warning(
                "extension %s cannot start sidecar (permissions=%s)",
                getattr(ext, "name", "?"),
                sorted(perms),
            )
            continue
        name = str(getattr(ext, "name", "") or "ext")
        try:
            # Prefer should_start_sidecar gate when present
            should = getattr(ext, "should_start_sidecar", None)
            if callable(should) and not should(profile):
                logger.info("sidecar skipped for %s (should_start_sidecar=False)", name)
                continue
            factory = getattr(ext, "sidecar_spec", None)
            if not callable(factory):
                continue
            raw = factory(profile)
        except Exception:
            logger.exception("extension %s sidecar_spec failed", name)
            continue
        spec = _coerce_spec(raw, fallback_id=name)
        if spec is None:
            continue
        if spec.id in seen:
            logger.warning("duplicate sidecar id %s — skipping", spec.id)
            continue
        seen.add(spec.id)
        specs.append(spec)
    return specs


def _build_command(spec: SidecarSpec) -> list[str]:
    argv = list(spec.argv)
    if not argv:
        raise ValueError("empty argv")
    first = argv[0]
    # Already full command with interpreter
    if first == sys.executable or first.endswith(("python", "python3")) or os.path.isabs(first):
        return argv
    # Module form: -m pkg.module …
    if first == "-m" or first.startswith("-"):
        return [sys.executable, *argv]
    # Bare module path style: package.module as first token after -m convention
    return [sys.executable, *argv]


def start_extension_sidecars(
    profile: str,
    *,
    gateway_host: str = "127.0.0.1",
    gateway_port: int = 8000,
) -> list[RunningSidecar]:
    """Start all eligible extension sidecars; return running process handles."""
    running: list[RunningSidecar] = []
    for spec in collect_sidecar_specs(profile):
        try:
            listen_port = resolve_listen_port(spec.host, spec.port, wait_timeout=2.0)
        except OSError as exc:
            print_warning(f"Sidecar {spec.display_label()}: no free port near {spec.port} ({exc})")
            continue
        if listen_port != spec.port:
            print_warning(
                f"Sidecar {spec.display_label()}: port {spec.port} busy; using {listen_port}"
            )
            # Allow argv that already embeds the preferred port — rebuild via env
            port = listen_port
        else:
            port = spec.port

        # Re-resolve argv if extension used fixed port in argv: replace last occurrence
        # of preferred port string with actual (best-effort).
        argv = list(spec.argv)
        preferred_s, actual_s = str(spec.port), str(port)
        if preferred_s != actual_s:
            argv = [actual_s if a == preferred_s else a for a in argv]

        try:
            cmd = _build_command(
                SidecarSpec(
                    id=spec.id,
                    host=spec.host,
                    port=port,
                    argv=argv,
                    env=spec.env,
                    label=spec.label,
                    url_path=spec.url_path,
                )
            )
        except ValueError:
            print_warning(f"Sidecar {spec.display_label()}: invalid command")
            continue

        env = os.environ.copy()
        env["HOLIX_PROFILE"] = profile
        env["HOLIX_GATEWAY_HOST"] = gateway_host
        env["HOLIX_GATEWAY_PORT"] = str(gateway_port)
        env["HOLIX_SIDECAR_HOST"] = spec.host
        env["HOLIX_SIDECAR_PORT"] = str(port)
        env.update(spec.env)

        try:
            proc = popen_background(cmd, env=env)
        except OSError as exc:
            print_warning(f"Sidecar {spec.display_label()} failed to start: {exc}")
            continue

        pid = int(proc.pid or 0)
        if not pid:
            print_warning(f"Sidecar {spec.display_label()}: no pid")
            continue

        item = RunningSidecar(
            id=spec.id,
            host=spec.host,
            port=port,
            pid=pid,
            label=spec.display_label(),
            url_path=spec.url_path,
            proc=proc,
        )
        running.append(item)
        print_success(f"Sidecar {item.label} starting on {item.public_url()} (pid={pid})")
        print_info(f"  cmd: {' '.join(cmd)}")
    return running


def terminate_sidecars(procs: list[RunningSidecar] | list[subprocess.Popen[bytes] | None]) -> None:
    """Stop sidecar processes (best-effort)."""
    for item in procs:
        proc: subprocess.Popen[bytes] | None
        if isinstance(item, RunningSidecar):
            proc = item.proc
            if proc is None and item.pid:
                try:
                    from core.platform_compat import terminate_process

                    terminate_process(item.pid, grace=5.0)
                    continue
                except Exception:
                    pass
        else:
            proc = item
        if proc is None or proc.poll() is not None:
            continue
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def sidecars_to_state(running: list[RunningSidecar]) -> list[dict[str, Any]]:
    return [r.to_state_dict() for r in running]
