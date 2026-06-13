"""Interactive gateway configuration for a Holix profile."""

from __future__ import annotations

import os
from dataclasses import dataclass

from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from cli.core import ProfileManager
from cli.services.gateway_state import list_running_states
from cli.utils.ports import is_port_available, resolve_listen_port
from cli.utils.rich_console import console, print_error, print_info, print_success, print_warning


@dataclass(frozen=True, slots=True)
class GatewayProfileConfig:
    profile: str
    host: str
    port: int
    require_auth: bool
    with_docs: bool
    docs_host: str
    docs_port: int
    env_path: str


def _env_bool_value(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int_value(raw: str | None, default: int) -> int:
    if not raw or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


def _profile_env_file(profile: str):
    from cli.core import profiles_dir

    return profiles_dir() / profile / ".env"


def _dotenv_from_path(path, *, profile: str | None = None) -> dict[str, str]:
    from core.crypto.profile_files import dotenv_values_for_path

    return {
        key: str(value)
        for key, value in dotenv_values_for_path(path, profile=profile).items()
        if value is not None and str(value).strip()
    }


def _profile_env_from_files(profile: str) -> dict[str, str]:
    """Merge global + profile ``.env`` files (profile wins); no shell overrides."""
    from core.global_config import global_env_path

    merged: dict[str, str] = {}
    global_path = global_env_path()
    if global_path.is_file():
        merged.update(_dotenv_from_path(global_path))
    profile_path = _profile_env_file(profile)
    if profile_path.is_file():
        merged.update(_dotenv_from_path(profile_path, profile=profile))
    return merged


def _merged_profile_env(profile: str) -> dict[str, str]:
    """Merge global + profile ``.env``; shell exports override files for this process."""
    merged = _profile_env_from_files(profile)
    for key in list(merged):
        shell_val = os.getenv(key)
        if shell_val is not None:
            merged[key] = shell_val
    return merged


def load_effective_gateway_config(profile: str) -> GatewayProfileConfig:
    """Return effective gateway settings (global + profile env, shell overrides)."""
    from config import settings

    env = _merged_profile_env(profile)
    return GatewayProfileConfig(
        profile=profile,
        host=env.get("HOLIX_GATEWAY_HOST", settings.gateway_host),
        port=_env_int_value(env.get("HOLIX_GATEWAY_PORT"), settings.gateway_port),
        require_auth=_env_bool_value(env.get("HOLIX_REQUIRE_AUTH")) or settings.is_production,
        with_docs=_env_bool_value(env.get("HOLIX_GATEWAY_WITH_DOCS"))
        or _env_bool_value(env.get("HOLIX_GATEWAY_DOCS"))
        or settings.gateway_with_docs,
        docs_host=env.get("HOLIX_DOCS_HOST", settings.docs_host),
        docs_port=_env_int_value(env.get("HOLIX_DOCS_PORT"), settings.docs_port),
        env_path=str(_profile_env_file(profile)),
    )


def _global_gateway_port_default() -> int:
    from core.global_config import global_env_path

    from config import settings

    default = settings.gateway_port
    path = global_env_path()
    if not path.is_file():
        return default
    return _env_int_value(_dotenv_from_path(path).get("HOLIX_GATEWAY_PORT"), default)


def list_configured_gateway_ports(*, exclude_profile: str | None = None) -> dict[str, int]:
    """Map profile name → configured HOLIX_GATEWAY_PORT (profile override or global default)."""
    global_port = _global_gateway_port_default()
    out: dict[str, int] = {}
    for name in ProfileManager().list_profiles():
        if exclude_profile and name == exclude_profile:
            continue
        env_map = _profile_env_from_files(name)
        raw = env_map.get("HOLIX_GATEWAY_PORT")
        out[name] = _env_int_value(raw, global_port) if raw else global_port
    return out


def suggest_gateway_port(
    host: str,
    *,
    profile: str,
    base_port: int = 8000,
) -> int:
    """Pick a listen port free on ``host`` and not assigned to another profile."""
    used_by_profile = set(list_configured_gateway_ports(exclude_profile=profile).values())
    running_ports = {state.port for state in list_running_states() if state.profile != profile}

    candidate = base_port
    for _ in range(200):
        if candidate in used_by_profile or candidate in running_ports:
            candidate += 1
            continue
        if is_port_available(host, candidate):
            return candidate
        candidate += 1
    return resolve_listen_port(host, base_port)


def show_gateway_config(profile: str) -> None:
    """Print effective gateway settings for a profile."""
    cfg = load_effective_gateway_config(profile)
    conflicts = _port_conflicts(cfg.profile, cfg.port)

    table = Table(title=f"Gateway configuration ({profile})")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Host", cfg.host)
    table.add_row("Port", str(cfg.port))
    table.add_row("Require auth", "yes" if cfg.require_auth else "no")
    table.add_row("With docs", "yes" if cfg.with_docs else "no")
    if cfg.with_docs:
        table.add_row("Docs host", cfg.docs_host)
        table.add_row("Docs port", str(cfg.docs_port))
    table.add_row("Env file", cfg.env_path)
    console.print()
    console.print(table)
    if conflicts:
        console.print()
        print_warning("Port conflicts with other profiles:")
        for name, port in conflicts:
            print_info(f"  {name}: {port}")
    console.print()


def _port_conflicts(profile: str, port: int) -> list[tuple[str, int]]:
    return [
        (name, other_port)
        for name, other_port in list_configured_gateway_ports(exclude_profile=profile).items()
        if other_port == port
    ]


def _upsert_env_var(path, key: str, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"{key}="
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    lines = [line for line in lines if not line.startswith(prefix)]
    lines.append(f"{prefix}{value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value


def _remove_env_vars(path, *keys: str) -> None:
    if not path.is_file():
        return
    prefixes = {f"{key}=" for key in keys}
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not any(line.startswith(prefix) for prefix in prefixes)
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    for key in keys:
        os.environ.pop(key, None)


def _save_gateway_env(profile: str, cfg: GatewayProfileConfig) -> None:
    path = _profile_env_file(profile)
    _upsert_env_var(path, "HOLIX_GATEWAY_HOST", cfg.host)
    _upsert_env_var(path, "HOLIX_GATEWAY_PORT", str(cfg.port))
    _upsert_env_var(path, "HOLIX_REQUIRE_AUTH", "true" if cfg.require_auth else "false")
    if cfg.with_docs:
        _upsert_env_var(path, "HOLIX_GATEWAY_WITH_DOCS", "1")
        _upsert_env_var(path, "HOLIX_DOCS_HOST", cfg.docs_host)
        _upsert_env_var(path, "HOLIX_DOCS_PORT", str(cfg.docs_port))
    else:
        _remove_env_vars(
            path,
            "HOLIX_GATEWAY_WITH_DOCS",
            "HOLIX_GATEWAY_DOCS",
            "HOLIX_DOCS_HOST",
            "HOLIX_DOCS_PORT",
        )


def run_gateway_configure(*, profile: str, start_after: bool = False) -> None:
    """Interactive wizard: bind address, port, auth, optional docs companion."""
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]Gateway — настройка профиля[/bold cyan]\n\n"
            "Каждый профиль Holix может запускать свой gateway (API + Telegram + cron).\n"
            "Для нескольких профилей задайте [bold]разные порты[/bold].",
            border_style="cyan",
        )
    )

    current = load_effective_gateway_config(profile)
    conflicts = _port_conflicts(profile, current.port)
    if conflicts:
        print_warning(
            f"Текущий порт {current.port} совпадает с: "
            + ", ".join(f"{n} ({p})" for n, p in conflicts)
        )

    host = Prompt.ask("Host (bind address)", default=current.host).strip() or current.host

    suggested = suggest_gateway_port(host, profile=profile, base_port=current.port)
    if suggested != current.port:
        print_info(f"Свободный порт для этого профиля: {suggested}")

    port_raw = Prompt.ask("Port", default=str(suggested)).strip()
    try:
        port = int(port_raw)
    except ValueError:
        print_error(f"Некорректный порт: {port_raw}")
        raise SystemExit(1)
    if port < 1 or port > 65535:
        print_error("Порт должен быть в диапазоне 1–65535")
        raise SystemExit(1)

    new_conflicts = _port_conflicts(profile, port)
    if new_conflicts:
        names = ", ".join(f"{n} ({p})" for n, p in new_conflicts)
        print_warning(f"Порт {port} уже настроен у профилей: {names}")
        if not Confirm.ask("Всё равно использовать этот порт?", default=False):
            raise SystemExit(1)

    if not is_port_available(host, port):
        print_warning(f"Порт {port} занят на {host} — gateway подберёт следующий свободный при старте")

    require_auth = Confirm.ask(
        "Требовать API key для /v1/*?",
        default=current.require_auth,
    )
    with_docs = Confirm.ask(
        "Запускать сайт документации вместе с gateway?",
        default=current.with_docs,
    )
    docs_host = current.docs_host
    docs_port = current.docs_port
    if with_docs:
        docs_host = Prompt.ask("Docs host", default=current.docs_host).strip() or current.docs_host
        docs_port_raw = Prompt.ask("Docs port", default=str(current.docs_port)).strip()
        try:
            docs_port = int(docs_port_raw)
        except ValueError:
            print_error(f"Некорректный порт документации: {docs_port_raw}")
            raise SystemExit(1)

    updated = GatewayProfileConfig(
        profile=profile,
        host=host,
        port=port,
        require_auth=require_auth,
        with_docs=with_docs,
        docs_host=docs_host,
        docs_port=docs_port,
        env_path=current.env_path,
    )
    _save_gateway_env(profile, updated)
    print_success(f"Настройки gateway сохранены в {updated.env_path}")
    print_info(f"URL: http://{host if host not in ('0.0.0.0', '::') else '127.0.0.1'}:{port}/health")

    if start_after:
        from cli.services.gateway_daemon import start_gateway_daemon

        print_info("Запуск gateway…")
        start_gateway_daemon(
            host,
            port,
            profile=profile,
            with_docs=with_docs,
            docs_host=docs_host,
            docs_port=docs_port,
        )
    else:
        print_info(f"Запуск: holix -p {profile} gateway start")