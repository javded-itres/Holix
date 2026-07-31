# Протокол Agent2Agent (A2A)

Holix участвует в открытом протоколе **[Agent2Agent (A2A)](https://a2a-protocol.org)**:

| Роль | Что делает Holix |
|------|------------------|
| **A2A Server** | Agent Card + JSON-RPC `/a2a` + REST + **SSE streaming** |
| **A2A Client** | Tools discovery и вызова удалённых A2A-агентов |

Внутренние **субагенты** Holix остаются локальными. A2A — для **внешних** систем.

## Включение

`config.yaml` профиля:

```yaml
a2a:
  enabled: true
  public_url: https://agent.example.com/a2a
  name: Holix Coding Agent
  remote_agents:
    - name: research
      url: https://other.example.com/a2a
```

| Переменная | Смысл |
|------------|--------|
| `HOLIX_A2A_ENABLED` | вкл/выкл |
| `HOLIX_A2A_PUBLIC_URL` | публичный URL карточки |
| `HOLIX_A2A_TIMEOUT_S` | таймаут клиента |

## Эндпоинты gateway

Нужен API-ключ gateway (`hx_…`).

| Метод | Путь | Назначение |
|-------|------|------------|
| `GET` | `/.well-known/agent.json` | Agent Card |
| `POST` | `/a2a` | JSON-RPC: `message/send`, **`message/stream` (SSE)**, `tasks/*` |
| `POST` | `/a2a/message:send` | REST (JSON или SSE при `Accept: text/event-stream`) |
| `POST` | `/a2a/message:stream` | REST, всегда SSE |
| `GET` | `/a2a/tasks/{id}` | статус задачи |
| `GET` | `/a2a/tasks/{id}/subscribe` | SSE-снимок состояния |

В карточке: `"capabilities": {"streaming": true}`.

### Streaming (SSE) — пример

```bash
curl -sSN -X POST "http://127.0.0.1:8000/a2a" \
  -H "Authorization: Bearer $HOLIX_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/stream",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "Привет"}]
      }
    }
  }'
```

События: `task` → `statusUpdate` / `artifactUpdate` → `statusUpdate.final=true`.

## Инструменты агента

- `a2a_list_agents`
- `a2a_discover`
- `a2a_send_message` (blocking)
- `a2a_get_task`

## Ограничения

- Push notifications (webhook) пока нет  
- Task store в памяти процесса gateway  
- Live progress — через `message/stream`; `/tasks/{id}/subscribe` даёт снимок  

Полная EN-версия: [en/A2A.md](../en/A2A.md).
