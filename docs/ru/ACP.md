# Agent Client Protocol (ACP)

Holix может запускать **внешнего coding-агента** по [Agent Client Protocol](https://agentclientprotocol.com) (JSON-RPC по stdio). Ребёнок — новый процесс и новая сессия: без истории, tools, PTY и todos родителя.

Это out-of-process пара к субагентам Holix (`delegate_to_subagent`). ACP нужен, когда ход должен вести Grok Build, Claude Code или другой ACP-бинарник.

## Настройка

```bash
export HOLIX_ACP_COMMAND='grok --acp'   # или: claude --acp
export HOLIX_ACP_PERMISSION=reject      # reject | allow
```

Бинарник должен говорить ACP: `initialize` → `session/new` → `session/prompt`, уведомления `session/update`.

## Инструмент

```text
run_acp_agent(prompt="…", cwd=optional, command=optional, timeout=300)
```

Запросы `session/request_permission` отвечаются автоматически. Holix не реализует fs/terminal callbacks агента.

## Связанное

- Воркеры Holix: [SUBAGENTS.md](SUBAGENTS.md)
- Запуск CLI в tmux: [LAUNCH.md](LAUNCH.md)
