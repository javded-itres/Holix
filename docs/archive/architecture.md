# Helix Architecture: LangGraph + Long-term Memory + Subagents

> **Version**: 0.2.0 (feature/subagents branch)  
> **Date**: June 2026  
> **Status**: All 6 phases implemented

---

## Overview

Helix has been upgraded from a monolithic while-loop agent to a **graph-based, self-evolving AI system** with:

- **LangGraph** execution engine with 3 modes (ReAct, Plan-and-Execute, Hybrid)
- **4 types of Long-term Memory** (Episodic, Semantic, Procedural, Strategic)
- **Subagents** running in-process (async) or as separate OS processes
- **Meta-Agent** for strategic analysis and quality assessment
- **Self-Refinement Loop** that iteratively improves responses
- **Evolution Engine** that learns from every task outcome

All new features are **feature-flagged** and **backward-compatible**.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        HelixAgent                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │  Memory  │  │  Skills  │  │  Tools   │  │  Events  │ │
│  │  (LTM)   │  │ (Proced.)│  │ (BaseTool)│  │  (Bus)   │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
│       │              │              │              │        │
│  ┌────┴──────────────┴──────────────┴──────────────┴─────┐ │
│  │                  LangGraph StateGraph                    │ │
│  │                                                          │ │
│  │  ┌──────────┐   ┌──────────┐   ┌──────────┐          │ │
│  │  │  Memory  │──▶│   ReAct  │──▶│   Final  │──▶ END  │ │
│  │  │ Retrieval │   │   Node   │   │   Node   │          │ │
│  │  └──────────┘   └────┬─────┘   └──────────┘          │ │
│  │                        │                                 │ │
│  │                   ┌────┴────┐                           │ │
│  │                   │  Route  │                           │ │
│  │                   └────┬────┘                           │ │
│  │                   tool │ final                           │ │
│  │                   ┌────┴─────┐                           │ │
│  │                   │  Tool    │──▶ back to ReAct          │ │
│  │                   │ Execution│                           │ │
│  │                   └──────────┘                           │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Meta-Agent  │  │ SubAgentMgr  │  │  Self-Refinement │  │
│  │  (advisory)  │  │ (async/proc) │  │     Loop         │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  Evolution Engine                        │  │
│  │  Task → Execute → Assess → Record → Learn → Repeat   │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Long-term Memory System

### Four Memory Types

| Type | Purpose | Storage | Key Methods |
|------|---------|---------|-------------|
| **Episodic** | Narrative summaries of past conversations | SQLite + ChromaDB `ltm_episodic` | `store_episode()`, `search()`, `auto_summarize_conversation()` |
| **Semantic** | Facts and knowledge (key-value) | SQLite + ChromaDB `ltm_semantic` | `store_fact()`, `get_fact()`, `search()` |
| **Procedural** | Skills + outcome history | SQLite + existing SkillsManager ChromaDB | `search()`, `record_skill_outcome()`, `get_skill_recommendations()` |
| **Strategic** | Preferences, patterns, heuristics | SQLite + ChromaDB `ltm_strategic` | `store_strategy()`, `search()`, `get_all_strategies()`, `format_strategies_for_prompt()` |

### Unified API

```python
from core.memory.manager import LongTermMemoryManager

memory = LongTermMemoryManager()
await memory.initialize_db()

# Legacy API (backward-compatible)
await memory.save_message(conv_id, "user", "Hello")
msgs = await memory.get_conversation(conv_id)

# New typed memory APIs
await memory.store_fact("project_language", "Python 3.14+", source="config")
await memory.store_strategy("user_prefers_async", "Always use async for I/O", category="user_preference")

# Unified context retrieval (searches all 4 types)
context = await memory.get_relevant_context("FastAPI routing", top_k=5)
# Returns: {"episodic": [...], "semantic": [...], "strategic": [...]}

# Auto-episodic summarization
await memory.auto_summarize_conversation(conv_id, messages, llm_client=client)
```

### Feature Flags

```python
# config.py
enable_long_term_memory: bool = True      # Core — ON by default
auto_summarize_conversations: bool = True   # Auto-create episodic entries
```

---

## LangGraph Execution Engine

### Three Execution Modes

| Mode | Description | Best For |
|------|-------------|----------|
| **ReAct** | Interactive reasoning with tool calls in a loop | Single-step queries, tool usage, quick lookups |
| **Plan-and-Execute** | Decomposes task into sub-steps, executes sequentially | Multi-step tasks with clear subgoals |
| **Hybrid** | Plans first, then ReAct per step | Complex tasks requiring planning + flexible execution |
| **Auto** | ModeRouter uses LLM to select the best mode | Default when you want the system to decide |

### Graph Structure

**ReAct** (default):
```
START → memory_retrieval → react → [conditional]
  → tool_calls → tool_execution → react (loop)
  → is_final / max_steps → finalize → END
```

**Plan-and-Execute**:
```
START → memory_retrieval → plan → execute_step → [conditional]
  → more steps → execute_step (loop)
  → all done → finalize → END
```

**Hybrid**:
```
START → memory_retrieval → plan → react → [conditional]
  → tool_calls → tool_execution → react (loop within step)
  → is_final step → next step? → react (next step loop)
  → all steps done → finalize → END
```

### Usage

```python
from core.graph.builder import build_helix_graph, run_graph_loop
from langgraph.checkpoint.memory import InMemorySaver

# Build graph (mode is configurable)
graph = build_helix_graph(agent=my_agent, execution_mode="react")

# Run the graph
async for event in run_graph_loop(agent, "Hello!", "conv_1", stream=False):
    agent.emit(event)  # Emits AgentEvent objects

# Auto mode selection
from core.graph.modes.router import ModeRouter
router = ModeRouter(client=agent.client)
mode = await router.select_mode("Refactor the auth module and add tests")
# Returns: "plan_and_execute"
```

### Feature Flags

```python
# config.py
use_langgraph: bool = True                # Core — ON by default
execution_mode: str = "react"              # "react" | "plan_and_execute" | "hybrid" | "auto"
langgraph_checkpoint_db_path: str = "data/memory/checkpoints.db"
```

---

## Subagents System

### Architecture

```
┌──────────────────────────────────────────────┐
│            HelixAgent (main process)          │
│  ┌────────────────────────────────────────┐  │
│  │          SubAgentManager                │  │
│  │  ┌───────────────┐  ┌────────────────┐│  │
│  │  │ Async Runner  │  │ Process Runner ││  │
│  │  │  (in-process) │  │ (OS process)   ││  │
│  │  └───────────────┘  └────────┬───────┘│  │
│  └─────────────────────────────┬──┘        │
│                                 │ IPC       │
│  ┌──────────────────────────────┘           │
│  │ multiprocessing.Queue / asyncio.Queue   │
│  └──────────────────────────────────────────┘
│                                              │
│  ┌─────────────────┐  ┌─────────────────┐   │
│  │  SubAgent (as)  │  │ SubAgent (proc) │   │
│  │  - researcher   │  │ - coder         │   │
│  │  - own tools    │  │ - own LLM       │   │
│  │  - heartbeat    │  │ - heartbeat      │   │
│  └─────────────────┘  └─────────────────┘   │
└──────────────────────────────────────────────┘
```

### Predefined Sub-Agent Types

| Type | System Prompt Focus | Tools | Description |
|------|---------------------|-------|-------------|
| `researcher` | Deep analysis, information gathering | web_search, web_fetch, read_file | Research specialist |
| `coder` | Code generation, editing, debugging | read_file, write_file, terminal, code_executor | Code specialist |
| `analyst` | Data analysis, SQL, calculations | sql_query, sql_schema, code_executor, math_calculator | Data specialist |
| `reviewer` | Code review, quality assessment | read_file, list_directory, terminal | Review specialist |
| `writer` | Documentation, content creation | read_file, write_file, list_directory | Writing specialist |

### Usage

```python
from core.subagents.manager import SubAgentManager
from core.subagents.registry import get_subagent_config

manager = SubAgentManager(agent)

# Spawn an async sub-agent (in-process)
config = get_subagent_config("researcher")
handle = await manager.spawn_sub_agent(config, task="Research FastAPI best practices")
result = await manager.wait_for("researcher", timeout=60)
print(result.response)

# Spawn a process sub-agent (OS process, isolated)
from core.subagents.base import SubAgentConfig, ProcessMode
config = SubAgentConfig(
    name="heavy_coder",
    system_prompt="You are a code generation specialist...",
    tools=["read_file", "write_file", "terminal"],
    process_mode=ProcessMode.PROCESS,  # OS process
    timeout=180.0,
)
handle = await manager.spawn_sub_agent(config, task="Implement authentication module")
result = await manager.wait_for("heavy_coder", timeout=200)

# Terminate all running sub-agents
await manager.terminate_all()
```

### Process Modes

| Mode | Startup | Memory | Crash Safety | Best For |
|------|---------|--------|-------------|----------|
| `async` | Zero overhead | Shared (same process) | N/A | LLM calls (I/O-bound) |
| `process` | ~200-500ms | Isolated (separate SQLite) | Sub-agent crash doesn't kill main | CPU-bound, risky ops |
| `thread` | Zero overhead | Shared | N/A | Reserved (not commonly used) |

### Feature Flags

```python
# config.py
enable_subagents: bool = False                    # Advanced — OFF by default
subagent_default_process_mode: str = "async"      # "async" | "process"
subagent_max_concurrent: int = 4                 # Max parallel sub-agents
subagent_process_timeout: float = 120.0          # Timeout for subprocess sub-agents
subagent_heartbeat_interval: float = 5.0          # Heartbeat interval in seconds
```

---

## Meta-Agent

The Meta-Agent is a **lightweight advisory layer** that runs at two points in the graph:

1. **Pre-thinking** (after memory retrieval): Reviews context and suggests execution mode changes
2. **Post-completion** (after finalize): Evaluates response quality for self-refinement

```python
from core.meta_agent import MetaAgent, MetaDecision, QualityAssessment

meta = MetaAgent(client=agent.client, model=agent.model)

# Pre-thinking: analyze task
decision = await meta.analyze_task(
    user_input="Refactor the auth module",
    context={"execution_mode": "react", "step_count": 0},
    memories={"episodic": [...], "semantic": [...], "strategic": [...]},
)
# decision.suggested_mode = "plan_and_execute"
# decision.confidence = 0.85

# Post-completion: evaluate response
assessment = await meta.evaluate_response(
    response="Here's the refactored code...",
    original_task="Refactor the auth module",
)
# assessment.quality_score = 0.75
# assessment.needs_refinement = True
# assessment.improvement_areas = ["test coverage", "error handling"]
```

### Feature Flag

```python
enable_meta_agent: bool = False  # Advanced — OFF by default
```

---

## Self-Refinement Loop

After generating a response, the Self-Refinement Loop evaluates it via the Meta-Agent. If quality is below threshold, it appends a refinement prompt and re-runs.

```python
from core.self_refinement.loop import SelfRefinementLoop

loop = SelfRefinementLoop(
    meta_agent=meta,
    max_iterations=2,
    quality_threshold=0.7,
)

result = await loop.refine(state)
# result.was_improved = True
# result.quality_scores = [0.65, 0.82]  # Improved from 0.65 to 0.82
```

### Feature Flags

```python
enable_self_refinement: bool = False              # Advanced — OFF by default
max_refinement_iterations: int = 2                # Max refinement iterations
refinement_quality_threshold: float = 0.7         # Min quality score (0.0-1.0)
```

---

## Evolution Engine

The Evolution Engine closes the **self-evolution feedback loop**:

```
Task → Execute → Assess → Record to Memory → Learn → Future Decisions
```

After every task completion, it:
1. Saves an **episodic memory** (what was done, which mode, success)
2. Updates **strategic memory** (which mode works for which task type)
3. Records **sub-agent outcomes** in procedural memory

```python
from core.evolution.engine import EvolutionEngine

engine = EvolutionEngine(memory=agent.memory)

await engine.after_task_completed(
    task="Refactor the auth module",
    result="Successfully refactored...",
    sub_agents_used=["coder"],
    mode="hybrid",
    duration_ms=45000,
    success=True,
)
```

### Feature Flags

```python
enable_evolution: bool = False              # Advanced — OFF by default
evolution_auto_learn: bool = True           # Auto-learn from outcomes
```

---

## Graph Visualization

```python
from core.graph.visualization import GraphVisualizer

viz = GraphVisualizer()

# ASCII representation for terminal
print(viz.render_ascii())

# Mermaid diagram for Markdown/HTML
print(viz.render_mermaid("react"))       # ReAct mode
print(viz.render_mermaid("plan_and_execute"))  # Plan mode
print(viz.render_mermaid("hybrid"))      # Hybrid mode

# Execution trace rendering
print(viz.render_graph_execution(events=[
    {"type": "node_start", "node": "react", "input": "..."},
    {"type": "node_end", "node": "react", "output": "..."},
]))
```

---

## LangGraph Studio Compatibility

The project includes `langgraph.json` for LangGraph Studio:

```json
{
  "dependencies": ["."],
  "graphs": {
    "helix_react": "./core/graph/builder.py:build_react_graph_for_studio",
    "helix_plan_execute": "./core/graph/builder.py:build_plan_execute_graph_for_studio"
  },
  "env": ".env"
}
```

Run with:
```bash
langgraph dev
```

---

## Configuration Reference

All feature flags are in `config.py`:

| Flag | Default | Phase | Description |
|------|---------|-------|-------------|
| `enable_long_term_memory` | `True` | 1 | Typed memory system |
| `auto_summarize_conversations` | `True` | 1 | Auto-create episodic entries |
| `use_langgraph` | `True` | 2 | Graph-based execution |
| `execution_mode` | `"react"` | 3 | Default mode |
| `langgraph_checkpoint_db_path` | `"data/memory/checkpoints.db"` | 2 | Checkpoint DB path |
| `enable_meta_agent` | `False` | 4a | Meta-agent advisory |
| `enable_subagents` | `False` | 4b | Sub-agent spawning |
| `subagent_default_process_mode` | `"async"` | 4b | Sub-agent process mode |
| `subagent_max_concurrent` | `4` | 4b | Max parallel sub-agents |
| `subagent_process_timeout` | `120.0` | 4b | Process sub-agent timeout |
| `subagent_heartbeat_interval` | `5.0` | 4b | Heartbeat interval |
| `enable_self_refinement` | `False` | 5 | Self-refinement loop |
| `max_refinement_iterations` | `2` | 5 | Max refinement iterations |
| `refinement_quality_threshold` | `0.7` | 5 | Min quality score |
| `enable_evolution` | `False` | 6 | Evolution engine |
| `evolution_auto_learn` | `True` | 6 | Auto-learn from outcomes |
| `ltm_db_path` | `"data/memory/ltm.db"` | 1 | LTM SQLite path |

---

## Dependencies

```
# Core (Phase 1) — no new deps
aiosqlite, chromadb  # Already in project

# LangGraph (Phase 2)
langgraph>=1.2.0
langgraph-checkpoint>=4.0.0
langchain-core>=0.3.0

# NOT added: langchain, langchain-openai, langchain-community
# The project uses the openai SDK directly.
```

---

## File Structure

```
core/
├── memory/
│   ├── manager.py              # LongTermMemoryManager (+ _ConversationStore)
│   ├── vector.py                # VectorMemoryStore (3 ChromaDB collections)
│   ├── episodic.py              # Episodic memory (conversation summaries)
│   ├── semantic.py              # Semantic memory (facts/knowledge)
│   ├── procedural.py            # Procedural memory (skills + outcomes)
│   ├── strategic.py             # Strategic memory (preferences/strategies)
│   └── markdown.py              # Markdown export (existing)
├── graph/
│   ├── __init__.py
│   ├── state.py                 # HelixGraphState TypedDict
│   ├── tools.py                 # BaseTool ↔ StructuredTool bridge
│   ├── builder.py               # build_helix_graph() + 3 mode variants + Studio
│   ├── visualization.py         # ASCII/Mermaid/Rich rendering
│   ├── modes/
│   │   ├── __init__.py
│   │   └── router.py            # ModeRouter (auto mode selection)
│   └── nodes/
│       ├── __init__.py
│       ├── memory_retrieval_node.py  # LTM retrieval (all 4 types)
│       ├── react_node.py             # ReAct reasoning + LLM call
│       ├── tool_execution_node.py     # Tool call execution
│       ├── finalize_node.py           # Save + self-improvement + auto-summarize
│       ├── plan_node.py               # Task decomposition into sub-steps
│       ├── execute_step_node.py       # Execute plan step via ReAct
│       ├── meta_agent_node.py         # Pre-thinking advisory node
│       └── self_refinement_node.py    # Self-refinement trigger node
├── subagents/
│   ├── __init__.py
│   ├── base.py                  # SubAgentConfig, SubAgentResult, SubAgentHandle
│   ├── manager.py               # SubAgentManager (unified interface)
│   ├── async_runner.py          # AsyncSubAgentRunner (in-process)
│   ├── process.py               # SubAgentProcess (OS process + IPC + heartbeat)
│   ├── communication.py         # AgentCommunicationBus (async + process)
│   └── registry.py              # 5 predefined types
├── meta_agent.py                # MetaAgent (analyze_task + evaluate_response)
├── self_refinement/
│   ├── __init__.py
│   └── loop.py                  # SelfRefinementLoop
├── evolution/
│   ├── __init__.py
│   └── engine.py                # EvolutionEngine (feedback loop closer)
├── agent.py                     # HelixAgent (updated with graph + subagents)
├── agent_execution.py            # run_agent_loop (legacy) + auto-summarize hook
├── agent_events.py              # Event system (existing)
├── persistence.py               # LangGraph checkpointing wrapper
├── loop.py                      # AgentLoop (updated)
├── loop_streaming.py            # StreamingAgentLoop (updated)
├── prompt_builder.py             # System prompt assembly (existing)
├── context/                      # Context management (existing)
├── models/                       # Model providers (existing)
├── security/                     # Security (existing)
├── monitoring/                    # Monitoring (existing)
├── skills/                        # Skills (existing)
└── tools/                         # Tools (existing)

cli/tui/
└── subagents_widget.py          # TUI widget for sub-agent management

tests/
└── test_long_term_memory.py     # 20 tests for LTM system
```