"""Interactive chat command for Helix CLI."""

import asyncio
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style
from pathlib import Path

from cli.core import ProfileConfig, get_profile_manager, switch_profile, HELIX_HOME
from cli.utils.banner import show_banner, show_welcome_message
from cli.utils.rich_console import (
    console, print_user_message, print_assistant_message,
    print_tool_call, print_error, print_info, print_success,
    create_spinner, print_table
)

# Import agent
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from core.agent import HelixAgent

# Prompt style
prompt_style = Style.from_dict({
    'prompt': '#00d7ff bold',  # Cyan
})


class ChatSession:
    """Interactive chat session with Helix."""

    def __init__(self, profile: str, config: ProfileConfig):
        """Initialize chat session.

        Args:
            profile: Profile name
            config: Profile configuration
        """
        self.profile = profile
        self.config = config
        self.agent: Optional[HelixAgent] = None
        self.conversation_id = f"cli_chat_{profile}"

        # Create prompt session with history
        history_file = HELIX_HOME / "logs" / f"history_{profile}.txt"
        history_file.parent.mkdir(parents=True, exist_ok=True)

        self.session = PromptSession(
            history=FileHistory(str(history_file)),
            auto_suggest=AutoSuggestFromHistory(),
            style=prompt_style
        )

    async def initialize_agent(self):
        """Initialize the Helix agent."""
        with console.status("[bold cyan]Initializing Helix...", spinner="dots"):
            # Update config
            import config as global_config
            from core.models.manager import ModelManager

            # Initialize model manager
            model_manager = ModelManager(self.config)

            # Get default model configuration
            try:
                model_config = model_manager.get_default_model_config()
                if model_config:
                    # Use provider configuration
                    global_config.settings.model = model_config.model
                    global_config.settings.base_url = model_config.base_url
                    global_config.settings.api_key = model_config.api_key
                    global_config.settings.temperature = model_config.temperature

                    # Display which provider is being used
                    console.print(f"[dim]Using provider: {model_config.provider}, model: {model_config.model}[/dim]")
                else:
                    # Fallback to legacy config
                    global_config.settings.model = self.config.model
                    global_config.settings.base_url = self.config.base_url
                    global_config.settings.api_key = self.config.api_key
                    global_config.settings.temperature = self.config.temperature
            except Exception as e:
                # Fallback to legacy config on error
                console.print(f"[dim yellow]Warning: Could not load provider config, using legacy settings[/dim yellow]")
                global_config.settings.model = self.config.model
                global_config.settings.base_url = self.config.base_url
                global_config.settings.api_key = self.config.api_key
                global_config.settings.temperature = self.config.temperature

            global_config.settings.max_steps = self.config.max_steps
            global_config.settings.data_dir = self.config.data_dir or "data"
            global_config.settings.memory_db_path = self.config.memory_db_path or "data/memory/memory.db"
            global_config.settings.vector_db_path = self.config.vector_db_path or "data/memory/vector_db"
            global_config.settings.skills_dir = self.config.skills_dir or "data/skills"

            # Create agent
            self.agent = HelixAgent()
            await self.agent.initialize()

    async def handle_special_command(self, command: str) -> bool:
        """Handle special slash commands.

        Args:
            command: Command string

        Returns:
            True if command was handled, False otherwise
        """
        cmd_lower = command.lower().strip()

        # /exit or /quit
        if cmd_lower in ["/exit", "/quit", "/q"]:
            print_info("Goodbye! 👋")
            return "exit"

        # /clear
        elif cmd_lower == "/clear":
            self.conversation_id = f"cli_chat_{self.profile}_{int(asyncio.get_event_loop().time())}"
            print_success("Conversation cleared")
            return True

        # /model
        elif cmd_lower.startswith("/model"):
            parts = command.split(maxsplit=1)
            if len(parts) == 2:
                self.config.model = parts[1]
                print_success(f"Switched to model: {parts[1]}")
                print_info("Reinitializing agent...")
                await self.initialize_agent()
            else:
                print_info(f"Current model: {self.config.model}")
            return True

        # /profile
        elif cmd_lower.startswith("/profile"):
            parts = command.split(maxsplit=1)
            if len(parts) == 2:
                new_profile = parts[1]
                manager = get_profile_manager()
                if manager.profile_exists(new_profile):
                    self.config = switch_profile(new_profile)
                    self.profile = new_profile
                    self.conversation_id = f"cli_chat_{new_profile}"
                    print_success(f"Switched to profile: {new_profile}")
                    print_info("Reinitializing agent...")
                    await self.initialize_agent()
                else:
                    print_error(f"Profile '{new_profile}' does not exist")
            else:
                manager = get_profile_manager()
                profiles = manager.list_profiles()
                rows = [[p, "✓" if p == self.profile else ""] for p in profiles]
                print_table("Available Profiles", ["Profile", "Active"], rows)
            return True

        # /skills
        elif cmd_lower == "/skills":
            if self.agent:
                skills = self.agent.get_skills()
                if skills:
                    rows = [[name, s.get("description", "")[:50]] for name, s in list(skills.items())[:10]]
                    print_table(f"Active Skills ({len(skills)} total)", ["Skill", "Description"], rows)
                else:
                    print_info("No skills available yet")
            return True

        # /memory
        elif cmd_lower.startswith("/memory"):
            parts = command.split(maxsplit=1)
            if len(parts) == 2 and self.agent:
                query = parts[1]
                with create_spinner() as progress:
                    task = progress.add_task("Searching memory...", total=None)
                    results = await self.agent.search_memory(query, top_k=5)
                    progress.remove_task(task)

                if results:
                    console.print("\n[cyan]Memory Search Results:[/cyan]\n")
                    for i, result in enumerate(results, 1):
                        content = result.get("content", "")[:100]
                        console.print(f"{i}. {content}...")
                    console.print()
                else:
                    print_info("No results found")
            else:
                print_error("Usage: /memory <query>")
            return True

        # /help
        elif cmd_lower == "/help":
            show_welcome_message(console)
            return True

        # /status
        elif cmd_lower == "/status":
            console.print(f"\n[cyan]Current Status:[/cyan]")
            console.print(f"  Profile: {self.profile}")
            console.print(f"  Model: {self.config.model}")
            console.print(f"  Temperature: {self.config.temperature}")
            console.print(f"  Conversation ID: {self.conversation_id}\n")
            return True

        return False

    async def chat_loop(self):
        """Main interactive chat loop."""
        show_banner(console, self.profile)
        show_welcome_message(console)

        # Initialize agent
        await self.initialize_agent()

        # Main loop
        while True:
            try:
                # Get user input
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.session.prompt([
                        ('class:prompt', '❯ '),
                    ])
                )

                if not user_input.strip():
                    continue

                # Handle special commands
                if user_input.startswith('/'):
                    result = await self.handle_special_command(user_input)
                    if result == "exit":
                        break
                    continue

                # Print user message
                print_user_message(user_input)

                # Run agent with spinner
                with create_spinner() as progress:
                    task = progress.add_task("Helix is thinking...", total=None)

                    try:
                        response = await self.agent.run(
                            user_input=user_input,
                            conversation_id=self.conversation_id
                        )
                    finally:
                        progress.remove_task(task)

                # Print assistant response
                print_assistant_message(response, markdown=True)

            except KeyboardInterrupt:
                console.print("\n")
                confirm = input("Exit chat? (y/n): ")
                if confirm.lower() == 'y':
                    print_info("Goodbye! 👋")
                    break
                console.print()
                continue

            except EOFError:
                print_info("\nGoodbye! 👋")
                break

            except Exception as e:
                print_error(f"Unexpected error: {e}")
                if self.config.__dict__.get("verbose"):
                    import traceback
                    console.print_exception()


async def run_interactive_chat(profile: str, config: ProfileConfig):
    """Run interactive chat session.

    Args:
        profile: Profile name
        config: Profile configuration
    """
    session = ChatSession(profile, config)
    await session.chat_loop()
