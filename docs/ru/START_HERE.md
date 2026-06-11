# С чего начать

Чеклист для новой машины.

## Требования

- Python **3.12+**
- OpenAI-совместимый LLM (Ollama, LiteLLM, OpenAI, Groq, …)
- [pipx](https://pipx.pypa.io/) (рекомендуется) или `pip` в venv

## 1. Установка с PyPI

Пакет **[HolixAgentAi](https://pypi.org/project/HelixAgentAi/)** на PyPI; команда в терминале — **`holix`**.

```bash
pipx install HelixAgentAi
# опционально: Telegram, браузер, веб-TUI, голос:
pipx install "HelixAgentAi[all]"

holix version
holix doctor
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
mkdir -p ~/.holix
holix doctor
holix doctor --fix
```

При **первом диалоге** в новом профиле Holix проводит короткий онбординг (пока есть `INIT.md`): знакомство, личность агента (`SOUL.md`) и ваши предпочтения (`USER.md`). См. [PROFILES.md](PROFILES.md#идентичность-агента-soul-init-user).

## 3. Модели

```bash
holix models setup
holix config show
```

## 4. Интерфейс

| Интерфейс | Команда |
|-----------|---------|
| TUI (рекомендуется) | `holix tui` |
| Чат в терминале | `holix chat-command` |
| Один запрос | `holix run "…"` |
| API | `holix gateway start` |

Слэш-команды: **`/help`** — [SLASH_COMMANDS.md](SLASH_COMMANDS.md).

## 5. Опции

```bash
pipx install "HelixAgentAi[telegram]"
holix -p shared telegram setup
# мультипользовательский бот: /start → holix -p shared telegram requests approve …
pipx install "HelixAgentAi[browser]"
playwright install chromium
holix hub browse
holix mcp setup
```

## Production

```bash
export HOLIX_ENV=production
export HOLIX_REQUIRE_AUTH=true
export HOLIX_API_KEY_PEPPER=$(openssl rand -hex 32)
holix gateway start
```

[SECURITY.md](SECURITY.md), [DEPLOYMENT.md](DEPLOYMENT.md).

## Дальше

- [CLI.md](CLI.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- Логи: `holix logs` — [LOGS.md](LOGS.md)
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)