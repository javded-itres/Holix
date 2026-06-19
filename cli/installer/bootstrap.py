"""First-run bootstrap: LLM provider + Telegram admin after install."""

from __future__ import annotations

import asyncio
import os
import re
import sys
from dataclasses import dataclass

from core.i18n.system_locale import apply_profile_locale, resolve_install_locale
from core.models.catalog import get_provider_preset, resolve_preset_base_url
from core.models.setup_helpers import (
    add_preset_to_config,
    discover_and_select_default_model,
    print_discovered_models_table,
    prompt_host_for_preset,
    resolve_api_key_for_preset,
    resolve_preset_api_key_interactive,
)
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from cli.core import ProfileManager, get_current_config, init_profile
from cli.installer.bootstrap_i18n import bootstrap_preset_labels, bt
from cli.utils.rich_console import console, print_error, print_info, print_success, print_warning


@dataclass(frozen=True, slots=True)
class BootstrapOptions:
    full_install: bool | None = None
    skip_llm: bool = False
    skip_search: bool = False
    skip_telegram: bool = False
    profile: str = "default"
    non_interactive: bool = False
    lang: str | None = None


def _is_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _upsert_env_var(path, key: str, value: str) -> None:
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if p.is_file():
        lines = p.read_text(encoding="utf-8").splitlines()
    found = False
    out: list[str] = []
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")
    content = "\n".join(out).rstrip() + "\n"
    p.write_text(content, encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass


def _global_env_path():
    from core.global_config import global_env_path

    return global_env_path()


def _store_api_key_in_env(preset_id: str, api_key: str) -> None:
    preset = get_provider_preset(preset_id)
    if preset is None or preset.auth_type == "none":
        return
    if not api_key or api_key.startswith("${"):
        return
    _upsert_env_var(_global_env_path(), preset.api_key_env, api_key)
    os.environ[preset.api_key_env] = api_key


def _resolve_lang(opts: BootstrapOptions) -> str:
    return resolve_install_locale(
        explicit=opts.lang,
        interactive=not opts.non_interactive and _is_tty(),
    )


def _apply_locales(lang: str, *, bot_profile: str, admin_profile: str | None = None) -> None:
    admin = (admin_profile or "admin").strip() or "admin"
    apply_profile_locale(lang, bot_profile, admin)
    print_info(
        bt(
            "locale_applied",
            lang,
            code=lang.upper(),
            profiles=", ".join({bot_profile, admin}),
        )
    )


async def _configure_llm(profile: str, lang: str) -> bool:
    from core.env_loader import init_holix_home

    init_holix_home()
    init_profile(profile)
    config = get_current_config()
    manager = ProfileManager()
    presets = bootstrap_preset_labels(lang)

    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]{bt('llm_title', lang)}[/bold cyan]\n\n{bt('llm_body', lang)}",
            border_style="cyan",
        )
    )

    if config.providers and config.default_provider:
        if not Confirm.ask(
            bt("llm_reconfigure", lang, name=config.default_provider),
            default=False,
        ):
            print_info(bt("llm_keep", lang))
            return True

    console.print()
    for idx, (_, label) in enumerate(presets, 1):
        console.print(f"  [cyan]{idx}[/cyan]. {label}")
    console.print(f"  [cyan]0[/cyan]. {bt('llm_skip_hint', lang)}")

    choice = Prompt.ask(
        bt("llm_choose", lang),
        choices=[str(i) for i in range(0, len(presets) + 1)],
        default="1",
    )
    if choice == "0":
        print_warning(bt("llm_not_configured", lang))
        return False

    preset_id, _ = presets[int(choice) - 1]
    preset = get_provider_preset(preset_id)
    if preset is None:
        print_error(bt("llm_unknown_preset", lang, id=preset_id))
        return False

    if preset.notes:
        console.print(f"[dim]{preset.notes}[/dim]")

    api_key = resolve_preset_api_key_interactive(preset, console=console)
    if preset.auth_type != "none" and not api_key.startswith("${") and api_key != preset.api_key_placeholder:
        _store_api_key_in_env(preset_id, api_key)

    host_arg: str | None = None
    if preset.configurable_host:
        host_arg = prompt_host_for_preset(preset, console=console)
        print_info(bt("llm_url", lang, url=host_arg))
    base_url = resolve_preset_base_url(preset, host=host_arg)
    store_key = resolve_api_key_for_preset(
        preset,
        custom_key=None if api_key.startswith("${") else api_key,
        use_env_value=True,
    )

    console.print(f"\n[bold]{bt('llm_probe', lang, name=preset.display_name)}[/bold]")
    probe_ok, models, err, default_model = await discover_and_select_default_model(
        preset,
        base_url,
        api_key,
        console=console,
        interactive=True,
    )
    if probe_ok and models:
        print_discovered_models_table(models, console=console, max_rows=15)
    elif not probe_ok:
        print_warning(bt("llm_probe_failed", lang, err=err or "error", url=base_url))
        if not Confirm.ask(bt("llm_save_anyway", lang), default=False):
            return False
        models = []
        default_model = preset.default_model

    ok, message = await add_preset_to_config(
        config,
        preset_id,
        api_key=store_key,
        host=host_arg,
        skip_probe=True,
        default_model=default_model,
        discovered_models=models if probe_ok else None,
    )
    if not ok:
        print_error(message)
        return False

    manager.save_profile(profile, config)
    print_success(message)
    return True


async def _configure_telegram(profile: str, lang: str) -> bool:
    from integrations.telegram.env_store import (
        apply_to_environ,
        load_telegram_env_files,
        read_telegram_env_values,
        save_telegram_env,
        token_looks_valid,
    )
    from integrations.telegram.setup_api import TelegramApiError, verify_bot_token

    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]{bt('telegram_title', lang)}[/bold cyan]\n\n{bt('telegram_body', lang)}",
            border_style="cyan",
        )
    )

    if not Confirm.ask(bt("telegram_configure", lang), default=True):
        print_info(bt("telegram_skipped", lang))
        return False

    try:
        import aiogram  # noqa: F401
    except ImportError:
        print_warning(bt("telegram_extra_missing", lang))
        return False

    existing = read_telegram_env_values(profile)
    default_token = existing.get("TELEGRAM_BOT_TOKEN", "")
    if default_token and Confirm.ask(bt("telegram_use_saved", lang), default=True):
        token = default_token
    else:
        token = Prompt.ask(bt("telegram_token_prompt", lang), password=True, default="").strip()

    if not token_looks_valid(token):
        print_error(bt("telegram_bad_token", lang))
        return False

    print_info(bt("telegram_verify", lang))
    try:
        me = await verify_bot_token(token)
    except TelegramApiError as exc:
        print_error(bt("telegram_api_error", lang, err=exc))
        return False

    username = me.get("username") or me.get("first_name") or "bot"
    print_success(bt("telegram_bot_ok", lang, name=username))

    admin_default = existing.get("HOLIX_TELEGRAM_ADMIN_USER_ID", "").strip()
    admin_raw = Prompt.ask(
        bt("telegram_admin_id", lang),
        default=admin_default or "",
    ).strip()
    if not re.fullmatch(r"\d{5,20}", admin_raw):
        print_error(bt("telegram_admin_id_bad", lang))
        return False

    admin_profile = Prompt.ask(
        bt("telegram_admin_profile", lang),
        default=existing.get("HOLIX_TELEGRAM_ADMIN_PROFILE", "admin") or "admin",
    ).strip() or "admin"

    voice_lang = "ru" if lang == "ru" else "en"
    values: dict[str, str] = {
        "TELEGRAM_BOT_TOKEN": token,
        "HOLIX_TELEGRAM_ACCESS_REQUESTS": "true",
        "HOLIX_TELEGRAM_ADMIN_USER_ID": admin_raw,
        "HOLIX_TELEGRAM_ADMIN_PROFILE": admin_profile,
        "HOLIX_TELEGRAM_ALLOWED_USERS": admin_raw,
        "HOLIX_TELEGRAM_PROFILE": profile,
        "HOLIX_TELEGRAM_VOICE_LANGUAGE": voice_lang,
    }
    path = save_telegram_env(values, profile=profile)
    apply_to_environ(values)
    load_telegram_env_files(profile)
    _apply_locales(lang, bot_profile=profile, admin_profile=admin_profile)
    print_success(bt("telegram_saved", lang, path=path))
    print_info(bt("telegram_open", lang, name=username))
    return True


def _configure_search(profile: str, lang: str) -> bool:
    from core.search.setup_helpers import configure_search_interactive
    from rich.prompt import Confirm

    console.print()
    if not Confirm.ask(bt("search_configure", lang), default=True):
        print_info(bt("search_skipped", lang))
        return False

    return configure_search_interactive(
        profile,
        lang=lang,
        allow_skip=True,
        title=bt("search_title", lang),
        body=bt("search_body", lang),
    )


def pypi_package_spec(*, full: bool) -> str:
    return "Holix[all]" if full else "Holix"


async def run_bootstrap_setup(options: BootstrapOptions | None = None) -> int:
    """Interactive post-install wizard."""
    opts = options or BootstrapOptions()
    from core.env_loader import init_holix_home

    init_holix_home()
    profile = (opts.profile or "default").strip() or "default"

    lang = _resolve_lang(opts)
    os.environ["HOLIX_BOOTSTRAP_LANG"] = lang
    init_profile(profile)
    _apply_locales(lang, bot_profile=profile, admin_profile="admin")

    console.print()
    console.print(
        Panel.fit(
            f"[bold green]{bt('welcome_title', lang)}[/bold green]\n\n{bt('welcome_body', lang)}",
            border_style="green",
        )
    )

    llm_ok = True
    if not opts.skip_llm:
        if opts.non_interactive or not _is_tty():
            print_info(bt("skip_llm_non_tty", lang))
        else:
            llm_ok = await _configure_llm(profile, lang)

    search_ok = True
    if not opts.skip_search:
        if opts.non_interactive or not _is_tty():
            print_info(bt("skip_search_non_tty", lang))
        else:
            search_ok = _configure_search(profile, lang)

    tg_ok = False
    if not opts.skip_telegram:
        if opts.non_interactive or not _is_tty():
            print_info(bt("skip_tg_non_tty", lang))
        else:
            tg_ok = await _configure_telegram(profile, lang)

    console.print()
    lines = [
        f"[bold]{bt('done_next', lang)}[/bold]",
        f"  {bt('done_doctor', lang)}",
        f"  {bt('done_tui', lang)}",
    ]
    if not llm_ok:
        lines.insert(1, f"  {bt('done_models', lang)}")
    if not search_ok:
        lines.append(f"  {bt('done_search', lang)}")
    if not tg_ok:
        lines.append(f"  {bt('done_telegram', lang)}")
    lines.append(f"  {bt('done_gateway', lang)}")
    console.print(Panel("\n".join(lines), title=bt("done_title", lang), border_style="green"))
    return 0 if llm_ok or opts.skip_llm else 1


def run_bootstrap_setup_sync(options: BootstrapOptions | None = None) -> int:
    return asyncio.run(run_bootstrap_setup(options))