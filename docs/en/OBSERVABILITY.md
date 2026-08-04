# Observability

## Plan-mode live progress

In **plan_and_execute** / **hybrid**, Holix emits `ThinkingEvent` phases while the plan is built so Studio/Telegram show that work is in progress:

| Phase | Meaning |
|-------|---------|
| Preparing | Plan mode started |
| Context | Memory + tools inventory |
| Handbook | Loading HOLIX.md / specs (`/init` pre-scan if missing) |
| LLM | Model call started (model + timeout) |
| Still generating | Heartbeat every ~12s with elapsed time |
| Attempt N | Retry after quality failure / timeout |
| Parsing / quality | Draft received, validation |
| Saving / ready | Draft persisted; waiting for approval |

## OpenTelemetry GenAI semantic conventions

Holix records LLM and planning spans using [OpenTelemetry GenAI conventions](https://github.com/open-telemetry/semantic-conventions-genai) (Development status).

### Install

```bash
pip install 'Holix[otel]'
# or
uv sync --extra otel
```

### Configure

Standard OTEL environment variables:

```bash
export OTEL_SERVICE_NAME=holix
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
# optional: disable Holix GenAI layer only
# export HOLIX_OTEL_GENAI=0
# export OTEL_SDK_DISABLED=true
```

On process start (`register_integration_hooks`), Holix installs a `TracerProvider` + `MeterProvider` with OTLP HTTP exporters when an endpoint is set.

### Spans and attributes

| Operation | Span name pattern | Key attributes |
|-----------|-------------------|----------------|
| Chat / completion | `chat {model}` | `gen_ai.operation.name=chat`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons`, `gen_ai.conversation.id` |
| Plan build | `plan holix` | `gen_ai.operation.name=plan`, `gen_ai.agent.name` |

Metrics (when MeterProvider is active):

- `gen_ai.client.token.usage` (`{token}`, attribute `gen_ai.token.type` = `input` \| `output`)
- `gen_ai.client.operation.duration` (`s`)

Without the OTEL packages or exporter, all GenAI helpers are **no-ops** (agent events and Studio metrics still work).
