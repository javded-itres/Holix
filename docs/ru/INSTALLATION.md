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

### B1 — Быстрый старт

```bash
export TELEGRAM_BOT_TOKEN="123456789:AAH..."
docker compose up -d
```

При первом запуске создаётся `HOLIX_HOME` в контейнере.

### B2 — Одобрение пользователей Telegram

Пользователь отправляет `/start`. Одобрение из контейнера:

```bash
docker compose exec holix holix -p shared telegram requests list
docker compose exec holix holix -p shared telegram requests approve USER_ID --create-profile alice
docker compose exec holix holix -p shared telegram requests approve USER_ID --profile existing
```

Используйте **именованный** профиль бота (`-p shared`). В production профиль `default` недоступен.

### B3 — Переменные окружения

| Переменная | Назначение |
|------------|------------|
| `TELEGRAM_BOT_TOKEN` | Токен бота |
| `MODEL`, `BASE_URL` | Облачная LLM вместо Ollama в контейнере |
| `HOLIX_API_KEY_PEPPER` | Хеширование API-ключей |
| `HOLIX_ENV=production` | Политика production |

Смонтируйте том для `HOLIX_HOME`, чтобы сохранить профили между перезапусками (см. `docker-compose.yml` в репозитории).

### B4 — Что работает внутри

`holix gateway start -f` — gateway, Telegram и cron в одном процессе.

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