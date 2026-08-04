"""OpenTelemetry GenAI semantic conventions (Development status, 2026).

Instruments LLM / agent operations per:
https://github.com/open-telemetry/semantic-conventions-genai

No hard dependency on the OTEL SDK: when ``opentelemetry-api`` is not
installed or no TracerProvider is configured, all helpers are no-ops.

Environment (standard OTEL):
  OTEL_SERVICE_NAME, OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_SDK_DISABLED=true
  HOLIX_OTEL_GENAI=0 to force-disable Holix GenAI spans even if OTEL is on.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

# Attribute keys (GenAI semantic conventions — Development)
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
GEN_AI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
GEN_AI_CONVERSATION_ID = "gen_ai.conversation.id"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_REQUEST_STREAM = "gen_ai.request.stream"
ERROR_TYPE = "error.type"

# Metric names
METRIC_TOKEN_USAGE = "gen_ai.client.token.usage"
METRIC_OPERATION_DURATION = "gen_ai.client.operation.duration"

_tracer = None
_meter = None
_token_hist = None
_duration_hist = None
_init_attempted = False


def _enabled() -> bool:
    if (os.getenv("HOLIX_OTEL_GENAI") or "").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False
    if (os.getenv("OTEL_SDK_DISABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return False
    return True


def _ensure_instruments() -> None:
    global _tracer, _meter, _token_hist, _duration_hist, _init_attempted
    if _init_attempted:
        return
    _init_attempted = True
    if not _enabled():
        return
    try:
        from opentelemetry import metrics, trace

        _tracer = trace.get_tracer("holix.genai", "1.0.0")
        _meter = metrics.get_meter("holix.genai", "1.0.0")
        _token_hist = _meter.create_histogram(
            METRIC_TOKEN_USAGE,
            unit="{token}",
            description="Number of input/output tokens used in a GenAI operation",
        )
        _duration_hist = _meter.create_histogram(
            METRIC_OPERATION_DURATION,
            unit="s",
            description="GenAI operation duration",
        )
    except Exception:
        logger.debug("OpenTelemetry GenAI instrumentation unavailable", exc_info=True)
        _tracer = None
        _meter = None
        _token_hist = None
        _duration_hist = None


def infer_provider_name(model: str = "", base_url: str = "") -> str:
    """Best-effort ``gen_ai.provider.name`` from model id or base URL."""
    url = (base_url or "").lower()
    m = (model or "").lower()
    if "anthropic" in url or m.startswith("claude"):
        return "anthropic"
    if "openai.com" in url or m.startswith("gpt-") or m.startswith("o1") or m.startswith("o3"):
        return "openai"
    if "azure" in url:
        return "azure.ai.inference"
    if "bedrock" in url or "amazonaws" in url:
        return "aws.bedrock"
    if "googleapis" in url or "generativelanguage" in url:
        return "gcp.gen_ai"
    if "localhost" in url or "11434" in url or "ollama" in m:
        return "ollama"
    if "litellm" in url:
        return "openai"  # OpenAI-compatible proxy
    return "openai"


@contextmanager
def genai_inference_span(
    *,
    model: str,
    operation_name: str = "chat",
    provider_name: str = "",
    conversation_id: str = "",
    agent_name: str = "holix",
    max_tokens: int | None = None,
    temperature: float | None = None,
    stream: bool = False,
    base_url: str = "",
) -> Iterator[Any]:
    """Context manager for a GenAI inference CLIENT span.

    Yields the span object (or ``None`` if OTEL is off). Call
    :func:`end_inference_span` or set attributes on the span yourself.
    """
    _ensure_instruments()
    if _tracer is None:
        yield None
        return

    from opentelemetry.trace import SpanKind, Status, StatusCode

    provider = provider_name or infer_provider_name(model, base_url)
    span_name = f"{operation_name} {model}".strip() or operation_name
    attrs: dict[str, Any] = {
        GEN_AI_OPERATION_NAME: operation_name,
        GEN_AI_PROVIDER_NAME: provider,
        GEN_AI_REQUEST_MODEL: model or "",
        GEN_AI_AGENT_NAME: agent_name or "holix",
    }
    if conversation_id:
        attrs[GEN_AI_CONVERSATION_ID] = conversation_id
    if max_tokens is not None:
        attrs[GEN_AI_REQUEST_MAX_TOKENS] = int(max_tokens)
    if temperature is not None:
        attrs[GEN_AI_REQUEST_TEMPERATURE] = float(temperature)
    if stream:
        attrs[GEN_AI_REQUEST_STREAM] = True

    t0 = time.perf_counter()
    with _tracer.start_as_current_span(
        span_name,
        kind=SpanKind.CLIENT,
        attributes=attrs,
    ) as span:
        try:
            yield span
        except Exception as exc:
            try:
                span.set_attribute(ERROR_TYPE, type(exc).__name__)
                span.set_status(Status(StatusCode.ERROR, str(exc)[:200]))
            except Exception:
                pass
            raise
        finally:
            elapsed = max(0.0, time.perf_counter() - t0)
            try:
                if _duration_hist is not None:
                    _duration_hist.record(
                        elapsed,
                        {
                            GEN_AI_OPERATION_NAME: operation_name,
                            GEN_AI_PROVIDER_NAME: provider,
                            GEN_AI_REQUEST_MODEL: model or "",
                        },
                    )
            except Exception:
                pass


@contextmanager
def genai_plan_span(
    *,
    agent_name: str = "holix",
    conversation_id: str = "",
    model: str = "",
) -> Iterator[Any]:
    """Internal span for agent planning / task decomposition (``plan``)."""
    _ensure_instruments()
    if _tracer is None:
        yield None
        return

    from opentelemetry.trace import SpanKind, Status, StatusCode

    attrs: dict[str, Any] = {
        GEN_AI_OPERATION_NAME: "plan",
        GEN_AI_AGENT_NAME: agent_name or "holix",
    }
    if conversation_id:
        attrs[GEN_AI_CONVERSATION_ID] = conversation_id
    if model:
        attrs[GEN_AI_REQUEST_MODEL] = model
    span_name = f"plan {agent_name}".strip() if agent_name else "plan"
    with _tracer.start_as_current_span(
        span_name,
        kind=SpanKind.INTERNAL,
        attributes=attrs,
    ) as span:
        try:
            yield span
        except Exception as exc:
            try:
                span.set_attribute(ERROR_TYPE, type(exc).__name__)
                span.set_status(Status(StatusCode.ERROR, str(exc)[:200]))
            except Exception:
                pass
            raise


def record_inference_result(
    span: Any,
    *,
    usage: dict[str, int] | None = None,
    finish_reason: str | None = None,
    response_model: str = "",
    duration_ms: float | None = None,
    estimated: bool = False,
    operation_name: str = "chat",
    provider_name: str = "",
    request_model: str = "",
) -> None:
    """Attach usage / finish attributes and record token metrics on a span."""
    usage = usage or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    if span is not None:
        try:
            if response_model:
                span.set_attribute(GEN_AI_RESPONSE_MODEL, response_model)
            if prompt > 0:
                span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, prompt)
            if completion > 0:
                span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, completion)
            if finish_reason:
                span.set_attribute(GEN_AI_RESPONSE_FINISH_REASONS, [str(finish_reason)])
            if estimated:
                span.set_attribute("gen_ai.usage.estimated", True)
        except Exception:
            logger.debug("Failed to set GenAI span attributes", exc_info=True)

    _ensure_instruments()
    if _token_hist is None:
        return
    provider = provider_name or "openai"
    model = request_model or response_model or ""
    base_attrs = {
        GEN_AI_OPERATION_NAME: operation_name,
        GEN_AI_PROVIDER_NAME: provider,
        GEN_AI_REQUEST_MODEL: model,
    }
    try:
        if prompt > 0:
            _token_hist.record(
                prompt,
                {**base_attrs, "gen_ai.token.type": "input"},
            )
        if completion > 0:
            _token_hist.record(
                completion,
                {**base_attrs, "gen_ai.token.type": "output"},
            )
        if duration_ms is not None and _duration_hist is not None:
            # Prefer duration from caller when span context was not used
            pass
    except Exception:
        logger.debug("Failed to record GenAI token metrics", exc_info=True)


def configure_otel_from_env() -> bool:
    """Install TracerProvider + MeterProvider with OTLP HTTP exporters when configured.

    Returns True if a provider was installed. Safe to call multiple times.
    Requires optional extra: ``pip install 'Holix[otel]'``.
    """
    if not _enabled():
        return False
    endpoint = (os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    if not endpoint and not (os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or "").strip():
        return False
    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception:
        logger.info(
            "HOLIX OTEL: install optional extra Holix[otel] for GenAI telemetry export"
        )
        return False

    service = (os.getenv("OTEL_SERVICE_NAME") or "holix").strip() or "holix"
    resource = Resource.create({"service.name": service})
    try:
        if not isinstance(trace.get_tracer_provider(), TracerProvider):
            tp = TracerProvider(resource=resource)
            tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
            trace.set_tracer_provider(tp)
        reader = PeriodicExportingMetricReader(OTLPMetricExporter())
        mp = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(mp)
        global _init_attempted, _tracer, _meter, _token_hist, _duration_hist
        _init_attempted = False
        _ensure_instruments()
        logger.info("HOLIX OTEL GenAI: TracerProvider + MeterProvider ready (service=%s)", service)
        return True
    except Exception:
        logger.warning("HOLIX OTEL GenAI setup failed", exc_info=True)
        return False


def record_llm_call(
    *,
    model: str,
    usage: dict[str, int] | None = None,
    duration_ms: float | None = None,
    finish_reason: str | None = None,
    conversation_id: str = "",
    provider_name: str = "",
    operation_name: str = "chat",
    agent_name: str = "holix",
    estimated: bool = False,
    base_url: str = "",
) -> None:
    """One-shot record of a completed LLM call (span + metrics).

    Used when the call already finished (e.g. from ``emit_llm_call_usage``).
    """
    _ensure_instruments()
    if _tracer is None and _token_hist is None:
        return
    usage = usage or {}
    provider = provider_name or infer_provider_name(model, base_url)
    t0 = time.perf_counter()
    with genai_inference_span(
        model=model,
        operation_name=operation_name,
        provider_name=provider,
        conversation_id=conversation_id,
        agent_name=agent_name,
        base_url=base_url,
    ) as span:
        # Span is short-lived for completed calls: set result immediately.
        if duration_ms is not None and duration_ms > 0:
            # Backdate is not supported; attribute duration instead.
            try:
                if span is not None:
                    span.set_attribute(
                        "gen_ai.client.operation.duration",
                        float(duration_ms) / 1000.0,
                    )
            except Exception:
                pass
        record_inference_result(
            span,
            usage=usage,
            finish_reason=finish_reason,
            response_model=model,
            duration_ms=duration_ms,
            estimated=estimated,
            operation_name=operation_name,
            provider_name=provider,
            request_model=model,
        )
        # Keep span open only for attribute write; elapsed ~0 when duration given.
        if duration_ms is None and _duration_hist is not None:
            _ = time.perf_counter() - t0
