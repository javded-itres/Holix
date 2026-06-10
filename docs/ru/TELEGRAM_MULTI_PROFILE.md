# Telegram: несколько изолированных профилей

Как организовать работу Helix в Telegram, когда нужно несколько пользователей или проектов с изоляцией данных, памяти и настроек.

См. также: [TELEGRAM.md](TELEGRAM.md), [PROFILES.md](PROFILES.md), [DEPLOYMENT.md](DEPLOYMENT.md).

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

См. [DEPLOYMENT.md](DEPLOYMENT.md).

### 5. Ограничить доступ в production

Для **личного** бота (один владелец) укажите свой user id в `telegram.env` или `.env` профиля:

```bash
HELIX_ENV=production
HELIX_TELEGRAM_ALLOWED_USERS=123456789
```

Для **общего** бота на многих пользователей используйте запросы доступа (следующий раздел).

---

## Один бот — много пользователей (access requests, рекомендуется)

Один токен, много изолированных пользователей — user id при настройке вводить не нужно.

```bash
helix -p shared telegram setup
HELIX_ENV=production helix -p shared gateway start -f
```

1. **Первый запуск** (один раз): назначить Telegram-админа из CLI — `helix -p shared telegram requests approve USER_ID --set-admin` (профиль `admin`, только CLI).
2. Пользователи отправляют `/start` (меню скрыто до approve); админ получает уведомление в Telegram.
3. Админ одобряет из CLI:

```bash
helix -p shared telegram requests list
helix -p shared telegram requests approve USER_ID -i
helix -p shared telegram requests approve USER_ID --create-profile ivan
```

При одобрении Helix создаёт **защищённый** профиль (с `--create-profile`), включает **workspace jail** в `profiles/ivan/workspace/`, привязывает пользователя, **отправляет ключ в Telegram** и включает меню команд для чата.

- Используйте **именованный профиль бота** (`-p shared`), не `default` — в production `default` только для dev.
- `HELIX_TELEGRAM_ACCESS_REQUESTS=true` выставляется мастером `telegram setup` (см. [TELEGRAM.md](TELEGRAM.md)).
- Перезапуск бота после approve не нужен.

---

## Альтернатива: один бот + ручной `/profile` или `map`

Для **доверенной команды** с явным управлением привязками (без access requests).

```bash
helix -p shared gateway start
```

Каждый переключается вручную: `/profile alice` или `/profile bob hp_xxxxxxxx` (защищённые профили).  
Или привязка user id: `helix telegram map set …` (см. ниже).

### Ограничения одного бота

| Ограничение | Пояснение |
|-------------|-----------|
| Автопривязка `user_id → профиль` | `helix telegram map` или `telegram requests approve` |
| Новый чат | Стартует на профиле, активном при `gateway start` |
| Один токен | Нельзя держать два профиля как два независимых бота на одном токене |
| Безопасность | Общий бот; изоляция — через профили, ключи и jail |

### Защита при одном боте

```bash
helix profile create alice --protect
helix profile create bob --protect
```

Защищённые профили получают workspace jail автоматически. См. [PROFILES.md](PROFILES.md).

---

## Сравнение подходов

| Подход | Изоляция | Удобство | Безопасность |
|--------|----------|----------|--------------|
| **1 бот = 1 профиль** (полная изоляция) | Полная | Каждый пишет своему боту | Высокая |
| **1 бот + access requests** (рекомендуется для общего бота) | Профиль на пользователя | `/start` → approve админом | Высокая (ключ + jail) |
| **1 бот + `/profile` / `map`** | После ручной настройки | Один бот на всех | Средняя |

---

## Типичные ошибки

- **Один токен в нескольких `telegram.env`** — только один процесс сможет polling; остальные упадут с конфликтом.
- **Одинаковый `HELIX_GATEWAY_PORT`** у разных профилей — второй gateway не стартует.
- **Нет пути доступа в production** — при `HELIX_ENV=production` нужны access requests, allowlist или привязки `map`.

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
- **Один бот, много пользователей** → `telegram setup` + `telegram requests approve --create-profile` (рекомендуется).
- **Ручная настройка команды** → привязки `map` или `/profile` с защищёнными профилями и jail.

## Привязка user id → профиль (один бот, вручную)

При `helix telegram setup` мастер предложит привязки, если профилей несколько.

```bash
helix -p shared telegram map set 123456789 alice
helix -p shared telegram map bind bob --user-id 987654321
helix -p shared telegram map import "111:alice,222:bob"
helix -p shared telegram map list
helix -p shared telegram map remove 111
```

- Файл: `~/.helix/profiles/<бот-профиль>/telegram-users.json`
- Env: `HELIX_TELEGRAM_USER_PROFILES=123456789:alice` в `telegram.env`

Пользователь автоматически попадает в свой профиль (память, модели, jail).  
`/profile` вручную отключает автопривязку для этого чата.