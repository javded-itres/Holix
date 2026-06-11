# Holix — полное руководство пользователя

Пошаговая инструкция: установка из `.whl`, первичная настройка, подключение к LiteLLM, MCP, навыки, Telegram и режимы работы.

> Все команды и пути взяты из репозитория Holix (`cli/`, `docs/`, `config.py`, `pyproject.toml`).  
> Пакет называется **`HelixAgentAi`**, команда в терминале — **`holix`**.

---

## Содержание

1. [Что умеет Holix](#1-что-умеет-holix)
2. [Требования](#2-требования)
3. [Шаг 1 — Установить Python](#3-шаг-1--установить-python)
4. [Шаг 2 — Установить UV (рекомендуется)](#4-шаг-2--установить-uv-рекомендуется)
5. [Шаг 3 — Установка с PyPI](#5-шаг-3--установка-с-pypi)
6. [Шаг 4 — Первый запуск и профиль](#6-шаг-4--первый-запуск-и-профиль)
7. [Шаг 5 — Настройка моделей через LiteLLM](#7-шаг-5--настройка-моделей-через-litellm)
8. [Шаг 6 — Поиск в интернете (опционально)](#8-шаг-6--поиск-в-интернете-опционально)
9. [Шаг 7 — Telegram-бот](#9-шаг-7--telegram-бот)
10. [Шаг 8 — Режимы выполнения](#10-шаг-8--режимы-выполнения)
11. [Шаг 9 — Как писать запросы](#11-шаг-9--как-писать-запросы)
12. [Шаг 10 — MCP пошагово](#12-шаг-10--mcp-пошагово)
13. [Шаг 11 — Навыки и плагины из Hub](#13-шаг-11--навыки-и-плагины-из-hub)
14. [Справочник CLI](#14-справочник-cli)
15. [Слэш-команды `/` в чате](#15-слэш-команды--в-чате)
16. [Особенности Holix](#16-особенности-holix)
17. [Что делать, если что-то не работает](#17-что-делать-если-что-то-не-работает)

---

## 1. Что умеет Holix

Holix — AI-агент с:

- **вызовом инструментов** — файлы, терминал, веб, код, опционально браузер (Playwright);
- **памятью** — SQLite + семантический поиск (ChromaDB);
- **навыками (skills)** — markdown-инструкции, каталоги Hub (ClawHub, Hermes, Claude plugins);
- **MCP** — подключение внешних серверов Model Context Protocol;
- **несколькими интерфейсами** — TUI (`holix tui`), чат (`holix chat-command`), один запрос (`holix run`), API (`holix gateway`), Telegram;
- **безопасностью** — подтверждение опасных действий, whitelist команд, API-ключи;
- **субагентами** — фоновые задачи в отдельных процессах;
- **планированием** — режимы с планом и согласованием шагов.

Данные хранятся в **`~/.holix/`** (Linux/macOS) или **`%LOCALAPPDATA%\Holix\`** (Windows).

---

## 2. Требования

| Компонент | Версия / примечание |
|-----------|---------------------|
| **Python** | **3.12+** (`requires-python` в `pyproject.toml`) |
| **uv** | рекомендуется для установки зависимостей |
| **LLM** | OpenAI-совместимый API (в этой инструкции — **LiteLLM**) |
| **Node.js / npx** | нужен для многих MCP-серверов (`holix doctor` проверит) |
| **Docker** | опционально (например, MCP GitHub) |

---

## 3. Шаг 1 — Установить Python

1. Откройте [https://www.python.org/downloads/](https://www.python.org/downloads/).
2. Скачайте **Python 3.12** или новее.
3. Установите. На Windows отметьте **«Add Python to PATH»**.
4. Проверьте в терминале:

```bash
python3 --version
# или на Windows:
python --version
```

Должно быть **3.12.x** или выше.

---

## 4. Шаг 2 — Установить UV (рекомендуется)

UV — быстрый менеджер пакетов Python. Holix в документации рекомендует его для разработки и установки.

**macOS / Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Проверка:**

```bash
uv --version
```

Альтернатива без UV: обычный `pip` (см. шаг 5).

---

## 5. Шаг 3 — Установка с PyPI

Пакет **[HolixAgentAi](https://pypi.org/project/HelixAgentAi/)** на PyPI; команда в терминале — **`holix`**.

> Не используйте `pip install helix` — на PyPI это **другой** проект.

### 5.1. Глобально (рекомендуется)

```bash
pipx install HelixAgentAi
holix version
```

С extras (Telegram, браузер, веб-TUI, голос):

```bash
pipx install "HelixAgentAi[all]"
```

Альтернатива: `uv tool install HolixAgentAi`

### 5.2. Виртуальное окружение

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install HelixAgentAi
pip install "HelixAgentAi[telegram]"
holix version
```

### 5.3. Пользовательский каталог (`~/.local/bin`)

```bash
pip install --user HolixAgentAi
export PATH="$HOME/.local/bin:$PATH"
holix version
```

### 5.4. Windows

Установка через PowerShell, пути `%LOCALAPPDATA%\Holix\` и troubleshooting: [INSTALLATION.md — Windows](INSTALLATION.md#windows).

```powershell
pipx install HelixAgentAi
holix version
# или из клона репозитория:
.\scripts\install.ps1
```

### 5.5. Альтернатива — установка из `.whl`

Для офлайн-машин или артефактов CI:

```bash
uv build && ls dist/holixagentai-*.whl
pipx install /путь/к/holixagentai-0.1.3-py3-none-any.whl
```

### 5.6. Проверка после установки

```bash
holix --help
holix doctor
```

---

## 6. Шаг 4 — Первый запуск и профиль

### 6.1. Создать файл окружения

При создании профиля Holix создаёт **`~/.holix/profiles/<имя>/.env`** из `.env.example` (или копирует legacy `~/.holix/.env`, если он есть).

```bash
holix profile env --edit
# или вручную:
cp .env.example ~/.holix/profiles/default/.env
```

Ключи API, порт gateway и флаги — в **`.env` профиля**, а не в глобальном `~/.holix/.env` (legacy только для старых установок).

### 6.2. Профиль

Каждый профиль — изолированное окружение:

```
~/.holix/profiles/<имя>/.env           # секреты и bind gateway
~/.holix/profiles/<имя>/telegram.env  # Telegram-бот (опционально)
~/.holix/profiles/<имя>/gateway/        # состояние и лог gateway
~/.holix/profiles/<имя>/config.yaml
~/.holix/profiles/<имя>/SOUL.md        # личность агента (каждая сессия)
~/.holix/profiles/<имя>/USER.md        # факты о вас
~/.holix/profiles/<имя>/INIT.md        # онбординг первого запуска (временно)
~/.holix/profiles/<имя>/data/
```

По умолчанию используется профиль **`default`**. При первом запуске Holix создаёт нужные каталоги.

**Первый диалог:** если есть `INIT.md`, агент представляется, узнаёт имя и предпочтения и сохраняет их в `USER.md` / `SOUL.md` встроенными инструментами. Скажите «сохрани свою личность» или «запомни, меня зовут …», когда будете готовы. Подробнее: [PROFILES.md](PROFILES.md#идентичность-агента-soul-init-user).

**Workspace jail** (опционально): ограничить файловые/терминальные инструменты одной папкой — `holix profile jail enable /path/to/dir`. См. [CONFIGURATION.md](CONFIGURATION.md).

**Whitelist терминала** (опционально): `holix profile whitelist enable`, `whitelist add "docker, make"`, `whitelist list` — см. [PROFILES.md](PROFILES.md).

Просмотр настроек:

```bash
holix status
holix config show
```

Смена профиля:

```bash
holix -p work tui
```

В чате: `/profile work` или `/profile` (список).

### 6.3. Диагностика

```bash
holix doctor
holix doctor --fix
```

Doctor проверяет: каталоги, YAML, LLM, gateway, Telegram, MCP env, платформу (node/npx/git).

---

## 7. Шаг 5 — Настройка моделей через LiteLLM

При локальном запуске LiteLLM используйте адрес по умолчанию:

**`http://localhost:4000`**

Holix общается с LiteLLM через **OpenAI-совместимый API** (`/v1/chat/completions`, `/v1/models`).

### 7.1. Что нужно получить у администратора LiteLLM

1. **Virtual API key** (ключ для клиентов) — сохраняется как `LITELLM_API_KEY`.
2. Список **имён моделей** (`model_name` в конфиге LiteLLM), которые вам разрешены.  
   В каталоге Holix для пресета `litellm` в качестве примеров указаны: `smart`, `fast`, `heavy` — **фактические имена на вашем сервере могут отличаться**; Holix покажет список при успешном подключении.

### 7.2. Записать ключ в `.env` профиля

Откройте `~/.holix/profiles/default/.env` (`holix profile env --edit`) и добавьте:

```bash
# LiteLLM proxy
LITELLM_API_BASE=http://localhost:4000/v1
LITELLM_API_KEY=sk-ваш-virtual-key-от-litellm
```

> Holix подставляет `${LITELLM_API_KEY}` и хост из `LITELLM_API_BASE` в `config.yaml` профиля.

Проверка доступности API (опционально, с машины пользователя):

```bash
curl -s http://localhost:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_API_KEY" | head
```

В ответе должен быть JSON со списком моделей.

### 7.3. Добавить провайдер LiteLLM в профиль (интерактивно)

```bash
holix models add litellm --host http://localhost:4000
```

Что произойдёт:

1. Holix предложит ввести API-ключ (если `LITELLM_API_KEY` уже в `.env` — возьмёт оттуда).
2. Подключится к `http://localhost:4000/v1`.
3. Загрузит список моделей с `/v1/models`.
4. Попросит выбрать **модель по умолчанию** для этого провайдера.
5. Сохранит настройки в `~/.holix/profiles/default/config.yaml`.

### 7.4. Полный мастер настройки (рекомендуется)

```bash
holix models setup
```

В меню:

| Пункт | Действие |
|-------|----------|
| **1** | Добавить провайдер (выберите пресет **litellm**, # из таблицы) |
| **2** | Список провайдеров |
| **3** | Тест подключения |
| **5** | **Назначить модели агентам** (`main`, субагентам) |
| **7** | Сохранить и выйти |

### 7.5. Назначение моделей агентам

В `holix models setup` → пункт **5** (Configure agent models):

- **`main`** — основной агент в чате;
- можно назначить разные модели субагентам (`researcher`, `coder`, …).

Просмотр назначений:

```bash
holix models agents
```

### 7.6. Пример фрагмента `config.yaml` после настройки

```yaml
default_provider: litellm
providers:
  litellm:
    base_url: http://localhost:4000/v1
    api_key: ${LITELLM_API_KEY}
    default_model: <имя-модели-из-списка-litellm>
    metadata:
      auth_type: bearer
      preset_id: litellm
agent_models:
  main:
    provider: litellm
    model: <имя-модели-из-списка-litellm>
    temperature: 0.7
```

### 7.7. Применить изменения

Если запущен gateway или Telegram:

```bash
holix gateway reload
```

В TUI смена модели на лету: `/models` или `/model`.

---

## 8. Шаг 6 — Поиск в интернете (опционально)

Holix поддерживает провайдеры: **DuckDuckGo** (по умолчанию), **SearXNG**, **Firecrawl**.

```bash
holix search configure   # интерактивный выбор провайдеров и порядка
holix search list
holix search test "тестовый запрос"
```

В чате: `/search`, `/search configure`, `/search test запрос`.

После настройки: `holix gateway reload`.

Секреты в `.env`: `FIRECRAWL_API_KEY`, `SEARXNG_BASE_URL` (см. `.env.example`).

---

## 9. Шаг 7 — Telegram-бот

### 9.1. Установить зависимость Telegram

```bash
uv sync --extra telegram
# или при установке wheel:
pip install "HelixAgentAi[telegram]"
```

### 9.2. Создать бота в Telegram

1. Откройте Telegram, найдите **[@BotFather](https://t.me/BotFather)**.
2. Отправьте команду **`/newbot`**.
3. Введите **имя** бота (отображаемое).
4. Введите **username** бота (должен заканчиваться на `bot`, например `my_company_holix_bot`).
5. BotFather пришлёт **токен** вида `123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` — сохраните его.

### 9.3. Подключить бота (админ)

```bash
holix -p shared telegram setup
```

Мастер проверяет токен через Telegram API (`getMe`), сохраняет его в **`~/.holix/profiles/<имя>/telegram.env`** и включает **режим запросов доступа** (`HOLIX_TELEGRAM_ACCESS_REQUESTS=true`). **User id при настройке вводить не нужно.**

Для production и мультипользовательского бота используйте **именованный** профиль (`-p shared`) — `default` в `HOLIX_ENV=production` недоступен.

### 9.4. Назначение Telegram-администратора (один раз, только CLI)

```bash
holix -p shared telegram requests approve USER_ID --set-admin
```

Создаёт профиль Holix **`admin`**, сохраняет единственного админа в `telegram.env` и включает меню команд. Из Telegram назначить нельзя. Проверка: `holix telegram admin show`.

### 9.5. Пользователи запрашивают доступ

1. Пользователь открывает бота в Telegram и отправляет **`/start`**.
2. Бот отвечает, что доступ ожидает одобрения (меню команд скрыто).
3. Telegram-администратор получает уведомление с командами CLI для одобрения или отклонения.

### 9.5.1. Админ одобряет и создаёт изолированный профиль

```bash
holix -p shared telegram requests list
holix -p shared telegram requests approve USER_ID -i
holix -p shared telegram requests approve USER_ID --create-profile ivan
```

Holix создаёт **защищённый** профиль (с `--create-profile`), включает **workspace jail**, привязывает пользователя, **отправляет ключ в Telegram** и включает меню команд. Перезапуск бота не нужен.

Другие варианты: `requests approve … --profile existing`, `requests reject USER_ID`.  
Ручные привязки: `holix telegram map set …` — см. [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).

### 9.6. Запуск бота

**Отдельно:**

```bash
holix telegram run
# или просто:
holix telegram
```

**Вместе с API gateway** (рекомендуется для постоянной работы):

```bash
HOLIX_ENV=production holix -p shared gateway start -f
```

Supervisor gateway также поднимает Telegram, если он настроен.

### 9.7. Обновить меню команд в Telegram

```bash
holix telegram sync-menu
```

Обновляет меню **только для одобренных** пользователей (скрыто до approve). После изменения навыков, MCP или слэш-команд.

### 9.8. Голосовые сообщения (опционально)

Если чат уже через LiteLLM, для Whisper настройте модель транскрибации **в конфиге LiteLLM** и в `.env` профиля:

```bash
HOLIX_WHISPER_BASE_URL=http://localhost:4000/v1
HOLIX_WHISPER_API_KEY=sk-...          # virtual key LiteLLM
HOLIX_WHISPER_MODEL=whisper           # model_name из LiteLLM (не whisper-1)
HOLIX_TELEGRAM_VOICE_LANGUAGE=ru
```

Подробнее: [TELEGRAM.md](TELEGRAM.md).

### 9.8. Production

При `HOLIX_ENV=production`:

- используйте **именованный** профиль бота (`-p shared`), не `default`;
- предпочтительно **запросы доступа** (`telegram setup` + `telegram requests approve --create-profile`);
- или задайте `HOLIX_TELEGRAM_ALLOWED_USERS` для личного бота на одного пользователя.

Полная инструкция: [TELEGRAM.md](TELEGRAM.md).

---

## 10. Шаг 8 — Режимы выполнения

В TUI и Telegram доступны четыре режима:

| Режим | Имя | Когда использовать |
|-------|-----|-------------------|
| **ReAct** | `react` | Быстрые вопросы, инструменты, разведка (по умолчанию) |
| **План** | `plan_and_execute` | Многошаговые задачи с понятными подцелями |
| **Гибрид** | `hybrid` | Крупные задачи: план, затем гибкая работа по шагам |
| **Авто** | `auto` | Holix сам выбирает режим через классификатор |

Переключение: **`/mode`**, **`/mode <имя>`** или **Shift+Tab**. Для планов — `/plan-confirm`, `/plan-auto`, `/plan-refine`, `/plan-reject`. Для рискованных инструментов — `/yes`, `/1`–`/4`.

**Подробно: схемы, поведение, настройки и примеры промптов** — [EXECUTION_MODES.md](EXECUTION_MODES.md).

---

## 11. Шаг 9 — Как писать запросы

1. Указывайте **пути к файлам** и **ожидаемый результат**.
2. Для кода — язык, фреймворк, ограничения.
3. Команды с `/` в начале — **слэш-команды**, они **не** уходят в LLM (`/help`, `/mode`, …).
4. Подбирайте режим под размер задачи — примеры промптов в [EXECUTION_MODES.md](EXECUTION_MODES.md).

---

## 12. Шаг 10 — MCP пошагово

MCP (Model Context Protocol) добавляет внешние инструменты (GitHub, файловая система, документация и т.д.).

### 12.1. Посмотреть популярные серверы

```bash
holix mcp list-popular
```

Примеры из каталога: `filesystem`, `github`, `context7`, `compass`, `postgres`, …

### 12.2. Установить MCP (простой способ)

```bash
holix mcp install
```

Интерактивно: выбор из списка → ввод параметров (пути, API-ключи) → тест → сохранение в профиль.

Или по имени:

```bash
holix mcp install context7
holix mcp install filesystem
```

Из git:

```bash
holix mcp install https://github.com/upstash/context7
```

### 12.3. Назначить MCP агентам

```bash
holix mcp assign
```

Например: `main` видит `filesystem` и `context7`, субагент `researcher` — только `context7`.

Проверка:

```bash
holix mcp list
holix mcp test <имя-сервера>
holix mcp tools
```

### 12.4. Полный мастер

```bash
holix mcp setup
```

Добавление серверов + назначение ролям.

### 12.5. В чате (TUI / Telegram)

```
/mcp
/mcp list
/mcp install
/mcp assign
/mcp test filesystem
/mcp tools
/mcp remove <имя>
```

### 12.6. Применить

```bash
holix gateway reload
```

Инструменты MCP в агенте имеют имена вида **`mcp_<сервер>_<tool>`**.

### 12.7. Переменные окружения для MCP

Секреты в конфиге MCP: `${GITHUB_TOKEN}`, `${CONTEXT7_API_KEY}` и т.д.  
Значения — в `~/.holix/.env`.  
`holix doctor` предупредит о неразрешённых `${VAR}`.

---

## 13. Шаг 11 — Навыки и плагины из Hub

### 13.1. Что такое skills

**Skill** — файл `SKILL.md` с инструкциями для агента.  
Хранятся в: `~/.holix/profiles/<profile>/data/skills/`

### 13.2. Установка из Hub (CLI)

```bash
# поиск
holix hub search "docker" -s clawhub
holix hub search "git" -s clawhub

# интерактивный обзор
holix hub browse

# установка
holix hub install <spec>
holix hub install <spec> --agents main,coder
```

Форматы spec (из документации Hub):

| Префикс | Пример |
|---------|--------|
| ClawHub | `my-skill` или `clawhub:slug@1.0` |
| Claude plugin | `claude:github@claude-official` |
| Hermes | `hermes:api-builder` |
| skills.sh | `skills-sh/owner/repo/path` |
| Git | `git:https://github.com/...` |

Плагины Claude могут добавить MCP (`--with-mcp` по умолчанию).

### 13.3. В TUI

```
/hub                  — выбор каталога
/hub browse           — поиск и установка
/hub installed        — что установлено
/skills               — подсказка по списку навыков
```

### 13.4. Назначение навыков агентам

По умолчанию **`main`** видит все навыки профиля.  
Ограничение — поле `skill_assignments` в `config.yaml`:

```bash
holix skills list --agent main
holix skills assign docker-manager --agents main,coder
holix skills unassign docker-manager --agent coder
holix skills assign-wizard    # интерактивно
```

### 13.5. Обновления Hub

```bash
holix hub list
holix hub check-updates
holix hub update
holix hub autoupdate --enable
holix hub slash-sync          # обновить skill-slash.json
```

### 13.6. Применить

```bash
holix gateway reload
```

---

## 14. Справочник CLI

Глобальные опции: **`--profile` / `-p`**, **`--verbose` / `-v`**.

### Основные команды

| Команда | Назначение |
|---------|------------|
| `holix tui` | Полноэкранный интерфейс (рекомендуется) |
| `holix chat-command` | Чат в терминале |
| `holix run "запрос"` | Один запрос без входа в чат |
| `holix status` | Статус профиля |
| `holix version` | Версия |
| `holix clear` | Очистить data профиля |
| `holix doctor` | Диагностика |
| `holix install` | Установка holix в PATH (из исходников) |
| `holix update` | Обновление |

### `holix models`

| Подкоманда | Описание |
|------------|----------|
| `setup` | Интерактивный мастер |
| `add <preset>` | Добавить провайдер (`litellm`, `ollama`, …) |
| `presets` | Список пресетов |
| `list` | Провайдеры в профиле |
| `agents` | Назначения моделей агентам |

### `holix config`

| Подкоманда | Описание |
|------------|----------|
| `show` | Показать YAML |
| `edit` | Редактор |
| `set ключ значение` | Изменить поле |

### `holix mcp`

`list`, `add`, `remove`, `test`, `assign`, `setup`, `list-popular`, `install`

### `holix hub`

`search`, `browse`, `install`, `list`, `remove`, `check-updates`, `update`, `autoupdate`, `slash-sync`

### `holix skills`

`list`, `search`, `show`, `assign`, `unassign`, `agents`, `assign-wizard`

### `holix memory`

`search "<запрос>"`

### `holix search`

`configure`, `list`, `test`

### `holix gateway`

`start`, `stop`, `status`, `reload`  
Эндпоинты: `/health`, `/v1/chat/completions`, … — см. [GATEWAY.md](GATEWAY.md).

### `holix cron`

Требует запущенный gateway.  
`add`, `list`, `enable`, `disable`, `remove`

### `holix logs`

`holix logs`, `holix logs -f`, `holix logs -s agent`, `holix logs list`, `holix logs rotate`, `holix logs debug on`

### `holix telegram`

`setup`, `admin show|clear`, `requests list|approve|reject` (`--set-admin`, `-i`), `run`, `status`, `sync-menu`, `map set|list|remove|bind|import` — см. [TELEGRAM.md](TELEGRAM.md) и [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md)

---

## 15. Слэш-команды `/` в чате

Работают в **TUI**, **Telegram** и частично в **`holix chat-command`**.

Полный список: [SLASH_COMMANDS.md](SLASH_COMMANDS.md).

Кратко:

| Группа | Примеры |
|--------|---------|
| Справка | `/help`, `/status`, `/clear` |
| Модели и режим | `/models`, `/mode`, `/stream`, `/stop` |
| Сессии | `/new`, `/sessions`, `/switch N`, `/profile` |
| Память | `/memory запрос`, `/memory-clear` |
| План | `/plan-confirm`, `/plan-auto`, `/plan-refine`, `/plan-reject` |
| Подтверждения | `/yes`, `/no`, `/1`…`/4` |
| MCP | `/mcp`, `/mcp install`, `/mcp assign` |
| Hub | `/hub`, `/hub browse`, `/hub installed` |
| Субагенты | `/subagents`, `/subagent-spawn`, `/subagent-result` |
| Поиск | `/search`, `/search configure`, `/search test` |
| Cron | `/cron`, `/cron add …` |

На macOS с русской раскладкой `/` — **Shift+7**.

---

## 16. Особенности Holix

1. **Профили** — несколько изолированных конфигураций (`holix -p имя`).
2. **Память** — диалоги + долгосрочная память + семантический поиск (`/memory`).
3. **Подтверждения** — опасные tool-вызовы требуют явного согласия.
4. **План с ревью** — многошаговые задачи не выполняются молча без вашего OK (если включено).
5. **Субагенты** — фоновые worker-процессы; основной чат не блокируется (`/subagent-spawn`).
6. **MCP и Hub** — расширение без правки кода агента.
7. **Мультиинтерфейс** — один профиль для TUI, Telegram и API gateway.
8. **Логи** — структурированные логи agent/gateway/cron/subagent (`holix logs`).
9. **Doctor** — самодиагностика окружения.
10. **OpenAI-совместимый API** — gateway для интеграции с другими клиентами.
11. **Голос в Telegram** — Whisper через LiteLLM, OpenAI или локально (`faster-whisper`).
12. **Сжатие контекста** — `/compress` при переполнении окна модели.

---

## 17. Что делать, если что-то не работает

```bash
holix doctor
holix doctor --fix
holix logs -l error -n 50
```

| Проблема | Что проверить |
|----------|----------------|
| `holix: command not found` | PATH, venv, `pipx` / `uv tool` |
| Нет ответа от модели | `LITELLM_API_KEY`, URL, `holix models list`, curl `/v1/models` |
| MCP не появляется | `holix mcp test`, `holix gateway reload`, `holix doctor` |
| Telegram молчит | `holix telegram status`, токен, `telegram requests list`, `holix gateway status` |
| Старые слэш-команды | `holix telegram sync-menu`, `holix gateway reload` |

Подробнее: [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [DOCTOR.md](DOCTOR.md).

---

## Быстрый чеклист «с нуля до чата»

1. Python 3.12+  
2. `uv` или `pip`  
3. `uv pip install holixagentai-….whl` (или `pipx install …`)  
4. `~/.holix/.env` с `LITELLM_API_BASE` и `LITELLM_API_KEY`  
5. `holix models add litellm --host http://localhost:4000`  
6. `holix models setup` → назначить модель для `main`  
7. `holix doctor`  
8. `holix tui` или `holix -p shared telegram setup` + `holix -p shared gateway start`  
9. По необходимости: `holix mcp install`, `holix hub browse`, `holix search configure`  

---

## См. также

- [INSTALLATION.md](INSTALLATION.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- [CLI.md](CLI.md)
- [SLASH_COMMANDS.md](SLASH_COMMANDS.md)
- [TELEGRAM.md](TELEGRAM.md)
- [HUB.md](HUB.md)
- [GATEWAY.md](GATEWAY.md)