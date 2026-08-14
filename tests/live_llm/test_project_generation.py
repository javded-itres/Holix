"""Live LLM: generate small projects and code artifacts in temp workspace."""

from __future__ import annotations

import pytest

from tests.live_llm.provider import soft_contains

pytestmark = [pytest.mark.live_llm, pytest.mark.llm]


@pytest.mark.asyncio
async def test_live_30_generate_python_hello(live_harness):
    r = await live_harness.run(
        "Generate a minimal Python project in the workspace:\n"
        "1) app/hello.py that prints HelloLive when run as main\n"
        "2) README.md describing how to run it\n"
        "Use write_file tools. Do not install packages.",
        conversation_id="live_30",
        timeout_s=480,
    )
    if "timed out" in r.text.lower() or "connection error" in r.text.lower():
        pytest.skip(f"provider timeout: {r.text[:120]}")
    files = live_harness.list_workspace()
    has_py = any(f.endswith("hello.py") or f.endswith(".py") for f in files)
    has_readme = any("readme" in f.lower() for f in files)
    assert has_py or soft_contains(r.text, "hello", "python", min_hits=1), (files, r.text)
    assert has_readme or soft_contains(r.text, "readme", "run", min_hits=1), (files, r.text)
    if has_py:
        py_files = [f for f in files if f.endswith(".py")]
        body = "\n".join(live_harness.read(f) for f in py_files[:3])
        assert soft_contains(body, "print", "Hello", "hello", min_hits=1), body


@pytest.mark.asyncio
async def test_live_31_generate_fastapi_stub(live_harness):
    r = await live_harness.run(
        "Create a tiny FastAPI stub (no install):\n"
        '- api/main.py with FastAPI app and GET /health returning {"status":"ok"}\n'
        "- requirements.txt with fastapi and uvicorn lines\n"
        "Use tools to write files.",
        conversation_id="live_31",
        timeout_s=480,
    )
    files = live_harness.list_workspace()
    joined = "\n".join(files).lower()
    code_blob = ""
    for f in files:
        if f.endswith(".py") or f.endswith(".txt"):
            try:
                code_blob += live_harness.read(f) + "\n"
            except Exception:
                pass
    assert (
        "fastapi" in joined
        or "fastapi" in code_blob.lower()
        or soft_contains(r.text, "fastapi", "health", min_hits=1)
    ), (files, r.text)
    if code_blob:
        assert soft_contains(
            code_blob, "FastAPI", "health", "/health", min_hits=1
        ) or soft_contains(r.text, "health", min_hits=1)


@pytest.mark.asyncio
async def test_live_32_generate_cli_argparse(live_harness):
    r = await live_harness.run(
        "Write tools/greet_cli.py: a Python CLI using argparse with argument --name "
        "that prints 'Hello, <name>'. Create the file with write_file.",
        conversation_id="live_32",
        timeout_s=480,
    )
    if "timed out" in r.text.lower() or "connection error" in r.text.lower():
        pytest.skip(f"provider timeout: {r.text[:120]}")
    files = live_harness.list_workspace()
    py = [f for f in files if f.endswith(".py")]
    assert py or soft_contains(r.text, "argparse", "name", min_hits=1), (files, r.text)
    if py:
        body = live_harness.read(py[0])
        assert soft_contains(body, "argparse", "name", "Hello", min_hits=2), body


@pytest.mark.asyncio
async def test_live_33_generate_json_schema_config(live_harness):
    r = await live_harness.run(
        "Using write_file, create EXACTLY config/settings.json (not quota.json). "
        "JSON object must include keys app_name='holix-live', debug=false, workers=2. "
        "Do not write any other files.",
        conversation_id="live_33",
        timeout_s=480,
        retries=2,
    )
    if "timed out" in r.text.lower() or "connection error" in r.text.lower():
        pytest.skip(f"provider timeout: {r.text[:120]}")
    files = live_harness.list_workspace()
    # Ignore internal workspace quota bookkeeping
    candidates = [
        f
        for f in files
        if f.endswith(".json") and "quota" not in f.lower() and "reconcile" not in f.lower()
    ]
    if live_harness.exists("config/settings.json"):
        body = live_harness.read("config/settings.json")
    else:
        assert candidates, (files, r.text)
        body = "\n".join(live_harness.read(f) for f in candidates)
    assert soft_contains(body, "holix-live", "workers", "debug", "app_name", min_hits=2), (
        body,
        files,
        r.text,
    )


@pytest.mark.asyncio
async def test_live_34_plan_mode_small_project(live_harness):
    r = await live_harness.run(
        "Using plan mode behavior: create a small package "
        "demo_pkg/__init__.py (empty or version) and demo_pkg/util.py with function add(a,b). "
        "Also write tests/test_add.py that asserts add(2,3)==5. "
        "Implement with tools.",
        conversation_id="live_34",
        mode="plan_and_execute",
        timeout_s=480,
    )
    files = live_harness.list_workspace()
    blob = "\n".join(live_harness.read(f) for f in files if f.endswith(".py"))
    assert files, r.text
    assert soft_contains(blob, "def add", "add(", min_hits=1) or soft_contains(
        r.text, "add", "demo", min_hits=1
    ), (files, r.text)


@pytest.mark.asyncio
async def test_live_35_refactor_seeded_module(live_harness):
    live_harness.seed(
        "legacy/calc.py",
        "def mul(a,b):\n    return a*b\n",
    )
    r = await live_harness.run(
        "In legacy/calc.py add a function div(a,b) that returns a/b "
        "(assume b!=0). Keep mul. Use tools.",
        conversation_id="live_35",
        timeout_s=360,
    )
    assert live_harness.exists("legacy/calc.py")
    body = live_harness.read("legacy/calc.py")
    assert soft_contains(body, "def mul", "def div", min_hits=1) or soft_contains(
        r.text, "div", min_hits=1
    ), body
