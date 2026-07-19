# Third-party and separately licensed components

## Holix Studio (`holix-studio`)

| Item | Value |
|------|--------|
| Package | `holix-studio` (Python extension) |
| Repository | [github.com/javded-itres/holix-studio](https://github.com/javded-itres/holix-studio) |
| License | **Holix Studio Source Available License v1.0** |
| Entry point | `holix.extensions` → `studio` |

Studio is **not part of MIT-licensed Holix core**. It includes the web UI, FastAPI routes, WebSocket session, and `holix studio` CLI.

### Install

```bash
pip install holix-studio
# or clone https://github.com/javded-itres/holix-studio and install editable
```

Studio is maintained in a **separate repository** (not bundled in the Holix monorepo).

### Extension API

Holix discovers extensions via `importlib.metadata` entry points (`core/extensions/registry.py`).

See [docs/en/EXTENSIONS.md](docs/en/EXTENSIONS.md) for the public `holix-sdk` contract and extension authoring guide.

Third-party extensions use the same `holix.extensions` and `holix.agent.extensions` groups (subject to their own licenses).

## Extension packages (MIT)

| Package | Repository | Entry point |
|---------|------------|-------------|
| `holix-sdk` | [github.com/javded-itres/holix-sdk](https://github.com/javded-itres/holix-sdk) | Public API for extension authors |
| `holix-extension-demo` | `packages/holix-extension-demo/` (Holix repo) | `holix.agent.extensions` → `demo` |