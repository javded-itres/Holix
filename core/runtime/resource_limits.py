"""Global CPU/RAM limits for Studio background processes and Docker.

Stored at ``{HOLIX_HOME}/global/resource_limits.json`` and applied by:

- background process spawns (memory via RLIMIT_AS; optional systemd-run CPUQuota)
- Studio Docker compose up (``docker update --cpus/--memory``)
- Studio desktop containers (cpus/memory)

Admin UI in Holix Studio edits the same file.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Defaults chosen for multi-tenant SaaS hosts (prevents one job eating the box).
_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "docker": {
        "cpus": 1.0,
        "memory_mb": 512,
        "pids_limit": 256,
        "max_containers_per_workspace": 20,
        "block_public_db_ports": True,
    },
    "process": {
        "cpu_percent": 100,  # relative to one core (systemd CPUQuota=100%)
        "memory_mb": 512,
    },
    "desktop": {
        "cpus": 1.5,
        "memory_mb": 2048,
    },
}

_DB_PORTS = frozenset({5432, 5433, 5434, 3306, 54320, 6379, 27017, 5672, 9200, 9300})
_PORT_PUBLISH_RE = re.compile(
    r"""(?x)
    (?:['"]?)
    (?:
        (?P<host>\d+\.\d+\.\d+\.\d+|\[::\]|\[::1\]|localhost)
        :
    )?
    (?P<host_port>\d+)
    :
    (?P<container_port>\d+)
    (?:/(?P<proto>\w+))?
    (?:['"]?)
    """
)


def resource_limits_path() -> Path:
    from core.global_config import global_dir

    return global_dir() / "resource_limits.json"


def _clamp_float(value: Any, *, default: float, lo: float, hi: float) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if n < lo:
        return lo
    if n > hi:
        return hi
    return n


def _clamp_int(value: Any, *, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if n < lo:
        return lo
    if n > hi:
        return hi
    return n


def normalize_resource_limits(raw: dict[str, Any] | None) -> dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    docker_in = src.get("docker") if isinstance(src.get("docker"), dict) else {}
    process_in = src.get("process") if isinstance(src.get("process"), dict) else {}
    desktop_in = src.get("desktop") if isinstance(src.get("desktop"), dict) else {}
    d0 = _DEFAULTS["docker"]
    p0 = _DEFAULTS["process"]
    k0 = _DEFAULTS["desktop"]

    # Accept legacy memory strings like "512m" / "1g" via memory field.
    def _mem_mb(section: dict[str, Any], default: int) -> int:
        if section.get("memory_mb") is not None:
            return _clamp_int(section.get("memory_mb"), default=default, lo=0, hi=65536)
        mem = section.get("memory")
        if mem is None or mem == "":
            return default
        parsed = parse_memory_to_mb(str(mem))
        return parsed if parsed is not None else default

    docker = {
        "cpus": _clamp_float(docker_in.get("cpus", d0["cpus"]), default=float(d0["cpus"]), lo=0.0, hi=64.0),
        "memory_mb": _mem_mb(docker_in, int(d0["memory_mb"])),
        "pids_limit": _clamp_int(
            docker_in.get("pids_limit", d0["pids_limit"]),
            default=int(d0["pids_limit"]),
            lo=0,
            hi=100_000,
        ),
        "max_containers_per_workspace": _clamp_int(
            docker_in.get("max_containers_per_workspace", d0["max_containers_per_workspace"]),
            default=int(d0["max_containers_per_workspace"]),
            lo=0,
            hi=500,
        ),
        "block_public_db_ports": bool(
            docker_in.get("block_public_db_ports", d0["block_public_db_ports"])
        ),
    }
    process = {
        "cpu_percent": _clamp_int(
            process_in.get("cpu_percent", p0["cpu_percent"]),
            default=int(p0["cpu_percent"]),
            lo=0,
            hi=6400,
        ),
        "memory_mb": _mem_mb(process_in, int(p0["memory_mb"])),
    }
    desktop = {
        "cpus": _clamp_float(
            desktop_in.get("cpus", k0["cpus"]),
            default=float(k0["cpus"]),
            lo=0.0,
            hi=64.0,
        ),
        "memory_mb": _mem_mb(desktop_in, int(k0["memory_mb"])),
    }
    return {
        "enabled": bool(src.get("enabled", _DEFAULTS["enabled"])),
        "docker": docker,
        "process": process,
        "desktop": desktop,
    }


def load_resource_limits() -> dict[str, Any]:
    path = resource_limits_path()
    if not path.is_file():
        return normalize_resource_limits(None)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Invalid resource_limits.json at %s — using defaults", path)
        return normalize_resource_limits(None)
    if not isinstance(raw, dict):
        return normalize_resource_limits(None)
    return normalize_resource_limits(raw)


def save_resource_limits(updates: dict[str, Any] | None) -> dict[str, Any]:
    from core.global_config import ensure_global_dir

    ensure_global_dir()
    current = load_resource_limits()
    merged = _deep_merge(current, updates if isinstance(updates, dict) else {})
    payload = normalize_resource_limits(merged)
    path = resource_limits_path()
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def parse_memory_to_mb(value: str | int | float | None) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value).strip().lower().replace(" ", "")
    if not text:
        return None
    if text.isdigit():
        return int(text)
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(b|k|kb|ki|m|mb|mi|g|gb|gi)?", text)
    if not m:
        return None
    amount = float(m.group(1))
    unit = m.group(2) or "m"
    mult = {
        "b": 1 / (1024 * 1024),
        "k": 1 / 1024,
        "kb": 1 / 1024,
        "ki": 1 / 1024,
        "m": 1,
        "mb": 1,
        "mi": 1,
        "g": 1024,
        "gb": 1024,
        "gi": 1024,
    }.get(unit, 1)
    return max(0, int(amount * mult))


def memory_mb_to_docker(memory_mb: int | None) -> str | None:
    if not memory_mb or memory_mb <= 0:
        return None
    if memory_mb % 1024 == 0 and memory_mb >= 1024:
        return f"{memory_mb // 1024}g"
    return f"{int(memory_mb)}m"


def memory_mb_to_bytes(memory_mb: int | None) -> int | None:
    if not memory_mb or memory_mb <= 0:
        return None
    return int(memory_mb) * 1024 * 1024


def docker_update_args(limits: dict[str, Any] | None = None) -> list[str]:
    """CLI args for ``docker update`` (without container id)."""
    cfg = limits or load_resource_limits()
    if not cfg.get("enabled"):
        return []
    docker = cfg.get("docker") or {}
    args: list[str] = []
    cpus = float(docker.get("cpus") or 0)
    if cpus > 0:
        args.extend(["--cpus", f"{cpus:g}"])
    mem = memory_mb_to_docker(int(docker.get("memory_mb") or 0))
    if mem:
        args.extend(["--memory", mem, "--memory-swap", mem])
    pids = int(docker.get("pids_limit") or 0)
    if pids > 0:
        args.extend(["--pids-limit", str(pids)])
    return args


def desktop_cpus_value(limits: dict[str, Any] | None = None) -> str:
    cfg = limits or load_resource_limits()
    if not cfg.get("enabled"):
        return "1.5"
    cpus = float((cfg.get("desktop") or {}).get("cpus") or 0)
    if cpus <= 0:
        return "0"  # docker treats 0 poorly — use large
    return f"{cpus:g}"


def desktop_memory_value(limits: dict[str, Any] | None = None) -> str:
    cfg = limits or load_resource_limits()
    if not cfg.get("enabled"):
        return "2g"
    mem = memory_mb_to_docker(int((cfg.get("desktop") or {}).get("memory_mb") or 0))
    return mem or "2g"


def process_preexec_fn(limits: dict[str, Any] | None = None):
    """Return a preexec_fn that applies RLIMIT_AS, or None."""
    cfg = limits or load_resource_limits()
    if not cfg.get("enabled"):
        return None
    mem_mb = int((cfg.get("process") or {}).get("memory_mb") or 0)
    mem_bytes = memory_mb_to_bytes(mem_mb)
    if not mem_bytes:
        return None

    def _preexec() -> None:
        try:
            import resource

            # Soft address-space cap (approx RSS+mmap). Not a perfect RAM limit
            # but stops runaway allocations on Linux.
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except Exception:
            pass

    return _preexec


def wrap_process_argv(argv: list[str], limits: dict[str, Any] | None = None) -> list[str]:
    """Optionally wrap argv with systemd-run for CPUQuota / MemoryMax."""
    cfg = limits or load_resource_limits()
    if not cfg.get("enabled") or not argv:
        return list(argv)
    proc = cfg.get("process") or {}
    cpu_percent = int(proc.get("cpu_percent") or 0)
    mem_mb = int(proc.get("memory_mb") or 0)
    if cpu_percent <= 0 and mem_mb <= 0:
        return list(argv)
    if not shutil.which("systemd-run"):
        return list(argv)
    # Prefer system scope when running as a service account.
    props: list[str] = ["--collect", "--quiet"]
    if cpu_percent > 0:
        props.extend(["-p", f"CPUQuota={cpu_percent}%"])
    if mem_mb > 0:
        props.extend(["-p", f"MemoryMax={mem_mb}M", "-p", f"MemoryHigh={max(1, mem_mb // 2)}M"])
    # Try --user first is fragile without lingering; use system scope (needs privileges)
    # so fall back to plain argv when systemd-run fails at spawn time.
    return ["systemd-run", "--scope", *props, "--", *argv]


def find_public_db_port_publishes(compose_text: str) -> list[str]:
    """Return human-readable host publishes of DB ports to non-loopback."""
    findings: list[str] = []
    for m in _PORT_PUBLISH_RE.finditer(compose_text or ""):
        host = (m.group("host") or "0.0.0.0").strip()
        host_port = int(m.group("host_port"))
        container_port = int(m.group("container_port"))
        if host_port not in _DB_PORTS and container_port not in _DB_PORTS:
            continue
        if host in {"127.0.0.1", "localhost", "::1", "[::1]"}:
            continue
        # bare "5432:5432" implies 0.0.0.0
        findings.append(f"{host}:{host_port}->{container_port}")
    return findings


def assert_compose_public_db_policy(compose_path: Path, limits: dict[str, Any] | None = None) -> None:
    cfg = limits or load_resource_limits()
    if not cfg.get("enabled"):
        return
    docker = cfg.get("docker") or {}
    if not docker.get("block_public_db_ports"):
        return
    try:
        text = compose_path.read_text(encoding="utf-8")
    except OSError:
        return
    bad = find_public_db_port_publishes(text)
    if not bad:
        return
    raise ValueError(
        "Public database port publish blocked by Studio resource policy: "
        + ", ".join(bad)
        + ". Bind to localhost only, e.g. \"127.0.0.1:5432:5432\", "
        "or disable block_public_db_ports in Admin → Resource limits."
    )
