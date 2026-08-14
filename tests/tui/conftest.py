"""TUI pilot fixtures and markers."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config, items):
    for item in items:
        nodeid = item.nodeid
        if "tests/tui/" in nodeid or "tests\\tui\\" in nodeid or "/tui/" in nodeid:
            if not item.get_closest_marker("tui"):
                item.add_marker(pytest.mark.tui)
            # Full app launch is slower than pure unit
            if not item.get_closest_marker("integration"):
                item.add_marker(pytest.mark.integration)


@pytest.fixture
def mock_agent():
    from tests.tui.harness import make_mock_agent

    return make_mock_agent(reply="mock-assistant-reply")
