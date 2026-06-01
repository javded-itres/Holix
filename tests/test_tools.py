import pytest
from core.tools.file_ops import ReadFileTool, WriteFileTool, ListDirectoryTool
from core.tools.code_executor import MathCalculatorTool
import tempfile
import os


@pytest.mark.asyncio
async def test_write_and_read_file():
    """Test writing and reading files."""
    write_tool = WriteFileTool()
    read_tool = ReadFileTool()

    with tempfile.TemporaryDirectory() as temp_dir:
        test_file = os.path.join(temp_dir, "test.txt")
        content = "Hello, World!"

        # Write file
        result = await write_tool.execute(test_file, content)
        assert "Successfully wrote" in result

        # Read file
        result = await read_tool.execute(test_file)
        assert content in result


@pytest.mark.asyncio
async def test_list_directory():
    """Test listing directory contents."""
    list_tool = ListDirectoryTool()

    with tempfile.TemporaryDirectory() as temp_dir:
        # Create some files
        open(os.path.join(temp_dir, "file1.txt"), 'w').close()
        open(os.path.join(temp_dir, "file2.txt"), 'w').close()
        os.mkdir(os.path.join(temp_dir, "subdir"))

        result = await list_tool.execute(temp_dir)
        assert "file1.txt" in result
        assert "file2.txt" in result
        assert "subdir" in result


@pytest.mark.asyncio
async def test_math_calculator():
    """Test math calculator tool."""
    calc = MathCalculatorTool()

    # Simple math
    result = await calc.execute("2 + 2")
    assert "4" in result

    # With functions
    result = await calc.execute("sqrt(16)")
    assert "4" in result

    # Pi
    result = await calc.execute("pi")
    assert "3.14" in result
