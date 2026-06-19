# Memory

Holix stores conversation history and long-term knowledge per profile: **SQLite** for structured data and **ChromaDB** for semantic search.

Data path: `~/.holix/profiles/<name>/data/memory/` (encrypted when [profile encryption](PROFILE_ENCRYPTION.md) is enabled).

---

## What is stored

| Layer | Role |
|-------|------|
| Conversation | Messages per `conversation_id` (TUI session, Telegram chat, `cron-<id>`, API) |
| Episodic / strategic | Summaries and extracted facts from successful runs |
| Semantic (Chroma) | Embeddings for `/memory` and `holix memory search` |
| Skills index | Chroma index for `holix skills search` (related, not chat memory) |

The agent retrieves relevant past context automatically during runs; you can also search explicitly.

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
| Cron jobs | `cron-<job-id>` (isolated from user chat) |
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