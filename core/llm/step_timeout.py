"""LLM per-step timeout helpers and user-facing messages."""

from __future__ import annotations


class LLMStepTimeoutError(TimeoutError):
    """Raised when an LLM step exceeds configured limits."""

    def __init__(self, user_message: str) -> None:
        self.user_message = user_message
        super().__init__(user_message)


def llm_step_timeout_message(
    timeout_s: float,
    *,
    model: str | None = None,
    reasoning_only: bool = False,
) -> str:
    """Build a localized timeout explanation for the messenger UI."""
    seconds = int(timeout_s)
    if reasoning_only:
        model_hint = f" (`{model}`)" if model else ""
        return (
            f"Модель{model_hint} больше {seconds} с отдаёт только внутренние рассуждения "
            "без видимого ответа и вызовов tools.\n"
            "Для основного чата переключитесь на `smart` (/models), "
            "сократите историю (/clear) или увеличьте `llm_step_timeout` в конфиге."
        )
    model_part = f" (модель: {model})" if model else ""
    return (
        f"Модель не ответила за {seconds} с{model_part}. "
        "Попробуйте ещё раз, выберите другую модель (/models) "
        "или увеличьте `llm_step_timeout`."
    )


def reasoning_only_abort_s(llm_timeout_s: float) -> float:
    """Abort reasoning-only streams before the hard step deadline."""
    return min(90.0, max(30.0, llm_timeout_s * 0.75))