# Holix Link — удалённый доступ к папке

Holix Link позволяет **агенту Holix на сервере** читать и записывать файлы в **папке на ПК пользователя** за NAT — без установки полного Holix на этой машине.

| Компонент | Пакет | Где работает |
|-----------|-------|--------------|
| **Клиент Holix Link** | [Holix-Link](https://pypi.org/project/Holix-Link/) (`holix-link`) | ПК пользователя (Windows / Linux / macOS) |
| **Link Relay + tools агента** | `Holix` (`holix`, `holix gateway`) | VPS / сервер |

Клиент открывает **исходящий WebSocket** (TLS/WSS). Входящие порты на стороне пользователя не нужны.

---

## Быстрый старт

### Сервер

```bash
holix link create --profile support --ttl 10m
# → LINK-7K3M-9Q2P

holix gateway start
```

Передайте pair-код пользователю (Telegram, email, support).

### ПК пользователя

```bash
pipx install Holix-Link
holix-link pair LINK-7K3M-9Q2P --folder ~/Projects/acme --server https://your-gateway.example.com
holix-link install-service
holix-link status
```

### Оператор (Telegram / чат профиля `support`)

Попросите агента прочитать файл — при наличии link используются tools `link_*`:

> Прочитай README.md в подключённой папке

---

## Команды сервера (`holix link`)

| Команда | Описание |
|---------|----------|
| `holix link create --profile NAME [--ttl 10m]` | Одноразовый pair-код (admin или владелец профиля) |
| `holix link list [--profile NAME] [--all]` | Список link |
| `holix link revoke <link_id>` | Отзыв связи |

```bash
holix -p support link create --ttl 15m
holix link list --profile support
holix link revoke link_abc123def456
```

Коды истекают (по умолчанию **10 минут**, максимум 1 час). Данные: `~/.holix/gateway/links.db`.

---

## Конфигурация профиля

В `~/.holix/profiles/<name>/config.yaml`:

```yaml
link:
  max_connections: 5
  permissions:
    read: true
    write: true
    mkdir: true
    delete: false
```

| Поле | По умолчанию | Описание |
|------|--------------|----------|
| `max_connections` | `5` | Макс. одновременных link на профиль |
| `permissions.read` | `true` | `link_read_file`, `link_list_dir`, `link_stat` |
| `permissions.write` | `true` | `link_write_file` |
| `permissions.mkdir` | `true` | `link_mkdir` |
| `permissions.delete` | `false` | `link_delete` (только файлы) |

Pair-код выдают **admin gateway** или **владелец профиля** (тот же Telegram-бот на сервере).

---

## Tools агента

Регистрируются автоматически, если у профиля есть активные link:

| Tool | Описание |
|------|----------|
| `link_list_dir` | Список каталога на клиенте |
| `link_read_file` | Чтение файла (макс. 10 MB) |
| `link_write_file` | Запись файла |
| `link_stat` | Метаданные пути |
| `link_mkdir` | Создать каталог |
| `link_delete` | Удалить файл |

При нескольких link на профиль укажите `link_id` в аргументах tool.

**Нужно:** запущенный gateway и онлайн-клиент (`holix-link daemon` / `install-service`).

---

## Команды клиента (`holix-link`)

| Команда | Описание |
|---------|----------|
| `holix-link wizard` | Интерактивный pairing |
| `holix-link pair CODE --folder PATH [--server URL]` | Pairing с gateway |
| `holix-link daemon --foreground` | Цикл подключения |
| `holix-link install-service` | Автозапуск (systemd / LaunchAgent / Task Scheduler) |
| `holix-link uninstall-service` | Убрать автозапуск |
| `holix-link stop` | Остановить daemon |
| `holix-link status` | Статус link и daemon |
| `holix-link disconnect` | Удалить локальные credentials |

### Установка (все платформы)

```bash
pipx install Holix-Link
# или
curl -fsSL https://raw.githubusercontent.com/javded-itres/Holix-Link/main/scripts/install-link.sh | bash
```

Windows: `scripts/install-link.ps1` из [репозитория Holix-Link](https://github.com/javded-itres/Holix-Link).

### Каталог данных

| ОС | Путь |
|----|------|
| Linux / macOS | `~/.holix-link/` |
| Windows | `%LOCALAPPDATA%\HolixLink\` |

Переопределение: `HOLIX_LINK_HOME`. URL gateway: `HOLIX_LINK_SERVER` или `--server`.

### Уведомления на клиенте (opt-in)

В `~/.holix-link/config.json`:

```json
{
  "notifications": {
    "enabled": true,
    "on_read": true,
    "on_write": true,
    "on_delete": true
  }
}
```

### Заметки по платформам

| ОС | Примеры папок | Автозапуск |
|----|---------------|------------|
| **Linux** | `~/work`, `/home/user/data` | systemd user unit |
| **macOS** | `~/Documents/project` | LaunchAgent |
| **Windows** | `C:\Users\me\Projects`, `\\server\share` | Task Scheduler при входе |

Поддерживаются UNC и сетевые пути; внутри jail — portable относительные пути.

---

## HTTP / WebSocket API

| Endpoint | Auth | Назначение |
|----------|------|------------|
| `POST /v1/link/create` | API key | Создать pair-код |
| `POST /v1/link/pair` | Публичный (rate limit) | Обмен кода на `link_id` |
| `GET /v1/link/list` | API key | Список link |
| `GET /v1/link/{id}` | API key | Статус link |
| `POST /v1/link/revoke/{id}` | API key | Отзыв |
| `WS /v1/link/ws` | Device key (первое сообщение) | Сессия клиента |

Подробнее: [GATEWAY_API.md](GATEWAY_API.md#holix-link-api).

---

## Безопасность

- TLS 1.3 (WSS)
- Fingerprint сервера при pairing; доверие через подтверждение или `HOLIX_LINK_TRUSTED_FP`
- Workspace jail на клиенте — без escape, symlink заблокирован
- Отзыв: `holix link revoke` или `holix-link disconnect`
- Только self-hosted relay

См. [SECURITY.md](SECURITY.md) и [design doc](../design/REMOTE_FOLDER_AGENT.md).

---

## Решение проблем

| Симптом | Проверка |
|---------|----------|
| Pairing 404 | Код истёк — `holix link create` снова |
| Pairing 409 | Лимит `link.max_connections` — отзовите старые link |
| Агент: link offline | `holix-link status`, daemon, исходящий HTTPS |
| Нет link tools | `holix link list` — нет активных link |
| Предупреждения doctor | Секция link в выводе `holix doctor` |

```bash
holix link list --profile support
holix gateway status
holix-link status    # на ПК клиента
```

---

## См. также

- [GATEWAY.md](GATEWAY.md)
- [PROFILES.md](PROFILES.md)
- [Holix-Link на GitHub](https://github.com/javded-itres/Holix-Link)