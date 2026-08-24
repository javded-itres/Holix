# Agent Client Protocol (ACP)

Holix can drive an **external coding agent** over the [Agent Client Protocol](https://agentclientprotocol.com) (JSON-RPC on stdio). The child is a fresh process and session — no parent conversation, tools, PTY, or todos.

This is the out-of-process counterpart to Holix sub-agents (`delegate_to_subagent`). Use ACP when you want Grok Build, Claude Code, or another ACP binary to own the turn.

## Setup

```bash
export HOLIX_ACP_COMMAND='grok --acp'   # or: claude --acp
# optional:
export HOLIX_ACP_ARGS=''                # extra argv
export HOLIX_ACP_PERMISSION=reject      # reject | allow
```

The binary must speak ACP: `initialize` → `session/new` → `session/prompt`, with `session/update` notifications.

## Tool

```text
run_acp_agent(prompt="…", cwd=optional, command=optional, timeout=300)
```

Permission requests from the child (`session/request_permission`) are answered automatically: `reject` (default) or the first `allow_once` / `allow_always` option when `HOLIX_ACP_PERMISSION=allow`. Holix does not expose the child's filesystem or terminal callbacks.

## Related

- Holix workers: [SUBAGENTS.md](SUBAGENTS.md)
- tmux CLI launch: [LAUNCH.md](LAUNCH.md)
