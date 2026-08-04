"""OpenTelemetry GenAI semantic conventions helpers (no SDK required)."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.llm.usage import emit_llm_call_usage
from core.monitoring.genai_otel import (
    GEN_AI_OPERATION_NAME,
    GEN_AI_PROVIDER_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
    infer_provider_name,
    record_llm_call,
)


def test_infer_provider_name() -> None:
    assert infer_provider_name("gpt-4o", "https://api.openai.com/v1") == "openai"
    assert infer_provider_name("claude-3", "https://api.anthropic.com") == "anthropic"
    assert infer_provider_name("qwen", "http://localhost:11434/v1") == "ollama"


def test_record_llm_call_noop_without_otel(monkeypatch) -> None:
    """Must not raise when OTEL packages are missing or disabled."""
    monkeypatch.setenv("HOLIX_OTEL_GENAI", "0")
    # Force re-init
    import core.monitoring.genai_otel as mod

    monkeypatch.setattr(mod, "_init_attempted", False)
    monkeypatch.setattr(mod, "_tracer", None)
    record_llm_call(
        model="gpt-test",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        duration_ms=120.0,
        finish_reason="stop",
        conversation_id="c1",
    )


def test_emit_llm_call_usage_still_emits_agent_event(monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_OTEL_GENAI", "0")
    import core.monitoring.genai_otel as mod

    monkeypatch.setattr(mod, "_init_attempted", False)

    agent = MagicMock()
    total = emit_llm_call_usage(
        agent,
        model="m1",
        step=2,
        conversation_id="cid",
        usage={"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
        duration_ms=50.0,
        finish_reason="stop",
    )
    assert total == 15
    agent.emit.assert_called_once()
    ev = agent.emit.call_args[0][0]
    assert ev.total_tokens == 15
    assert ev.prompt_tokens == 11
    assert ev.model == "m1"


def test_genai_attribute_constants() -> None:
    assert GEN_AI_OPERATION_NAME == "gen_ai.operation.name"
    assert GEN_AI_PROVIDER_NAME == "gen_ai.provider.name"
    assert GEN_AI_REQUEST_MODEL == "gen_ai.request.model"
    assert GEN_AI_USAGE_INPUT_TOKENS == "gen_ai.usage.input_tokens"
    assert GEN_AI_USAGE_OUTPUT_TOKENS == "gen_ai.usage.output_tokens"
