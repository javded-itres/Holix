# Skill Hub

Install skills and Claude Code plugins from public catalogs into the active profile.

Data layout:

- Bundles: `{profile}/data/skills/_hub/<slug>/`
- Lockfile: `{profile}/data/hub-lock.json`
- Flat copies (optional): `{profile}/data/skills/<name>.md`
- Slash registry: `{profile}/data/skills/skill-slash.json`

## CLI

```bash
holix hub search "git" -s clawhub
holix hub search "react" -s skills-sh
holix hub search "" -s hermes
holix hub browse                    # interactive picker
holix hub install <spec>
holix hub install --agents main,coder
holix hub list
holix hub remove <lock-id>
holix hub check-updates
holix hub update                    # all ClawHub bumps
holix hub autoupdate --enable       # background policy in profile
```

### Install specs

| Prefix | Example |
|--------|---------|
| ClawHub | `my-skill` or `clawhub:slug@1.0` |
| Claude plugin | `claude:github@claude-official` |
| Hermes | `hermes:api-builder` |
| skills.sh | `skills-sh/owner/repo/path` |
| Git | `git:https://github.com/...` |
| Local | path to `SKILL.md` or bundle |

Claude plugins may ship MCP servers; use `--with-mcp` (default) to merge into `mcp_servers`.

## TUI

```bash
uv sync --extra tui-web    # optional: browser mode
holix tui
```

In TUI:

| Action | Command / UI |
|--------|----------------|
| Pick catalog | `/hub` |
| Installed list | `/hub installed` or mode **Installed** |
| Browse & install | `/hub browse` → Search → Install |
| Remove hub bundle | Installed view → highlight hub row → **Remove hub** or Delete |
| Browser UI | `holix tui --web` → http://127.0.0.1:8787 |

## Per-agent skills

Profile field `skill_assignments` limits which skills each agent/subagent may use.

```bash
holix skills list --agent main
holix skills assign my-skill --agents main,coder
holix skills unassign my-skill --agent coder
holix hub install <spec> --agents main
```

Skill frontmatter may include `agents:` / `agent_roles:` for defaults.

## MCP env in plugins

`${VAR}` and `${ENV:VAR}` in Claude plugin MCP configs are resolved at load time.  
`holix doctor` reports `mcp.unresolved_env` when variables are missing.