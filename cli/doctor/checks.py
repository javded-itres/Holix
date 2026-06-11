"""Deterministic Helix doctor checks."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

import httpx
import yaml
from core.models.discovery import ModelDiscovery
from core.models.manager import ModelManager
from core.platform_compat import (
    IS_WINDOWS,
    clipboard_tools_available,
    helix_home_display,
    process_subagents_supported,
    psutil_available,
)

from cli.core import HELIX_HOME, LOGS_DIR, PROFILES_DIR, ProfileConfig, ProfileManager
from cli.doctor.findings import DoctorFinding, Severity
from cli.services.gateway_daemon import _running_state
from cli.services.gateway_state import is_process_alive, load_state
from cli.utils.profile import profile_cli_prefix


async def run_all_checks(profile: str, *, skip_llm_check: bool = False) -> list[DoctorFinding]:
    findings: list[DoctorFinding] = []
    manager = ProfileManager()

    findings.extend(_check_helix_home())
    findings.extend(_check_platform())
    findings.extend(_check_profile_config(profile, manager))
    if not skip_llm_check:
        findings.extend(await _check_llm(profile, manager))
    findings.extend(_check_gateway(profile))
    findings.extend(_check_telegram(profile))
    findings.extend(_check_env_file())
    findings.extend(_check_security_settings())
    findings.extend(_check_stray_project_data(profile, manager))

    return findings


def _check_security_settings() -> list[DoctorFinding]:
    from config import settings

    out: list[DoctorFinding] = []
    if settings.is_production and not settings.api_key_pepper:
        out.append(
            DoctorFinding(
                code="security.missing_api_key_pepper",
                severity=Severity.ERROR.value,
                title="API key pepper not set",
                detail="HELIX_API_KEY_PEPPER is required in production",
                recommendation="Set HELIX_API_KEY_PEPPER to a long random secret in .env",
            )
        )
    if not settings.effective_require_auth:
        out.append(
            DoctorFinding(
                code="security.gateway_auth_disabled",
                severity=Severity.WARNING.value,
                title="Gateway authentication disabled",
                detail="HELIX_REQUIRE_AUTH=false and not in production mode",
                recommendation="Set HELIX_REQUIRE_AUTH=true before exposing gateway publicly",
            )
        )
    if settings.is_production and "*" in settings.cors_origins:
        out.append(
            DoctorFinding(
                code="security.cors_wildcard",
                severity=Severity.ERROR.value,
                title="CORS allows all origins in production",
                detail="HELIX_CORS_ORIGINS must not be * in production",
                recommendation="Set HELIX_CORS_ORIGINS to explicit origins",
            )
        )
    if settings.enable_code_executor and settings.is_production:
        out.append(
            DoctorFinding(
                code="security.code_executor_enabled",
                severity=Severity.WARNING.value,
                title="Python code executor enabled in production",
                detail="Agent can run arbitrary Python snippets",
                recommendation="Set HELIX_ENABLE_CODE_EXECUTOR=false in production",
            )
        )
    if settings.is_production and not os.getenv("HELIX_TUI_WEB_TOKEN", "").strip():
        out.append(
            DoctorFinding(
                code="security.tui_web_token_unset",
                severity=Severity.INFO.value,
                title="Web TUI token not configured",
                detail="HELIX_TUI_WEB_TOKEN is empty",
                recommendation=(
                    "Before `helix tui --web`, set HELIX_TUI_WEB_TOKEN or pass --token. "
                    "Never bind 0.0.0.0 without --allow-lan and a strong token."
                ),
            )
        )
    return out


def _check_platform() -> list[DoctorFinding]:
    out: list[DoctorFinding] = []
    home = helix_home_display()
    out.append(
        DoctorFinding(
            code="platform.info",
            severity=Severity.INFO.value,
            title=f"Platform: {sys.platform}",
            detail=f"Helix data: {home}",
            recommendation=(
                "Override with HELIX_HOME if needed. "
                "On Windows, OS-process sub-agents use async mode automatically."
                if IS_WINDOWS
                else "Set HELIX_HOME or XDG_DATA_HOME to relocate profile data."
            ),
        )
    )
    if IS_WINDOWS and not process_subagents_supported():
        out.append(
            DoctorFinding(
                code="platform.subagent_process",
                severity=Severity.INFO.value,
                title="Sub-agent process mode unavailable on Windows",
                detail="PROCESS mode falls back to in-process async execution",
                recommendation="Use async sub-agents (default) on Windows",
            )
        )
    if IS_WINDOWS and not psutil_available():
        out.append(
            DoctorFinding(
                code="platform.psutil_missing",
                severity=Severity.INFO.value,
                title="psutil not installed (optional)",
                detail="Gateway/subprocess cleanup uses taskkill; psutil improves process-tree termination",
                recommendation="Install: uv sync --extra windows",
            )
        )
    if not clipboard_tools_available():
        out.append(
            DoctorFinding(
                code="platform.clipboard_missing",
                severity=Severity.INFO.value,
                title="System clipboard tools not found",
                detail="TUI /copy may fall back to terminal OSC 52 only",
                recommendation=(
                    "On Windows install PowerShell or ensure clip.exe is on PATH; "
                    "on Linux install wl-clipboard or xclip"
                ),
            )
        )
    if IS_WINDOWS:
        out.append(
            DoctorFinding(
                code="platform.windows_terminal",
                severity=Severity.INFO.value,
                title="Terminal tool uses Windows shell",
                detail="Whitelist allows cmd builtins (dir, type, where); Unix commands (ls, grep) are blocked",
                recommendation=(
                    "Use dir/type/where instead of ls/cat, or extend "
                    "HELIX_TERMINAL_WHITELIST_EXTRA in .env"
                ),
            )
        )
    for tool, label in (
        ("node", "Node.js (MCP npx servers)"),
        ("npx", "npx (MCP package runner)"),
        ("uv", "uv (Python tooling)"),
        ("uvx", "uvx (MCP Python servers)"),
        ("git", "git (hub / MCP git installs)"),
    ):
        if shutil.which(tool) is None:
            out.append(
                DoctorFinding(
                    code=f"platform.missing_{tool}",
                    severity=Severity.INFO.value,
                    title=f"{label} not found in PATH",
                    detail=f"`{tool}` is not available",
                    recommendation=f"Install {label} or add it to PATH for full MCP/hub support",
                )
            )
    return out


def _check_helix_home() -> list[DoctorFinding]:
    out: list[DoctorFinding] = []
    try:
        HELIX_HOME.mkdir(parents=True, exist_ok=True)
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        test = HELIX_HOME / ".doctor_write_test"
        test.write_text("ok", encoding="utf-8")
        test.unlink()
    except OSError as e:
        out.append(
            DoctorFinding(
                code="helix_home.not_writable",
                severity=Severity.ERROR.value,
                title="Helix home not writable",
                detail=str(e),
                recommendation=f"Fix permissions on {HELIX_HOME} or set a writable HELIX data location.",
                fix_id=None,
            )
        )
    return out


def _check_profile_config(profile: str, manager: ProfileManager) -> list[DoctorFinding]:
    out: list[DoctorFinding] = []
    config_path = manager.get_profile_dir(profile) / "config.yaml"

    if not config_path.exists():
        out.append(
            DoctorFinding(
                code="profile.missing",
                severity=Severity.ERROR.value,
                title=f"Profile '{profile}' not found",
                detail=f"No config at {config_path}",
                recommendation=f"Run: helix doctor --fix -p {profile}  (creates profile layout)",
                fix_id="create_profile",
                context={"profile": profile},
            )
        )
        return out

    raw: Any
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        out.append(
            DoctorFinding(
                code="profile.invalid_yaml",
                severity=Severity.ERROR.value,
                title="Invalid profile YAML",
                detail=str(e),
                recommendation="Run: helix doctor --fix  (LLM will attempt to repair config.yaml)",
                context={"path": str(config_path), "raw_error": str(e)},
            )
        )
        return out

    if not isinstance(raw, dict):
        out.append(
            DoctorFinding(
                code="profile.invalid_structure",
                severity=Severity.ERROR.value,
                title="Profile config must be a YAML mapping",
                detail=f"Got {type(raw).__name__}",
                recommendation="Run: helix doctor --fix  to regenerate a valid config.",
                context={"path": str(config_path)},
            )
        )
        return out

    try:
        cfg = ProfileConfig(**raw)
    except Exception as e:
        out.append(
            DoctorFinding(
                code="profile.validation_error",
                severity=Severity.ERROR.value,
                title="Profile config validation failed",
                detail=str(e),
                recommendation="Run: helix doctor --fix  to repair fields via LLM.",
                context={"path": str(config_path), "validation_error": str(e)},
            )
        )
        return out

    cfg.profile_name = profile
    out.extend(_check_profile_paths(cfg, profile, manager))
    out.extend(_check_providers(cfg, profile))
    out.extend(_check_skill_assignments(cfg, manager))
    out.extend(_check_hub_lockfile(cfg))
    out.extend(_check_mcp_env_placeholders(cfg))
    return out


def _check_hub_lockfile(cfg: ProfileConfig) -> list[DoctorFinding]:
    """Warn when hub-lock.json entries point at missing bundle directories."""
    skills_dir = Path(cfg.skills_dir or "")
    if not skills_dir.exists():
        return []
    lock_path = skills_dir.parent / "hub-lock.json"
    if not lock_path.exists():
        return []

    from core.hub.lockfile import HubLockfile

    broken: list[str] = []
    for entry in HubLockfile(lock_path).list_entries():
        if not Path(entry.install_path).exists():
            broken.append(entry.id)

    if not broken:
        return []
    return [
        DoctorFinding(
            code="hub.missing_bundle",
            severity=Severity.WARNING.value,
            title="Hub lockfile references missing install paths",
            detail=", ".join(broken[:15]),
            recommendation="Remove stale entries: `helix hub remove <id>` or reinstall: `helix hub update <id>`.",
        )
    ]


def _check_mcp_env_placeholders(cfg: ProfileConfig) -> list[DoctorFinding]:
    """Warn when MCP config still contains unresolved ${VAR} placeholders."""

    from core.config_utils import _INLINE_ENV_REF

    servers = getattr(cfg, "mcp_servers", None) or {}
    if not servers:
        return []

    unresolved: list[str] = []
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        blob = str(spec)
        for m in _INLINE_ENV_REF.finditer(blob):
            var = m.group(2) or m.group(1)
            if var not in os.environ:
                unresolved.append(f"{name}:${var}")

    if not unresolved:
        return []
    return [
        DoctorFinding(
            code="mcp.unresolved_env",
            severity=Severity.WARNING.value,
            title="MCP servers reference unset environment variables",
            detail=", ".join(unresolved[:15]),
            recommendation="Export the variables in your shell or .env, then helix doctor again.",
        )
    ]


def _check_skill_assignments(
    cfg: ProfileConfig, manager: ProfileManager
) -> list[DoctorFinding]:
    """Warn when skill_assignments reference missing skill files."""
    out: list[DoctorFinding] = []
    assigns = getattr(cfg, "skill_assignments", None) or {}
    if not assigns:
        return out

    skills_dir = Path(
        cfg.skills_dir or manager.get_profile_dir(cfg.profile_name) / "data" / "skills"
    )
    if not skills_dir.exists():
        out.append(
            DoctorFinding(
                code="skills.assignments_no_dir",
                severity=Severity.WARNING.value,
                title="skill_assignments set but skills directory missing",
                detail=str(skills_dir),
                recommendation="Run `helix hub install` or create skills under the profile skills dir.",
            )
        )
        return out

    from core.hub.normalize import discover_skill_files, parse_skill_file

    known: set[str] = set()
    for sf in discover_skill_files(skills_dir):
        parsed = parse_skill_file(sf)
        if parsed and parsed.get("name"):
            known.add(parsed["name"])
        elif sf.name == "SKILL.md":
            known.add(sf.parent.name)
        else:
            known.add(sf.stem)

    missing: list[str] = []
    for slot, names in assigns.items():
        for name in names or []:
            if name not in known:
                missing.append(f"{slot}:{name}")

    if missing:
        out.append(
            DoctorFinding(
                code="skills.assignments_unknown",
                severity=Severity.WARNING.value,
                title="skill_assignments reference unknown skills",
                detail=", ".join(sorted(set(missing))[:20]),
                recommendation="Install skills via `helix hub install` or remove stale names from skill_assignments.",
            )
        )
    return out


def _check_profile_paths(
    cfg: ProfileConfig, profile: str, manager: ProfileManager
) -> list[DoctorFinding]:
    out: list[DoctorFinding] = []
    profile_dir = manager.get_profile_dir(profile)
    expected = {
        "data_dir": profile_dir / "data",
        "memory_db_path": profile_dir / "data" / "memory" / "memory.db",
        "vector_db_path": profile_dir / "data" / "memory" / "vector_db",
        "ltm_db_path": profile_dir / "data" / "memory" / "ltm.db",
        "langgraph_checkpoint_db_path": profile_dir / "data" / "memory" / "checkpoints.db",
        "skills_dir": profile_dir / "data" / "skills",
    }

    missing_dirs: list[str] = []
    for key, path in expected.items():
        current = getattr(cfg, key, None)
        if not current:
            out.append(
                DoctorFinding(
                    code=f"profile.missing_{key}",
                    severity=Severity.WARNING.value,
                    title=f"Missing {key} in config",
                    detail="Path not set in config.yaml",
                    recommendation="Run: helix doctor --fix  to set standard profile paths.",
                    fix_id="init_paths",
                    context={"profile": profile},
                )
            )
            continue
        p = Path(current)
        if key.endswith("_path") and key != "memory_db_path":
            if not p.exists():
                missing_dirs.append(str(p))
        elif key == "memory_db_path":
            if not p.parent.exists():
                missing_dirs.append(str(p.parent))

    if missing_dirs:
        out.append(
            DoctorFinding(
                code="profile.missing_directories",
                severity=Severity.WARNING.value,
                title="Profile data directories missing",
                detail=", ".join(missing_dirs),
                recommendation="Run: helix doctor --fix  to create directories.",
                fix_id="ensure_dirs",
                context={"profile": profile, "dirs": missing_dirs},
            )
        )
    return out


def _check_stray_project_data(
    profile: str, manager: ProfileManager
) -> list[DoctorFinding]:
    """Detect Helix runtime ``data/`` leaked into the current working directory."""
    from core.paths import is_stray_helix_data_dir

    out: list[DoctorFinding] = []
    cwd = Path.cwd().resolve()
    stray = cwd / "data"
    profile_data = manager.get_profile_dir(profile) / "data"
    if profile_data.resolve() == stray.resolve():
        return out
    if not is_stray_helix_data_dir(stray):
        return out

    out.append(
        DoctorFinding(
            code="project.stray_data_dir",
            severity=Severity.WARNING.value,
            title="Helix data directory in project root",
            detail=str(stray),
            recommendation=(
                "Run: helix doctor --fix  to move files into the active profile "
                f"and remove {stray}."
            ),
            fix_id="migrate_stray_data",
            context={"profile": profile, "stray_dir": str(stray)},
        )
    )
    return out


def _check_providers(cfg: ProfileConfig, profile: str) -> list[DoctorFinding]:
    out: list[DoctorFinding] = []
    if cfg.default_provider and cfg.providers:
        if cfg.default_provider not in cfg.providers:
            out.append(
                DoctorFinding(
                    code="profile.invalid_default_provider",
                    severity=Severity.ERROR.value,
                    title="default_provider not found",
                    detail=f"'{cfg.default_provider}' is not in providers",
                    recommendation=(
                        f"Run: helix models setup -p {profile}  or  helix doctor --fix"
                    ),
                    fix_id="fix_default_provider",
                    context={
                        "profile": profile,
                        "default_provider": cfg.default_provider,
                        "available": list(cfg.providers.keys()),
                    },
                )
            )
        else:
            pdata = cfg.providers[cfg.default_provider]
            if not pdata.get("base_url"):
                out.append(
                    DoctorFinding(
                        code="provider.missing_base_url",
                        severity=Severity.ERROR.value,
                        title=f"Provider '{cfg.default_provider}' missing base_url",
                        detail="Cannot connect to LLM without base_url",
                        recommendation="Run: helix models setup  or  helix doctor --fix",
                        context={"profile": profile, "provider": cfg.default_provider},
                    )
                )
            if not pdata.get("default_model"):
                out.append(
                    DoctorFinding(
                        code="provider.missing_default_model",
                        severity=Severity.WARNING.value,
                        title=f"Provider '{cfg.default_provider}' missing default_model",
                        detail="Model routing may fail",
                        recommendation="Set default_model in providers or run helix models setup",
                        context={"profile": profile, "provider": cfg.default_provider},
                    )
                )
    else:
        from core.models.profile_cleanup import profile_has_llm_config

        if not profile_has_llm_config(cfg):
            out.append(
                DoctorFinding(
                    code="profile.missing_llm",
                    severity=Severity.ERROR.value,
                    title="No LLM configuration",
                    detail="Set model/base_url or configure providers with default_provider",
                    recommendation=f"Run: helix models setup -p {profile}",
                    context={"profile": profile},
                )
            )
    return out


async def _check_llm(profile: str, manager: ProfileManager) -> list[DoctorFinding]:
    out: list[DoctorFinding] = []
    try:
        cfg = manager.load_profile(profile)
    except Exception:
        return out

    mm = ModelManager(cfg)
    mc = mm.get_default_model_config()
    if mc is None or not mc.base_url:
        return out

    base_url = mc.base_url.rstrip("/")
    api_key = mc.api_key or "dummy"
    model = mc.model

    try:
        ok = await ModelDiscovery.test_endpoint(
            base_url, api_key, metadata=mc.metadata or None
        )
    except Exception as e:
        ok = False
        err = str(e)
    else:
        err = ""

    if not ok:
        hint = "ollama serve" if "11434" in base_url else "check API URL and API key"
        out.append(
            DoctorFinding(
                code="llm.endpoint_unreachable",
                severity=Severity.ERROR.value,
                title="LLM endpoint unreachable",
                detail=f"{base_url} — {err or 'connection failed'}",
                recommendation=f"Start your LLM server ({hint}) or fix base_url in config.",
                context={"base_url": base_url, "profile": profile},
            )
        )
        return out

    try:
        models = await ModelDiscovery.discover_models(
            base_url, api_key, metadata=mc.metadata or None
        )
        ids = {m["id"] for m in models}
        if model and model not in ids and ids:
            out.append(
                DoctorFinding(
                    code="llm.model_not_found",
                    severity=Severity.ERROR.value,
                    title=f"Model '{model}' not available",
                    detail=f"Available: {', '.join(sorted(ids)[:8])}{'…' if len(ids) > 8 else ''}",
                    recommendation=(
                        f"Pull/install the model or run: helix models list -p {profile}\n"
                        "Then: helix doctor --fix  to pick a valid default model."
                    ),
                    fix_id="fix_model_from_list",
                    context={
                        "profile": profile,
                        "model": model,
                        "available": sorted(ids),
                        "base_url": base_url,
                        "api_key": api_key,
                    },
                )
            )
    except Exception as e:
        out.append(
            DoctorFinding(
                code="llm.discovery_failed",
                severity=Severity.WARNING.value,
                title="Could not list models",
                detail=str(e),
                recommendation="Endpoint responds but /models failed; verify OpenAI-compatible API.",
                context={"base_url": base_url},
            )
        )

    return out


def _check_gateway(profile: str) -> list[DoctorFinding]:
    out: list[DoctorFinding] = []
    from cli.services.gateway_state import log_path

    state = load_state(profile)
    if state and not is_process_alive(state.pid):
        out.append(
            DoctorFinding(
                code="gateway.stale_state",
                severity=Severity.WARNING.value,
                title="Stale gateway state file",
                detail=f"PID {state.pid} is not running (profile={profile})",
                recommendation=f"Run: helix doctor --fix  or  {profile_cli_prefix(profile)} gateway stop",
                fix_id="clear_gateway_state",
            )
        )
    running = _running_state(profile)
    if running:
        try:
            from cli.services.gateway_state import health_url

            resp = httpx.get(health_url(running), timeout=2.0)
            if resp.status_code != 200:
                out.append(
                    DoctorFinding(
                        code="gateway.unhealthy",
                        severity=Severity.WARNING.value,
                        title="Gateway not healthy",
                        detail=f"HTTP {resp.status_code} on port {running.port}",
                        recommendation=f"Run: {profile_cli_prefix(profile)} gateway reload  or check {log_path(profile)}",
                    )
                )
        except Exception as e:
            out.append(
                DoctorFinding(
                    code="gateway.health_unreachable",
                    severity=Severity.WARNING.value,
                    title="Gateway health check failed",
                    detail=str(e),
                    recommendation="Run: helix gateway reload",
                )
            )
    return out


def _check_telegram(profile: str) -> list[DoctorFinding]:
    out: list[DoctorFinding] = []
    try:
        from integrations.telegram.env_store import load_telegram_env_files

        load_telegram_env_files(profile)
    except Exception:
        pass

    from integrations.telegram.env_store import telegram_env_path

    token = os.getenv("TELEGRAM_BOT_TOKEN", os.getenv("HELIX_TELEGRAM_BOT_TOKEN", ""))
    if not token:
        out.append(
            DoctorFinding(
                code="telegram.not_configured",
                severity=Severity.INFO.value,
                title="Telegram not configured",
                detail=f"No bot token in environment or {telegram_env_path(profile)}",
                recommendation="Run: helix telegram setup",
            )
        )
        return out

    if ":" not in token or len(token) < 20:
        out.append(
            DoctorFinding(
                code="telegram.invalid_token",
                severity=Severity.ERROR.value,
                title="Telegram token looks invalid",
                detail="Expected format <bot_id>:<secret>",
                recommendation="Set TELEGRAM_BOT_TOKEN from @BotFather",
            )
        )

    allowed = os.getenv("HELIX_TELEGRAM_ALLOWED_USERS", "")
    allow_all = os.getenv("HELIX_TELEGRAM_ALLOW_ALL", "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    access_requests_raw = os.getenv("HELIX_TELEGRAM_ACCESS_REQUESTS", "").strip().lower()
    access_requests = access_requests_raw not in {"0", "false", "no", "off"}
    if not allowed.strip() and not allow_all:
        if access_requests:
            out.append(
                DoctorFinding(
                    code="telegram.access_requests",
                    severity=Severity.INFO.value,
                    title="Telegram access-request mode",
                    detail=(
                        "Allowlist is empty; new users must send /start and be approved "
                        "via `helix telegram requests`"
                    ),
                    recommendation="helix telegram requests list",
                )
            )
        else:
            out.append(
                DoctorFinding(
                    code="telegram.no_allowlist",
                    severity=Severity.ERROR.value,
                    title="Telegram allowlist empty",
                    detail="Bot will deny all users until HELIX_TELEGRAM_ALLOWED_USERS is set",
                    recommendation=(
                        "Enable HELIX_TELEGRAM_ACCESS_REQUESTS=true (default), "
                        "set HELIX_TELEGRAM_ALLOWED_USERS, "
                        "or HELIX_TELEGRAM_ALLOW_ALL=true for local development only"
                    ),
                )
            )
    elif allow_all:
        out.append(
            DoctorFinding(
                code="telegram.allow_all",
                severity=Severity.WARNING.value,
                title="Telegram allow-all mode enabled",
                detail="HELIX_TELEGRAM_ALLOW_ALL=true permits any Telegram user",
                recommendation="Disable in production; use HELIX_TELEGRAM_ALLOWED_USERS instead",
            )
        )
    return out


def _check_env_file() -> list[DoctorFinding]:
    out: list[DoctorFinding] = []
    env_path = HELIX_HOME / ".env"
    cwd_env = Path.cwd() / ".env"

    if not env_path.exists():
        hint = f"Create {env_path} (copy from .env.example in the repo or run helix doctor --fix)"
        if cwd_env.exists() and cwd_env.resolve() != env_path.resolve():
            hint = (
                f"Project .env found at {cwd_env}, but Helix reads {env_path}. "
                f"Copy or move settings to ~/.helix/.env"
            )
        out.append(
            DoctorFinding(
                code="env.missing",
                severity=Severity.INFO.value,
                title="~/.helix/.env not found",
                detail=hint,
                recommendation=f"cp .env.example {env_path}",
            )
        )
        return out

    try:
        env_path.read_text(encoding="utf-8")
    except OSError as e:
        out.append(
            DoctorFinding(
                code="env.unreadable",
                severity=Severity.WARNING.value,
                title="~/.helix/.env not readable",
                detail=str(e),
                recommendation=f"Fix file permissions on {env_path}",
            )
        )
    return out