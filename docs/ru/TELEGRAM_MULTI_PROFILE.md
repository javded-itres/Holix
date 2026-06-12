# Telegram: несколько изолированных профилей

Как организовать работу Holix в Telegram, когда нужно несколько пользователей или проектов с изоляцией данных, памяти и настроек.

См. также: [TELEGRAM.md](TELEGRAM.md), [PROFILES.md](PROFILES.md), [DEPLOYMENT.md](DEPLOYMENT.md).

---

## Как устроено в Holix

У каждого **профиля** своё изолированное окружение:

| Ресурс | Путь |
|--------|------|
| Секреты, LLM, порты | `~/.holix/profiles/<имя>/.env` |
| Telegram-бот | `~/.holix/profiles/<имя>/telegram.env` |
| Gateway | `~/.holix/profiles/<имя>/gateway/` |
| Память, навыки, cron | `~/.holix/profiles/<имя>/data/` |

**Важно:** один токен Telegram-бота = один процесс polling = один профиль при запуске. Holix **не** запускает несколько полностью изолированных профилей параллельно на **одном** токене бота.

Документированная схема:

> **Разные люди → разные профили → разные боты**

```bash
holix -p alice telegram setup   # свой токен от @BotFather
holix -p bob telegram setup     # другой токен
```

Каждый gateway поднимает **своего** бота:

```bash
holix -p alice gateway start   # бот Alice + gateway :8001
holix -p bob gateway start     # бот Bob + gateway :8002
```

Порты в `.env` профилей должны различаться:

```bash
# ~/.holix/profiles/alice/.env
HOLIX_GATEWAY_PORT=8001

# ~/.holix/profiles/bob/.env
HOLIX_GATEWAY_PORT=8002
```

Это **рекомендуемый** вариант для нескольких пользователей с полной изоляцией.

---

## Рекомендуемая схема: один бот на профиль

### 1. Создать профили

```bash
holix profile create alice
holix profile create bob --protect   # опционально: ключ доступа hp_…
```

### 2. Настроить окружение и jail (опционально)

```bash
holix -p alice profile env --edit
holix -p bob profile env --edit
holix -p bob profile jail enable /home/bob/projects   # только своя папка
```

### 3. Свой бот у каждого профиля

В [@BotFather](https://t.me/BotFather) создайте **отдельного бота** на каждый профиль:

```bash
holix -p alice telegram setup
holix -p bob telegram setup
```

Токен и allowlist сохраняются в `profiles/<имя>/telegram.env`.

### 4. Запустить gateway (и бота) на профиль

```bash
holix -p alice gateway start
holix -p bob gateway start
```

Или через systemd — по одному unit на профиль:

```bash
sudo systemctl enable --now holix-gateway@alice
sudo systemctl enable --now holix-gateway@bob
```

См. [DEPLOYMENT.md](DEPLOYMENT.md).

### 5. Ограничить доступ в production

Для **личного** бота (один владелец) укажите свой user id в `telegram.env` или `.env` профиля:

```bash
HOLIX_ENV=production
HOLIX_TELEGRAM_ALLOWED_USERS=123456789
```

Для **общего** бота на многих пользователей используйте запросы доступа (следующий раздел).

---

## Один бот — много пользователей (access requests, рекомендуется)

Один токен, много изолированных пользователей — user id при настройке вводить не нужно.

```bash
holix -p shared telegram setup
HOLIX_ENV=production holix -p shared gateway start -f
```

1. **Первый запуск** (один раз): назначить Telegram-админа из CLI — `holix -p shared telegram requests approve USER_ID --set-admin` (профиль `admin`, только CLI).
2. Пользователи отправляют `/start` (меню скрыто до approve); админ получает уведомление в Telegram.
3. Админ одобряет из CLI:

```bash
holix -p shared telegram requests list
holix -p shared telegram requests approve USER_ID -i
holix -p shared telegram requests approve USER_ID --create-profile ivan
```

При одобрении Holix создаёт **защищённый** профиль (с `--create-profile`), включает **workspace jail** в `profiles/ivan/workspace/`, привязывает пользователя, **отправляет ключ в Telegram** и включает меню команд для чата.

- Используйте **именованный профиль бота** (`-p shared`), не `default` — в production `default` только для dev.
- `HOLIX_TELEGRAM_ACCESS_REQUESTS=true` выставляется мастером `telegram setup` (см. [TELEGRAM.md](TELEGRAM.md)).
- Перезапуск бота после approve не нужен.

---

## Альтернатива: один бот + ручной `/profile` или `map`

Для **доверенной команды** с явным управлением привязками (без access requests).

```bash
holix -p shared gateway start
```

Каждый переключается вручную: `/profile alice` или `/profile bob hp_xxxxxxxx` (защищённые профили).  
Или привязка user id: `holix telegram map set …` (см. ниже).

### Ограничения одного бота

| Ограничение | Пояснение |
|-------------|-----------|
| Автопривязка `user_id → профиль` | `holix telegram map` или `telegram requests approve` |
| Новый чат | Стартует на профиле, активном при `gateway start` |
| Один токен | Нельзя держать два профиля как два независимых бота на одном токене |
| Безопасность | Общий бот; изоляция — через профили, ключи и jail |

### Защита при одном боте

```bash
holix profile create alice --protect
holix profile create bob --protect
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
- **Одинаковый `HOLIX_GATEWAY_PORT`** у разных профилей — второй gateway не стартует.
- **Нет пути доступа в production** — при `HOLIX_ENV=production` нужны access requests, allowlist или привязки `map`.

Проверка:

```bash
holix doctor
holix -p alice gateway status
holix -p bob gateway status
holix logs -s gateway -n 50
```

---

## Итог

- **Полная изоляция** → отдельный бот (токен) + отдельный gateway на каждый профиль.
- **Один бот, много пользователей** → `telegram setup` + `telegram requests approve --create-profile` (рекомендуется).
- **Ручная настройка команды** → привязки `map` или `/profile` с защищёнными профилями и jail.

## Привязка user id → профиль (один бот, вручную)

При `holix telegram setup` мастер предложит привязки, если профилей несколько.

```bash
holix -p shared telegram map set 123456789 alice
holix -p shared telegram map bind bob --user-id 987654321
holix -p shared telegram map import "111:alice,222:bob"
holix -p shared telegram map list
holix -p shared telegram map remove 111
```

- Файл: `~/.holix/profiles/<бот-профиль>/telegram-users.json`
- Env: `HOLIX_TELEGRAM_USER_PROFILES=123456789:alice` в `telegram.env`

Пользователь автоматически попадает в свой профиль (память, модели, jail).  
`/profile` вручную отключает автопривязку для этого чата.