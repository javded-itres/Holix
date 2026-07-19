import os
import tempfile

import pytest
from core.project.holix_md import HOLIX_MD_FILENAME
from core.tools.code_executor import MathCalculatorTool
from core.tools.file_ops import ListDirectoryTool, PatchFileTool, ReadFileTool, WriteFileTool


@pytest.mark.asyncio
async def test_read_file_rejects_binary_image_with_helpful_message(tmp_path):
    read_tool = ReadFileTool()
    image = tmp_path / "scan.jpg"
    image.write_bytes(b"\xff\xd8\xff\xe0binary")

    result = await read_tool.execute(str(image))
    assert "binary image" in result
    assert "vision description" in result
    assert "re-upload" in result


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
        assert "Created" in result or "Updated" in result

        # Read file
        result = await read_tool.execute(test_file)
        assert content in result


@pytest.mark.asyncio
async def test_patch_file_applies_replacements(tmp_path):
    patch_tool = PatchFileTool()
    read_tool = ReadFileTool()
    target = tmp_path / "notes.md"
    target.write_text("# Doc\n- Purpose:\n- Stack:\n", encoding="utf-8")

    result = await patch_tool.execute(
        str(target),
        replacements=[
            {"old_string": "- Purpose:", "new_string": "- Purpose: Demo project"},
            {"old_string": "- Stack:", "new_string": "- Stack: Python"},
        ],
    )
    assert "2 replacement" in result

    content = await read_tool.execute(str(target))
    assert "Demo project" in content
    assert "Python" in content


@pytest.mark.asyncio
async def test_write_file_rejects_oversized_holix_md(tmp_path):
    write_tool = WriteFileTool()
    holix = tmp_path / ".holix" / HOLIX_MD_FILENAME
    holix.parent.mkdir(parents=True, exist_ok=True)
    holix.write_text("# skeleton\n", encoding="utf-8")

    result = await write_tool.execute(str(holix), "x" * 7000)
    assert "patch_file" in result
    assert holix.read_text(encoding="utf-8") == "# skeleton\n"


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
