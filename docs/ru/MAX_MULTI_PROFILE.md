# MAX: несколько изолированных профилей

Как организовать работу Holix в MAX, когда нужно несколько пользователей или проектов с изоляцией данных, памяти и настроек.

См. также: [MAX.md](MAX.md), [PROFILES.md](PROFILES.md), [DEPLOYMENT.md](DEPLOYMENT.md).

---

## Как устроено в Holix

У каждого **профиля** своё изолированное окружение:

| Ресурс | Путь |
|--------|------|
| Секреты, LLM, порты | `~/.holix/profiles/<имя>/.env` |
| MAX-бот | `~/.holix/profiles/<имя>/max.env` |
| Gateway | `~/.holix/profiles/<имя>/gateway/` |
| Память, навыки, cron | `~/.holix/profiles/<имя>/data/` |

**Важно:** один токен MAX-бота = один host-профиль = один webhook (или один polling-процесс). Holix **не** запускает несколько полностью изолированных host-профилей параллельно на **одном** токене бота.

Документированная схема для полной изоляции:

> **Разные люди → разные профили → разные боты**

```bash
holix -p alice max setup   # свой токен с business.max.ru
holix -p bob max setup     # другой токен
```

Каждый gateway поднимает **своего** бота и webhook:

```bash
holix -p alice gateway start   # бот Alice + gateway :8001
holix -p bob gateway start     # бот Bob + gateway :8002
```

Порты и webhook URL в `.env` / `max.env` профилей должны различаться:

```bash
# ~/.holix/profiles/alice/.env
HOLIX_GATEWAY_PORT=8001

# ~/.holix/profiles/alice/max.env
HOLIX_MAX_WEBHOOK_URL=https://alice.example.com/max/webhook

# ~/.holix/profiles/bob/.env
HOLIX_GATEWAY_PORT=8002

# ~/.holix/profiles/bob/max.env
HOLIX_MAX_WEBHOOK_URL=https://bob.example.com/max/webhook
```

Это **рекомендуемый** вариант для нескольких пользователей с полной изоляцией.

---

## Рекомендуемая схема: один бот на профиль

### 1. Создать профили

```bash
holix profile create alice
holix profile create bob --protect   # опционально: ключ доступа hp_…
```

### 2. Настроить бота в каждом профиле

```bash
holix -p alice max setup
holix -p bob max setup
```

### 3. Запустить gateway

```bash
holix -p alice gateway start
holix -p bob gateway start
```

Каждый пользователь пишет **своему** боту в MAX.

---

## Альтернатива: один бот — много профилей Holix

Один токен MAX на host-профиле `shared`; каждый пользователь получает **свой** профиль Holix через access requests или `map`.

```bash
holix -p shared max setup
HOLIX_ENV=production holix -p shared gateway start -f
```

Поток:

1. Пользователь → `/start` в MAX
2. Админ → `holix -p shared max requests approve USER_ID --create-profile ivan`
3. Пользователь `ivan` пишет боту; агент работает в `~/.holix/profiles/ivan/`

Привязки хранятся в `profiles/shared/max-users.json` и Management API:

```bash
holix -p shared max map list
curl -H "Authorization: Bearer hx_…" \
  http://127.0.0.1:8000/api/holix/profiles/shared/max/map
```

После изменений:

```bash
holix -p shared gateway reload
```

### Когда выбрать общий бот

| Критерий | Один бот (`shared`) | Бот на профиль |
|----------|---------------------|----------------|
| Изоляция данных | Через `map` / access requests | Полная по умолчанию |
| Операционная сложность | Один webhook, один токен | N webhook URL, N токенов |
| Масштаб | Команда / SaaS с админом | Независимые клиенты |

---

## Безопасность

- В production не используйте `HOLIX_MAX_ALLOW_ALL=true`.
- Назначайте **одного** MAX-админа: `holix max requests approve … --set-admin`.
- Для пользовательских данных включайте `--create-profile` и workspace jail.
- Шифруйте `max.env` через [шифрование профиля](PROFILE_ENCRYPTION.md).
- Webhook secret (`HOLIX_MAX_WEBHOOK_SECRET`) обязателен на публичном endpoint.

---

## Management API (кратко)

| Эндпоинт | Назначение |
|----------|------------|
| `GET …/max/status` | Токен (masked), режим, admin, подписки |
| `GET/POST …/max/requests` | Очередь заявок доступа |
| `GET/PUT …/max/map` | Привязки user_id → profile |
| `GET/DELETE …/max/admin` | Администратор MAX |

Полный справочник: [GATEWAY_API.md](GATEWAY_API.md).

---

## См. также

- [MAX.md](MAX.md) — быстрый старт, переменные, troubleshooting
- [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md) — аналогичная схема для Telegram
- [GATEWAY.md](GATEWAY.md) — multi-profile gateway и companions