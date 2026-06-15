"""CLI: spawn and manage sub-agents without interactive chat."""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from cli.utils.rich_console import print_error, print_info, print_success

app = typer.Typer(help="Spawn and manage background sub-agents", no_args_is_help=True)


def _profile(ctx: typer.Context) -> str:
    if ctx.obj and ctx.obj.get("profile"):
        return str(ctx.obj["profile"])
    return "default"


def _config(ctx: typer.Context) -> Any:
    return ctx.obj["config"] if ctx.obj else None


async def _with_agent(config: Any):
    from core.di import create_agent, resolve_runtime_config

    runtime_config = resolve_runtime_config(config)
    agent, container = await create_agent(runtime_config, event_listeners=[])
    return agent, container


class _CliSubagentHost:
    def __init__(self, agent: Any, profile: str) -> None:
        self.agent = agent
        self.profile = profile

    def transcript_write(self, content: object) -> None:
        text = str(content).strip()
        if not text:
            return
        low = text.lower()
        if "failed" in low or low.startswith("unknown") or "disabled" in low or "not ready" in low:
            print_error(text)
        elif low.startswith("spawned"):
            print_success(text)
        else:
            print_info(text)


@app.command("spawn")
def subagent_spawn(
    ctx: typer.Context,
    agent_type: str = typer.Argument(..., help="Sub-agent type (writer, coder, researcher, …)"),
    task: str = typer.Argument(..., help="Task description"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for completion and print result"),
    timeout: float | None = typer.Option(None, "--timeout", "-t", help="Wait timeout in seconds"),
) -> None:
    """Spawn a background sub-agent."""
    config = _config(ctx)

    async def _run() -> int:
        from core.config_utils import is_subagents_enabled

        agent, container = await _with_agent(config)
        try:
            if not is_subagents_enabled(agent.config):
                print_error(
                    "Sub-agents disabled. Set enable_subagents: true in profile config.yaml "
                    "or HOLIX_ENABLE_SUBAGENTS=true."
                )
                return 1
            handle, result = await agent.subagents.spawn_typed(
                agent_type.strip(),
                task.strip(),
                wait=wait,
                timeout=timeout,
            )
            print_success(
                f"spawned {handle.name} ({handle.config.process_mode.value}) "
                f"pid={handle.process_id or '—'}"
            )
            if wait and result is not None:
                text = (result.response or result.error or "").strip()
                if text:
                    print_info(text)
            elif wait:
                print_info(f"Job {handle.name} still running. Try: holix subagent result {handle.name} --wait")
            return 0
        except Exception as exc:
            print_error(f"spawn failed: {exc}")
            return 1
        finally:
            if container is not None:
                await container.close()

    raise typer.Exit(asyncio.run(_run()))


@app.command("list")
def subagent_list(ctx: typer.Context) -> None:
    """List running sub-agents."""
    profile = _profile(ctx)
    config = _config(ctx)

    async def _run() -> None:
        from cli.shared.commands.subagent_commands import run_subagents_command

        agent, container = await _with_agent(config)
        try:
            host = _CliSubagentHost(agent, profile)
            await run_subagents_command(host, "/subagents")
        finally:
            if container is not None:
                await container.close()

    asyncio.run(_run())


@app.command("result")
def subagent_result(
    ctx: typer.Context,
    job_id: str = typer.Argument(..., help="Sub-agent job id"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait until the job completes"),
    timeout: float | None = typer.Option(None, "--timeout", "-t", help="Wait timeout in seconds"),
) -> None:
    """Show sub-agent result."""
    config = _config(ctx)

    async def _run() -> int:
        agent, container = await _with_agent(config)
        try:
            mgr = agent.subagents
            handle = mgr.get_handle(job_id)
            if not handle:
                print_error(f"unknown job: {job_id}")
                return 1
            if wait and not handle.is_done:
                try:
                    result = await mgr.wait_for(job_id, timeout=timeout)
                except Exception as exc:
                    print_error(str(exc))
                    return 1
                text = (result.response or result.error or "").strip()
                print_info(text or "(empty result)")
                return 0
            if not handle.is_done:
                print_info(f"{job_id} still running [{handle.status.value}]")
                return 0
            res = handle.result
            text = (res.response or res.error or "") if res else ""
            print_info(text.strip() or "(empty result)")
            return 0
        finally:
            if container is not None:
                await container.close()

    raise typer.Exit(asyncio.run(_run()))


@app.command("terminate")
def subagent_terminate(
    ctx: typer.Context,
    job_id: str = typer.Argument(..., help="Sub-agent job id"),
) -> None:
    """Terminate a running sub-agent."""
    profile = _profile(ctx)
    config = _config(ctx)

    async def _run() -> int:
        from cli.shared.commands.subagent_commands import run_subagents_command

        agent, container = await _with_agent(config)
        try:
            host = _CliSubagentHost(agent, profile)
            await run_subagents_command(host, f"/subagent-terminate {job_id}")
            return 0
        finally:
            if container is not None:
                await container.close()

    asyncio.run(_run())