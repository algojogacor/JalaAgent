"""Lazy-loading MCP server manager — start on first call, kill after idle timeout."""

import asyncio
import logging
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)

# Default idle timeout before killing an unused MCP server (5 minutes).
_DEFAULT_IDLE_TIMEOUT = 300

# Base MCP servers shipped by default (CLAUDE.md).
_BASE_SERVERS = {
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
    },
    "shell": {
        "command": "npx",
        "args": ["-y", "@anthropic/mcp-server-shell"],
    },
    "fetch": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-fetch"],
    },
    "graphify": {
        "command": "graphify",
        "args": ["--mcp"],
        "env": {},
        "description": "Knowledge graph for codebase — query, explain, path-find",
        "docs": "https://github.com/safishamsi/graphify",
    },
}


class MCPServer:
    """Wrapper around a running MCP server subprocess."""

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name = name
        self.config = config
        self.process: subprocess.Popen[bytes] | None = None
        self.last_used: float = 0.0
        self.tools: list[dict[str, Any]] = []

    async def start(self) -> None:
        """Launch the MCP server subprocess."""
        cmd = [self.config["command"]] + self.config.get("args", [])
        env = self.config.get("env", {})
        merged_env = {**__import__("os").environ, **env}

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=merged_env,
        )
        self.last_used = time.monotonic()
        logger.info("MCP server %s started (pid=%s)", self.name, self.process.pid)

    async def stop(self) -> None:
        """Kill the MCP server subprocess."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            logger.info("MCP server %s stopped", self.name)

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


class MCPManager:
    """Lazy-loading MCP server lifecycle manager.

    Per CLAUDE.md:
    - MCP servers are NOT started at agent boot.
    - Started on first tool call that requires them.
    - Killed after idle timeout (default: 5 minutes).
    """

    def __init__(self, idle_timeout: float = _DEFAULT_IDLE_TIMEOUT) -> None:
        self._idle_timeout = idle_timeout
        self._servers: dict[str, MCPServer] = {}
        self._cleanup_task: asyncio.Task[None] | None = None

        # Register base servers.
        for name, config in _BASE_SERVERS.items():
            self.register(name, config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, name: str, config: dict[str, Any]) -> None:
        """Register an MCP server configuration (does NOT start it)."""
        self._servers[name] = MCPServer(name, config)

    async def get_server(self, name: str) -> MCPServer | None:
        """Get a running server, starting it lazily if needed."""
        server = self._servers.get(name)
        if server is None:
            return None
        if not server.is_running:
            await server.start()
        server.last_used = time.monotonic()
        self._ensure_cleanup()
        return server

    async def get_tools(self, name: str) -> list[dict[str, Any]]:
        """Return the tool list for a running MCP server."""
        server = await self.get_server(name)
        if server is None:
            return []
        # In production this would call tools/list via MCP protocol.
        # For v1, return a placeholder based on the server name.
        return [
            {
                "name": f"mcp_{name}_execute",
                "description": f"Execute on MCP server: {name}",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]

    async def stop_all(self) -> None:
        """Stop all running MCP servers."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        for server in self._servers.values():
            await server.stop()

    async def list_servers(self) -> list[dict[str, Any]]:
        """List all registered MCP servers with status."""
        return [
            {
                "name": s.name,
                "running": s.is_running,
                "command": s.config.get("command", ""),
            }
            for s in self._servers.values()
        ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_cleanup(self) -> None:
        """Start the idle cleanup background task if not already running."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """Periodically kill idle servers."""
        while True:
            await asyncio.sleep(30)  # Check every 30 seconds.
            now = time.monotonic()
            for server in list(self._servers.values()):
                if (
                    server.is_running
                    and now - server.last_used > self._idle_timeout
                ):
                    logger.info(
                        "MCP server %s idle for %.0fs — stopping",
                        server.name,
                        now - server.last_used,
                    )
                    await server.stop()
