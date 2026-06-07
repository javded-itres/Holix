# С чего начать

Чеклист для новой машины.

## Требования

- Python **3.14+**
- [uv](https://github.com/astral-sh/uv)
- OpenAI-совместимый LLM (Ollama, LiteLLM, OpenAI, Groq, …)

## 1. Установка

```bash
git clone https://github.com/YOUR_ORG/helix.git
cd helix
./scripts/install.sh
cp .env.example .env
```

[INSTALLATION.md](INSTALLATION.md)

## 2. Диагностика

```bash
helix doctor
helix doctor --fix
```

## 3. Модели

```bash
helix models setup
helix config show
```

## 4. Интерфейс

| Интерфейс | Команда |
|-----------|---------|
| TUI (рекомендуется) | `helix tui` |
| Чат в терминале | `helix chat-command` |
| Один запрос | `helix run "…"` |
| API | `helix gateway start` |

Слэш-команды: **`/help`** — [SLASH_COMMANDS.md](SLASH_COMMANDS.md).

## 5. Опции

```bash
uv sync --extra telegram
uv sync --extra browser
helix hub browse
helix mcp setup
```

## Production

```bash
export HELIX_ENV=production
export HELIX_REQUIRE_AUTH=true
export HELIX_API_KEY_PEPPER=$(openssl rand -hex 32)
helix gateway start
```

[SECURITY.md](SECURITY.md), [DEPLOYMENT.md](DEPLOYMENT.md).

## Дальше

- [CLI.md](CLI.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- Логи: `helix logs` — [LOGS.md](LOGS.md)
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)