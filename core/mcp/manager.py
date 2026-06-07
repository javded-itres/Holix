"""MCPManager — manages connections to one or more MCP servers and exposes Helix tools."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from core.mcp.config import MCPServerConfig, validate_server_config
from core.mcp.tool import MCPTool

logger = logging.getLogger(__name__)

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client
    MCP_AVAILABLE = True
except Exception:  # pragma: no cover
    MCP_AVAILABLE = False
    ClientSession = None  # type: ignore
    StdioServerParameters = None  # type: ignore


class MCPManager:
    """Manages long-lived connections to MCP servers using dedicated keeper tasks.

    This avoids "exit cancel scope in different task" errors from anyio by ensuring
    that the stdio_client / ClientSession context managers are always entered and
    exited (via cancellation) from within their own dedicated asyncio task.

    Usage:
        mgr = MCPManager(servers)
        await mgr.connect_all()
        ... use tools ...
        await mgr.disconnect_all()
    """

    def __init__(self, servers: Dict[str, Dict[str, Any]]):
        self._raw = servers or {}
        self._configs: Dict[str, MCPServerConfig] = {}
        for name, data in self._raw.items():
            try:
                cfg = MCPServerConfig.from_dict(name, data)
                errs = validate_server_config(cfg)
                if errs:
                    logger.warning("MCP server %s config invalid: %s", name, errs)
                    continue
                self._configs[name] = cfg
            except Exception as e:
                logger.warning("Skipping bad MCP server %s: %s", name, e)

        self._sessions: Dict[str, ClientSession] = {}
        self._discovered_tools: Dict[str, List[Dict[str, Any]]] = {}
        self._keeper_tasks: Dict[str, asyncio.Task] = {}
        self._ready_events: Dict[str, asyncio.Event] = {}
        self._last_errors: Dict[str, str] = {}
        self._connected = False
        self._lock = asyncio.Lock()

    @property
    def available_servers(self) -> List[str]:
        return list(self._configs.keys())

    async def connect_all(self) -> None:
        if not MCP_AVAILABLE:
            logger.warning("mcp package not available; MCP support disabled")
            return
        async with self._lock:
            if self._connected:
                return
            self._discovered_tools = {}
            for name, cfg in list(self._configs.items()):
                if name in self._keeper_tasks:
                    continue
                task = asyncio.create_task(
                    self._keep_server(name, cfg),
                    name=f"mcp-keeper-{name}"
                )
                self._keeper_tasks[name] = task
            self._connected = True
            logger.info("MCPManager keeper tasks started for %d servers", len(self._keeper_tasks))

    async def wait_ready(self, server_names: Optional[List[str]] = None, timeout: float = 10.0) -> Dict[str, bool]:
        """Wait (up to timeout) for the given servers (or all) to finish initialize + list_tools.

        Returns dict of name -> succeeded (reached ready state).
        This helps with slow first-time npx/uvx downloads and auth for servers like context7.
        """
        names = list(server_names) if server_names is not None else list(self._configs.keys())
        results: Dict[str, bool] = {}
        for name in names:
            ev = self._ready_events.get(name)
            if ev is None:
                ev = asyncio.Event()
                self._ready_events[name] = ev
            if ev.is_set():
                results[name] = name not in self._last_errors
                continue
            try:
                await asyncio.wait_for(ev.wait(), timeout=timeout)
                results[name] = name not in self._last_errors
            except asyncio.TimeoutError:
                results[name] = False
        return results

    async def _keep_server(self, name: str, cfg: MCPServerConfig) -> None:
        """Dedicated task that owns the lifetime of one MCP connection."""
        session: Optional[ClientSession] = None
        try:
            if cfg.transport == "stdio":
                if not cfg.command:
                    return
                params = StdioServerParameters(
                    command=cfg.command,
                    args=cfg.args or [],
                    env={**os.environ, **(cfg.env or {})},
                    cwd=cfg.cwd,
                )
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as sess:
                        await sess.initialize()
                        session = sess
                        self._sessions[name] = session
                        # discover tools
                        try:
                            tools_resp = await sess.list_tools()
                            tools = []
                            for t in getattr(tools_resp, "tools", []):
                                tools.append({
                                    "name": getattr(t, "name", ""),
                                    "description": getattr(t, "description", "") or "",
                                    "inputSchema": getattr(t, "inputSchema", {}) or {"type": "object", "properties": {}},
                                })
                            self._discovered_tools[name] = tools
                            # Signal ready for waiters
                            ev = self._ready_events.setdefault(name, asyncio.Event())
                            ev.set()
                        except Exception as disc_err:
                            logger.warning("MCP tool discovery failed for %s: %s", name, disc_err)
                            self._discovered_tools[name] = []
                            self._last_errors[name] = f"discovery: {disc_err}"
                            ev = self._ready_events.setdefault(name, asyncio.Event())
                            ev.set()  # signal even on discovery failure so waiters unblock
                        # Park until cancelled. Use a simple event that never sets.
                        await asyncio.Event().wait()
            else:  # sse
                if not cfg.url:
                    return
                async with sse_client(cfg.url) as (read, write):
                    async with ClientSession(read, write) as sess:
                        await sess.initialize()
                        session = sess
                        self._sessions[name] = session
                        try:
                            tools_resp = await sess.list_tools()
                            tools = []
                            for t in getattr(tools_resp, "tools", []):
                                tools.append({
                                    "name": getattr(t, "name", ""),
                                    "description": getattr(t, "description", "") or "",
                                    "inputSchema": getattr(t, "inputSchema", {}) or {"type": "object", "properties": {}},
                                })
                            self._discovered_tools[name] = tools
                            ev = self._ready_events.setdefault(name, asyncio.Event())
                            ev.set()
                        except Exception as disc_err:
                            logger.warning("MCP tool discovery failed for %s: %s", name, disc_err)
                            self._discovered_tools[name] = []
                            self._last_errors[name] = f"discovery: {disc_err}"
                            ev = self._ready_events.setdefault(name, asyncio.Event())
                            ev.set()
                        await asyncio.Event().wait()
        except asyncio.CancelledError:
            logger.info("MCP keeper for %s cancelled (normal shutdown)", name)
            raise
        except Exception as exc:
            from core.mcp.validate import format_mcp_error

            msg = format_mcp_error(exc)
            logger.error("MCP keeper for %s failed: %s", name, msg)
            self._last_errors[name] = msg
            ev = self._ready_events.setdefault(name, asyncio.Event())
            ev.set()
        finally:
            self._sessions.pop(name, None)
            self._discovered_tools.pop(name, None)
            # The async with blocks will handle proper __aexit__ for stdio_client / ClientSession
            # because exit happens inside this task (on cancellation or exception).

    async def disconnect_all(self) -> None:
        async with self._lock:
            tasks_to_cancel = []
            for name, task in list(self._keeper_tasks.items()):
                if not task.done():
                    task.cancel()
                    tasks_to_cancel.append(task)
            if tasks_to_cancel:
                await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
            self._keeper_tasks.clear()
            self._sessions.clear()
            self._discovered_tools.clear()
            self._ready_events.clear()
            self._last_errors.clear()
            self._connected = False
            logger.info("MCPManager disconnected")

    def get_tool_adapters(self, enabled_server_names: Optional[List[str]] = None) -> List[MCPTool]:
        """Return MCPTool adapters for the enabled servers (or all if None/empty)."""
        enabled = set(enabled_server_names) if enabled_server_names else set(self._configs.keys())
        adapters: List[MCPTool] = []
        for srv_name in enabled:
            if srv_name not in self._sessions:
                continue
            cfg = self._configs.get(srv_name)
            if not cfg:
                continue
            for t in self._discovered_tools.get(srv_name, []):
                adapters.append(
                    MCPTool(
                        server_name=srv_name,
                        tool_name=t["name"],
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                        manager=self,
                        risk_level=cfg.default_risk_level,
                    )
                )
        return adapters

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        session = self._sessions.get(server_name)
        if not session:
            raise RuntimeError(f"MCP server not connected: {server_name}")
        result = await session.call_tool(tool_name, arguments or {})

        # Some MCP SDKs / servers return structured error results
        is_error = getattr(result, "isError", False) or (isinstance(result, dict) and result.get("isError"))
        if hasattr(result, "content"):
            contents = []
            for c in result.content:
                if hasattr(c, "text"):
                    contents.append(c.text)
                else:
                    contents.append(str(c))
            text = "\n".join(contents)
            if is_error:
                raise RuntimeError(text or "MCP tool returned error")
            return {"content": [{"type": "text", "text": x} for x in contents]}
        if is_error:
            # Structured error without content
            raise RuntimeError(str(result))
        return result

    async def __aenter__(self):
        await self.connect_all()
        return self

    async def __aexit__(self, *a):
        await self.disconnect_all()
