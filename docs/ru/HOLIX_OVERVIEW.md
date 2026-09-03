# Holix — полный обзор возможностей

**Holix** — это self-improving AI-агент с долговременной памятью, навыками, инструментами, MCP и несколькими способами работы: терминал, TUI, API, Telegram и MAX.

| | |
|---|---|
| **Сайт** | [holix-agent.ru](https://holix-agent.ru) |
| **Документация** | [holix-agent.ru/docs](https://holix-agent.ru/docs) |
| **PyPI** | [`Holix`](https://pypi.org/project/Holix/) · команда `holix` |
| **GitHub** | [javded-itres/Holix](https://github.com/javded-itres/Holix) |
| **Telegram-канал** | [@helix_agent](https://t.me/helix_agent) |
| **Лицензия** | MIT |
| **Python** | 3.12+ |

> Этот документ — **презентация продукта для пользователей**: что умеет Holix, зачем он нужен и как с ним работать. Технические детали — в связанных страницах документации.

---

## 1. Зачем Holix

Обычный чат с LLM отвечает текстом и забывает контекст. **Holix** — рабочий агент, который:

- **читает и меняет файлы** в вашем проекте;
- **запускает команды** в терминале (с контролем безопасности);
- **ищет в интернете** и открывает страницы;
- **пишет и выполняет код**;
- **помнит** прошлые диалоги и факты о вас;
- **растёт** — подключает навыки (skills), MCP-серверы и расширения;
- **работает там, где вы** — в TUI, CLI, Telegram, MAX или через HTTP API.

Итог: не «умный собеседник», а **личный AI-сотрудник** на вашей машине или сервере.

---

## 2. Что Holix умеет — карта возможностей

```text
┌─────────────────────────────────────────────────────────────────┐
│                         HOLIX AGENT                             │
│  LLM (Ollama / OpenAI / LiteLLM / Groq / …) + LangGraph        │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│  Инструменты │  Память      │  Навыки      │  Интеграции        │
│  файлы, shell│  SQLite +    │  Skills Hub  │  Telegram, MAX     │
│  web, browser│  ChromaDB    │  MCP         │  Gateway API       │
│  code, SQL   │  SOUL/USER   │  Extensions  │  Cron, Subagents   │
├──────────────┴──────────────┴──────────────┴────────────────────┤
│  Интерфейсы:  TUI · CLI · Web-TUI · Telegram · MAX · HTTP API   │
└─────────────────────────────────────────────────────────────────┘
```

| Область | Возможности |
|---------|-------------|
| **Работа с кодом и файлами** | Чтение, запись, патчи, обход каталогов, выполнение Python, SQL |
| **Терминал** | Shell-команды, фоновые процессы (dev-серверы), whitelist и подтверждения |
| **Веб** | Поиск, загрузка URL, опционально Playwright (клики, формы, снимки) |
| **Память** | История диалогов, семантический поиск, профиль личности агента |
| **Навыки (Skills)** | Markdown-инструкции + автогенерация + каталоги Hub |
| **MCP** | Подключение внешних Model Context Protocol серверов |
| **Субагенты** | Параллельные воркеры: researcher, coder, analyst, reviewer… |
| **Режимы мышления** | ReAct, Plan & Execute, Hybrid, Auto |
| **Автоматизация** | Cron («каждый день в 10…»), фоновые задачи |
| **SDD** | Spec-Driven Development: спецификация → задачи → apply → archive |
| **Мессенджеры** | Telegram-бот, MAX-бот (доступ, профили пользователей) |
| **API Gateway** | HTTP API, совместимость с OpenAI-клиентами, admin API |
| **Безопасность** | Ключи, rate limits, whitelist, шифрование профиля, jail workspace |
| **Эксплуатация** | `doctor`, логи, Docker, systemd, multi-profile |

---

## 3. Интерфейсы: как вы общаетесь с агентом

### 3.1. TUI — основной интерфейс (рекомендуется)

```bash
holix tui
holix tui -p myprofile
```

Полноценный code-style чат в терминале:

- диалог с агентом и стриминг ответов;
- вызовы инструментов «на глазах»;
- слэш-команды (`/help`, `/mode`, `/hub`, `/memory`…);
- полоска фоновых процессов (логи, стоп);
- доступ к Skill Hub и MCP;
- копирование транскрипта (F2 / `/open`, `/copy`).

**Веб-TUI** (браузер):

```bash
uv sync --extra tui-web
holix tui --web
# http://127.0.0.1:8787/?token=...
```

Удобно для удалённой работы; для LAN нужны явный token и осторожность (полный доступ агента = доступ к машине).

### 3.2. CLI и one-shot

```bash
holix chat-command          # лёгкий REPL
holix run "Что в этом репо?" # один запрос
holix version
holix doctor
holix doctor --fix
```

### 3.3. Telegram

Один бот — много пользователей: запросы доступа, allowlist, админ, привязка к профилям Holix.

```bash
uv sync --extra telegram   # или Holix[telegram]
holix -p shared telegram setup
holix -p shared gateway start -f
```

В чате работают слэш-команды, режимы, подтверждения опасных действий. Подходит для мобильного доступа к «своему» агенту.

### 3.4. MAX (мессенджер)

Аналогичная модель для платформы MAX: setup, polling/webhook, multi-user, профили.

```bash
holix max setup
holix gateway start   # companion Long Polling / webhook
```

### 3.5. API Gateway

```bash
holix gateway start
holix gateway status
holix gateway stop
holix gateway reload
```

HTTP API для приложений, интеграций и OpenAI-совместимых клиентов. В production — auth, pepper, reverse proxy с TLS.

---

## 4. Инструменты агента

Агент не ограничен «текстом». Типичный набор:

| Группа | Примеры |
|--------|---------|
| **Файлы** | `read_file`, `write_file`, `patch_file`, `list_directory` |
| **Терминал** | `run_terminal_command`, `terminal`, фоновые процессы |
| **Веб** | `web_search`, `fetch_url` / `web_fetch`, `research_site_pages` |
| **Чат** | `send_chat_files` (вложение Telegram/MAX), `self_diagnose` («проверь себя») |
| **Код** | `execute_python`, `code_executor`, `calculate` |
| **Данные** | `sql_query`, `sql_schema` |
| **Браузер** *(extra)* | `browser_open`, `browser_click`, `browser_fill`, snapshot… |
| **Память и сессии** | поиск по сессиям, soul/profile, background processes |
| **Субагенты** | `delegate_to_subagent`, wait / list / terminate |
| **SDD** | init, propose, apply, archive, dispatch |
| **Расширения** | `manage_agent_extensions`, tools от плагинов |

Опасные действия (удаление, shell, запись) могут требовать **подтверждения** (`/yes` или варианты `/1`–`/4`).

---

## 5. Режимы работы (как агент думает)

Переключение: **`/mode`** или **`/mode <имя>`**. Текущий: **`/status`**.

| Режим | Имя | Когда |
|-------|-----|--------|
| **ReAct** | `react` | Быстрые задачи, разведка, один цикл мысль → инструменты (по умолчанию) |
| **Plan & Execute** | `plan_and_execute` | Многошаговые задачи с планом и согласованием |
| **Hybrid** | `hybrid` | Крупные задачи: план + гибкий ReAct внутри шагов |
| **Auto** | `auto` | Holix сам выбирает подходящий режим |

```text
/mode react
/mode plan_and_execute
/mode hybrid
/mode auto
```

---

## 6. Память и личность агента

### Память

- **Диалоги** — SQLite по `conversation_id` (TUI, Telegram, cron, API).
- **Семантика** — ChromaDB: поиск по смыслу (`/memory …`, `holix memory search`).
- **Индекс навыков** — отдельный поиск по skills.

Данные лежат в профиле: `~/.holix/profiles/<имя>/data/memory/` (при шифровании профиля — на диске в зашифрованном виде).

### Личность и предпочтения

При первом запуске профиля — онбординг:

| Файл | Смысл |
|------|--------|
| `SOUL.md` | Кто агент, стиль, границы |
| `USER.md` | Кто вы, предпочтения, контекст |
| `INIT.md` | Сценарий знакомства |

Профили изолируют проекты, модели, workspace и секреты. Подробнее: [PROFILES.md](PROFILES.md), [MEMORY.md](MEMORY.md).

---

## 7. Skills, Hub и MCP

### Skills

Навыки — markdown-инструкции, которые агент подключает под задачу. Можно:

- писать свои skills в профиле;
- получать **автогенерацию** навыков из опыта;
- ставить готовые из **Hub**.

### Skill Hub

```bash
holix hub browse
# в TUI: /hub , /hub browse , /hub installed
```

Каталоги вроде ClawHub, Hermes, Claude plugins — поиск и установка без ручного копирования файлов.

### MCP (Model Context Protocol)

```bash
holix mcp setup
```

Подключение внешних MCP-серверов (базы, SaaS, внутренние API) **на агента/профиль**. Инструменты MCP появляются у модели наряду со встроенными.

---

## 8. Субагенты

Фоновые специалисты **не блокируют** основной чат:

| Тип | Роль |
|-----|------|
| `researcher` | Исследование, файлы, веб |
| `web_researcher` | Поиск и синтез из интернета |
| `page_analyst` | Одна страница сайта (`research_site_pages`) |
| `coder` | Код, правки, отладка |
| `analyst` | Данные, SQL, расчёты |
| `reviewer` | Ревью кода |
| `writer` | Документация и тексты |

Управление: делегирование из агента, `/subagent-spawn`, лимиты concurrent. Режимы process / async. Подробнее: [SUBAGENTS.md](SUBAGENTS.md).

---

## 9. Автоматизация: Cron и Launch

### Cron

Повторяющиеся задачи на естественном языке («каждый день в 10 присылай сводку») или через CLI:

```bash
holix cron list
# в TUI: /cron
```

Задачи выполняются фоном; удобно для отчётов, мониторинга, напоминаний.

### Launch

`holix launch` — интеграция с внешними CLI/воркфлоу (см. [LAUNCH.md](LAUNCH.md)).

---

## 10. Spec-Driven Development (SDD)

Встроенная модель **«сначала спецификация, потом код»** (в духе OpenSpec):

1. Читаем main specs → создаём change (proposal, design, tasks).
2. Выбираем режим apply: **self | subagents | hybrid**.
3. Apply / dispatch → реализация → check tasks.
4. Archive — merge delta в main specs.

Инструменты `sdd_*`, слэш **`/spec`**, skills `holix-sdd-*`, вкладка Specs в Studio. Дерево `openspec/` в workspace. Подробнее: [SDD.md](SDD.md).

---

## 11. Модели и провайдеры

Holix не привязан к одному вендору:

| Провайдер | Примеры |
|-----------|---------|
| Локально | **Ollama** |
| Облако | OpenAI, Groq, и любые **OpenAI-compatible** API |
| Роутинг | **LiteLLM** |

```bash
holix models setup
holix models list
```

Модель, base URL, temperature, лимиты — на профиль или глобально. Подробнее: [MODELS.md](MODELS.md), [CONFIGURATION.md](CONFIGURATION.md).

---

## 12. Профили: несколько агентов на одной машине

Профиль = отдельный мир:

- свой `config.yaml`, `.env`, workspace;
- своя память и skills;
- свои Telegram/MAX-привязки;
- опционально **шифрование** и ключ профиля (`hp_…`).

```bash
holix -p work tui
holix -p personal telegram setup
```

Типичные сценарии: «домашний» и «рабочий» агент; shared-бот для команды; изоляция клиентов.

---

## 13. Безопасность (кратко)

Holix рассчитан на реальные инструменты → **контроль обязателен**:

| Механизм | Зачем |
|----------|--------|
| API keys (`hx_…`) + pepper | Auth gateway |
| Profile keys (`hp_…`) | Доступ к management API профиля |
| Rate limits | Защита от злоупотреблений |
| Terminal whitelist | Ограничение shell |
| Confirmation prompts | Явное «да» на рискованные действия |
| Workspace jail | Агент не выходит за пределы workspace без политики |
| Profile encryption | Секреты и память на диске |
| Access requests (Telegram/MAX) | Кто может писать боту |

Production checklist: `HOLIX_ENV=production`, auth, pepper, CORS, bind на localhost + TLS proxy. Полностью: [SECURITY.md](SECURITY.md), [TERMINAL_SECURITY.md](TERMINAL_SECURITY.md).

---

## 14. Расширения (Extensions)

Экосистема плагинов без «раздувания» ядра:

- host-расширения (billing, console, demo…);
- tools и middleware для агента;
- gateway-маршруты, sidecars;
- SDK: [holix-sdk](https://github.com/javded-itres/holix-sdk).

Авторам: [EXTENSIONS.md](EXTENSIONS.md), [EXTENSION_AUTHOR_GUIDE.md](EXTENSION_AUTHOR_GUIDE.md).

---

## 15. Эксплуатация и production

```bash
holix doctor              # диагностика
holix doctor --fix       # автопочинка где возможно
holix logs [-s agent] [-f]
holix update --channel pypi
```

Развёртывание:

- **локально** — uv / pipx;
- **Docker** — `docker compose`;
- **VDS / systemd** — gateway + companions (Telegram, MAX, cron);
- reverse proxy (nginx), TLS, мониторинг.

См. [DEPLOYMENT.md](DEPLOYMENT.md), [LOGS.md](LOGS.md), [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## 16. Быстрый старт за 5 минут

```bash
# Установка
curl -fsSL https://raw.githubusercontent.com/javded-itres/Holix/main/scripts/install.sh | bash
# или: pipx install "Holix[all]"

holix version
holix doctor
holix bootstrap          # LLM (+ опционально Telegram)
holix models setup
holix tui                # начать работу
```

Шпаргалка:

```bash
holix tui
holix run "Привет"
holix hub browse
holix mcp setup
holix gateway start
holix -p shared telegram setup
holix max setup
holix cron list
holix logs -l error
holix update --channel pypi
```

В чате: **`/help`** — все слэш-команды.

---

## 17. Кому подходит Holix

| Аудитория | Польза |
|-----------|--------|
| **Разработчики** | Агент в репозитории: правки, тесты, ревью, SDD |
| **Команды / DevOps** | Gateway, cron, Docker, multi-profile, audit |
| **Продуктовые / ops-команды** | Telegram/MAX-бот с доступом к знаниям и задачам |
| **Энтузиасты local LLM** | Ollama + полный tool-loop без vendor lock-in |
| **Авторы расширений** | MCP, skills, holix-sdk, host plugins |

---

## 18. Чем Holix отличается от «просто ChatGPT»

| | Чат в браузере | Holix |
|--|----------------|--------|
| Файлы и shell на вашей машине | Нет / ограничено | Да, с политиками |
| Долговременная память проекта | Слабо | Профили + SQLite + Chroma |
| Кастомные tools / MCP | Редко | Да |
| Мессенджеры «из коробки» | Отдельные продукты | Telegram + MAX |
| Self-host / offline модели | Нет | Да (Ollama и др.) |
| Open source | Нет | MIT, свой деплой |
| Субагенты и plan-режимы | Ограничено | Встроены |
| SDD / specs в workspace | Нет | Да |

---

## 19. Карта документации

| Тема | Документ |
|------|----------|
| Установка | [INSTALLATION.md](INSTALLATION.md) |
| Первый запуск | [START_HERE.md](START_HERE.md) |
| Маршрут обучения | [USER_GUIDE.md](USER_GUIDE.md) |
| CLI | [CLI.md](CLI.md) |
| Слэш-команды | [SLASH_COMMANDS.md](SLASH_COMMANDS.md) |
| TUI | [TUI.md](TUI.md) |
| Конфиг и модели | [CONFIGURATION.md](CONFIGURATION.md), [MODELS.md](MODELS.md) |
| Профили | [PROFILES.md](PROFILES.md) |
| Память | [MEMORY.md](MEMORY.md) |
| Режимы | [EXECUTION_MODES.md](EXECUTION_MODES.md) |
| Hub / MCP | [HUB.md](HUB.md), [MCP.md](MCP.md) |
| Субагенты | [SUBAGENTS.md](SUBAGENTS.md) |
| Cron / Launch | [CRON.md](CRON.md), [LAUNCH.md](LAUNCH.md) |
| SDD | [SDD.md](SDD.md) |
| Telegram / MAX | [TELEGRAM.md](TELEGRAM.md), [MAX.md](MAX.md) |
| Gateway | [GATEWAY.md](GATEWAY.md), [GATEWAY_API.md](GATEWAY_API.md) |
| Безопасность | [SECURITY.md](SECURITY.md) |
| Деплой | [DEPLOYMENT.md](DEPLOYMENT.md) |
| Архитектура | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Changelog | [../CHANGELOG.md](../CHANGELOG.md) |

Английская документация (канон по точности): [../en/README.md](../en/README.md).

---

## 20. Ссылки

- Сайт: [holix-agent.ru](https://holix-agent.ru)
- Docs: [holix-agent.ru/docs](https://holix-agent.ru/docs)
- PyPI: [pypi.org/project/Holix](https://pypi.org/project/Holix/)
- GitHub: [github.com/javded-itres/Holix](https://github.com/javded-itres/Holix)
- Telegram: [t.me/helix_agent](https://t.me/helix_agent)
- SDK: [holix-sdk](https://github.com/javded-itres/holix-sdk)

---

*Holix — self-improving AI agent. Устанавливаете локально или на сервер, подключаете модель, открываете TUI или бота — и работаете.*
