"""
SubAgent base types — configuration, results, and handles.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ProcessMode(StrEnum):
    """How a sub-agent should be executed."""
    ASYNC = "async"          # In-process asyncio.Task (default, I/O-bound)
    PROCESS = "process"      # Separate OS process (CPU-bound, isolation)
    THREAD = "thread"        # In-process thread (rarely needed)


class MemoryAccess(StrEnum):
    """How a sub-agent accesses the parent's memory."""
    SHARED = "shared"        # Read/write access to parent's LTM
    READONLY = "readonly"    # Read-only access to parent's LTM
    ISOLATED = "isolated"    # Own separate memory stores


class SubAgentStatus(StrEnum):
    """Status of a sub-agent."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass
class SubAgentConfig:
    """Configuration for a sub-agent.

    Defines what the sub-agent can do: which model to use,
    which tools, what system prompt, and how it runs.
    """

    name: str                                    # Unique name (e.g., "researcher")
    system_prompt: str = ""                      # Specialized system prompt
    model: str = ""                              # Model override (empty = inherit from parent)
    tools: list[str] = field(default_factory=list)  # Subset of tool names
    max_steps: int = 10                          # Max reasoning steps
    mode: str = "react"                          # Execution mode
    process_mode: ProcessMode = ProcessMode.ASYNC  # How to run
    timeout: float = 120.0                       # Timeout in seconds
    memory_access: MemoryAccess = MemoryAccess.SHARED  # Memory access level
    temperature: float = 0.7                     # LLM temperature
    description: str = ""                        # Human-readable description
    tags: list[str] = field(default_factory=list)  # Tags for categorization

    # MCP servers enabled for this sub-agent (by server name). Their tools must also
    # be listed in `tools` (or auto-included by runners) for the names to be usable.
    mcp_servers: list[str] = field(default_factory=list)

    def __post_init__(self):
        if isinstance(self.process_mode, str):
            self.process_mode = ProcessMode(self.process_mode)
        if isinstance(self.memory_access, str):
            self.memory_access = MemoryAccess(self.memory_access)


@dataclass
class SubAgentResult:
    """Result from a completed sub-agent execution.

    Contains the response, metadata about tool usage,
    and performance metrics.
    """

    name: str                                    # Sub-agent name
    success: bool                                 # Whether the task completed successfully
    response: str = ""                            # The sub-agent's final response
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # Tool calls made
    error: str | None = None                   # Error message if failed
    duration_ms: float = 0.0                      # Execution time in ms
    memory_used: int = 0                          # Approximate memory used (bytes)
    steps_taken: int = 0                          # Number of reasoning steps

    @property
    def status(self) -> SubAgentStatus:
        """Derive status from result data."""
        if self.error:
            if "timeout" in (self.error or "").lower():
                return SubAgentStatus.TIMED_OUT
            elif "cancel" in (self.error or "").lower():
                return SubAgentStatus.CANCELLED
            return SubAgentStatus.FAILED
        return SubAgentStatus.COMPLETED if self.success else SubAgentStatus.FAILED


@dataclass
class SubAgentHandle:
    """Handle to a running or completed sub-agent.

    Provides methods to check status, get results, and cancel.
    """

    name: str                                    # Sub-agent name
    config: SubAgentConfig = field(default_factory=SubAgentConfig)
    status: SubAgentStatus = SubAgentStatus.PENDING
    task: Any | None = None                   # asyncio.Task or multiprocessing.Process
    result: SubAgentResult | None = None
    started_at: float | None = None           # time.monotonic timestamp
    process_id: int | None = None             # OS PID for process-mode agents
    task_preview: str = ""                       # Short task description for UI
    agent_type: str = ""                         # Registry type (researcher, coder, …)
    done_event: Any = field(default=None, repr=False)  # asyncio.Event set on completion

    @property
    def is_running(self) -> bool:
        return self.status == SubAgentStatus.RUNNING

    @property
    def is_done(self) -> bool:
        return self.status in (
            SubAgentStatus.COMPLETED,
            SubAgentStatus.FAILED,
            SubAgentStatus.CANCELLED,
            SubAgentStatus.TIMED_OUT,
        )

    @property
    def elapsed_ms(self) -> float:
        """Milliseconds since start, or total duration if done."""
        import time
        if self.started_at is None:
            return 0.0
        if self.is_done and self.result:
            return self.result.duration_ms
        return (time.monotonic() - self.started_at) * 1000