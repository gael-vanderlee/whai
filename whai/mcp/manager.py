"""Manager for multiple MCP servers."""

import re
import shutil
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from whai.mcp.client import MCPClient
from whai.mcp.config import load_mcp_config, MCPServerConfig, MCPConfig
from whai.logging_setup import get_logger
from whai.utils import PerformanceLogger

logger = get_logger(__name__)


def _validate_server_config(server_name: str, server_config: MCPServerConfig) -> Tuple[bool, str]:
    """
    Validate server configuration before connection.
    
    Returns:
        (is_valid, error_message) tuple. Error message is empty if valid.
    """
    # Check command exists
    if not shutil.which(server_config.command):
        return False, (
            f"MCP server '{server_name}' failed to start:\n"
            f"  Command not found: {server_config.command}\n"
            f"  Please check the 'command' in your mcp.json configuration."
        )
    
    # Check file paths in args (only absolute paths)
    if server_config.args:
        for arg in reversed(server_config.args):
            if arg.endswith(('.py', '.js', '.sh')) or '/' in arg or '\\' in arg:
                file_path = Path(arg)
                if file_path.is_absolute():
                    if not file_path.exists():
                        return False, (
                            f"MCP server '{server_name}' failed to start:\n"
                            f"  Server script not found: {file_path}\n"
                            f"  Please check the 'command' and 'args' in your mcp.json configuration."
                        )
                    if not file_path.is_file():
                        return False, (
                            f"MCP server '{server_name}' failed to start:\n"
                            f"  Server script path is not a file: {file_path}\n"
                            f"  Please check the 'args' in your mcp.json configuration."
                        )
                break
    
    return True, ""


def _format_mcp_error(server_name: str, error: Exception, context: str = "connection") -> str:
    """
    Format user-friendly error message for MCP failures.
    
    Args:
        server_name: Name of the MCP server
        error: Exception that occurred
        context: "connection" or "list_tools"
    
    Returns:
        Formatted error message.
    """
    error_msg = str(error)
    error_type = type(error).__name__
    
    # Extract file errors from traceback
    tb_str = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
    if "can't open file" in tb_str or "No such file or directory" in tb_str:
        file_match = re.search(
            r"can't open file ['\"]([^'\"]+)['\"]|No such file or directory: ['\"]?([^'\"]+)['\"]?",
            tb_str
        )
        if file_match:
            file_path = file_match.group(1) or file_match.group(2)
            return (
                f"MCP server '{server_name}' failed to start:\n"
                f"  Server script not found: {file_path}\n"
                f"  Please check the 'command' and 'args' in your mcp.json configuration."
            )
    
    # Permission errors
    if "Permission denied" in error_msg:
        return (
            f"MCP server '{server_name}' failed to start:\n"
            f"  Permission denied when trying to execute the server.\n"
            f"  Please check that the server script is executable."
        )
    
    # Connection/list_tools errors
    if "CancelledError" in error_type or "Cancelled" in error_msg:
        if context == "list_tools":
            return (
                f"MCP server '{server_name}' connection failed:\n"
                f"  Could not communicate with the server.\n"
                f"  The server may have failed to start or the connection was lost.\n"
                f"  Please verify that the server script exists and can run successfully."
            )
        return (
            f"MCP server '{server_name}' failed to start:\n"
            f"  Could not start the server process.\n"
            f"  Please verify that the server script is executable and can run successfully."
        )
    
    # Generic error
    short_msg = error_msg[:200] if len(error_msg) > 200 else error_msg
    action = "start" if context == "connection" else "communicate with"
    return (
        f"MCP server '{server_name}' failed to {action}:\n"
        f"  {short_msg}\n"
        f"  Please check your mcp.json configuration for server '{server_name}'."
    )


class MCPManager:
    """Manages connections to multiple MCP servers."""

    def __init__(self):
        """Initialize MCP manager."""
        self.clients: Dict[str, MCPClient] = {}
        self._server_configs: Dict[str, MCPServerConfig] = {}
        self._tools_cache: Optional[List[Dict]] = None
        self._initialized = False
        self._enabled_cache: Optional[bool] = None
        self._config_cache: Optional[MCPConfig] = None
        self._closed = False

    async def initialize(self) -> List[Tuple[str, str]]:
        """
        Initialize all configured MCP servers.

        Loads configuration and connects to all configured servers.
        
        Returns:
            List of (server_name, error_message) tuples for failed servers.
            Empty list if all servers initialized successfully.
        """
        if self._initialized:
            return []

        perf = PerformanceLogger("MCP Initialization")
        perf.start()

        # Reuse cached config if available (from is_enabled() call)
        if self._config_cache is not None:
            config = self._config_cache
        else:
            config = load_mcp_config()
            if config is None:
                logger.debug("No MCP config found, MCP support disabled")
                perf.log_section("Config loading (not found)", level="debug")
                self._initialized = True
                return []

            if not config.mcp_servers:
                logger.debug("MCP config found but no servers configured")
                perf.log_section("Config loading (no servers)", level="debug")
                self._initialized = True
                return []

            perf.log_section("Config loading", extra_info={"servers": len(config.mcp_servers)}, level="debug")
            self._config_cache = config

        errors = []

        for server_name, server_config in config.mcp_servers.items():
            # Validate first
            is_valid, validation_error = _validate_server_config(server_name, server_config)
            if not is_valid:
                errors.append((server_name, validation_error))
                continue

            # Try to connect
            try:
                self._server_configs[server_name] = server_config
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
                error_msg = _format_mcp_error(server_name, e, context="connection")
                errors.append((server_name, error_msg))

        self._initialized = True
        perf.log_complete(extra_info={"servers": len(self.clients), "errors": len(errors)})
        return errors

    async def get_all_tools(self) -> List[Dict]:
        """
        Get all tools from all MCP servers.

        Returns:
            List of all tool definitions in OpenAI function format.
        
        Raises:
            RuntimeError: If any server fails during tool listing, with formatted error messages.
        """
        if not self._initialized:
            init_errors = await self.initialize()
            if init_errors:
                error_msgs = [msg for _, msg in init_errors]
                raise RuntimeError("\n\n".join(error_msgs))

        if self._tools_cache is not None:
            return self._tools_cache

        perf = PerformanceLogger("MCP Tool Discovery")
        perf.start()

        all_tools = []
        errors = []

        for server_name, client in list(self.clients.items()):
            try:
                tools = await client.list_tools()
                all_tools.extend(tools)
                logger.debug("Retrieved %d tools from server %s", len(tools), server_name)
            except Exception as e:
                error_msg = _format_mcp_error(server_name, e, context="list_tools")
                errors.append((server_name, error_msg))
                # Remove failed client to prevent retry
                self.clients.pop(server_name, None)

        if errors:
            error_msgs = [msg for _, msg in errors]
            raise RuntimeError("\n\n".join(error_msgs))

        self._tools_cache = all_tools
        perf.log_complete(extra_info={"tools": len(all_tools), "servers": len(self.clients)})
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
        # Skip if already closed
        if self._closed:
            return

        # Close all clients (they handle their own closed state)
        for server_name, client in list(self.clients.items()):
            await client.close()
            logger.debug("Closed connection to MCP server: %s", server_name)

        self.clients.clear()
        self._server_configs.clear()
        self._tools_cache = None
        self._config_cache = None
        self._initialized = False
        self._closed = True

    def get_server_config(self, server_name: str) -> Optional[MCPServerConfig]:
        """
        Get server configuration by server name.

        Args:
            server_name: Name of the MCP server.

        Returns:
            MCPServerConfig if found, None otherwise.
        """
        return self._server_configs.get(server_name)

    def get_tool_description(self, tool_name: str) -> Optional[str]:
        """
        Get tool description from cached tool definitions.

        Args:
            tool_name: Full tool name (e.g., "mcp_time-server_get_current_time").

        Returns:
            Tool description if found, None otherwise.
        """
        # Tools are cached, but get_all_tools is async
        # We need to access the cache synchronously
        if self._tools_cache is None:
            return None
        
        for tool in self._tools_cache:
            if tool.get("function", {}).get("name") == tool_name:
                return tool.get("function", {}).get("description")
        
        return None

    def is_enabled(self) -> bool:
        """
        Check if MCP support is enabled (config file exists and has servers).

        Returns:
            True if MCP is enabled, False otherwise.
        """
        if self._enabled_cache is not None:
            return self._enabled_cache
        
        # Load and cache config for reuse in initialize()
        config = load_mcp_config()
        if config is None:
            self._enabled_cache = False
            return False
        
        # Cache the config so initialize() can reuse it
        self._config_cache = config
        self._enabled_cache = len(config.mcp_servers) > 0
        return self._enabled_cache

