"""Live LLM end-to-end scenarios (real provider calls).

Run only via::

    ./scripts/test_live_llm.sh
    # or
    uv run python -m pytest tests/live_llm -m live_llm

Requires a reachable OpenAI-compatible endpoint (see ``tests/live_llm/README.md``).
"""
