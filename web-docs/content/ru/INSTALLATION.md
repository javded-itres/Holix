# Установка

Helix требует **Python 3.12+** и устанавливается как CLI-команда `helix`.

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
| `tui-web` | `pip install "HelixAgentAi[tui-web]"` | `uv sync --extra tui-web` | `helix tui --web` |
| `windows` | `pip install "HelixAgentAi[windows]"` | `uv sync --extra windows` | `psutil` для процессов |
| `all` | `pip install "HelixAgentAi[all]"` | `uv sync --extra all` | всё выше |

После `browser`: `playwright install chromium`

## Быстрая установка (пользователям)

### PyPI — `helix` из любой папки (рекомендуется)

Опубликовано: [pypi.org/project/HelixAgentAi](https://pypi.org/project/HelixAgentAi/) (версия **0.1.8**).

Пакет **`HelixAgentAi`** (не `pip install helix` — это другой проект). Команда: **`helix`**.

**Глобально (рекомендуется):**

```bash
pipx install HelixAgentAi
# или: uv tool install HelixAgentAi
helix version
```

**В venv** (после `source .venv/bin/activate`):

```bash
pip install HelixAgentAi
helix version
```

**В пользовательский каталог** (`~/.local/bin` в PATH):

```bash
pip install --user HelixAgentAi
export PATH="$HOME/.local/bin:$PATH"
helix version
```

### Из git

```bash
git clone https://github.com/javded-itres/HelixAgent.git
cd HelixAgent
./scripts/install.sh          # macOS / Linux
# Windows: .\scripts\install.ps1
helix install
helix doctor
```

## Windows

**Требования:** Python 3.12+ с [python.org](https://www.python.org/downloads/) (при установке отметьте «Add python.exe to PATH»).  
**Рекомендуется:** [uv](https://github.com/astral-sh/uv).

### Глобальная команда `helix` из любой папки

**PyPI (проще всего):**

```powershell
pipx install HelixAgentAi
# или:
uv tool install HelixAgentAi

helix version
helix doctor
```

**Из git:**

```powershell
git clone https://github.com/javded-itres/HelixAgent.git
cd HelixAgent
.\scripts\install.ps1
# или, если helix уже в PATH:
helix install --extra telegram
```

Установщик добавляет Helix в PATH пользователя. **Откройте новое окно PowerShell**, затем `helix version`.

### Данные и профили

| Что | Путь |
|-----|------|
| Домашний каталог Helix | `%LOCALAPPDATA%\Helix\` (или `HELIX_HOME`) |
| Профили | `%LOCALAPPDATA%\Helix\profiles\<имя>\` |
| Лог gateway | `%LOCALAPPDATA%\Helix\profiles\<имя>\gateway\` |

### Типичный запуск

```powershell
helix models setup
helix tui
helix gateway start
helix -p shared telegram setup
```

Опционально extra `windows` для корректного завершения дочерних процессов: `pip install "HelixAgentAi[windows]"`.

### Проблемы на Windows

| Симптом | Решение |
|---------|---------|
| `helix` не найден | Новый терминал; проверьте `%USERPROFILE%\.local\bin` или повторите `.\scripts\install.ps1` |
| Скрипт заблокирован | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Кракозябры в TUI | Windows Terminal, кодировка UTF-8 |

Подробнее: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

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
helix update --channel pypi
helix update --check
```

Или: `pipx upgrade HelixAgentAi` / `pip install -U HelixAgentAi`

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