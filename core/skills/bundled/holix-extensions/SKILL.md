---
name: holix-extensions
description: >
  Author and manage Holix agent drop-in extensions so the agent can extend itself
  without editing Holix core. Use when the user asks to write an extension, add tools,
  register slash commands, list extensions, disable a broken extension, or self-modify
  agent capabilities. Invoke via /holix-extensions.
tags:
  - extensions
  - agent
  - scaffold
  - self-extension
  - tools
  - slash
  - holix
user-invocable: true
---

## When to use

The user wants the agent to **grow new capabilities** safely:

- add a custom tool or slash command
- “напиши расширение”, “допиши себя”, “добавь skill/tool”
- list what extensions are loaded
- disable something that breaks the agent

**Never edit Holix core** (`core/`, `cli/`, `integrations/`, package source).  
Only create **profile-local drop-in extensions**.

## Mode restriction (important)

Self-authored extensions (**create / enable / hot-reload**) work **only in local single-operator** mode:

| Mode | Create / hot-reload |
|------|---------------------|
| CLI, TUI, `holix run` (local operator) | **Allowed** |
| Telegram / MAX multi-user bots | **Denied** |

Messenger hosts set `HOLIX_MESSENGER_HOST` and `self_extensions_enabled=False`.  
Override (not recommended on shared bots): `HOLIX_SELF_EXTENSIONS=1`.

If `manage_agent_extensions` returns `self_extensions_denied`, tell the user to use a **local** profile session — do not try to force-create on the group bot.

## Architecture (safe zone)

```text
~/.holix/profiles/<profile>/extensions/<name>/
  agent.py              # get_agent_extension()
  holix.plugin.json
  settings.default.yaml
  README.md
```

- Discovered on agent start **and** via **hot-reload** after `create` / `reload` (local mode).
- Does **not** require pip install.
- Same profile only (unless user copies to `~/.holix/extensions/`).

## Primary tool

Use **`manage_agent_extensions`**:

| action | Purpose | Local only? |
|--------|---------|-------------|
| `list` | Folders + blocked status | No |
| `registered` | Settings + slash commands | No |
| `create` | Scaffold + **hot-reload** into this session | **Yes** |
| `disable` | Kill-switch; hot-unload when local | Prefer anytime |
| `enable` | Re-enable + hot-reload | **Yes** |
| `quarantine_clear` | Clear auto-quarantine + reload | **Yes** |
| `reload` | Re-scan extensions / reimport modules | **Yes** |
| `show_control` | Show `agent_extensions_control.yaml` | No |

### Create (local)

```text
manage_agent_extensions(
  action=create,
  name=my_helper,
  description=Short helper tools for this project
)
```

The tool **hot-reloads** the agent: new tools and slash specs appear in the **current** session.  
If you edit `agent.py` further, call `manage_agent_extensions(action=reload)`.

### List / inspect

```text
manage_agent_extensions(action=list)
manage_agent_extensions(action=registered)
manage_agent_extensions(action=reload)   # after manual agent.py edits
```

## Editing an extension

1. Prefer `manage_agent_extensions(action=create, …)` then edit `agent.py` with `write_file` / `edit`.
2. Call `manage_agent_extensions(action=reload)` so code changes load without restart.
3. Keep API surface small: `BaseTool` + optional `register_slash_commands` + optional prompt fragment.
4. Always set `default_settings()` → `{"enabled": True}`.
5. Never import private Holix internals beyond:
   - `core.extensions.agent_base.AgentExtensionBase`
   - `core.tools.base.BaseTool`
   - `holix_sdk.agent.SlashCommandSpec`

### Minimal tool pattern

```python
class MyTool(BaseTool):
    def __init__(self):
        super().__init__()
        self.name = "my_tool"
        self.description = "…"
        self.risk_level = "no"  # or low/medium/high
        self.parameters = {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    async def execute(self, text: str = "", **kwargs) -> str:
        return text
```

## Kill-switch (if extension breaks the agent)

### A. Soft disable (preferred)

```text
manage_agent_extensions(action=disable, name=broken_ext, reason=causes crash)
```

Or CLI:

```bash
holix extensions agent-disable broken_ext -p <profile>
```

File: `~/.holix/profiles/<profile>/agent_extensions_control.yaml`

```yaml
disabled:
  - broken_ext
quarantine:
  broken_ext: "TypeError: ..."
```

### B. Auto-quarantine

If `register_tools` / middleware **raises** on load, Holix records quarantine automatically.  
Fix code → `manage_agent_extensions(action=quarantine_clear, name=…)` → auto-reload (local).

### C. Emergency (process env)

```bash
export HOLIX_AGENT_EXTENSIONS_OFF=1          # disable ALL agent drop-ins
export HOLIX_AGENT_EXTENSIONS_DISABLED=a,b  # disable listed names
holix gateway restart   # or restart bot
```

Core Holix + built-in tools (including `manage_agent_extensions`) still load.

## CLI cheat sheet

```bash
holix extensions agent-list -p default
holix extensions agent-create my_helper -d "…" -p default
holix extensions agent-disable my_helper -p default
holix extensions agent-enable my_helper -p default
holix extensions agent-control -p default
```

CLI create is an **operator** action (local machine). Agent-side create remains blocked on multi-user messenger agents.

## Slash / skill

- Skill: `/holix-extensions` (this file)
- Extension-defined slashes: after create/reload, e.g. `/my-helper` from scaffold

## Workflow for “extend yourself” (local only)

1. Confirm session is local (CLI/TUI), not a group Telegram/MAX bot.
2. `manage_agent_extensions(action=create, name=…, description=…)`.
3. Edit `agent.py` if needed; then `action=reload`.
4. Verify with `manage_agent_extensions(action=registered)` and a test call.
5. If broken → **disable** immediately; do not patch core.

## Do NOT

- Modify Holix `core/`, `cli/`, `integrations/` for product features.
- Create self-extensions on multi-user messenger bots.
- Install random packages system-wide without user approval.
- Leave a crashing extension enabled — use disable/quarantine.

## Quick reference

```text
manage_agent_extensions action=list
manage_agent_extensions action=create name=notes description=Save short notes
manage_agent_extensions action=reload
manage_agent_extensions action=disable name=notes reason=syntax error
manage_agent_extensions action=show_control
```
