"""
Agent Communication Bus — message passing between the main agent and sub-agents.

Supports two modes:
- Async (in-process): asyncio.Queue for fast, zero-overhead communication
- Process (OS process): multiprocessing.Queue with pickle serialization
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import pickle
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass
class AgentMessage:
    """Message exchanged between agents.

    Supports task assignment, result delivery, queries,
    cancellation, and heartbeat monitoring.
    """

    from_agent: str          # Sender name ("main" or sub-agent name)
    to_agent: str            # Recipient name
    msg_type: str            # "task" | "result" | "query" | "response" | "cancel" | "heartbeat" | "error"
    content: str = ""        # Message content
    metadata: dict[str, Any] = field(default_factory=dict)  # Additional data
    timestamp: float = field(default_factory=time.time)  # Unix timestamp
    message_id: str = ""     # Optional unique ID for request-response correlation

    def serialize(self) -> bytes:
        """Serialize for IPC via multiprocessing.Queue."""
        return pickle.dumps(self)

    @classmethod
    def deserialize(cls, data: bytes) -> AgentMessage:
        """Deserialize from IPC data."""
        return pickle.loads(data)


class MessageHandler(Protocol):
    """Protocol for message handlers."""
    async def __call__(self, message: AgentMessage) -> None: ...


class AsyncCommunicationBus:
    """Async communication bus for in-process sub-agents.

    Uses asyncio.Queue for fast, zero-overhead message passing.
    Each agent gets its own queue, enabling targeted messaging
    and broadcast.
    """

    def __init__(self):
        self._queues: dict[str, asyncio.Queue] = {}
        self._handlers: dict[str, list[Callable]] = {}
        self._lock = asyncio.Lock()

    async def register(self, agent_name: str) -> None:
        """Register an agent with the bus, creating its queue.

        Args:
            agent_name: Unique agent name.
        """
        async with self._lock:
            if agent_name not in self._queues:
                self._queues[agent_name] = asyncio.Queue()

    async def unregister(self, agent_name: str) -> None:
        """Unregister an agent from the bus.

        Args:
            agent_name: Agent name to remove.
        """
        async with self._lock:
            self._queues.pop(agent_name, None)
            self._handlers.pop(agent_name, None)

    async def send(self, message: AgentMessage) -> None:
        """Send a message to a specific agent.

        Args:
            message: The message to send.
        """
        async with self._lock:
            queue = self._queues.get(message.to_agent)
            if queue is None:
                logger.warning(f"No queue for agent '{message.to_agent}'")
                return
            await queue.put(message)

        # Notify handlers
        handlers = self._handlers.get(message.to_agent, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                logger.warning(f"Handler error for {message.to_agent}: {e}")

    async def receive(
        self,
        agent_name: str,
        timeout: float = 0.1,
    ) -> AgentMessage | None:
        """Receive a message for a specific agent.

        Args:
            agent_name: Agent name to receive for.
            timeout: Max wait time in seconds.

        Returns:
            AgentMessage or None if timeout.
        """
        async with self._lock:
            queue = self._queues.get(agent_name)

        if queue is None:
            return None

        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except TimeoutError:
            return None

    async def broadcast(self, message: AgentMessage) -> None:
        """Broadcast a message to all registered agents.

        Args:
            message: Message to broadcast (to_agent is ignored).
        """
        async with self._lock:
            for agent_name, queue in self._queues.items():
                if agent_name != message.from_agent:  # Don't send to self
                    msg = AgentMessage(
                        from_agent=message.from_agent,
                        to_agent=agent_name,
                        msg_type=message.msg_type,
                        content=message.content,
                        metadata=message.metadata,
                    )
                    await queue.put(msg)

    async def subscribe(
        self,
        agent_name: str,
        handler: Callable,
    ) -> None:
        """Subscribe a handler for an agent's messages.

        Args:
            agent_name: Agent name.
            handler: Callback function.
        """
        async with self._lock:
            if agent_name not in self._handlers:
                self._handlers[agent_name] = []
            self._handlers[agent_name].append(handler)

    @property
    def registered_agents(self) -> list[str]:
        """List of registered agent names."""
        return list(self._queues.keys())


class ProcessCommunicationBus:
    """Communication bus for process-mode sub-agents.

    Uses multiprocessing.Queue for IPC with pickle serialization.
    Thread-safe for cross-process communication.
    """

    def __init__(self):
        self._input_queues: dict[str, multiprocessing.Queue] = {}
        self._output_queues: dict[str, multiprocessing.Queue] = {}

    def register(self, agent_name: str) -> None:
        """Register an agent with input/output queues.

        Args:
            agent_name: Unique agent name.
        """
        self._input_queues[agent_name] = multiprocessing.Queue()
        self._output_queues[agent_name] = multiprocessing.Queue()

    def unregister(self, agent_name: str) -> None:
        """Unregister an agent."""
        self._input_queues.pop(agent_name, None)
        self._output_queues.pop(agent_name, None)

    def send_to_sub_agent(self, message: AgentMessage) -> None:
        """Send a message from main agent to a sub-agent process.

        Args:
            message: Message to send.
        """
        queue = self._input_queues.get(message.to_agent)
        if queue is None:
            logger.warning(f"No input queue for sub-agent '{message.to_agent}'")
            return
        queue.put(message.serialize())

    def receive_from_sub_agent(
        self,
        agent_name: str,
        timeout: float = 0.1,
    ) -> AgentMessage | None:
        """Receive a message from a sub-agent process.

        Args:
            agent_name: Sub-agent name.
            timeout: Max wait time in seconds.

        Returns:
            AgentMessage or None.
        """
        queue = self._output_queues.get(agent_name)
        if queue is None:
            return None
        try:
            data = queue.get(timeout=timeout)
            return AgentMessage.deserialize(data)
        except Exception:
            return None

    def send_to_main(self, message: AgentMessage) -> None:
        """Send a message from a sub-agent to the main agent.

        Args:
            message: Message to send (to_agent should be "main").
        """
        queue = self._output_queues.get(message.from_agent)
        if queue is None:
            logger.warning(f"No output queue for sub-agent '{message.from_agent}'")
            return
        queue.put(message.serialize())

    def receive_from_main(
        self,
        agent_name: str,
        timeout: float = 0.1,
    ) -> AgentMessage | None:
        """Receive a message from the main agent (in sub-agent process).

        Args:
            agent_name: This sub-agent's name.
            timeout: Max wait time in seconds.

        Returns:
            AgentMessage or None.
        """
        queue = self._input_queues.get(agent_name)
        if queue is None:
            return None
        try:
            data = queue.get(timeout=timeout)
            return AgentMessage.deserialize(data)
        except Exception:
            return None

    def get_input_queue(self, agent_name: str) -> multiprocessing.Queue | None:
        """Get the raw input queue for a sub-agent (for subprocess init)."""
        return self._input_queues.get(agent_name)

    def get_output_queue(self, agent_name: str) -> multiprocessing.Queue | None:
        """Get the raw output queue for a sub-agent (for subprocess init)."""
        return self._output_queues.get(agent_name)

    @property
    def registered_agents(self) -> list[str]:
        """List of registered agent names."""
        return list(self._input_queues.keys())


class AgentCommunicationBus:
    """Unified communication bus supporting both async and process modes.

    Automatically routes messages through the appropriate channel
    based on the sub-agent's process_mode.
    """

    def __init__(self):
        self.async_bus = AsyncCommunicationBus()
        self.process_bus = ProcessCommunicationBus()

    def register(self, agent_name: str, process_mode: str = "async") -> None:
        """Register an agent with the appropriate bus.

        Args:
            agent_name: Unique agent name.
            process_mode: "async" or "process".
        """
        if process_mode == "process":
            self.process_bus.register(agent_name)
        else:
            # Async registration must be done in an async context
            # We'll store it for later async registration
            if not hasattr(self, "_pending_async_registrations"):
                self._pending_async_registrations = []
            self._pending_async_registrations.append(agent_name)

    async def register_async(self, agent_name: str) -> None:
        """Async registration for in-process agents."""
        await self.async_bus.register(agent_name)

    async def unregister(self, agent_name: str, process_mode: str = "async") -> None:
        """Unregister an agent."""
        if process_mode == "process":
            self.process_bus.unregister(agent_name)
        else:
            await self.async_bus.unregister(agent_name)

    async def send(self, message: AgentMessage, process_mode: str = "async") -> None:
        """Send a message through the appropriate bus.

        Args:
            message: The message to send.
            process_mode: Which bus to use.
        """
        if process_mode == "process":
            self.process_bus.send_to_sub_agent(message)
        else:
            await self.async_bus.send(message)

    async def receive(
        self,
        agent_name: str,
        process_mode: str = "async",
        timeout: float = 0.1,
    ) -> AgentMessage | None:
        """Receive a message for an agent.

        Args:
            agent_name: Agent name.
            process_mode: Which bus to use.
            timeout: Max wait time.

        Returns:
            AgentMessage or None.
        """
        if process_mode == "process":
            return self.process_bus.receive_from_sub_agent(agent_name, timeout)
        else:
            return await self.async_bus.receive(agent_name, timeout)

    async def broadcast(self, message: AgentMessage) -> None:
        """Broadcast to all async agents."""
        await self.async_bus.broadcast(message)