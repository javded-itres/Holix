# holix-extension-demo

Minimal MIT reference extension for the Holix ecosystem.

- **Agent extension** (`holix.agent.extensions`): `demo_echo` tool + `/demo` slash command
- **Manifest**: `holix.plugin.json`
- **Depends on**: `holix-sdk` (separate package)

```bash
uv sync --extra demo
holix extensions agent-list
```

Full authoring guide: [docs/en/EXTENSIONS.md](../../docs/en/EXTENSIONS.md) · [docs/ru/EXTENSIONS.md](../../docs/ru/EXTENSIONS.md)