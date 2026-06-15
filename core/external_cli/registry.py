"""Catalog of supported external coding CLIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EnvStyle = Literal["openai_compat", "anthropic", "gigacode"]


@dataclass(frozen=True, slots=True)
class ExternalCliSpec:
    cli_id: str
    display_name: str
    binary_names: tuple[str, ...]
    default_model_slot: str
    env_style: EnvStyle
    launch_args: tuple[str, ...] = ()
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
        env_style="openai_compat",
        launch_args=(),
        install_hint="curl -fsSL https://opencode.ai/install | bash",
        install_commands=(),
        docs_url="https://opencode.ai",
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
    "codex": ExternalCliSpec(
        cli_id="codex",
        display_name="OpenAI Codex CLI",
        binary_names=("codex",),
        default_model_slot="coder",
        env_style="openai_compat",
        launch_args=(),
        install_hint="npm install -g @openai/codex",
        install_commands=(("npm", "install", "-g", "@openai/codex"),),
        docs_url="https://github.com/openai/codex",
        description="OpenAI Codex terminal agent",
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