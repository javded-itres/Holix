"""Resolve spawn type names (custom preferred over generic built-ins when unambiguous)."""

from __future__ import annotations

from core.subagents.registry import (
    builtin_subagent_names,
    list_available_subagents,
    subagent_type_names,
)


def resolve_subagent_type(agent_type: str, *, profile: str | None = None) -> str:
    """Return a spawnable type name.

    Rules:
    - Exact match (builtin or custom) → keep
    - Unknown name → raise KeyError with available list
    - Generic builtin (e.g. ``coder``) when custom types exist that clearly specialize
      it (name starts with ``coder-`` or contains the builtin as prefix) → prefer the
      single matching custom type if exactly one; otherwise keep builtin
    """
    raw = (agent_type or "").strip().lower()
    if not raw:
        raise ValueError("agent_type is required")

    available = subagent_type_names(profile=profile)
    if raw in available:
        # Prefer specialized custom when user asked for bare builtin and exactly one
        # custom specialisation exists (coder → coder-python).
        if raw in builtin_subagent_names():
            customs = [
                t["name"]
                for t in list_available_subagents(profile=profile)
                if not t.get("builtin")
                and (
                    t["name"].startswith(f"{raw}-")
                    or t["name"].startswith(f"{raw}_")
                )
            ]
            if len(customs) == 1:
                return customs[0]
        return raw

    # Fuzzy: unique custom that starts with requested token
    customs = [
        t["name"]
        for t in list_available_subagents(profile=profile)
        if not t.get("builtin")
        and (t["name"] == raw or t["name"].startswith(f"{raw}-") or raw in t["name"])
    ]
    if len(customs) == 1:
        return customs[0]

    names = ", ".join(sorted(available))
    raise KeyError(f"No sub-agent '{agent_type}'. Available: {names}")
