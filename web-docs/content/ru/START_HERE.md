# С чего начать

Чеклист для новой машины.

## Требования

- Python **3.12+**
- OpenAI-совместимый LLM (Ollama, LiteLLM, OpenAI, Groq, …)
- [pipx](https://pipx.pypa.io/) (рекомендуется) или `pip` в venv

## 1. Установка с PyPI

Пакет **[HelixAgentAi](https://pypi.org/project/HelixAgentAi/)** на PyPI; команда в терминале — **`helix`**.

```bash
pipx install HelixAgentAi
# опционально: Telegram, браузер, веб-TUI, голос:
pipx install "HelixAgentAi[all]"

helix version
helix doctor
```

В виртуальном окружении вместо pipx:

```bash
python -m venv .venv && source .venv/bin/activate
pip install HelixAgentAi
```

Не используйте `pip install helix` — это **другой** пакет на PyPI.

**Разработчикам** (из git): [INSTALLATION.md](INSTALLATION.md)

## 2. Первичная настройка

```bash
mkdir -p ~/.helix
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
pipx install "HelixAgentAi[telegram]"
helix -p shared telegram setup
# мультипользовательский бот: /start → helix -p shared telegram requests approve …
pipx install "HelixAgentAi[browser]"
playwright install chromium
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