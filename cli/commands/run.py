"""Single query execution command."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from cli.core import ProfileConfig
from cli.utils.rich_console import print_user_message, print_assistant_message, print_error, create_spinner
from core.agent import HelixAgent


async def run_single_query(query: str, conversation_id: str, config: ProfileConfig):
    """Execute a single query and exit.

    Args:
        query: Query to execute
        conversation_id: Conversation ID
        config: Profile configuration
    """
    # Update global config
    import config as global_config
    from core.models.manager import ModelManager

    # Initialize model manager
    model_manager = ModelManager(config)

    # Get default model configuration
    try:
        model_config = model_manager.get_default_model_config()
        if model_config:
            # Use provider configuration
            global_config.settings.model = model_config.model
            global_config.settings.base_url = model_config.base_url
            global_config.settings.api_key = model_config.api_key
            global_config.settings.temperature = model_config.temperature
        else:
            # Fallback to legacy config
            global_config.settings.model = config.model
            global_config.settings.base_url = config.base_url
            global_config.settings.api_key = config.api_key
            global_config.settings.temperature = config.temperature
    except Exception:
        # Fallback to legacy config on error
        global_config.settings.model = config.model
        global_config.settings.base_url = config.base_url
        global_config.settings.api_key = config.api_key
        global_config.settings.temperature = config.temperature

    global_config.settings.max_steps = config.max_steps
    global_config.settings.data_dir = config.data_dir or "data"
    global_config.settings.memory_db_path = config.memory_db_path or "data/memory/memory.db"
    global_config.settings.vector_db_path = config.vector_db_path or "data/memory/vector_db"
    global_config.settings.skills_dir = config.skills_dir or "data/skills"

    # Initialize agent
    with create_spinner() as progress:
        task = progress.add_task("Initializing Helix...", total=None)
        agent = HelixAgent()
        await agent.initialize()
        progress.remove_task(task)

    # Print query
    print_user_message(query)

    # Run query
    with create_spinner() as progress:
        task = progress.add_task("Helix is thinking...", total=None)
        try:
            response = await agent.run(user_input=query, conversation_id=conversation_id)
        except Exception as e:
            progress.remove_task(task)
            print_error(f"Error: {e}")
            return
        finally:
            if task in progress.task_ids:
                progress.remove_task(task)

    # Print response
    print_assistant_message(response, markdown=True)
