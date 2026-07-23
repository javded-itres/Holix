"""Optional SDD understanding gate: clarify until score ≥ user threshold."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.sdd.paths import change_dir, validate_change_id

UNDERSTANDING_FILE = ".understanding.json"
DEFAULT_THRESHOLD = 80


@dataclass
class UnderstandingTurn:
    role: str  # agent | user
    text: str
    score_after: int | None = None


@dataclass
class UnderstandingState:
    enabled: bool = True
    threshold: int = DEFAULT_THRESHOLD
    score: int = 0
    status: str = "clarifying"  # clarifying | ready | confirmed | skipped
    summary: str = ""
    open_questions: list[str] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> UnderstandingState:
        if not raw:
            return cls()
        hist = raw.get("history") or []
        return cls(
            enabled=bool(raw.get("enabled", True)),
            threshold=int(raw.get("threshold") or DEFAULT_THRESHOLD),
            score=max(0, min(100, int(raw.get("score") or 0))),
            status=str(raw.get("status") or "clarifying"),
            summary=str(raw.get("summary") or ""),
            open_questions=[str(q) for q in (raw.get("open_questions") or [])],
            history=[dict(h) for h in hist if isinstance(h, dict)],
        )


def understanding_path(project_root: Path, change_id: str) -> Path:
    return change_dir(project_root, validate_change_id(change_id)) / UNDERSTANDING_FILE


def load_understanding(project_root: Path, change_id: str) -> UnderstandingState | None:
    path = understanding_path(project_root, change_id)
    if not path.is_file():
        return None
    try:
        return UnderstandingState.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return UnderstandingState()


def save_understanding(
    project_root: Path,
    change_id: str,
    state: UnderstandingState,
) -> UnderstandingState:
    path = understanding_path(project_root, change_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return state


def init_understanding(
    project_root: Path,
    change_id: str,
    *,
    enabled: bool,
    threshold: int = DEFAULT_THRESHOLD,
    request: str = "",
) -> UnderstandingState:
    thr = max(1, min(100, int(threshold)))
    if not enabled:
        state = UnderstandingState(
            enabled=False,
            threshold=thr,
            score=100,
            status="skipped",
            summary="Understanding gate disabled by user settings.",
            history=(
                [{"role": "user", "text": request.strip(), "score_after": 100}]
                if request.strip()
                else []
            ),
        )
    else:
        # Gate ON: always start at 0 / clarifying so the agent runs Q&A.
        # Do NOT set score=100 here — that skips the survey mode.
        state = UnderstandingState(
            enabled=True,
            threshold=thr,
            score=0,
            status="clarifying",
            summary="",
            history=(
                [{"role": "user", "text": request.strip(), "score_after": 0}]
                if request.strip()
                else []
            ),
        )
    return save_understanding(project_root, change_id, state)


def update_understanding(
    project_root: Path,
    change_id: str,
    *,
    score: int,
    summary: str = "",
    questions: list[str] | None = None,
    agent_note: str = "",
    user_answer: str = "",
) -> dict[str, Any]:
    """Update score after agent assessment or user answers.

    Rules:
    - score is 0–100
    - if score >= threshold → status ready (may propose proceed)
    - if was ready and score drops below threshold → clarifying again
    - confirmed only via confirm_understanding
    """
    state = load_understanding(project_root, change_id) or UnderstandingState()
    if not state.enabled or state.status == "skipped":
        return {"ok": True, "understanding": state.to_dict(), "action": "skipped"}
    if state.status == "confirmed":
        return {
            "ok": True,
            "understanding": state.to_dict(),
            "action": "already_confirmed",
            "message": "User already confirmed; continue SDD propose/apply.",
        }

    new_score = max(0, min(100, int(score)))
    if agent_note.strip():
        state.history.append(
            {"role": "agent", "text": agent_note.strip(), "score_after": new_score}
        )
    if user_answer.strip():
        state.history.append(
            {"role": "user", "text": user_answer.strip(), "score_after": new_score}
        )
    state.score = new_score
    if summary.strip():
        state.summary = summary.strip()
    if questions is not None:
        state.open_questions = [q.strip() for q in questions if str(q).strip()]

    thr = state.threshold
    if new_score >= thr:
        state.status = "ready"
        action = "ready"
        message = (
            f"Understanding {new_score}% ≥ {thr}%. "
            "Offer user: proceed with SDD propose, or ask more questions."
        )
    else:
        state.status = "clarifying"
        action = "clarify"
        message = (
            f"Understanding {new_score}% < {thr}%. "
            "Ask clarifying questions until score reaches the threshold."
        )
        if not state.open_questions and not questions:
            message += " Provide open_questions in the next sdd_update_understanding call."

    save_understanding(project_root, change_id, state)
    return {
        "ok": True,
        "understanding": state.to_dict(),
        "action": action,
        "message": message,
        "threshold": thr,
        "score": new_score,
        "meets_threshold": new_score >= thr,
    }


def confirm_understanding(project_root: Path, change_id: str) -> dict[str, Any]:
    state = load_understanding(project_root, change_id) or UnderstandingState()
    if not state.enabled or state.status == "skipped":
        state.status = "confirmed"
        save_understanding(project_root, change_id, state)
        return {"ok": True, "understanding": state.to_dict(), "action": "confirmed"}
    if state.score < state.threshold:
        return {
            "ok": False,
            "error": (
                f"Cannot confirm: understanding {state.score}% "
                f"< threshold {state.threshold}%"
            ),
            "understanding": state.to_dict(),
        }
    state.status = "confirmed"
    state.open_questions = []
    save_understanding(project_root, change_id, state)
    return {
        "ok": True,
        "understanding": state.to_dict(),
        "action": "confirmed",
        "message": "User confirmed. Proceed with SDD propose artifacts.",
    }


def accept_request_understanding(
    project_root: Path,
    change_id: str,
    *,
    request: str = "",
    unlock: bool = True,
) -> UnderstandingState:
    """Record the user request and optionally unlock artifact writes.

    Parameters
    ----------
    unlock:
        True (default for **fill** / «Fill again»): set score ≥ threshold and
        ``confirmed`` so ``sdd_write_artifact`` is allowed immediately.
        False (create with gate ON): only seed history/summary — keep
        ``clarifying`` and score 0 so the agent must run the understanding Q&A.
    """
    state = load_understanding(project_root, change_id)
    req = (request or "").strip()

    if state is None:
        if unlock:
            state = UnderstandingState(
                enabled=True,
                threshold=DEFAULT_THRESHOLD,
                score=100,
                status="confirmed",
                summary=req[:500],
                history=(
                    [{"role": "user", "text": req, "score_after": 100}] if req else []
                ),
            )
        else:
            state = UnderstandingState(
                enabled=True,
                threshold=DEFAULT_THRESHOLD,
                score=0,
                status="clarifying",
                summary="",
                history=(
                    [{"role": "user", "text": req, "score_after": 0}] if req else []
                ),
            )
        return save_understanding(project_root, change_id, state)

    # Gate disabled or already terminal
    if not state.enabled or state.status == "skipped":
        return state
    if state.status == "confirmed" and unlock:
        return state

    # Seed request into history without inventing understanding score
    if req:
        already = any(
            (h.get("role") == "user" and (h.get("text") or "").strip() == req)
            for h in state.history
        )
        if not already:
            state.history = list(state.history) + [
                {
                    "role": "user",
                    "text": req,
                    "score_after": state.score if not unlock else 100,
                }
            ]
        if not (state.summary or "").strip():
            # Only set summary on unlock; during Q&A the agent owns summary
            if unlock:
                state.summary = req[:500]

    if unlock:
        # Explicit fill path: user asked to write artifacts now
        state.score = max(int(state.score), int(state.threshold), 100)
        state.status = "confirmed"
        state.open_questions = []
        if req and not (state.summary or "").strip():
            state.summary = req[:500]
    # else: leave clarifying/ready and score as init_understanding left them

    return save_understanding(project_root, change_id, state)


def gate_blocks_propose(project_root: Path, change_id: str) -> str | None:
    """Return blocking message if propose should not continue yet."""
    state = load_understanding(project_root, change_id)
    if state is None:
        return None
    if not state.enabled or state.status in ("skipped", "confirmed"):
        return None
    if state.status == "ready":
        return (
            f"Understanding ready at {state.score}% (≥ {state.threshold}%). "
            "Ask user to confirm proceed (sdd_confirm_understanding) or continue Q&A."
        )
    return (
        f"Understanding gate active: {state.score}% < {state.threshold}% "
        f"(status={state.status}). "
        "Continue clarifying with sdd_update_understanding; do not fill full proposal yet."
    )
