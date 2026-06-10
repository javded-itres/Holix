# Telegram: несколько изолированных профилей

Как организовать работу Helix в Telegram, когда нужно несколько пользователей или проектов с изоляцией данных, памяти и настроек.

См. также: [docs/ru/TELEGRAM.md](docs/ru/TELEGRAM.md), [docs/ru/PROFILES.md](docs/ru/PROFILES.md), [docs/ru/DEPLOYMENT.md](docs/ru/DEPLOYMENT.md).

---

## Как устроено в Helix

У каждого **профиля** своё изолированное окружение:

| Ресурс | Путь |
|--------|------|
| Секреты, LLM, порты | `~/.helix/profiles/<имя>/.env` |
| Telegram-бот | `~/.helix/profiles/<имя>/telegram.env` |
| Gateway | `~/.helix/profiles/<имя>/gateway/` |
| Память, навыки, cron | `~/.helix/profiles/<имя>/data/` |

**Важно:** один токен Telegram-бота = один процесс polling = один профиль при запуске. Helix **не** запускает несколько полностью изолированных профилей параллельно на **одном** токене бота.

Документированная схема:

> **Разные люди → разные профили → разные боты**

```bash
helix -p alice telegram setup   # свой токен от @BotFather
helix -p bob telegram setup     # другой токен
```

Каждый gateway поднимает **своего** бота:

```bash
helix -p alice gateway start   # бот Alice + gateway :8001
helix -p bob gateway start     # бот Bob + gateway :8002
```

Порты в `.env` профилей должны различаться:

```bash
# ~/.helix/profiles/alice/.env
HELIX_GATEWAY_PORT=8001

# ~/.helix/profiles/bob/.env
HELIX_GATEWAY_PORT=8002
```

Это **рекомендуемый** вариант для нескольких пользователей с полной изоляцией.

---

## Рекомендуемая схема: один бот на профиль

### 1. Создать профили

```bash
helix profile create alice
helix profile create bob --protect   # опционально: ключ доступа hp_…
```

### 2. Настроить окружение и jail (опционально)

```bash
helix -p alice profile env --edit
helix -p bob profile env --edit
helix -p bob profile jail enable /home/bob/projects   # только своя папка
```

### 3. Свой бот у каждого профиля

В [@BotFather](https://t.me/BotFather) создайте **отдельного бота** на каждый профиль:

```bash
helix -p alice telegram setup
helix -p bob telegram setup
```

Токен и allowlist сохраняются в `profiles/<имя>/telegram.env`.

### 4. Запустить gateway (и бота) на профиль

```bash
helix -p alice gateway start
helix -p bob gateway start
```

Или через systemd — по одному unit на профиль:

```bash
sudo systemctl enable --now helix-gateway@alice
sudo systemctl enable --now helix-gateway@bob
```

См. [docs/ru/DEPLOYMENT.md](docs/ru/DEPLOYMENT.md).

### 5. Ограничить доступ в production

В `telegram.env` или `.env` профиля:

```bash
HELIX_ENV=production
HELIX_TELEGRAM_ALLOWED_USERS=123456789   # только свой Telegram user id
```

Узнать свой ID: например, [@userinfobot](https://t.me/userinfobot).

---

## Альтернатива: один бот на всех (с ограничениями)

Подходит для **доверенной команды**, когда все пользуются одним ботом и вручную переключают профиль.

```bash
helix -p shared gateway start
```

В Telegram каждый пользователь:

1. Пишет боту.
2. Переключается: `/profile alice` или `/profile bob hp_xxxxxxxx` (если профиль защищён).
3. Работает в своём профиле (память и сессии: `tg_<profile>_<chat_id>`).

Также доступны кнопка **Профиль** в меню бота и `/profile` без аргументов — список профилей.

### Ограничения одного бота

| Ограничение | Пояснение |
|-------------|-----------|
| Автопривязка `user_id → профиль` | Настраивается через `helix telegram map` (см. ниже) |
| Новый чат | Стартует на профиле, с которым запущен `gateway start` |
| Один токен | Нельзя держать два профиля как два независимых бота на одном токене |
| Безопасность | Все видят одного бота; изоляция — после `/profile`, ключей и jail |

### Защита при одном боте

```bash
helix profile create alice --protect
helix profile create bob --protect
```

Вход в защищённый профиль:

```text
/profile bob hp_xxxxxxxx
```

Плюс **workspace jail** — ограничить файловые и терминальные tools одной директорией:

```bash
helix -p alice profile jail enable /home/alice/work
helix -p bob profile jail enable /home/bob/work
```

См. [docs/ru/PROFILES.md](docs/ru/PROFILES.md) — разделы «Ключи доступа» и «Workspace jail».

---

## Сравнение подходов

| Подход | Изоляция | Удобство | Безопасность |
|--------|----------|----------|--------------|
| **1 бот = 1 профиль** (рекомендуется) | Полная | Каждый пишет своему боту | Высокая |
| **1 бот + `/profile`** | После ручного переключения | Один бот на всех | Средняя (нужны ключи + jail + allowlist) |

---

## Типичные ошибки

- **Один токен в нескольких `telegram.env`** — только один процесс сможет polling; остальные упадут с конфликтом.
- **Одинаковый `HELIX_GATEWAY_PORT`** у разных профилей — второй gateway не стартует.
- **Пустой `HELIX_TELEGRAM_ALLOWED_USERS` в production** — бот не примет сообщения (`HELIX_ENV=production`).

Проверка:

```bash
helix doctor
helix -p alice gateway status
helix -p bob gateway status
helix logs -s gateway -n 50
```

---

## Итог

- **Полная изоляция** → отдельный бот (токен) + отдельный gateway на каждый профиль.
- **Один бот на команду** → профили с `--protect`, jail, `HELIX_TELEGRAM_ALLOWED_USERS`, переключение через `/profile`.

## Привязка Telegram user id → профиль (один бот)

Настройка при `helix telegram setup` (если несколько профилей) или вручную:

```bash
# Профиль shared — тот, где лежит telegram.env и запущен gateway
helix -p shared telegram map set 123456789 alice
helix -p shared telegram map set 987654321 bob
helix -p shared telegram map list

# Быстро: привязать user id из allowlist к профилю
helix -p shared telegram map bind alice --user-id 123456789

# Импорт одной строкой
helix -p shared telegram map import "123456789:alice,987654321:bob"
```

Файл: `~/.helix/profiles/<бот-профиль>/telegram-users.json`  
Переменная: `HELIX_TELEGRAM_USER_PROFILES=123456789:alice,987654321:bob` в `telegram.env`

После привязки пользователь автоматически попадает в свой профиль Helix (память, модели, jail).  
Ручное `/profile` по-прежнему работает и отключает автопривязку для этого чата.