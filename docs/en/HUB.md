# Skill Hub

Install skills and Claude Code plugins from public catalogs into the active profile.

Data layout:

- Bundles: `{profile}/data/skills/_hub/<slug>/`
- Lockfile: `{profile}/data/hub-lock.json`
- Flat copies (optional): `{profile}/data/skills/<name>.md`
- Slash registry: `{profile}/data/skills/skill-slash.json`

## CLI

```bash
helix hub search "git" -s clawhub
helix hub search "react" -s skills-sh
helix hub search "" -s hermes
helix hub browse                    # interactive picker
helix hub install <spec>
helix hub install --agents main,coder
helix hub list
helix hub remove <lock-id>
helix hub check-updates
helix hub update                    # all ClawHub bumps
helix hub autoupdate --enable       # background policy in profile
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
helix tui
```

In TUI:

| Action | Command / UI |
|--------|----------------|
| Pick catalog | `/hub` |
| Installed list | `/hub installed` or mode **Installed** |
| Browse & install | `/hub browse` → Search → Install |
| Remove hub bundle | Installed view → highlight hub row → **Remove hub** or Delete |
| Browser UI | `helix tui --web` → http://127.0.0.1:8787 |

## Per-agent skills

Profile field `skill_assignments` limits which skills each agent/subagent may use.

```bash
helix skills list --agent main
helix skills assign my-skill --agents main,coder
helix skills unassign my-skill --agent coder
helix hub install <spec> --agents main
```

Skill frontmatter may include `agents:` / `agent_roles:` for defaults.

## MCP env in plugins

`${VAR}` and `${ENV:VAR}` in Claude plugin MCP configs are resolved at load time.  
`helix doctor` reports `mcp.unresolved_env` when variables are missing.