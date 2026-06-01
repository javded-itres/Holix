import pytest
import asyncio
from pathlib import Path
import tempfile
import shutil

from core.agent import HelixAgent
from core.memory.manager import MemoryManager
from core.skills.manager import SkillsManager
from core.tools.registry import ToolRegistry


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def temp_dir():
    """Create temporary directory for tests."""
    temp = tempfile.mkdtemp()
    yield temp
    shutil.rmtree(temp)


@pytest.fixture
async def memory_manager(temp_dir):
    """Create memory manager with temp database."""
    from config import settings
    original_db_path = settings.memory_db_path
    settings.memory_db_path = f"{temp_dir}/test_memory.db"
    settings.vector_db_path = f"{temp_dir}/test_vector_db"

    manager = MemoryManager()
    await manager.initialize_db()

    yield manager

    settings.memory_db_path = original_db_path


@pytest.fixture
def tools_registry():
    """Create tools registry."""
    registry = ToolRegistry()
    registry.register_all()
    return registry


@pytest.fixture
def skills_manager(temp_dir):
    """Create skills manager with temp directory."""
    from config import settings
    original_skills_dir = settings.skills_dir
    settings.skills_dir = f"{temp_dir}/skills"

    manager = SkillsManager()
    yield manager

    settings.skills_dir = original_skills_dir
