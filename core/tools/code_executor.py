import asyncio
import sys
import os
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from typing import Dict, Any
from core.tools.base import BaseTool


class PythonExecutorTool(BaseTool):
    """Tool for safely executing Python code in a restricted environment."""

    def __init__(self):
        super().__init__()
        self.name = "execute_python"
        self.description = "Execute Python code safely in a restricted environment. Returns stdout, stderr, and result. Use for calculations, data processing, testing code snippets."
        self.parameters = {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 10)",
                    "default": 10
                }
            },
            "required": ["code"]
        }

        # Whitelist of safe modules
        self.safe_modules = {
            'math', 'random', 'datetime', 'json', 'collections',
            're', 'itertools', 'functools', 'statistics', 'decimal',
            'fractions', 'string', 'textwrap', 'unicodedata',
        }

    async def execute(self, code: str, timeout: int = 10) -> str:
        """Execute Python code safely.

        Args:
            code: Python code to execute
            timeout: Maximum execution time

        Returns:
            Execution result
        """
        try:
            # Run in separate process for safety
            result = await asyncio.wait_for(
                self._run_code(code),
                timeout=timeout
            )
            return result

        except asyncio.TimeoutError:
            return f"Error: Code execution timed out after {timeout} seconds"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _run_code(self, code: str) -> str:
        """Run code in a restricted environment.

        Args:
            code: Python code

        Returns:
            Execution output
        """
        # Capture output
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        result_value = None

        # Create restricted globals
        safe_globals = {
            '__builtins__': {
                'print': print,
                'len': len,
                'range': range,
                'enumerate': enumerate,
                'zip': zip,
                'map': map,
                'filter': filter,
                'sum': sum,
                'min': min,
                'max': max,
                'abs': abs,
                'round': round,
                'sorted': sorted,
                'list': list,
                'dict': dict,
                'set': set,
                'tuple': tuple,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'type': type,
                'isinstance': isinstance,
                'any': any,
                'all': all,
            }
        }

        # Add safe modules
        for module in self.safe_modules:
            try:
                safe_globals[module] = __import__(module)
            except ImportError:
                pass

        try:
            # Redirect stdout and stderr
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                # Try to eval first (for expressions)
                try:
                    result_value = eval(code, safe_globals, {})
                except SyntaxError:
                    # If eval fails, use exec (for statements)
                    exec(code, safe_globals, {})

            stdout_text = stdout_capture.getvalue()
            stderr_text = stderr_capture.getvalue()

            # Format result
            output_parts = []

            if stdout_text:
                output_parts.append(f"STDOUT:\n{stdout_text}")

            if stderr_text:
                output_parts.append(f"STDERR:\n{stderr_text}")

            if result_value is not None:
                output_parts.append(f"RESULT: {repr(result_value)}")

            if not output_parts:
                return "Code executed successfully (no output)"

            return "\n\n".join(output_parts)

        except Exception as e:
            stderr_text = stderr_capture.getvalue()
            if stderr_text:
                return f"Error: {type(e).__name__}: {str(e)}\n\nSTDERR:\n{stderr_text}"
            return f"Error: {type(e).__name__}: {str(e)}"


class MathCalculatorTool(BaseTool):
    """Tool for mathematical calculations using Python's math module."""

    def __init__(self):
        super().__init__()
        self.name = "calculate"
        self.description = "Perform mathematical calculations. Supports basic arithmetic, trigonometry, logarithms, etc. Examples: '2+2', 'sqrt(16)', 'sin(pi/2)'"
        self.parameters = {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate"
                }
            },
            "required": ["expression"]
        }

    async def execute(self, expression: str) -> str:
        """Evaluate mathematical expression.

        Args:
            expression: Math expression

        Returns:
            Result or error
        """
        import math

        try:
            # Safe globals with math functions
            safe_globals = {
                '__builtins__': {},
                'abs': abs,
                'round': round,
                'min': min,
                'max': max,
                'sum': sum,
                'pow': pow,
                # Math module functions
                'sqrt': math.sqrt,
                'sin': math.sin,
                'cos': math.cos,
                'tan': math.tan,
                'asin': math.asin,
                'acos': math.acos,
                'atan': math.atan,
                'log': math.log,
                'log10': math.log10,
                'exp': math.exp,
                'pi': math.pi,
                'e': math.e,
                'ceil': math.ceil,
                'floor': math.floor,
                'factorial': math.factorial,
            }

            result = eval(expression, safe_globals, {})
            return f"Result: {result}"

        except Exception as e:
            return f"Error: {type(e).__name__}: {str(e)}"
