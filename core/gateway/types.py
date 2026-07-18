"""Typed gateway DI tokens."""

from __future__ import annotations

from typing import NewType

# Dishka-injected host profile name (HOLIX_PROFILE / gateway process profile).
HostProfileName = NewType("HostProfileName", str)
