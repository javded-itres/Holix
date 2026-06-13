# Шифрование профиля на диске

Holix может шифровать **секреты профиля и память** на диске так, чтобы бэкапы, украденные диски и администраторы хоста не могли прочитать API-ключи, токены Telegram, soul агента или историю диалогов без **ключа разблокировки** пользователя.

**Файлы workspace остаются plaintext** — код проекта и документы в `profiles/<имя>/workspace/` удобны для git и **не шифруются**. Старые зашифрованные файлы workspace из прежних сборок мигрируют один раз: `holix profile crypto decrypt-workspace`.

> **См. также:** [SECURITY.md](SECURITY.md#шифрование-на-диске) · [CONFIGURATION.md](CONFIGURATION.md#шифрование-профиля-опционально) · [CLI.md](CLI.md#holix-profile-crypto) · [DEPLOYMENT.md](DEPLOYMENT.md)

## Что шифруется

| Шифруется на диске | Plaintext (намеренно) |
|--------------------|------------------------|
| `profiles/<имя>/.env` — API-ключи, порты | `profiles/<имя>/config.yaml` — модели, MCP (несекретные настройки) |
| `profiles/<имя>/telegram.env` — токен бота, allowlist | `profiles/<имя>/workspace/` — файлы проекта агента |
| `profiles/<имя>/SOUL.md`, `USER.md`, `INIT.md` | `profiles/<имя>/gateway/` — PID, логи |
| SQLite-память: `memory.db`, `ltm.db`, `checkpoints.db` | `telegram-users.json` — привязки user id → профиль |
| Chroma (архив `vector_db.sealed`) | Большинство файлов в `data/skills/`, `data/cron/` |

**Формат:** файлы с заголовком `HOLIXENC1` (AES-256-GCM). Метаданные в `profiles/<имя>/crypto.json` (DEK обёрнут через Argon2id).

**Вложения Telegram:** при включённом шифровании файлы из `workspace/` или `data/files/` отправляются пользователю **расшифрованными** (`materialize_file_for_delivery`) — получатель не видит ciphertext.

## Чего шифрование не защищает

Пока профиль **разблокирован** и агент работает, привилегированный процесс на хосте теоретически может читать память процесса или перехватывать трафик к LLM. Шифрование закрывает **at-rest** и **офлайн-бэкапы**, а не live forensics и промпты у провайдера.

Потеря ключа разблокировки = **данные невосстановимы** — сервер не восстанавливает DEK без пользовательского ключа.

## Ключи и разблокировка

| Термин | Env / файл | Роль |
|--------|------------|------|
| **Ключ разблокировки** (UEK) | `HOLIX_UNLOCK_KEY` или ввод в CLI | Секрет пользователя; на диск не пишется |
| **DEK** | Обёртка в `crypto.json` | Ключ шифрования данных профиля (256 bit) |
| **KEK** | Производный в памяти (Argon2id) | Расшифровывает DEK из `crypto.json` |

```mermaid
flowchart LR
  UEK[HOLIX_UNLOCK_KEY] --> KDF[Argon2id + salt]
  KDF --> KEK[KEK в памяти]
  KEK --> DEK[распаковка DEK]
  DEK --> SEC[.env telegram.env SOUL БД памяти]
```

**CLI:** `holix profile crypto unlock` загружает DEK в кэш процесса.

**Gateway / systemd:** задайте `HOLIX_UNLOCK_KEY` в `global/.env` или `profiles/<имя>/.env`, чтобы `gateway_worker` разблокировал профиль до чтения `telegram.env` и памяти.

После остановки gateway скрипт `holix-gateway-seal.sh` (systemd `ExecStopPost`) может снова запечатать память.

## Политика по ОС (`HOLIX_ENCRYPTION_MODE`)

Holix шифрует/расшифровывает прозрачно только когда **глобальная политика разрешает runtime crypto** *и* у профиля есть `crypto.json`.

| Режим | Значение | Linux-сервер | macOS (dev) | Windows (dev) |
|-------|----------|--------------|-------------|-----------------|
| **Linux production** (по умолчанию) | `linux-production` | Активно при `crypto.json` | **Неактивно** — файлы plaintext, пока не включите `on` | **Неактивно** |
| **Всегда** | `on` | Активно | Активно | Активно |
| **Выключено** | `off` | Неактивно | Неактивно | Неактивно |

```bash
# По умолчанию — переменная не обязательна
HOLIX_ENCRYPTION_MODE=linux-production

# Принудительно на Mac или Windows
HOLIX_ENCRYPTION_MODE=on

# Полностью отключить (блокирует holix profile crypto enable)
HOLIX_ENCRYPTION_MODE=off
```

### Рекомендации по ОС

**Linux (VPS, systemd, Docker, production)** — основной сценарий:

1. `HOLIX_ENV=production`, `HOLIX_ENCRYPTION_MODE=linux-production` (или не задавать — это default).
2. `holix profile crypto enable` или `holix profile crypto migrate --all --yes` на сервере.
3. `HOLIX_UNLOCK_KEY` в `global/.env` (`chmod 600`).
4. Перезапуск gateway после включения шифрования.

**macOS / Windows (локальная разработка)** — при политике по умолчанию runtime-шифрование **выключено**, даже если есть `crypto.json`. Для теста шифрования локально: `HOLIX_ENCRYPTION_MODE=on` перед `holix profile crypto enable`.

**Включение на не-Linux с default-политикой** — ошибка:

```text
Profile encryption is limited to Linux hosts (HOLIX_ENCRYPTION_MODE=linux-production).
Use HOLIX_ENCRYPTION_MODE=on to force enable on this machine.
```

Проверка политики:

```bash
holix -p alice profile crypto status
```

Пример: `linux-production (active, host=linux)` или `linux-production (inactive, host=other)`.

## Включение шифрования (пошагово)

### Один профиль

```bash
holix -p alice profile crypto enable
# дважды запросит ключ разблокировки — сохраните надёжно

holix -p alice profile crypto status
```

Создаётся `crypto.json`, шифруются секреты и память, legacy encrypted workspace переводится в plaintext.

### Все профили на сервере

```bash
holix profile crypto migrate --all --yes
```

Пропускает профили с уже существующим `crypto.json`.

### После включения — gateway

В `~/.holix/global/.env` или `profiles/<профиль-gateway>/.env`:

```bash
HOLIX_UNLOCK_KEY=длинная-случайная-фраза
HOLIX_ENCRYPTION_MODE=linux-production
```

```bash
holix -p docs gateway restart
holix -p docs telegram status   # токен маскирован, не пустой
```

## Повседневные операции

| Задача | Команда |
|--------|---------|
| Разблокировка для CLI | `holix -p alice profile crypto unlock` |
| Редактирование зашифрованного `.env` | `holix -p alice profile env --edit` |
| Статус | `holix -p alice profile crypto status` |
| Запечатать после обслуживания | `holix profile crypto seal --all --yes` |
| Заблокировать CLI-сессию | `holix profile crypto lock` |
| Очистить устаревший кэш | `holix profile crypto purge-cache` |

## Миграция workspace (старые установки)

В старых сборках Holix мог шифровать файлы в `workspace/`. Сейчас workspace — plaintext.

```bash
holix -p alice profile crypto decrypt-workspace --yes
holix profile crypto decrypt-workspace --all --yes
```

Для systemd: `deploy/scripts/holix-decrypt-workspaces.sh`.

## Telegram и пустой токен в global

Если `telegram.env` зашифрован, gateway должен выполнить unlock **до** загрузки токена.

Типичная ошибка: `TELEGRAM_BOT_TOKEN=` (пусто) в `global/.env` блокирует токен из `profiles/<имя>/telegram.env`. **Удалите пустую строку** или не задавайте переменную.

Holix перезаписывает пустые значения при загрузке `telegram.env`. См. [TELEGRAM.md](TELEGRAM.md#хранение-и-загрузка-токена) и [TROUBLESHOOTING.md](TROUBLESHOOTING.md#telegram-бот-не-стартует-вместе-с-gateway).

## Модель угроз (кратко)

| Угроза | Без шифрования | С шифрованием, ключ только у клиента |
|--------|----------------|--------------------------------------|
| `cat profiles/alice/.env` на сервере | Секреты в открытом виде | Ciphertext `HOLIXENC1` |
| Украденный бэкап диска | Все данные профиля | Ciphertext без ключа |
| Admin / root до unlock | Читает файлы | Ciphertext + metadata |
| Потеря ключа разблокировки | — | **Безвозвратная потеря данных** |

Ключи доступа к профилю (`hp_…`) — **кто может переключиться** в профиль, не расшифровка файлов. API-ключи gateway (`hx_…`) — HTTP-аутентификация, не замена `HOLIX_UNLOCK_KEY`.

## Справочник CLI

```bash
holix profile crypto enable [--unlock-key KEY] [--skip-existing]
holix profile crypto migrate --all [--yes] [--unlock-key KEY]
holix profile crypto status
holix profile crypto unlock [--unlock-key KEY]
holix profile crypto lock
holix profile crypto seal [--all] [--yes]
holix profile crypto decrypt-workspace [--all] [--yes]
holix profile crypto purge-cache
```

Полный список опций: `holix profile crypto --help`.

## См. также

- [PROFILES.md](PROFILES.md) — изоляция, удаление с уведомлением в Telegram
- [DEPLOYMENT.md](DEPLOYMENT.md) — systemd, `HOLIX_UNLOCK_KEY`, `uv tool install --with aiogram`
- [SECURITY.md](SECURITY.md) — production checklist
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — Telegram bot skipped, зашифрованный env