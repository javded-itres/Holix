from core.monitoring.logger import logger
from core.monitoring.metrics import metrics

__all__ = ["logger", "metrics", "genai_otel"]


def __getattr__(name: str):
    if name == "genai_otel":
        from core.monitoring import genai_otel as _genai_otel

        return _genai_otel
    raise AttributeError(name)
