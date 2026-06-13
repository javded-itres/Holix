"""Manual conversation context compression (/compress)."""

from __future__ import annotations

from typing import Any


async def run_context_compress(host: Any) -> None:
    """Compress current session history via ContextManager (all hosts)."""
    write = getattr(host, "transcript_write", None)
    if not write:
        return

    agent = getattr(host, "agent", None)
    conversation_id = getattr(host, "conversation_id", None)

    if not agent or not conversation_id:
        write("[yellow]Agent not ready.[/yellow]")
        return

    ctx_mgr = getattr(agent, "context_manager", None)
    if not ctx_mgr or not getattr(ctx_mgr, "compressor", None):
        write("[yellow]Context compression not available.[/yellow]")
        return

    write("[dim]Compressing context…[/dim]")

    try:
        messages = await agent.memory.get_conversation(conversation_id, limit=200)
        compressed, was_compressed = await ctx_mgr.compress_context(messages)
    except Exception as e:
        write(f"[red]Compression error: {e}[/red]")
        return

    if not was_compressed:
        write("[dim]Not enough messages to compress.[/dim]")
        return

    from core.profile.soul import inject_soul_into_messages, profile_name_from_agent

    profile = profile_name_from_agent(agent)
    compressed = inject_soul_into_messages(compressed, profile)

    usage_before = agent.token_counter.count_message_tokens(messages)
    usage_after = agent.token_counter.count_message_tokens(compressed)
    write(
        f"[green]Context compressed:[/green] "
        f"{usage_before:,} → {usage_after:,} tokens "
        f"({len(messages)} → {len(compressed)} messages)"
    )

    try:
        await agent.memory.replace_conversation_messages(conversation_id, compressed)
        write("[dim]Compressed context saved to memory.[/dim]")
    except Exception as persist_err:
        summary = getattr(ctx_mgr, "last_summary", None)
        if summary:
            try:
                await agent.memory.save_message(
                    conversation_id,
                    "system",
                    f"Context compressed. Summary of previous conversation:\n\n{summary}",
                    metadata={"type": "context_compression"},
                )
                write("[dim]Summary saved as system message (partial persist).[/dim]")
            except Exception:
                write(f"[yellow]Could not persist compression: {persist_err}[/yellow]")
        else:
            write(f"[yellow]Could not persist compression: {persist_err}[/yellow]")

    refresh = getattr(host, "_update_context_display_async", None)
    if refresh:
        try:
            result = refresh()
            if hasattr(result, "__await__"):
                await result
        except Exception:
            pass

    refresh_bar = getattr(host, "_refresh_status_bar", None)
    if refresh_bar:
        try:
            refresh_bar()
        except Exception:
            pass

    refresh_header = getattr(host, "_refresh_header_subtitle", None)
    if refresh_header:
        try:
            refresh_header()
        except Exception:
            pass