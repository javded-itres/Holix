# Установка

Helix требует **Python 3.14+** и устанавливается как CLI-команда `helix`.

## Требования

| Компонент | Примечание |
|-----------|------------|
| Python | 3.14+ |
| [uv](https://github.com/astral-sh/uv) | Рекомендуется |
| LLM | OpenAI-совместимый API (Ollama, LiteLLM, OpenAI, Groq, …) |

Опциональные extras:

| Extra | Команда | Назначение |
|-------|---------|------------|
| `telegram` | `uv sync --extra telegram` | Telegram-бот |
| `browser` | `uv sync --extra browser` | Playwright `browser_*` — [BROWSER_TOOLS.md](BROWSER_TOOLS.md) |
| `tui-web` | `uv sync --extra tui-web` | `helix tui --web` |
| `windows` | `uv sync --extra windows` | `psutil` для остановки дерева процессов (опционально на Windows) |
| `all` | `uv sync --extra all` | telegram + browser + tui-web + windows |

## Быстрая установка (пользователям)

### PyPI — `helix` из любой папки

Пакет на PyPI: **`helix-agent`** (не `pip install helix` — это другой проект). Команда: **`helix`**.

**Глобально (рекомендуется):**

```bash
pipx install helix-agent
# или: uv tool install helix-agent
helix version
```

**В venv** (после `source .venv/bin/activate`):

```bash
pip install helix-agent
helix version
```

**В пользовательский каталог** (`~/.local/bin` в PATH):

```bash
pip install --user helix-agent
export PATH="$HOME/.local/bin:$PATH"
helix version
```

### Из git

```bash
git clone https://github.com/YOUR_ORG/helix.git
cd helix
./scripts/install.sh          # macOS / Linux
# Windows: .\scripts\install.ps1
helix install
helix doctor
```

## Установка для разработки

```bash
uv sync
uv pip install -e .
cp .env.example .env
helix models setup
```

## Первый запуск

1. `cp .env.example .env`
2. `helix doctor`
3. `helix models setup`
4. `helix tui` или `helix chat-command`

Данные: `~/.helix/` (Linux/macOS), `%LOCALAPPDATA%\Helix\` (Windows) или `HELIX_HOME` — см. [CONFIGURATION.md](CONFIGURATION.md). Логи: [LOGS.md](LOGS.md).

## Обновление

```bash
helix update
helix update --check
```

## Docker

```bash
docker compose up -d
```

Подробнее: [DEPLOYMENT.md](DEPLOYMENT.md).

## Удаление

1. Удалите `helix` из PATH.
2. При необходимости удалите `~/.helix/`.
3. Удалите каталог клона.

См. также [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [DOCTOR.md](DOCTOR.md).