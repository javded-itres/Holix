# Установка

Holix требует **Python 3.12+** и устанавливается как CLI-команда `holix`.

## Требования

| Компонент | Примечание |
|-----------|------------|
| Python | 3.12+ |
| [uv](https://github.com/astral-sh/uv) | Рекомендуется |
| LLM | OpenAI-совместимый API (Ollama, LiteLLM, OpenAI, Groq, …) |

Опциональные extras:

| Extra | PyPI (`pip` / `pipx`) | Из исходников (`uv sync`) | Назначение |
|-------|----------------------|---------------------------|------------|
| `telegram` | `pip install "HelixAgentAi[telegram]"` | `uv sync --extra telegram` | Telegram-бот |
| `browser` | `pip install "HelixAgentAi[browser]"` | `uv sync --extra browser` | Playwright — [BROWSER_TOOLS.md](BROWSER_TOOLS.md) |
| `voice` | `pip install "HelixAgentAi[voice]"` | `uv sync --extra voice` | Голосовые сообщения (Whisper) |
| `tui-web` | `pip install "HelixAgentAi[tui-web]"` | `uv sync --extra tui-web` | `holix tui --web` |
| `windows` | `pip install "HelixAgentAi[windows]"` | `uv sync --extra windows` | `psutil` для процессов |
| `all` | `pip install "HelixAgentAi[all]"` | `uv sync --extra all` | всё выше |

После `browser`: `playwright install chromium`

## Быстрая установка (пользователям)

### PyPI — `holix` из любой папки (рекомендуется)

Опубликовано: [pypi.org/project/HelixAgentAi](https://pypi.org/project/HelixAgentAi/) (версия **0.1.8**).

Пакет **`HelixAgentAi`** (не `pip install helix` — это другой проект). Команда: **`holix`**.

**Глобально (рекомендуется):**

```bash
pipx install HelixAgentAi
# или: uv tool install HolixAgentAi
holix version
```

**В venv** (после `source .venv/bin/activate`):

```bash
pip install HelixAgentAi
holix version
```

**В пользовательский каталог** (`~/.local/bin` в PATH):

```bash
pip install --user HolixAgentAi
export PATH="$HOME/.local/bin:$PATH"
holix version
```

### Из git

```bash
git clone https://github.com/javded-itres/Holix.git
cd HolixAgent
./scripts/install.sh          # macOS / Linux
# Windows: .\scripts\install.ps1
holix install
holix doctor
```

## Windows

**Требования:** Python 3.12+ с [python.org](https://www.python.org/downloads/) (при установке отметьте «Add python.exe to PATH»).  
**Рекомендуется:** [uv](https://github.com/astral-sh/uv).

### Глобальная команда `holix` из любой папки

**PyPI (проще всего):**

```powershell
pipx install HelixAgentAi
# или:
uv tool install HolixAgentAi

holix version
holix doctor
```

**Из git:**

```powershell
git clone https://github.com/javded-itres/Holix.git
cd HolixAgent
.\scripts\install.ps1
# или, если holix уже в PATH:
holix install --extra telegram
```

Установщик добавляет Holix в PATH пользователя. **Откройте новое окно PowerShell**, затем `holix version`.

### Данные и профили

| Что | Путь |
|-----|------|
| Домашний каталог Holix | `%LOCALAPPDATA%\Holix\` (или `HOLIX_HOME`) |
| Профили | `%LOCALAPPDATA%\Holix\profiles\<имя>\` |
| Лог gateway | `%LOCALAPPDATA%\Holix\profiles\<имя>\gateway\` |

### Типичный запуск

```powershell
holix models setup
holix tui
holix gateway start
holix -p shared telegram setup
```

Опционально extra `windows` для корректного завершения дочерних процессов: `pip install "HelixAgentAi[windows]"`.

### Проблемы на Windows

| Симптом | Решение |
|---------|---------|
| `holix` не найден | Новый терминал; проверьте `%USERPROFILE%\.local\bin` или повторите `.\scripts\install.ps1` |
| Скрипт заблокирован | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Кракозябры в TUI | Windows Terminal, кодировка UTF-8 |

Подробнее: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Установка для разработки

```bash
uv sync
uv pip install -e .
cp .env.example .env
holix models setup
```

## Первый запуск

1. `cp .env.example .env`
2. `holix doctor`
3. `holix models setup`
4. `holix tui` или `holix chat-command`

Данные: `~/.holix/` (Linux/macOS), `%LOCALAPPDATA%\Holix\` (Windows) или `HOLIX_HOME` — см. [CONFIGURATION.md](CONFIGURATION.md). Логи: [LOGS.md](LOGS.md).

## Обновление

```bash
holix update --channel pypi
holix update --check
```

Или: `pipx upgrade HolixAgentAi` / `pip install -U HolixAgentAi`

## Docker

```bash
docker compose up -d
```

Подробнее: [DEPLOYMENT.md](DEPLOYMENT.md).

## Удаление

1. Удалите `holix` из PATH.
2. При необходимости удалите `~/.holix/`.
3. Удалите каталог клона.

См. также [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [DOCTOR.md](DOCTOR.md).