"""Restricted Python executor (execute_python)."""

from __future__ import annotations

import pytest
from core.tools.code_executor import MathCalculatorTool, PythonExecutorTool


@pytest.mark.asyncio
async def test_execute_python_print_and_math() -> None:
    tool = PythonExecutorTool()
    out = await tool.execute("print(2 + 2)\nprint(math.sqrt(16))")
    assert "STDOUT" in out
    assert "4" in out
    assert "4.0" in out


@pytest.mark.asyncio
async def test_execute_python_import_allowed_module() -> None:
    tool = PythonExecutorTool()
    out = await tool.execute("import math\nprint(math.pi)")
    assert "Error" not in out
    assert "3.14" in out


@pytest.mark.asyncio
async def test_execute_python_import_os_blocked() -> None:
    tool = PythonExecutorTool()
    out = await tool.execute("import os\nprint(os.listdir('.'))")
    assert "Error" in out
    assert "not allowed" in out.lower() or "ImportError" in out


@pytest.mark.asyncio
async def test_execute_python_import_subprocess_blocked() -> None:
    tool = PythonExecutorTool()
    out = await tool.execute("import subprocess\nsubprocess.run(['echo','x'])")
    assert "Error" in out
    assert "ImportError" in out or "not allowed" in out.lower()


@pytest.mark.asyncio
async def test_execute_python_try_except() -> None:
    tool = PythonExecutorTool()
    out = await tool.execute(
        "try:\n    1/0\nexcept ZeroDivisionError as e:\n    print(type(e).__name__)"
    )
    assert "ZeroDivisionError" in out
    assert "Error: " not in out.split("STDOUT")[0] if "STDOUT" in out else "ZeroDivisionError" in out


@pytest.mark.asyncio
async def test_execute_python_expression_result() -> None:
    tool = PythonExecutorTool()
    out = await tool.execute("sum([1, 2, 3])")
    assert "RESULT: 6" in out


@pytest.mark.asyncio
async def test_calculate_basic() -> None:
    tool = MathCalculatorTool()
    out = await tool.execute("2+2")
    assert "Result: 4" in out


@pytest.mark.asyncio
async def test_execute_python_timeout_kills_subprocess() -> None:
    """CPU-bound infinite loop must not hang forever (subprocess kill)."""
    tool = PythonExecutorTool()
    out = await tool.execute("while True:\n    pass", timeout=1)
    assert "timed out" in out.lower()


@pytest.mark.asyncio
async def test_permission_checker_execute_required_semantics() -> None:
    """Document hermes create_run gate: read-only is not enough (audit #4)."""
    from core.security.permissions import PermissionChecker

    assert not PermissionChecker(["read"]).can_execute()
    assert PermissionChecker(["read", "execute"]).can_execute()
    assert PermissionChecker(["execute"]).can_execute()
