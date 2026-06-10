# Профили и изоляция

**Профили** Helix — полностью изолированные окружения агента на одной машине. У каждого профиля свои настройки, секреты, память, Telegram-бот и API gateway — разные люди или проекты не мешают друг другу.

### Профиль `default` (только для разработки)

В **development** (`HELIX_ENV` не `production`) можно не указывать `-p` — Helix использует профиль `default`:

```bash
helix gateway start
helix profile env --edit
```

В **production** профиль `default` **недоступен**. Всегда указывайте именованный профиль:

```bash
HELIX_ENV=production helix -p shared gateway start
HELIX_ENV=production helix -p alice profile env --edit
```

## Что изолировано в профиле

| Ресурс | Путь |
|--------|------|
| Ключ доступа к профилю (хэш) | `~/.helix/profiles/<имя>/profile.key` |
| Окружение (ключи API, порты) | `~/.helix/profiles/<имя>/.env` |
| Telegram-бот | `~/.helix/profiles/<имя>/telegram.env` |
| Состояние и лог gateway | `~/.helix/profiles/<имя>/gateway/` |
| Модели, MCP, навыки | `~/.helix/profiles/<имя>/config.yaml` |
| Память (SQLite + ChromaDB) | `~/.helix/profiles/<имя>/data/memory/` |
| Навыки | `~/.helix/profiles/<имя>/data/skills/` |
| Cron-задачи | `~/.helix/profiles/<имя>/data/cron/` |

Глобально в `~/.helix/`:

| Путь | Назначение |
|------|------------|
| `global/config.yaml` | Общие модели, MCP, search, поведение |
| `global/.env` | Общие ключи API, голос, флаги инструментов |
| `logs/`, клоны MCP | Общие операционные данные |

Профили **по умолчанию наследуют** глобальные настройки. Файлы профиля хранят **только переопределения** — можно сменить модель в одном профиле, не трогая global; изменение global обновит все наследующие профили.

```bash
helix profile global edit                 # общие настройки
helix profile create team-a               # наследует global (по умолчанию)
helix profile create team-b --clean       # чистый профиль
helix -p team-a config set model smart    # переопределить модель только в team-a
```

Токены Telegram, память и состояние gateway остаются **на профиль** (не наследуются).

## Несколько gateway и Telegram-ботов

Несколько gateway на разных портах — по одному на профиль:

```bash
# profiles/alice/.env
HELIX_GATEWAY_PORT=8001

# profiles/bob/.env
HELIX_GATEWAY_PORT=8002

helix -p alice gateway start
helix -p bob gateway start
```

У каждого профиля может быть **свой Telegram-бот**:

```bash
helix -p alice telegram setup
helix -p bob telegram setup
```

### Один бот на многих пользователей

**Рекомендуется** — запросы доступа + защищённый профиль на каждого:

```bash
helix -p shared telegram setup
HELIX_ENV=production helix -p shared gateway start -f
# пользователи отправляют /start; админ одобряет:
helix -p shared telegram requests approve USER_ID --create-profile ivan
```

Каждому одобренному пользователю создаётся защищённый профиль, workspace jail и ключ доступа в Telegram.

Ручные привязки (`helix telegram map`) по-прежнему поддерживаются. См. [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).

## Workspace jail (изоляция в директории)

**Workspace jail** ограничивает файловые и терминальные инструменты одной директорией. Агент не может читать, писать или выполнять команды за её пределами, но внутри работает без ограничений.

**Автоматически:** при создании **защищённого** профиля (`--protect`, `profile key init` или `telegram requests approve --create-profile`) Helix создаёт:

`~/.helix/profiles/<имя>/workspace/`

и включает jail с корнем в этой директории.

**Вручную** (любой профиль):

```bash
helix profile jail enable ~/data-agent
helix profile jail status
helix profile jail disable
```

Или в `config.yaml`:

```yaml
workspace_jail_enabled: true
workspace_root: /home/user/data-agent
```

При включении jail действует на:

- `read_file`, `write_file`, `list_directory`
- `run_terminal_command` (рабочая директория = корень jail)
- отправку файлов в Telegram с локальных путей

Внутренние данные Helix (память, навыки в `~/.helix/profiles/`) **не затрагиваются** — jail только для файловых и терминальных инструментов агента.

## Whitelist терминала (опционально)

Ограничение списка shell-команд, которые агент может выполнять. Настройки хранятся в `.env` профиля.

```bash
helix -p dev profile whitelist enable
helix -p dev profile whitelist add "docker, make"
helix -p dev profile whitelist list
```

Переменные в `.env`:

```bash
HELIX_TERMINAL_COMMAND_WHITELIST=true
HELIX_TERMINAL_WHITELIST_EXTRA=docker,make
```

Helix всегда применяет встроенный набор для платформы (`ls`, `git status`, `python`, `helix` на Unix; `dir`, `type`, `where` в Windows). Extras профиля расширяют этот список. Дубликаты игнорируются.

После изменений перезапустите gateway/Telegram или заново запустите CLI. См. [TERMINAL_SECURITY.md](TERMINAL_SECURITY.md) и [SECURITY.md](SECURITY.md).

## Ключи доступа к профилю (опционально)

По умолчанию все профили **открыты** — переключение только по имени (`helix -p alice`, `/profile alice`).

При необходимости можно включить **ключ доступа** (формат `hp_…`): тогда переключиться в профиль из CLI, TUI, чата или Telegram можно только зная ключ. Ключ показывается **один раз**; в `~/.helix/profiles/<имя>/profile.key` хранится только хэш.

```bash
# Создать профиль (по умолчанию открытый)
helix profile create alice
helix -p alice gateway start

# Создать сразу с ключом + workspace jail
helix profile create bob --protect
# → ~/.helix/profiles/bob/workspace/ + profile.key (hp_…)

# Защитить существующий открытый профиль (также включает workspace jail)
helix -p alice profile key init

# Войти в защищённый профиль
helix -p bob --profile-key hp_xxxxxxxx
HELIX_PROFILE_KEY=hp_xxxxxxxx helix -p bob

# Управление ключом активного профиля
helix profile key status
helix profile key rotate    # сменить ключ (нужен текущий)
helix profile key disable   # убрать ключ — снова свободное переключение по имени
```

Чтобы **отключить** защиту и переключаться свободно (только по имени профиля):

```bash
helix -p alice --profile-key <текущий-ключ> profile key disable
# или уже находясь в профиле:
helix -p alice profile key disable
```

После `key disable` файл `profile.key` удаляется, и `/profile alice` работает без ключа.

В интерактивном чате, TUI или Telegram:

```text
/profile alice hp_xxxxxxxx
```

`helix status` показывает режим доступа: `locked` (нужен ключ) или `open`.

Для **systemd** и фоновых процессов добавьте ключ в `.env` профиля, чтобы сервис стартовал без запроса:

```bash
# ~/.helix/profiles/alice/.env
HELIX_PROFILE_KEY=hp_xxxxxxxx
```

Ключ защищает **переключение в** профиль через интерфейсы Helix. Он не заменяет права файловой системы на `~/.helix` и API-ключи gateway — см. [SECURITY.md](SECURITY.md).

Подробная инструкция по Telegram (один бот vs несколько ботов): [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).

## Типичная настройка для нескольких пользователей

```bash
# Alice — разработчик, полный доступ к ФС
helix profile create alice
helix -p alice profile env --edit
helix -p alice telegram setup
helix -p alice gateway start

# Bob — только своя папка проекта (опционально с ключом)
helix profile create bob --protect
helix -p bob --profile-key <ключ> profile env --edit
helix -p bob profile jail enable /home/bob/projects
helix -p bob telegram setup
helix -p bob gateway start
```

## Справочник CLI

| Команда | Описание |
|---------|----------|
| `helix -p <имя> …` | Выбор профиля (для `default` не нужен) |
| `helix --profile-key <ключ>` | Ключ доступа к защищённому профилю |
| `helix profile create <имя>` | Создать профиль с наследованием global (по умолчанию) |
| `helix profile create <имя> --clean` | Чистый профиль без наследования global |
| `helix profile create <имя> --protect` | Создать профиль с ключом доступа |
| `helix profile global show` | Показать общий global config |
| `helix profile global edit` | Редактировать `global/config.yaml` |
| `helix profile global edit --env` | Редактировать `global/.env` |
| `helix profile global init` | (Пере)создать global (`--from-profile`) |
| `helix profile key status` | Защищён ли активный профиль |
| `helix profile key init` | Сгенерировать ключ для открытого профиля |
| `helix profile key rotate` | Сменить ключ доступа |
| `helix profile key disable` | Убрать ключ и разрешить свободное переключение |
| `helix profile env` | Показать `.env` профиля |
| `helix profile env --edit` | Редактировать секреты и bind gateway |
| `helix profile jail enable <path>` | Включить изоляцию в директории |
| `helix profile jail disable` | Выключить jail |
| `helix profile jail status` | Статус jail |
| `helix profile whitelist add "<команды>"` | Добавить команды через запятую |
| `helix profile whitelist list` | Статус whitelist и итоговый список |
| `helix profile whitelist enable` | Включить проверку whitelist |
| `helix status` | Список профилей (`locked` / `open`) и активный |

В TUI/чате/Telegram: `/profile <имя> <ключ>` для переключения в защищённый профиль.

## systemd

Один instance gateway на профиль. Шаблонный unit `helix-gateway@<имя>`:

```bash
sudo systemctl enable --now helix-gateway@alice
sudo systemctl enable --now helix-gateway@bob
```

Профиль `default`: `helix-gateway.service`. Секреты в `profiles/<имя>/.env`, не в `/etc/helix/`.

Полная инструкция: [DEPLOYMENT.md](DEPLOYMENT.md#systemd).

## См. также

- [CONFIGURATION.md](CONFIGURATION.md) — слои env и YAML
- [GATEWAY.md](GATEWAY.md) — gateway на профиль
- [TELEGRAM.md](TELEGRAM.md) — бот на профиль
- [CLI.md](CLI.md) — справочник команд
- [SECURITY.md](SECURITY.md) — auth, подтверждения, production