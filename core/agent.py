from openai import AsyncOpenAI

from config import settings
from core.memory.manager import MemoryManager
from core.skills.manager import SkillsManager
from core.tools.registry import ToolRegistry
from core.loop import AgentLoop


class HelixAgent:
    """Main Helix Agent - A self-improving AI agent with memory and skills."""

    def __init__(self):
        """Initialize the Helix agent."""
        # LLM Client
        self.client = AsyncOpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key
        )
        self.model = settings.model

        # Core components
        self.memory = MemoryManager()
        self.skills = SkillsManager()
        self.tools = ToolRegistry()
        self.loop = AgentLoop(self)

        # Initialize
        self._initialized = False

    async def initialize(self):
        """Initialize the agent (async setup)."""
        if self._initialized:
            return

        print("Initializing Helix Agent...")

        # Initialize memory database
        await self.memory.initialize_db()

        # Register tools
        self.tools.register_all()
        print(f"Registered {len(self.tools.tools)} tools: {', '.join(self.tools.get_tool_names())}")

        # Load skills
        self.skills.load_all_skills()
        print(f"Loaded {len(self.skills.all_skills)} skills")

        self._initialized = True
        print("Helix Agent ready!\n")

    async def run(
        self,
        user_input: str,
        conversation_id: str = "default"
    ) -> str:
        """Run the agent with user input.

        Args:
            user_input: User's input message
            conversation_id: Optional conversation ID for multi-turn conversations

        Returns:
            Agent's response
        """
        if not self._initialized:
            await self.initialize()

        return await self.loop.run_conversation(user_input, conversation_id)

    async def get_conversation_history(
        self,
        conversation_id: str = "default",
        limit: int = 30
    ) -> list:
        """Get conversation history.

        Args:
            conversation_id: Conversation ID
            limit: Maximum number of messages

        Returns:
            List of messages
        """
        return await self.memory.get_conversation(conversation_id, limit)

    async def search_memory(
        self,
        query: str,
        top_k: int = 5
    ) -> list:
        """Search through memory using semantic search.

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            List of relevant memories
        """
        return await self.memory.search(query, top_k)

    def get_skills(self) -> dict:
        """Get all loaded skills.

        Returns:
            Dictionary of skills
        """
        return self.skills.all_skills

    def get_tools(self) -> list:
        """Get all registered tools.

        Returns:
            List of tool names
        """
        return self.tools.get_tool_names()
