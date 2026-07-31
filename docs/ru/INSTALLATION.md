# Установка

Holix требует **Python 3.12+** (для локальной установки) и устанавливается как команда **`holix`**. Выберите один путь ниже.

## Выберите путь

| Путь | Когда подходит | Результат |
|------|----------------|-----------|
| **A — Локально (uv / pipx)** | Ежедневная работа, разработка, TUI, несколько профилей на машине | `holix` на хосте; данные в `~/.holix/` (или `%LOCALAPPDATA%\Holix\`) |
| **B — Docker** | Сервер, в первую очередь Telegram, минимум зависимостей на хосте | Контейнер: gateway + Telegram + cron в одном процессе |

После любого пути — [START_HERE.md](START_HERE.md) (чеклист первого запуска).

---

## Требования (оба пути)

| Компонент | Примечание |
|-----------|------------|
| Python 3.12+ | Только путь A (на хосте) |
| [uv](https://github.com/astral-sh/uv) | **Рекомендуется** для пути A — установка, sync, `uv tool install`, `uv run` |
| LLM | OpenAI-совместимый API (Ollama, LiteLLM, OpenAI, Groq, …) |

### Опциональные extras (путь A)

| Extra | PyPI | Из исходников | Назначение |
|-------|------|---------------|------------|
| `telegram` | `pip install "Holix[telegram]"` | `uv sync --extra telegram` | Telegram-бот |
| `browser` | `pip install "Holix[browser]"` | `--extra browser` | Playwright — [BROWSER_TOOLS.md](BROWSER_TOOLS.md) |
| `voice` | `pip install "Holix[voice]"` | `--extra voice` | Голос в Telegram |
| `tui-web` | `pip install "Holix[tui-web]"` | `--extra tui-web` | `holix tui --web` |
| `windows` | `pip install "Holix[windows]"` | `--extra windows` | Завершение дерева процессов |
| `all` | `pip install "Holix[all]"` | `--extra all` | всё выше |

После `browser`: `playwright install chromium`

Пакет на PyPI: **[Holix](https://pypi.org/project/Holix/)**. Команда: **`holix`**. Не используйте `pip install helix` — это другой проект.

---

## Путь A — Локальная установка

### A1 — uv tool install (рекомендуется)

Глобальный `holix` без ручного venv:

```bash
uv tool install Holix
uv tool install "Holix[all]"

holix version
holix bootstrap
holix doctor
```

Обновление: `uv tool upgrade Holix` или `holix update --channel pypi`.

### A2 — Установка одной командой (curl)

macOS/Linux: язык, полная/минимальная установка, PyPI, `holix bootstrap`:

```bash
curl -fsSL https://raw.githubusercontent.com/javded-itres/Holix/main/scripts/install.sh | bash
```

| Выбор | Пакет | Состав |
|-------|-------|--------|
| **Полная** | `Holix[all]` | Telegram, браузер, голос, web TUI |
| **Минимальная** | `Holix` | CLI, TUI, gateway, MCP |

Повтор настройки:

```bash
HOLIX_BOOTSTRAP_LANG=ru bash install.sh
holix bootstrap --lang en
holix bootstrap --skip-telegram
holix bootstrap -y
```

Подробнее: [START_HERE.md](START_HERE.md#1-install).

### A3 — pipx или pip

```bash
pipx install Holix
holix bootstrap
```

В venv:

```bash
python -m venv .venv && source .venv/bin/activate
pip install "Holix[telegram]"
holix doctor
```

В `~/.local/bin` (добавьте в PATH):

```bash
pip install --user Holix
export PATH="$HOME/.local/bin:$PATH"
```

### A4 — Windows

Python 3.12+ с [python.org](https://www.python.org/downloads/) — **Add python.exe to PATH**.

```powershell
uv tool install Holix
holix version
holix doctor
```

Из git: `.\scripts\install.ps1` — после установки **новое** окно PowerShell.

| Что | Путь |
|-----|------|
| Домашний каталог | `%LOCALAPPDATA%\Holix\` |
| Профили | `%LOCALAPPDATA%\Holix\profiles\<имя>\` |

Опционально: `Holix[windows]`.

### A5 — Из git (разработка)

```bash
git clone https://github.com/javded-itres/Holix.git
cd Holix
uv sync
uv pip install -e .
cp .env.example .env
holix doctor
holix models setup
```

Без глобальной установки:

```bash
uv run holix tui
```

Или: `./scripts/install.sh` / `holix install --extra telegram`.

### Путь A — первый запуск

Обычно делает `holix bootstrap`. Иначе:

```bash
holix doctor
holix models setup
holix telegram setup
holix tui
```

Данные: `~/.holix/` или `HOLIX_HOME`. Конфигурация: [CONFIGURATION.md](CONFIGURATION.md). Логи: [LOGS.md](LOGS.md).

### Путь A — обновление и удаление

```bash
holix update --channel pypi
```

Удаление: `uv tool uninstall Holix` / `pipx uninstall Holix`; при необходимости удалите `~/.holix/`.

---

## Путь B — Docker

Python на хосте не нужен. В образе уже Telegram, voice, browser.

Файлы:

| Файл | Назначение |
|------|------------|
| `docker-compose.yml` | Агент + опционально Ollama + профиль gateway-only |
| `docker-compose.prod.yml` | Bind-mount хранилища, restart always, ротация логов |
| `docker/env.example` | Полный шаблон env → скопировать в `.env` |
| `./extensions/` | Drop-in расширения (монтируются в контейнер) |

### B1 — Быстрый старт (модель + Telegram → рабочий агент)

```bash
cp docker/env.example .env
# Минимум:
#   TELEGRAM_BOT_TOKEN=123456789:AAH...
#   MODEL=gpt-4o-mini
#   BASE_URL=https://api.openai.com/v1
#   API_KEY=sk-...
#   HOLIX_API_KEY_PEPPER=$(openssl rand -hex 32)

docker compose up -d --build
# с локальной Ollama:
# docker compose --profile ollama up -d --build
```

При старте создаётся профиль `shared` (в production `default` запрещён), пишутся LLM и Telegram в `HOLIX_HOME`, включается workspace jail, поднимаются **gateway + Telegram + cron**.

Health: `http://127.0.0.1:8000/health`

### B2 — Одобрение пользователей Telegram (мультипользователь)

Пользователь шлёт `/start`. Одобрение из контейнера:

```bash
docker compose exec holix holix -p shared telegram requests list
docker compose exec holix holix -p shared telegram requests approve USER_ID --create-profile alice
docker compose exec holix holix -p shared telegram requests approve USER_ID --profile existing
```

У каждого пользователя — изолированный профиль `profiles/<name>/` (память, workspace, SOUL). Хост-бот: **именованный** профиль (`-p shared`).

### B3 — Только gateway (API без мессенджеров)

```bash
docker compose --profile gateway-only up -d holix-gateway
```

Тот же образ и тома; companions Telegram/MAX не стартуют. Удобно за Studio, мобильным клиентом или reverse proxy.

### B4 — Production multi-user (файловое хранилище на хосте)

```bash
mkdir -p ./data/holix ./extensions ./data/files
# в .env (пути → bind mounts через docker-compose.yml):
#   HOLIX_DATA_DIR=./data/holix
#   HOLIX_EXTENSIONS_DIR=./extensions
#   HOLIX_FILES_DIR=./data/files
# + секреты, MODEL, TELEGRAM_BOT_TOKEN
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

| Env / путь на хосте | Контейнер | Содержимое |
|---------------------|-----------|------------|
| `HOLIX_DATA_DIR` (по умолчанию том `holix-data`) | `/data/.holix` | Профили, память, gateway, telegram.env |
| `HOLIX_EXTENSIONS_DIR` (по умолчанию `./extensions`) | `/data/.holix/extensions` | Drop-in / git-clone расширения |
| `HOLIX_FILES_DIR` (по умолчанию `./data/files`) | `/data/files` | Общие файлы хоста (опционально) |

Workspace: `$HOLIX_DATA_DIR/profiles/<user>/workspace/` (`HOLIX_WORKSPACE_JAIL=true` по умолчанию).

### B5 — Расширения (загрузка и регистрация)

**Drop-in (без пересборки образа):**

```bash
git clone <repo> ./extensions/my-billing
docker compose restart holix
docker compose exec holix holix extensions list
docker compose exec holix holix extensions agent-list
```

**Pip при старте** (в `.env`, через запятую):

```bash
HOLIX_EXTENSIONS_PIP=some-pypi-package,/data/.holix/extensions/local-pkg
HOLIX_EXTENSIONS_SYNC=true
```

См. [EXTENSIONS.md](EXTENSIONS.md).

### B6 — Основные переменные

| Переменная | Назначение |
|------------|------------|
| `TELEGRAM_BOT_TOKEN` | Токен бота |
| `MODEL`, `BASE_URL`, `API_KEY` | OpenAI-совместимая LLM |
| `HOLIX_API_KEY_PEPPER` | **Обязателен** в production |
| `HOLIX_PROFILE` | Профиль хоста бота (по умолчанию `shared`) |
| `HOLIX_WORKSPACE_JAIL` | Изоляция файлов на профиль |
| `HOLIX_TELEGRAM_AUTOSTART` | Companion Telegram (`false` = только API) |
| `HOLIX_EXTENSIONS_PIP` | pip/path-пакеты при старте |
| `HOLIX_DATA_DIR` | Путь `HOLIX_HOME` на хосте (prod compose) |

Полный шаблон: [`docker/env.example`](../../docker/env.example).

### B7 — Что внутри

Команда `agent` (по умолчанию): `holix gateway start -f` — gateway, Telegram/MAX при наличии токенов, cron, sidecars расширений.

Команды entrypoint: `agent` | `gateway` | `telegram` | `max` | `bootstrap` | `extensions` | `cli` | `shell`.

Эксплуатация (systemd, TLS, шифрование): [DEPLOYMENT.md](DEPLOYMENT.md).

---

## Решение проблем при установке

| Симптом | Действие |
|---------|----------|
| `holix: command not found` | Добавьте `~/.local/bin` в PATH или `uv tool install Holix` |
| Версия Python | 3.12+; `uv python install 3.12` |
| Ошибки после git pull | `uv sync && uv pip install -e .` |
| Doctor: нет провайдера | `holix models setup` |
| Docker: бот молчит | Токен, логи, `telegram requests approve` |
| Windows: скрипт заблокирован | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

Подробнее: [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [DOCTOR.md](DOCTOR.md).

## См. также

- [START_HERE.md](START_HERE.md) — чеклист после установки
- [CONFIGURATION.md](CONFIGURATION.md) — `.env`, профили
- [DEPLOYMENT.md](DEPLOYMENT.md) — systemd, reverse proxy
- [PYPI.md](PYPI.md) — публикация (для мейнтейнеров)