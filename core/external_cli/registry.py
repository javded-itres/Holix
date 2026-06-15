"""Catalog of supported external coding CLIs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

EnvStyle = Literal["openai_compat", "anthropic", "gigacode", "grok", "opencode"]


@dataclass(frozen=True, slots=True)
class ExternalCliSpec:
    cli_id: str
    display_name: str
    binary_names: tuple[str, ...]
    default_model_slot: str
    env_style: EnvStyle
    launch_args: tuple[str, ...] = ()
    model_cli_flag: str | None = None
    task_cli_flag: str | None = None
    task_positional: bool = False
    binary_paths: tuple[str, ...] = ()
    install_hint: str = ""
    install_commands: tuple[tuple[str, ...], ...] = ()
    docs_url: str = ""
    description: str = ""


EXTERNAL_CLI_REGISTRY: dict[str, ExternalCliSpec] = {
    "claude": ExternalCliSpec(
        cli_id="claude",
        display_name="Claude Code",
        binary_names=("claude",),
        default_model_slot="coder",
        env_style="anthropic",
        launch_args=(),
        install_hint="npm install -g @anthropic-ai/claude-code",
        install_commands=(("npm", "install", "-g", "@anthropic-ai/claude-code"),),
        docs_url="https://docs.anthropic.com/en/docs/claude-code",
        description="Anthropic Claude Code terminal agent",
    ),
    "opencode": ExternalCliSpec(
        cli_id="opencode",
        display_name="OpenCode",
        binary_names=("opencode",),
        default_model_slot="coder",
        env_style="opencode",
        launch_args=(),
        model_cli_flag="-m",
        binary_paths=("~/.opencode/bin/opencode",),
        install_hint="curl -fsSL https://opencode.ai/install | bash",
        install_commands=(
            ("bash", "-c", "curl -fsSL https://opencode.ai/install | bash"),
        ),
        docs_url="https://opencode.ai/docs/cli/",
        description="Open-source terminal coding agent (OpenAI-compatible providers)",
    ),
    "gigacode": ExternalCliSpec(
        cli_id="gigacode",
        display_name="GigaCode",
        binary_names=("gigacode", "giga"),
        default_model_slot="coder",
        env_style="gigacode",
        launch_args=(),
        install_hint="See vendor docs — install GigaCode CLI and ensure `gigacode` is on PATH",
        install_commands=(),
        docs_url="https://gitverse.ru/gigacode",
        description="GigaCode CLI (maps Holix profile LLM to GigaCode env)",
    ),
    "grok-build": ExternalCliSpec(
        cli_id="grok-build",
        display_name="Grok Build",
        binary_names=("grok", "grok-build"),
        default_model_slot="coder",
        env_style="grok",
        launch_args=(),
        model_cli_flag="-m",
        task_positional=True,
        binary_paths=("~/.grok/bin/grok",),
        install_hint="curl -fsSL https://x.ai/cli/install.sh | bash",
        install_commands=(
            ("bash", "-c", "curl -fsSL https://x.ai/cli/install.sh | bash"),
        ),
        docs_url="https://docs.x.ai/build/overview",
        description="xAI Grok Build coding agent (TUI, headless, ACP)",
    ),
    "aider": ExternalCliSpec(
        cli_id="aider",
        display_name="Aider",
        binary_names=("aider",),
        default_model_slot="coder",
        env_style="openai_compat",
        launch_args=("--no-git",),
        install_hint="uv tool install aider-chat  OR  pip install aider-chat",
        install_commands=(("uv", "tool", "install", "aider-chat"),),
        docs_url="https://aider.chat",
        description="Pair-programming CLI (OpenAI-compatible endpoint from profile)",
    ),
}


def list_cli_specs() -> list[ExternalCliSpec]:
    return list(EXTERNAL_CLI_REGISTRY.values())


def get_cli_spec(cli_id: str) -> ExternalCliSpec | None:
    return EXTERNAL_CLI_REGISTRY.get(cli_id.strip().lower())


def _normalize_cli_token(token: str) -> str:
    return re.sub(r"[^a-z0-9]", "", token.lower())


def resolve_cli_token(token: str) -> str | None:
    """Map user input (id, display name, or alias) to a registry cli_id."""
    raw = (token or "").strip()
    if not raw:
        return None

    lower = raw.lower()
    if lower in EXTERNAL_CLI_REGISTRY:
        return lower

    for spec in list_cli_specs():
        if spec.display_name.lower() == lower:
            return spec.cli_id

    slug = _normalize_cli_token(raw)
    if not slug:
        return None

    for spec in list_cli_specs():
        if _normalize_cli_token(spec.cli_id) == slug:
            return spec.cli_id
        if _normalize_cli_token(spec.display_name) == slug:
            return spec.cli_id

    matches: list[str] = []
    for spec in list_cli_specs():
        name_lower = spec.display_name.lower()
        if lower in name_lower or slug in _normalize_cli_token(spec.display_name):
            matches.append(spec.cli_id)

    if len(matches) == 1:
        return matches[0]
    return None


def resolve_cli_selection(raw: str) -> tuple[list[str], list[str]]:
    """Parse setup input into resolved cli_ids and unknown tokens.

    Accepts ``all``, comma-separated ids (``claude,aider``), or display names
    (``Claude Code``, ``OpenAI Codex CLI``).
    """
    text = (raw or "").strip()
    if not text or text.lower() == "all":
        return [s.cli_id for s in list_cli_specs()], []

    resolved: list[str] = []
    unknown: list[str] = []
    seen: set[str] = set()

    for part in text.split(","):
        token = part.strip()
        if not token:
            continue
        cli_id = resolve_cli_token(token)
        if cli_id is None:
            unknown.append(token)
            continue
        if cli_id not in seen:
            resolved.append(cli_id)
            seen.add(cli_id)

    return resolved, unknown


def format_cli_id_choices() -> str:
    """Compact id list for setup prompts."""
    return ", ".join(spec.cli_id for spec in list_cli_specs())