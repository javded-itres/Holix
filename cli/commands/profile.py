"""Profile isolation commands: env, workspace jail, access keys."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import typer
from core.profile_keys import (
    profile_has_access_key,
    remove_profile_access_key,
    store_profile_access_key,
    verify_profile_access_key,
)

from cli.core import get_current_config, get_profile_manager, unlock_profile
from cli.utils.rich_console import print_error, print_info, print_success, print_warning

app = typer.Typer(help="Manage profile isolation (env, workspace jail, access keys)")
global_app = typer.Typer(help="Shared global settings inherited by profiles")
jail_app = typer.Typer(help="Restrict agent file/terminal access to one directory")
key_app = typer.Typer(help="Profile access keys (required to switch into protected profiles)")
whitelist_app = typer.Typer(help="Terminal command whitelist for the active profile")
crypto_app = typer.Typer(help="At-rest encryption for profile secrets (.env, memory); workspace stays plaintext")
quota_app = typer.Typer(help="Workspace storage quota (platform-managed)")
app.add_typer(global_app, name="global")
app.add_typer(jail_app, name="jail")
app.add_typer(key_app, name="key")
app.add_typer(whitelist_app, name="whitelist")
app.add_typer(crypto_app, name="crypto")
app.add_typer(quota_app, name="quota")


def _profile(ctx: typer.Context) -> str:
    return ctx.obj["profile"]


@app.command("delete")
def profile_delete(
    ctx: typer.Context,
    name: str | None = typer.Argument(
        None,
        help="Profile to delete (defaults to active profile)",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
    skip_notify: bool = typer.Option(
        False,
        "--skip-notify",
        help="Do not send Telegram notification to mapped users",
    ),
) -> None:
    """Delete a profile after notifying mapped Telegram users."""
    from core.profile.lifecycle import PROTECTED_PROFILES, delete_profile_with_notification

    profile = (name or _profile(ctx)).strip()
    if profile in PROTECTED_PROFILES:
        print_error(f"Cannot delete protected profile '{profile}'")
        raise typer.Exit(1)

    manager = get_profile_manager()
    if not manager.profile_exists(profile):
        print_error(f"Profile '{profile}' does not exist")
        raise typer.Exit(1)

    from core.profile.lifecycle import find_telegram_users_for_profile

    bindings = find_telegram_users_for_profile(profile)
    if bindings:
        uids = sorted({uid for _, uid in bindings})
        print_info(
            f"Telegram users mapped to '{profile}': {', '.join(str(u) for u in uids)}"
        )
    if not yes:
        confirmed = typer.confirm(
            f"Delete profile '{profile}' and notify users in Telegram?",
            default=False,
        )
        if not confirmed:
            print_info("Cancelled")
            raise typer.Exit(0)

    result = delete_profile_with_notification(
        profile,
        notify=not skip_notify,
        manager=manager,
    )
    if result.error:
        print_error(result.error)
        raise typer.Exit(1)

    if result.notified:
        print_success(
            f"Notified {len(result.notified)} user(s) in Telegram before deletion"
        )
    for uid, err in result.notify_failed:
        print_warning(f"Could not notify user {uid}: {err}")

    if result.deleted:
        print_success(f"Profile '{profile}' deleted")
    else:
        print_error(f"Profile '{profile}' was not deleted")
        raise typer.Exit(1)


@app.command("create")
def profile_create(
    name: str = typer.Argument(..., help="New profile name"),
    protect: bool = typer.Option(
        False,
        "--protect",
        help="Generate an access key (profile is open by default)",
    ),
    inherit_global: bool = typer.Option(
        True,
        "--inherit/--clean",
        help="Inherit shared global settings (default) or create a standalone profile",
    ),
) -> None:
    """Create a profile (inherits global settings by default; --clean for manual setup)."""
    from cli.utils.rich_console import print_panel

    manager = get_profile_manager()
    if manager.profile_exists(name):
        print_error(f"Profile '{name}' already exists")
        raise typer.Exit(1)

    manager.create_profile(name, with_access_key=protect, inherit_global=inherit_global)
    access_key = manager.pop_last_created_access_key()
    mode = "inherits global settings" if inherit_global else "standalone (clean)"
    print_success(f"Created profile '{name}' ({mode})")
    if inherit_global:
        from core.global_config import global_config_path, global_env_path

        print_info(f"Global config: [dim]{global_config_path()}[/dim]")
        print_info(f"Global env: [dim]{global_env_path()}[/dim]")
    if access_key:
        workspace = manager.get_profile_dir(name) / "workspace"
        print_panel(
            f"[cyan]{access_key}[/cyan]\n\n"
            "Save this key — it is shown only once.\n"
            f"Workspace jail: [dim]{workspace}[/dim]\n"
            f"Switch with: [bold]holix -p {name} --profile-key <key>[/bold]",
            title="Profile access key",
            border_style="yellow",
        )
    else:
        print_info(f"Switch freely: [bold]holix -p {name}[/bold]")
        print_info("Protect later: [cyan]holix -p {name} profile key init[/cyan]")


@global_app.command("show")
def global_show() -> None:
    """Show shared global configuration (models, MCP, behavior)."""
    import yaml
    from core.global_config import global_config_path, global_env_path, load_global_config_resolved

    from cli.utils.rich_console import print_panel

    data = load_global_config_resolved()
    body = yaml.dump(data, default_flow_style=False, allow_unicode=True)
    print_panel(
        body,
        title="Global configuration",
        subtitle=f"{global_config_path()}\nEnv: {global_env_path()}",
        border_style="cyan",
    )


@global_app.command("edit")
def global_edit(
    env: bool = typer.Option(False, "--env", help="Edit global .env instead of config.yaml"),
) -> None:
    """Open global settings in $EDITOR."""
    from core.global_config import (
        ensure_global_config,
        ensure_global_env_template,
    )

    editor = os.environ.get("EDITOR", "nano")
    if env:
        target = ensure_global_env_template()
    else:
        target = ensure_global_config()
    print_info(f"Opening {target} in {editor}...")
    try:
        subprocess.run([editor, str(target)], check=False)
        print_success("Global configuration updated")
        print_info("Profiles with --inherit pick up changes on next gateway/CLI start")
    except Exception as exc:
        print_error(f"Failed to open editor: {exc}")
        raise typer.Exit(1) from exc


@global_app.command("init")
def global_init(
    from_profile: str = typer.Option(
        "default",
        "--from-profile",
        help="Seed global config from an existing profile (empty = built-in defaults)",
    ),
) -> None:
    """Create or reset ``~/.holix/global/`` from defaults or an existing profile."""
    import yaml
    from core.global_config import (
        default_global_config_data,
        ensure_global_env_template,
        global_config_path,
        global_dir,
    )

    ensure_global_env_template()
    path = global_config_path()
    if from_profile:
        from core.global_config import strip_profile_only_keys

        from cli.core import ProfileManager

        manager = ProfileManager()
        if manager.profile_exists(from_profile):
            raw = yaml.safe_load((manager.get_profile_dir(from_profile) / "config.yaml").read_text(encoding="utf-8")) or {}
            data = strip_profile_only_keys(raw)
        else:
            print_warning(f"Profile '{from_profile}' not found — using built-in defaults")
            data = default_global_config_data()
    else:
        data = default_global_config_data()

    global_dir().mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.dump(data, handle, default_flow_style=False, allow_unicode=True)
    print_success(f"Global config written: {path}")
    print_info(f"Global env: {global_dir() / '.env'}")


@key_app.command("status")
def key_status(ctx: typer.Context) -> None:
    """Show whether the active profile requires an access key."""
    from cli.utils.rich_console import print_panel

    profile = _profile(ctx)
    if profile_has_access_key(profile):
        body = (
            "[green]Protected[/green]\n\n"
            "Switching into this profile requires its access key.\n"
            "Disable with: [cyan]holix profile key disable[/cyan]"
        )
        border = "green"
    else:
        body = (
            "[yellow]Open[/yellow]\n\n"
            "Free switching — no access key required.\n"
            "Protect with: [cyan]holix profile key init[/cyan]"
        )
        border = "yellow"
    print_panel(body, title=f"Profile access — {profile}", border_style=border)


@key_app.command("init")
def key_init(ctx: typer.Context) -> None:
    """Generate an access key for the active profile (shown once)."""
    from cli.utils.rich_console import print_panel

    profile = _profile(ctx)
    manager = get_profile_manager()
    if not manager.profile_exists(profile):
        print_error(f"Profile '{profile}' does not exist")
        raise typer.Exit(1)
    if profile_has_access_key(profile):
        print_warning(f"Profile '{profile}' already has an access key")
        raise typer.Exit(1)

    from cli.core import enable_profile_workspace_isolation

    access_key = store_profile_access_key(profile)
    workspace = enable_profile_workspace_isolation(manager, profile)
    print_success(f"Access key created for profile '{profile}'")
    print_panel(
        f"[cyan]{access_key}[/cyan]\n\n"
        "Save this key — it is shown only once.\n"
        f"Workspace jail: [dim]{workspace}[/dim]",
        title="Profile access key",
        border_style="yellow",
    )


@key_app.command("rotate")
def key_rotate(
    ctx: typer.Context,
    current_key: str = typer.Option(
        ...,
        "--current-key",
        prompt=True,
        hide_input=True,
        help="Current profile access key",
    ),
) -> None:
    """Replace the active profile access key."""
    from cli.utils.rich_console import print_panel

    profile = _profile(ctx)
    if not profile_has_access_key(profile):
        print_error("This profile has no access key yet. Use: holix profile key init")
        raise typer.Exit(1)
    if not verify_profile_access_key(profile, current_key):
        print_error("Current access key is invalid")
        raise typer.Exit(1)

    access_key = store_profile_access_key(profile)
    unlock_profile(profile, access_key)
    print_success(f"Access key rotated for profile '{profile}'")
    print_panel(
        f"[cyan]{access_key}[/cyan]\n\n"
        "Save this key — it is shown only once.",
        title="New profile access key",
        border_style="yellow",
    )


@key_app.command("disable")
def key_disable(
    ctx: typer.Context,
    current_key: str = typer.Option(
        ...,
        "--current-key",
        prompt=True,
        hide_input=True,
        help="Current profile access key",
    ),
) -> None:
    """Remove access key protection and allow free profile switching."""
    from cli import core as cli_core

    profile = _profile(ctx)
    if not profile_has_access_key(profile):
        print_warning(f"Profile '{profile}' is already open (no access key)")
        raise typer.Exit(0)
    if not verify_profile_access_key(profile, current_key):
        print_error("Current access key is invalid")
        raise typer.Exit(1)

    remove_profile_access_key(profile)
    cli_core._unlocked_profiles.discard(profile)
    print_success(f"Access key disabled for profile '{profile}'")
    print_info("Anyone can switch into this profile by name.")


@app.command("env")
def profile_env(
    ctx: typer.Context,
    edit: bool = typer.Option(False, "--edit", "-e", help="Open profile .env in editor"),
) -> None:
    """Show or edit the active profile's ``.env`` file."""
    from core.crypto.profile_crypto import ProfileCryptoLockedError, is_profile_encryption_enabled
    from core.env_loader import (
        edit_profile_env_file,
        ensure_profile_env_template,
        read_profile_env_map,
    )

    profile = _profile(ctx)
    path = ensure_profile_env_template(profile)

    if edit:
        if is_profile_encryption_enabled(profile):
            from core.crypto.unlock_context import get_profile_session_dek

            if get_profile_session_dek(profile) is None:
                print_warning(
                    "Profile is encrypted — unlock first: "
                    f"holix -p {profile} --unlock-key <key> profile env --edit"
                )
        editor = os.environ.get("EDITOR", "nano")
        print_info(f"Editing {path} (decrypted in a temporary file)…")
        try:
            edit_profile_env_file(profile, editor=editor)
        except ProfileCryptoLockedError as exc:
            print_error(str(exc))
            raise typer.Exit(1) from exc
        except OSError as exc:
            print_error(f"Failed to open editor: {exc}")
            raise typer.Exit(1) from exc
        print_success("Profile env updated")
        print_info("Restart gateway/Telegram or re-run CLI for changes to apply")
        return

    print_info(f"Profile: {profile}")
    print_info(f"Env file: {path}")
    try:
        values = read_profile_env_map(profile)
    except ProfileCryptoLockedError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc
    if values:
        for key in sorted(values):
            print_info(f"{key}={values[key]}")
    else:
        print_warning("Env file is empty, missing, or locked")


@jail_app.command("enable")
def jail_enable(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="Directory the agent must stay inside"),
) -> None:
    """Enable workspace jail for the active profile."""
    profile = _profile(ctx)
    manager = get_profile_manager()
    config = manager.load_profile(profile)

    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        print_error(f"Directory does not exist: {root}")
        raise typer.Exit(1)

    config.workspace_jail_enabled = True
    config.workspace_root = str(root)
    manager.save_profile(profile, config)
    print_success(f"Workspace jail enabled for profile '{profile}'")
    print_info(f"Root: {root}")
    print_info("File and terminal tools are restricted to this directory tree.")


@jail_app.command("disable")
def jail_disable(ctx: typer.Context) -> None:
    """Disable workspace jail for the active profile."""
    profile = _profile(ctx)
    manager = get_profile_manager()
    config = manager.load_profile(profile)

    config.workspace_jail_enabled = False
    config.workspace_root = None
    manager.save_profile(profile, config)
    print_success(f"Workspace jail disabled for profile '{profile}'")


@jail_app.command("status")
def jail_status(ctx: typer.Context) -> None:
    """Show workspace jail settings for the active profile."""
    from cli.utils.rich_console import print_panel

    config = get_current_config()
    if config.workspace_jail_enabled and config.workspace_root:
        body = (
            f"[green]Enabled[/green]\n"
            f"[cyan]Root:[/cyan] {config.workspace_root}\n\n"
            "The agent cannot read/write/run commands outside this directory."
        )
        border = "green"
    else:
        body = (
            "[yellow]Disabled[/yellow]\n\n"
            "Enable with: [cyan]holix profile jail enable /path/to/dir[/cyan]"
        )
        border = "yellow"

    print_panel(body, title=f"Workspace jail — {config.profile_name}", border_style=border)


@whitelist_app.command("add")
def whitelist_add(
    ctx: typer.Context,
    commands: str = typer.Argument(
        ...,
        help='Comma-separated commands or prefixes, e.g. "docker, make, git push"',
    ),
) -> None:
    """Add commands to the profile terminal whitelist."""
    from core.env_loader import profile_env_path
    from core.terminal_whitelist_config import add_whitelist_commands, parse_command_list

    profile = _profile(ctx)
    parsed = parse_command_list(commands)
    if not parsed:
        print_error("No commands provided")
        raise typer.Exit(1)

    added = add_whitelist_commands(profile, commands)
    path = profile_env_path(profile)
    if added:
        print_success(f"Added to whitelist for profile '{profile}': {', '.join(added)}")
    else:
        print_info(f"All commands were already in the whitelist for profile '{profile}'")
    print_info(f"Saved in: {path}")
    print_info("Restart gateway/Telegram or re-run CLI for changes to apply")


@whitelist_app.command("list")
def whitelist_list(ctx: typer.Context) -> None:
    """List terminal whitelist settings for the active profile."""
    from core.env_loader import profile_env_path
    from core.platform_compat import IS_WINDOWS
    from core.terminal_whitelist_config import (
        builtin_whitelist_commands,
        effective_whitelist_commands,
        read_whitelist_enabled,
        read_whitelist_extra,
    )

    from cli.utils.rich_console import print_panel

    profile = _profile(ctx)
    enabled = read_whitelist_enabled(profile)
    extra = read_whitelist_extra(profile)
    builtin = builtin_whitelist_commands()
    effective = effective_whitelist_commands(profile)
    platform = "Windows" if IS_WINDOWS else "Unix"

    status = "[green]Enabled[/green]" if enabled else "[yellow]Disabled[/yellow]"
    extra_line = ", ".join(extra) if extra else "[dim]none[/dim]"
    body = (
        f"{status}\n"
        f"[cyan]Platform defaults ({platform}):[/cyan] {len(builtin)} commands\n"
        f"[cyan]Profile extras:[/cyan] {extra_line}\n"
        f"[cyan]Effective total:[/cyan] {len(effective)} commands\n\n"
        f"Env file: {profile_env_path(profile)}"
    )
    print_panel(body, title=f"Terminal whitelist — {profile}", border_style="green" if enabled else "yellow")


@whitelist_app.command("enable")
def whitelist_enable(ctx: typer.Context) -> None:
    """Enable terminal command whitelist enforcement for the active profile."""
    from core.env_loader import profile_env_path
    from core.terminal_whitelist_config import read_whitelist_enabled, set_whitelist_enabled

    profile = _profile(ctx)
    if read_whitelist_enabled(profile):
        print_info(f"Terminal whitelist is already enabled for profile '{profile}'")
        raise typer.Exit(0)

    set_whitelist_enabled(profile, True)
    print_success(f"Terminal whitelist enabled for profile '{profile}'")
    print_info(f"Saved in: {profile_env_path(profile)}")
    print_info("Restart gateway/Telegram or re-run CLI for changes to apply")


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KiB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MiB"
    return f"{size / (1024 * 1024 * 1024):.2f} GiB"


@crypto_app.command("enable")
def crypto_enable(
    ctx: typer.Context,
    unlock_key: str | None = typer.Option(
        None,
        "--unlock-key",
        help="User encryption key (prompted twice if omitted)",
    ),
    skip_existing: bool = typer.Option(
        False,
        "--skip-existing",
        help="Do not encrypt existing profile secrets",
    ),
) -> None:
    """Enable profile encryption for the active profile."""
    from core.crypto.bootstrap import enable_profile_encryption
    from core.crypto.profile_crypto import ProfileCryptoError

    profile = _profile(ctx)
    manager = get_profile_manager()
    if not manager.profile_exists(profile):
        print_error(f"Profile '{profile}' does not exist")
        raise typer.Exit(1)

    key = (unlock_key or "").strip()
    if not key:
        key = typer.prompt("Encryption unlock key", hide_input=True)
        confirm = typer.prompt("Confirm unlock key", hide_input=True)
        if key != confirm:
            print_error("Unlock keys do not match")
            raise typer.Exit(1)

    try:
        result = enable_profile_encryption(
            manager,
            profile,
            key,
            encrypt_existing=not skip_existing,
        )
    except ProfileCryptoError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc

    print_success(f"Encryption enabled for profile '{profile}'")
    print_info(f"Workspace: {result.workspace}")
    if getattr(result, "secrets_encrypted", 0):
        print_info(f"Encrypted {result.secrets_encrypted} profile secret file(s)")
    if getattr(result, "deliverables_decrypted", 0):
        print_info(f"Decrypted {result.deliverables_decrypted} workspace file(s) to plaintext")
    print_warning("Save your unlock key — data cannot be recovered without it")
    print_info(f"Unlock session: holix -p {profile} --unlock-key <key> chat")


@crypto_app.command("migrate")
def crypto_migrate(
    ctx: typer.Context,
    all_profiles: bool = typer.Option(
        False,
        "--all",
        help="Migrate every profile that is not encrypted yet",
    ),
    unlock_key: str | None = typer.Option(
        None,
        "--unlock-key",
        help="User encryption key (same key wraps each profile DEK)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="List profiles that would be migrated without changing anything",
    ),
    skip_existing: bool = typer.Option(
        False,
        "--skip-existing",
        help="Enable encryption but do not encrypt existing profile secrets",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Enable encryption for existing unencrypted profiles (bulk migration)."""
    from core.crypto.bootstrap import list_unencrypted_profiles, migrate_profiles_encryption
    from core.crypto.profile_crypto import is_profile_encryption_enabled

    manager = get_profile_manager()
    active = _profile(ctx)

    if all_profiles:
        targets = list_unencrypted_profiles(manager)
    else:
        if is_profile_encryption_enabled(active):
            print_info(f"Profile '{active}' is already encrypted")
            raise typer.Exit(0)
        targets = [active]

    if not targets:
        print_info("All profiles are already encrypted")
        raise typer.Exit(0)

    print_info(f"Profiles to migrate ({len(targets)}): {', '.join(targets)}")
    if dry_run:
        raise typer.Exit(0)

    if not yes:
        confirmed = typer.confirm("Enable encryption for these profiles?", default=False)
        if not confirmed:
            print_info("Migration cancelled")
            raise typer.Exit(0)

    key = (unlock_key or "").strip()
    if not key:
        key = typer.prompt("Encryption unlock key", hide_input=True)
        confirm = typer.prompt("Confirm unlock key", hide_input=True)
        if key != confirm:
            print_error("Unlock keys do not match")
            raise typer.Exit(1)

    summary = migrate_profiles_encryption(
        manager,
        key,
        profiles=targets,
        encrypt_existing=not skip_existing,
    )

    for result in summary.migrated:
        notes: list[str] = []
        if result.secrets_encrypted:
            notes.append(f"{result.secrets_encrypted} secret(s)")
        if result.deliverables_decrypted:
            notes.append(f"{result.deliverables_decrypted} workspace file(s) decrypted")
        detail = f" ({', '.join(notes)})" if notes else ""
        print_success(f"Migrated '{result.profile}' ({result.workspace}{detail})")

    for name in summary.skipped:
        print_info(f"Skipped '{name}' (already encrypted)")

    for name, error in summary.failed:
        print_error(f"Failed '{name}': {error}")

    if summary.failed:
        raise typer.Exit(1)

    print_warning("Save your unlock key — data cannot be recovered without it")
    if len(summary.migrated) > 1:
        print_info("Use the same unlock key for all migrated profiles")


@crypto_app.command("seal")
def crypto_seal(
    ctx: typer.Context,
    all_profiles: bool = typer.Option(
        False,
        "--all",
        help="Seal secrets for every encrypted profile",
    ),
    unlock_key: str | None = typer.Option(
        None,
        "--unlock-key",
        help="User encryption key",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Encrypt plaintext secrets and memory stores for encrypted profiles."""
    from core.crypto.bootstrap import seal_profiles_secrets
    from core.crypto.profile_crypto import is_profile_encryption_enabled

    manager = get_profile_manager()
    active = _profile(ctx)

    if all_profiles:
        targets = [
            name
            for name in manager.list_profiles()
            if is_profile_encryption_enabled(name)
        ]
    else:
        if not is_profile_encryption_enabled(active):
            print_error(f"Profile '{active}' is not encrypted. Run: holix profile crypto enable")
            raise typer.Exit(1)
        targets = [active]

    if not targets:
        print_info("No encrypted profiles found")
        raise typer.Exit(0)

    print_info(f"Profiles to seal ({len(targets)}): {', '.join(targets)}")
    if not yes:
        confirmed = typer.confirm("Encrypt profile secrets and memory on disk?", default=False)
        if not confirmed:
            print_info("Seal cancelled")
            raise typer.Exit(0)

    key = (unlock_key or "").strip()
    if not key:
        key = typer.prompt("Encryption unlock key", hide_input=True)

    summary = seal_profiles_secrets(manager, key, profiles=targets)
    for result in summary.migrated:
        parts: list[str] = []
        if result.secrets_encrypted:
            parts.append(f"{result.secrets_encrypted} secret(s)")
        if result.memory_sealed:
            parts.append(f"{result.memory_sealed} memory store(s)")
        if result.deliverables_decrypted:
            parts.append(f"{result.deliverables_decrypted} workspace file(s) decrypted")
        if parts:
            print_success(f"Sealed '{result.profile}' ({', '.join(parts)})")
        else:
            print_info(f"No plaintext secrets or memory left in '{result.profile}'")

    for name in summary.skipped:
        print_info(f"Skipped '{name}' (not encrypted)")

    for name, error in summary.failed:
        print_error(f"Failed '{name}': {error}")

    if summary.failed:
        raise typer.Exit(1)


@crypto_app.command("status")
def crypto_status(ctx: typer.Context) -> None:
    """Show encryption status for the active profile."""
    from core.crypto.policy import (
        encryption_policy_label,
        encryption_policy_status,
        is_encryption_runtime_active,
        profile_has_crypto_metadata,
    )
    from core.crypto.profile_crypto import load_crypto_meta
    from core.crypto.runtime_cache import (
        iter_world_readable_runtime_caches,
        legacy_profile_cache_dir,
        profile_runtime_cache_dir,
    )
    from core.crypto.unlock_context import get_profile_session_dek

    from cli.utils.rich_console import print_panel

    profile = _profile(ctx)
    config = get_current_config()
    has_meta = profile_has_crypto_metadata(profile)
    runtime = is_encryption_runtime_active()
    enabled = bool(getattr(config, "encryption_enabled", False)) or has_meta
    policy = encryption_policy_status()
    if not enabled:
        body = (
            "[yellow]Disabled[/yellow]\n\n"
            f"Policy: {encryption_policy_label()}\n\n"
            "Enable with: [cyan]holix profile crypto enable[/cyan]"
        )
        border = "yellow"
    elif has_meta and not runtime:
        body = (
            "[yellow]Metadata present, runtime inactive[/yellow]\n"
            f"Policy: {encryption_policy_label()}\n"
            f"Platform: {policy['platform']}, HOLIX_ENV={policy['holix_env']}\n\n"
            "Encrypted files stay sealed on this host. "
            "Use Linux production or HOLIX_ENCRYPTION_MODE=on."
        )
        border = "yellow"
    else:
        meta = load_crypto_meta(profile)
        locked = get_profile_session_dek(profile) is None
        state = "[red]locked[/red]" if locked else "[green]unlocked[/green]"
        algo = meta.algorithm if meta else "unknown"
        runtime_cache = profile_runtime_cache_dir(profile)
        legacy_cache = legacy_profile_cache_dir(profile)
        cache_bits: list[str] = []
        if runtime_cache.is_dir():
            cache_bits.append(f"runtime: {runtime_cache}")
        if legacy_cache.is_dir():
            cache_bits.append(f"legacy: {legacy_cache}")
        cache_line = "\n".join(cache_bits) if cache_bits else "runtime cache: none"
        weak = iter_world_readable_runtime_caches()
        if weak:
            cache_line += f"\n[yellow]Warning: world-readable cache ({len(weak)})[/yellow]"
        body = (
            f"[green]Enabled[/green]\n"
            f"Session: {state}\n"
            f"Algorithm: {algo}\n"
            f"{cache_line}\n\n"
            f"Unlock: [cyan]holix -p {profile} --unlock-key <key> …[/cyan]\n"
            "Lock: [cyan]holix profile crypto lock[/cyan]\n"
            "Purge cache: [cyan]holix profile crypto purge-cache[/cyan]"
        )
        border = "green" if not locked else "yellow"

    print_panel(body, title=f"Profile encryption — {profile}", border_style=border)


@crypto_app.command("unlock")
def crypto_unlock(
    ctx: typer.Context,
    unlock_key: str = typer.Option(
        ...,
        "--unlock-key",
        prompt=True,
        hide_input=True,
        help="User encryption key",
    ),
) -> None:
    """Unlock encrypted profile data for this CLI process."""
    from core.crypto.profile_crypto import ProfileCryptoError, is_profile_encryption_enabled

    from cli.core import unlock_profile_encryption

    profile = _profile(ctx)
    if not is_profile_encryption_enabled(profile):
        print_error(f"Profile '{profile}' is not encrypted")
        raise typer.Exit(1)
    try:
        unlock_profile_encryption(profile, unlock_key)
    except ProfileCryptoError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc
    print_success(f"Profile '{profile}' unlocked for this process")
    print_info("Workspace files are stored as plaintext (legacy encrypted files are decrypted on unlock)")


@crypto_app.command("decrypt-workspace")
def crypto_decrypt_workspace(
    ctx: typer.Context,
    all_profiles: bool = typer.Option(
        False,
        "--all",
        help="Decrypt workspace for every encrypted profile",
    ),
    unlock_key: str | None = typer.Option(
        None,
        "--unlock-key",
        help="User encryption key (uses active session if already unlocked)",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Decrypt legacy encrypted workspace files to plaintext (git-friendly)."""
    from core.crypto.bootstrap import decrypt_all_profile_workspaces, list_encrypted_profiles
    from core.crypto.profile_crypto import (
        ProfileCryptoError,
        is_profile_encryption_enabled,
        unlock_profile_dek,
    )
    from core.crypto.profile_files import decrypt_deliverable_files
    from core.crypto.unlock_context import get_profile_session_dek, set_profile_session_unlock

    manager = get_profile_manager()
    active = _profile(ctx)

    if all_profiles:
        targets = list_encrypted_profiles(manager)
        if not targets:
            print_info("No encrypted profiles found")
            raise typer.Exit(0)

        print_info(f"Profiles to decrypt workspace ({len(targets)}): {', '.join(targets)}")
        if not yes:
            confirmed = typer.confirm("Decrypt legacy encrypted workspace files?", default=False)
            if not confirmed:
                print_info("Cancelled")
                raise typer.Exit(0)

        key = (unlock_key or "").strip()
        if not key:
            key = typer.prompt("Encryption unlock key", hide_input=True)

        summary = decrypt_all_profile_workspaces(manager, key, profiles=targets)
        total = sum(r.deliverables_decrypted for r in summary.migrated)
        for result in summary.migrated:
            if result.deliverables_decrypted:
                print_success(
                    f"'{result.profile}': decrypted {result.deliverables_decrypted} file(s) "
                    f"in {result.workspace}"
                )
            else:
                print_info(f"'{result.profile}': no encrypted workspace files")

        for name in summary.skipped:
            print_info(f"Skipped '{name}' (not encrypted)")

        for name, error in summary.failed:
            print_error(f"Failed '{name}': {error}")

        if summary.failed:
            raise typer.Exit(1)

        if total:
            print_success(f"Done: {total} workspace file(s) decrypted across {len(summary.migrated)} profile(s)")
        else:
            print_info("No encrypted workspace files found")
        raise typer.Exit(0)

    profile = active
    if not is_profile_encryption_enabled(profile):
        print_error(f"Profile '{profile}' is not encrypted")
        raise typer.Exit(1)

    dek = get_profile_session_dek(profile)
    if dek is None:
        key = (unlock_key or "").strip()
        if not key:
            key = typer.prompt("Encryption unlock key", hide_input=True)
        try:
            dek = unlock_profile_dek(profile, key)
        except ProfileCryptoError as exc:
            print_error(str(exc))
            raise typer.Exit(1) from exc
        count = set_profile_session_unlock(profile, dek)
    else:
        count = decrypt_deliverable_files(profile, dek)

    if count:
        print_success(f"Decrypted {count} workspace file(s) to plaintext")
    else:
        print_info("No encrypted workspace files found")


@crypto_app.command("purge-cache")
def crypto_purge_cache(
    ctx: typer.Context,
    all_profiles: bool = typer.Option(
        False,
        "--all",
        help="Purge runtime memory cache for every profile",
    ),
) -> None:
    """Remove decrypted memory cache directories from disk."""
    from core.crypto.memory_vault import purge_profile_memory_cache
    from core.crypto.runtime_cache import recover_stale_runtime_caches

    active = _profile(ctx)
    if all_profiles:
        stats = recover_stale_runtime_caches()
        print_success(
            f"Purged runtime caches ({stats['runtime_removed']} profile dir(s)); "
            f"legacy removed: {stats['legacy_removed']}"
        )
        return

    removed = purge_profile_memory_cache(active)
    if removed:
        print_success(f"Purged {removed} memory cache location(s) for '{active}'")
    else:
        print_info(f"No memory cache found for '{active}'")


@crypto_app.command("lock")
def crypto_lock(ctx: typer.Context) -> None:
    """Clear in-process encryption unlock state."""
    from core.crypto.unlock_context import clear_profile_unlock

    profile = _profile(ctx)
    clear_profile_unlock(profile)
    print_success(f"Profile '{profile}' locked in this process")


@quota_app.command("status")
def quota_status_cmd(ctx: typer.Context) -> None:
    """Show workspace quota usage for the active profile."""
    from core.workspace.quota import quota_status

    from cli.utils.rich_console import print_panel

    profile = _profile(ctx)
    config = get_current_config()
    if not config.workspace_root:
        print_error("Workspace jail is not configured for this profile")
        raise typer.Exit(1)

    limits, usage = quota_status(profile, Path(config.workspace_root))
    pct = (usage.used_bytes / limits.workspace_max_bytes * 100) if limits.workspace_max_bytes else 0
    body = (
        f"[cyan]Tariff:[/cyan] {limits.tariff_id}\n"
        f"[cyan]Used:[/cyan] {_format_bytes(usage.used_bytes)} / "
        f"{_format_bytes(limits.workspace_max_bytes)} ({pct:.1f}%)\n"
        f"[cyan]Files:[/cyan] {usage.file_count} / {limits.workspace_max_files}\n"
        f"[cyan]Workspace:[/cyan] {config.workspace_root}"
    )
    print_panel(body, title=f"Workspace quota — {profile}", border_style="cyan")


@quota_app.command("set")
def quota_set(
    ctx: typer.Context,
    tariff: str = typer.Option(..., "--tariff", help="Tariff id (free, basic, pro)"),
    admin: bool = typer.Option(
        False,
        "--admin",
        help="Allow changing platform-managed limits (admin only)",
    ),
) -> None:
    """Set workspace quota tariff (admin only)."""
    from core.workspace.limits import set_profile_tariff

    if not admin:
        print_error("Quota limits are platform-managed. Use --admin to override.")
        raise typer.Exit(1)

    profile = _profile(ctx)
    limits = set_profile_tariff(profile, tariff, updated_by="cli-admin")
    print_success(f"Tariff set to '{limits.tariff_id}' for profile '{profile}'")
    print_info(
        f"Limits: {_format_bytes(limits.workspace_max_bytes)}, "
        f"{limits.workspace_max_files} files"
    )