# Helix — полное руководство пользователя

Пошаговая инструкция: установка из `.whl`, первичная настройка, подключение к LiteLLM, MCP, навыки, Telegram и режимы работы.

> Все команды и пути взяты из репозитория Helix (`cli/`, `docs/`, `config.py`, `pyproject.toml`).  
> Пакет называется **`HelixAgentAi`**, команда в терминале — **`helix`**.

---

## Содержание

1. [Что умеет Helix](#1-что-умеет-helix)
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
16. [Особенности Helix](#16-особенности-helix)
17. [Что делать, если что-то не работает](#17-что-делать-если-что-то-не-работает)

---

## 1. Что умеет Helix

Helix — AI-агент с:

- **вызовом инструментов** — файлы, терминал, веб, код, опционально браузер (Playwright);
- **памятью** — SQLite + семантический поиск (ChromaDB);
- **навыками (skills)** — markdown-инструкции, каталоги Hub (ClawHub, Hermes, Claude plugins);
- **MCP** — подключение внешних серверов Model Context Protocol;
- **несколькими интерфейсами** — TUI (`helix tui`), чат (`helix chat-command`), один запрос (`helix run`), API (`helix gateway`), Telegram;
- **безопасностью** — подтверждение опасных действий, whitelist команд, API-ключи;
- **субагентами** — фоновые задачи в отдельных процессах;
- **планированием** — режимы с планом и согласованием шагов.

Данные хранятся в **`~/.helix/`** (Linux/macOS) или **`%LOCALAPPDATA%\Helix\`** (Windows).

---

## 2. Требования

| Компонент | Версия / примечание |
|-----------|---------------------|
| **Python** | **3.12+** (`requires-python` в `pyproject.toml`) |
| **uv** | рекомендуется для установки зависимостей |
| **LLM** | OpenAI-совместимый API (в этой инструкции — **LiteLLM**) |
| **Node.js / npx** | нужен для многих MCP-серверов (`helix doctor` проверит) |
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

UV — быстрый менеджер пакетов Python. Helix в документации рекомендует его для разработки и установки.

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

Пакет **[HelixAgentAi](https://pypi.org/project/HelixAgentAi/)** на PyPI; команда в терминале — **`helix`**.

> Не используйте `pip install helix` — на PyPI это **другой** проект.

### 5.1. Глобально (рекомендуется)

```bash
pipx install HelixAgentAi
helix version
```

С extras (Telegram, браузер, веб-TUI, голос):

```bash
pipx install "HelixAgentAi[all]"
```

Альтернатива: `uv tool install HelixAgentAi`

### 5.2. Виртуальное окружение

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install HelixAgentAi
pip install "HelixAgentAi[telegram]"
helix version
```

### 5.3. Пользовательский каталог (`~/.local/bin`)

```bash
pip install --user HelixAgentAi
export PATH="$HOME/.local/bin:$PATH"
helix version
```

### 5.4. Windows

Установка через PowerShell, пути `%LOCALAPPDATA%\Helix\` и troubleshooting: [INSTALLATION.md — Windows](INSTALLATION.md#windows).

```powershell
pipx install HelixAgentAi
helix version
# или из клона репозитория:
.\scripts\install.ps1
```

### 5.5. Альтернатива — установка из `.whl`

Для офлайн-машин или артефактов CI:

```bash
uv build && ls dist/helixagentai-*.whl
pipx install /путь/к/helixagentai-0.1.3-py3-none-any.whl
```

### 5.6. Проверка после установки

```bash
helix --help
helix doctor
```

---

## 6. Шаг 4 — Первый запуск и профиль

### 6.1. Создать файл окружения

При создании профиля Helix создаёт **`~/.helix/profiles/<имя>/.env`** из `.env.example` (или копирует legacy `~/.helix/.env`, если он есть).

```bash
helix profile env --edit
# или вручную:
cp .env.example ~/.helix/profiles/default/.env
```

Ключи API, порт gateway и флаги — в **`.env` профиля**, а не в глобальном `~/.helix/.env` (legacy только для старых установок).

### 6.2. Профиль

Каждый профиль — изолированное окружение:

```
~/.helix/profiles/<имя>/.env           # секреты и bind gateway
~/.helix/profiles/<имя>/telegram.env  # Telegram-бот (опционально)
~/.helix/profiles/<имя>/gateway/        # состояние и лог gateway
~/.helix/profiles/<имя>/config.yaml
~/.helix/profiles/<имя>/data/
```

По умолчанию используется профиль **`default`**. При первом запуске Helix создаёт нужные каталоги.

**Workspace jail** (опционально): ограничить файловые/терминальные инструменты одной папкой — `helix profile jail enable /path/to/dir`. См. [CONFIGURATION.md](CONFIGURATION.md).

**Whitelist терминала** (опционально): `helix profile whitelist enable`, `whitelist add "docker, make"`, `whitelist list` — см. [PROFILES.md](PROFILES.md).

Просмотр настроек:

```bash
helix status
helix config show
```

Смена профиля:

```bash
helix -p work tui
```

В чате: `/profile work` или `/profile` (список).

### 6.3. Диагностика

```bash
helix doctor
helix doctor --fix
```

Doctor проверяет: каталоги, YAML, LLM, gateway, Telegram, MCP env, платформу (node/npx/git).

---

## 7. Шаг 5 — Настройка моделей через LiteLLM

При локальном запуске LiteLLM используйте адрес по умолчанию:

**`http://localhost:4000`**

Helix общается с LiteLLM через **OpenAI-совместимый API** (`/v1/chat/completions`, `/v1/models`).

### 7.1. Что нужно получить у администратора LiteLLM

1. **Virtual API key** (ключ для клиентов) — сохраняется как `LITELLM_API_KEY`.
2. Список **имён моделей** (`model_name` в конфиге LiteLLM), которые вам разрешены.  
   В каталоге Helix для пресета `litellm` в качестве примеров указаны: `smart`, `fast`, `heavy` — **фактические имена на вашем сервере могут отличаться**; Helix покажет список при успешном подключении.

### 7.2. Записать ключ в `.env` профиля

Откройте `~/.helix/profiles/default/.env` (`helix profile env --edit`) и добавьте:

```bash
# LiteLLM proxy
LITELLM_API_BASE=http://localhost:4000/v1
LITELLM_API_KEY=sk-ваш-virtual-key-от-litellm
```

> Helix подставляет `${LITELLM_API_KEY}` и хост из `LITELLM_API_BASE` в `config.yaml` профиля.

Проверка доступности API (опционально, с машины пользователя):

```bash
curl -s http://localhost:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_API_KEY" | head
```

В ответе должен быть JSON со списком моделей.

### 7.3. Добавить провайдер LiteLLM в профиль (интерактивно)

```bash
helix models add litellm --host http://localhost:4000
```

Что произойдёт:

1. Helix предложит ввести API-ключ (если `LITELLM_API_KEY` уже в `.env` — возьмёт оттуда).
2. Подключится к `http://localhost:4000/v1`.
3. Загрузит список моделей с `/v1/models`.
4. Попросит выбрать **модель по умолчанию** для этого провайдера.
5. Сохранит настройки в `~/.helix/profiles/default/config.yaml`.

### 7.4. Полный мастер настройки (рекомендуется)

```bash
helix models setup
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

В `helix models setup` → пункт **5** (Configure agent models):

- **`main`** — основной агент в чате;
- можно назначить разные модели субагентам (`researcher`, `coder`, …).

Просмотр назначений:

```bash
helix models agents
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
helix gateway reload
```

В TUI смена модели на лету: `/models` или `/model`.

---

## 8. Шаг 6 — Поиск в интернете (опционально)

Helix поддерживает провайдеры: **DuckDuckGo** (по умолчанию), **SearXNG**, **Firecrawl**.

```bash
helix search configure   # интерактивный выбор провайдеров и порядка
helix search list
helix search test "тестовый запрос"
```

В чате: `/search`, `/search configure`, `/search test запрос`.

После настройки: `helix gateway reload`.

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
4. Введите **username** бота (должен заканчиваться на `bot`, например `my_company_helix_bot`).
5. BotFather пришлёт **токен** вида `123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` — сохраните его.

### 9.3. Узнать свой Telegram user id

Нужен для ограничения доступа (кто может писать боту):

- напишите [@userinfobot](https://t.me/userinfobot), или
- мастер `helix telegram setup` может определить id автоматически.

### 9.4. Интерактивная настройка Helix

```bash
helix telegram setup
```

Мастер:

1. Проверит токен через Telegram API (`getMe`).
2. Спросит **allowlist** пользователей (`HELIX_TELEGRAM_ALLOWED_USERS`).
3. Сохранит настройки в **`~/.helix/profiles/<имя>/telegram.env`**.
4. При нескольких профилях Helix предложит **привязку user id → профиль** (один бот — разные пользователи).

### 9.4.1. Привязка user id к профилю (общий бот)

```bash
helix -p shared telegram map set 123456789 alice
helix -p shared telegram map bind bob --user-id 987654321
helix -p shared telegram map list
```

Подробно: [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).

### 9.5. Запуск бота

**Отдельно:**

```bash
helix telegram run
# или просто:
helix telegram
```

**Вместе с API gateway** (рекомендуется для постоянной работы):

```bash
helix gateway start
```

Supervisor gateway также поднимает Telegram, если он настроен.

### 9.6. Обновить меню команд в Telegram

```bash
helix telegram sync-menu
```

После изменения навыков, MCP или слэш-команд.

### 9.7. Голосовые сообщения (опционально)

Если чат уже через LiteLLM, для Whisper настройте модель транскрибации **в конфиге LiteLLM** и в `.env` профиля:

```bash
HELIX_WHISPER_BASE_URL=http://localhost:4000/v1
HELIX_WHISPER_API_KEY=sk-...          # virtual key LiteLLM
HELIX_WHISPER_MODEL=whisper           # model_name из LiteLLM (не whisper-1)
HELIX_TELEGRAM_VOICE_LANGUAGE=ru
```

Подробнее: [TELEGRAM.md](TELEGRAM.md).

### 9.8. Production

При `HELIX_ENV=production` обязателен `HELIX_TELEGRAM_ALLOWED_USERS`.

---

## 10. Шаг 8 — Режимы выполнения

В TUI и Telegram доступны четыре режима:

| Режим | Имя | Когда использовать |
|-------|-----|-------------------|
| **ReAct** | `react` | Быстрые вопросы, инструменты, разведка (по умолчанию) |
| **План** | `plan_and_execute` | Многошаговые задачи с понятными подцелями |
| **Гибрид** | `hybrid` | Крупные задачи: план, затем гибкая работа по шагам |
| **Авто** | `auto` | Helix сам выбирает режим через классификатор |

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
helix mcp list-popular
```

Примеры из каталога: `filesystem`, `github`, `context7`, `compass`, `postgres`, …

### 12.2. Установить MCP (простой способ)

```bash
helix mcp install
```

Интерактивно: выбор из списка → ввод параметров (пути, API-ключи) → тест → сохранение в профиль.

Или по имени:

```bash
helix mcp install context7
helix mcp install filesystem
```

Из git:

```bash
helix mcp install https://github.com/upstash/context7
```

### 12.3. Назначить MCP агентам

```bash
helix mcp assign
```

Например: `main` видит `filesystem` и `context7`, субагент `researcher` — только `context7`.

Проверка:

```bash
helix mcp list
helix mcp test <имя-сервера>
helix mcp tools
```

### 12.4. Полный мастер

```bash
helix mcp setup
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
helix gateway reload
```

Инструменты MCP в агенте имеют имена вида **`mcp_<сервер>_<tool>`**.

### 12.7. Переменные окружения для MCP

Секреты в конфиге MCP: `${GITHUB_TOKEN}`, `${CONTEXT7_API_KEY}` и т.д.  
Значения — в `~/.helix/.env`.  
`helix doctor` предупредит о неразрешённых `${VAR}`.

---

## 13. Шаг 11 — Навыки и плагины из Hub

### 13.1. Что такое skills

**Skill** — файл `SKILL.md` с инструкциями для агента.  
Хранятся в: `~/.helix/profiles/<profile>/data/skills/`

### 13.2. Установка из Hub (CLI)

```bash
# поиск
helix hub search "docker" -s clawhub
helix hub search "git" -s clawhub

# интерактивный обзор
helix hub browse

# установка
helix hub install <spec>
helix hub install <spec> --agents main,coder
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
helix skills list --agent main
helix skills assign docker-manager --agents main,coder
helix skills unassign docker-manager --agent coder
helix skills assign-wizard    # интерактивно
```

### 13.5. Обновления Hub

```bash
helix hub list
helix hub check-updates
helix hub update
helix hub autoupdate --enable
helix hub slash-sync          # обновить skill-slash.json
```

### 13.6. Применить

```bash
helix gateway reload
```

---

## 14. Справочник CLI

Глобальные опции: **`--profile` / `-p`**, **`--verbose` / `-v`**.

### Основные команды

| Команда | Назначение |
|---------|------------|
| `helix tui` | Полноэкранный интерфейс (рекомендуется) |
| `helix chat-command` | Чат в терминале |
| `helix run "запрос"` | Один запрос без входа в чат |
| `helix status` | Статус профиля |
| `helix version` | Версия |
| `helix clear` | Очистить data профиля |
| `helix doctor` | Диагностика |
| `helix install` | Установка helix в PATH (из исходников) |
| `helix update` | Обновление |

### `helix models`

| Подкоманда | Описание |
|------------|----------|
| `setup` | Интерактивный мастер |
| `add <preset>` | Добавить провайдер (`litellm`, `ollama`, …) |
| `presets` | Список пресетов |
| `list` | Провайдеры в профиле |
| `agents` | Назначения моделей агентам |

### `helix config`

| Подкоманда | Описание |
|------------|----------|
| `show` | Показать YAML |
| `edit` | Редактор |
| `set ключ значение` | Изменить поле |

### `helix mcp`

`list`, `add`, `remove`, `test`, `assign`, `setup`, `list-popular`, `install`

### `helix hub`

`search`, `browse`, `install`, `list`, `remove`, `check-updates`, `update`, `autoupdate`, `slash-sync`

### `helix skills`

`list`, `search`, `show`, `assign`, `unassign`, `agents`, `assign-wizard`

### `helix memory`

`search "<запрос>"`

### `helix search`

`configure`, `list`, `test`

### `helix gateway`

`start`, `stop`, `status`, `reload`  
Эндпоинты: `/health`, `/v1/chat/completions`, … — см. [GATEWAY.md](GATEWAY.md).

### `helix cron`

Требует запущенный gateway.  
`add`, `list`, `enable`, `disable`, `remove`

### `helix logs`

`helix logs`, `helix logs -f`, `helix logs -s agent`, `helix logs list`, `helix logs rotate`, `helix logs debug on`

### `helix telegram`

`setup`, `run`, `status`, `sync-menu`, `map set|list|remove|bind|import` — см. [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md)

---

## 15. Слэш-команды `/` в чате

Работают в **TUI**, **Telegram** и частично в **`helix chat-command`**.

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

## 16. Особенности Helix

1. **Профили** — несколько изолированных конфигураций (`helix -p имя`).
2. **Память** — диалоги + долгосрочная память + семантический поиск (`/memory`).
3. **Подтверждения** — опасные tool-вызовы требуют явного согласия.
4. **План с ревью** — многошаговые задачи не выполняются молча без вашего OK (если включено).
5. **Субагенты** — фоновые worker-процессы; основной чат не блокируется (`/subagent-spawn`).
6. **MCP и Hub** — расширение без правки кода агента.
7. **Мультиинтерфейс** — один профиль для TUI, Telegram и API gateway.
8. **Логи** — структурированные логи agent/gateway/cron/subagent (`helix logs`).
9. **Doctor** — самодиагностика окружения.
10. **OpenAI-совместимый API** — gateway для интеграции с другими клиентами.
11. **Голос в Telegram** — Whisper через LiteLLM, OpenAI или локально (`faster-whisper`).
12. **Сжатие контекста** — `/compress` при переполнении окна модели.

---

## 17. Что делать, если что-то не работает

```bash
helix doctor
helix doctor --fix
helix logs -l error -n 50
```

| Проблема | Что проверить |
|----------|----------------|
| `helix: command not found` | PATH, venv, `pipx` / `uv tool` |
| Нет ответа от модели | `LITELLM_API_KEY`, URL, `helix models list`, curl `/v1/models` |
| MCP не появляется | `helix mcp test`, `helix gateway reload`, `helix doctor` |
| Telegram молчит | `helix telegram status`, токен, allowlist, `helix gateway status` |
| Старые слэш-команды | `helix telegram sync-menu`, `helix gateway reload` |

Подробнее: [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [DOCTOR.md](DOCTOR.md).

---

## Быстрый чеклист «с нуля до чата»

1. Python 3.12+  
2. `uv` или `pip`  
3. `uv pip install helixagentai-….whl` (или `pipx install …`)  
4. `~/.helix/.env` с `LITELLM_API_BASE` и `LITELLM_API_KEY`  
5. `helix models add litellm --host http://localhost:4000`  
6. `helix models setup` → назначить модель для `main`  
7. `helix doctor`  
8. `helix tui` или `helix telegram setup` + `helix gateway start`  
9. По необходимости: `helix mcp install`, `helix hub browse`, `helix search configure`  

---

## См. также

- [INSTALLATION.md](INSTALLATION.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- [CLI.md](CLI.md)
- [SLASH_COMMANDS.md](SLASH_COMMANDS.md)
- [TELEGRAM.md](TELEGRAM.md)
- [HUB.md](HUB.md)
- [GATEWAY.md](GATEWAY.md)