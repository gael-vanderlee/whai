"""Manager for multiple MCP servers."""

import asyncio
from typing import Dict, List, Optional

from whai.mcp.client import MCPClient
from whai.mcp.config import load_mcp_config
from whai.logging_setup import get_logger

logger = get_logger(__name__)


class MCPManager:
    """Manages connections to multiple MCP servers."""

    def __init__(self):
        """Initialize MCP manager."""
        self.clients: Dict[str, MCPClient] = {}
        self._tools_cache: Optional[List[Dict]] = None
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize all configured MCP servers.

        Loads configuration and connects to all configured servers.
        """
        if self._initialized:
            return

        config = load_mcp_config()
        if config is None:
            logger.debug("No MCP config found, MCP support disabled")
            self._initialized = True
            return

        if not config.mcp_servers:
            logger.debug("MCP config found but no servers configured")
            self._initialized = True
            return

        logger.info("Initializing %d MCP server(s)", len(config.mcp_servers))

        for server_name, server_config in config.mcp_servers.items():
            try:
                client = MCPClient(
                    server_name=server_name,
                    command=server_config.command,
                    args=server_config.args,
                    env=server_config.env,
                )
                await client.connect()
                self.clients[server_name] = client
                logger.info("Initialized MCP server: %s", server_name)
            except Exception as e:
                logger.warning(
                    "Failed to initialize MCP server %s: %s (continuing with other servers)",
                    server_name,
                    e,
                )

        self._initialized = True

    async def get_all_tools(self) -> List[Dict]:
        """
        Get all tools from all MCP servers.

        Returns:
            List of all tool definitions in OpenAI function format.
        """
        if not self._initialized:
            await self.initialize()

        if self._tools_cache is not None:
            return self._tools_cache

        all_tools = []
        for server_name, client in self.clients.items():
            try:
                tools = await client.list_tools()
                all_tools.extend(tools)
                logger.debug("Retrieved %d tools from server %s", len(tools), server_name)
            except Exception as e:
                logger.warning("Failed to get tools from MCP server %s: %s", server_name, e)

        self._tools_cache = all_tools
        logger.info("Total MCP tools available: %d", len(all_tools))
        return all_tools

    async def call_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """
        Call a tool by name (handles routing to correct MCP server).

        Args:
            tool_name: Full tool name (e.g., "mcp_server_name_tool_name").
            arguments: Tool arguments.

        Returns:
            Tool result dictionary.

        Raises:
            ValueError: If tool name format is invalid or server not found.
            RuntimeError: If tool call fails.
        """
        if not self._initialized:
            await self.initialize()

        if not tool_name.startswith("mcp_"):
            raise ValueError(f"Invalid MCP tool name format: {tool_name} (must start with 'mcp_')")

        parts = tool_name.split("_", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid MCP tool name format: {tool_name} (expected: mcp_<server>_<tool>)")

        server_name = parts[1]
        if server_name not in self.clients:
            available = list(self.clients.keys())
            raise ValueError(
                f"MCP server '{server_name}' not found. Available servers: {available}"
            )

        return await self.clients[server_name].call_tool(tool_name, arguments)

    def clear_cache(self) -> None:
        """Clear the tools cache (forces re-discovery on next get_all_tools call)."""
        self._tools_cache = None

    async def close_all(self) -> None:
        """Close all MCP connections."""
        for server_name, client in list(self.clients.items()):
            try:
                await client.close()
                logger.debug("Closed connection to MCP server: %s", server_name)
            except Exception as e:
                logger.warning("Error closing MCP server %s: %s", server_name, e)

        self.clients.clear()
        self._tools_cache = None
        self._initialized = False

    def is_enabled(self) -> bool:
        """
        Check if MCP support is enabled (config file exists and has servers).

        Returns:
            True if MCP is enabled, False otherwise.
        """
        config = load_mcp_config()
        if config is None:
            return False
        return len(config.mcp_servers) > 0

