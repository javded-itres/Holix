# Memory

Holix stores conversation history and long-term knowledge per profile: **SQLite** for structured data and **ChromaDB** for semantic search.

Data path: `~/.holix/profiles/<name>/data/memory/` (encrypted when [profile encryption](PROFILE_ENCRYPTION.md) is enabled).

---

## What is stored

| Layer | Role |
|-------|------|
| Conversation | Messages per `conversation_id` (TUI session, Telegram chat, `cron-<id>`, API) |
| Episodic / strategic | Summaries and extracted facts from successful runs |
| Reflexion episodes | Quality critiques / retries (`metadata.type=reflexion` or `self_refinement`) |
| Semantic (Chroma) | Embeddings for `/memory` and `holix memory search` |
| Skills index | Chroma index for `holix skills search` (related, not chat memory) |
| LangGraph checkpoints | Technical graph-state snapshots in `checkpoints.db` (not chat/LTM knowledge) |

The agent retrieves relevant past context automatically during runs; you can also search explicitly.

### Reflexion and LTM

When **self-refinement** is enabled (default), each evaluate/retry cycle may store:

- **Episodic** — quality score, improvement areas, accept vs retry
- **Strategic** (on retry) — short “when quality is low on X, apply …” tips

See [EXECUTION_MODES.md](EXECUTION_MODES.md#reflexion-self-critique).

### LangGraph `checkpoints.db` size guard

Each graph run may append state to `data/memory/checkpoints.db`. This file is **not** conversation or LTM memory; it only stores LangGraph thread state.

When the on-disk bundle (`checkpoints.db` + WAL/SHM) exceeds a limit, Holix **deletes it and recreates an empty DB** on the next graph open. Defaults:

| Setting | Env | Default |
|---------|-----|---------|
| Auto prune | `HOLIX_CHECKPOINT_AUTO_PRUNE` | `true` |
| Max size (MiB) | `HOLIX_CHECKPOINT_MAX_MB` | `200` |

Set `HOLIX_CHECKPOINT_MAX_MB=0` to disable size-based reset. Example in profile `.env`:

```bash
HOLIX_CHECKPOINT_MAX_MB=200
HOLIX_CHECKPOINT_AUTO_PRUNE=true
```

Manual wipe (agent idle): `rm -f ~/.holix/profiles/<name>/data/memory/checkpoints.db*`. Full profile data wipe: `holix clear`.

---

## Search in chat

```text
/memory deployment nginx config
/memory-clear
```

Slash reference: [SLASH_COMMANDS.md](SLASH_COMMANDS.md).

---

## CLI

```bash
holix memory search "how we configured LiteLLM"
```

No separate “clear all memory” CLI — use `holix clear` to wipe profile `data/` (destructive; see [CLI.md](CLI.md#holix-clear)).

---

## Compression

When the context window fills, use `/compress` in TUI/Telegram/chat-command to summarize older turns in the DB.

Plan/Hybrid modes may also trigger summarization during long runs — [EXECUTION_MODES.md](EXECUTION_MODES.md).

---

## Per-interface behavior

| Interface | Conversation id |
|-----------|-------------------|
| TUI | Session id (switch with `/switch`) |
| Telegram / MAX | Per chat + profile binding |
| `holix run -c` | Your `--conversation-id` |
| Cron (log) | `cron-<job-id>` (hidden in Telegram / MAX session lists) |
| Cron → Telegram / MAX | Active chat session |
| Cron → Studio | New session `studio_cron-…` |
| API gateway | Client-supplied or server-generated session |

---

## Encryption

With `holix profile crypto enable`, memory SQLite and Chroma stores are encrypted at rest. Gateway needs `HOLIX_UNLOCK_KEY` to read them — [PROFILE_ENCRYPTION.md](PROFILE_ENCRYPTION.md).

---

## Troubleshooting

| Symptom | Action |
|---------|--------|
| `/memory` returns nothing | Run a few tasks first; check correct profile (`holix status`) |
| Search quality poor | Ensure embedding model/provider is configured; check `holix doctor` |
| Locked memory on gateway | Set `HOLIX_UNLOCK_KEY`; `holix profile crypto status` |

---

## See also

- [ARCHITECTURE.md](ARCHITECTURE.md) — `core/memory/`
- [PROFILES.md](PROFILES.md) — isolation per profile
- [CLI.md](CLI.md#holix-memory)
