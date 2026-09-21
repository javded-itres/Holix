"""Sub-agent step-limit policy (enable/disable + optional cap)."""

from __future__ import annotations

from types import SimpleNamespace

from core.subagents.step_limits import apply_subagent_step_policy


def test_disabled_forces_unlimited() -> None:
    parent = SimpleNamespace(subagent_max_steps_enabled=False, subagent_max_steps=80)
    child = SimpleNamespace(max_steps=150)
    assert apply_subagent_step_policy(parent, child, requested=40) == 0
    assert child.max_steps == 0


def test_enabled_uses_explicit_spawn_override() -> None:
    parent = SimpleNamespace(subagent_max_steps_enabled=True, subagent_max_steps=80)
    child = SimpleNamespace(max_steps=150)
    assert apply_subagent_step_policy(parent, child, requested=12) == 12
    assert child.max_steps == 12


def test_enabled_uses_profile_cap_when_no_override() -> None:
    parent = SimpleNamespace(subagent_max_steps_enabled=True, subagent_max_steps=80)
    child = SimpleNamespace(max_steps=150)
    assert apply_subagent_step_policy(parent, child, requested=None) == 80
    assert child.max_steps == 80


def test_enabled_keeps_type_default_when_profile_cap_zero() -> None:
    parent = SimpleNamespace(subagent_max_steps_enabled=True, subagent_max_steps=0)
    child = SimpleNamespace(max_steps=150)
    assert apply_subagent_step_policy(parent, child, requested=None) == 150
    assert child.max_steps == 150


def test_explicit_zero_is_unlimited_when_limits_on() -> None:
    parent = SimpleNamespace(subagent_max_steps_enabled=True, subagent_max_steps=80)
    child = SimpleNamespace(max_steps=150)
    assert apply_subagent_step_policy(parent, child, requested=0) == 0
    assert child.max_steps == 0
