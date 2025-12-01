"""MCP client for connecting to MCP servers."""

import asyncio
from typing import Any, Dict, List, Optional

from mcp import ClientSession
from mcp.client.stdio import stdio_client
from mcp.types import Tool

from whai.logging_setup import get_logger
from whai.utils import PerformanceLogger

logger = get_logger(__name__)

class MCPClient:
    """Client for connecting to MCP servers and discovering tools."""

    def __init__(
        self,
        server_name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize MCP client.

        Args:
            server_name: Name identifier for this MCP server.
            command: Command to start the MCP server.
            args: Optional arguments for the command.
            env: Optional environment variables.
        """

        self.server_name = server_name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self._session: Optional[ClientSession] = None
        self._read_stream = None
        self._write_stream = None
        self._tools: Optional[List[Tool]] = None
        self._connected = False
        self._closed = False
        self._entry_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Connect to the MCP server."""
        if self._connected:
            return

        perf = PerformanceLogger(f"MCP Connection ({self.server_name})")
        perf.start()

        try:
            from mcp import StdioServerParameters

            server_params = StdioServerParameters(
                command=self.command,
                args=self.args,
                env=self.env,
            )

            self._stdio_context = stdio_client(server_params)
            self._read_stream, self._write_stream = await self._stdio_context.__aenter__()
            perf.log_section("Stdio context setup", level="debug")

            self._session = ClientSession(self._read_stream, self._write_stream)
            await self._session.__aenter__()
            # Track the task where contexts were entered for proper cleanup
            try:
                self._entry_task = asyncio.current_task()
            except RuntimeError:
                self._entry_task = None
            perf.log_section("Session creation", level="debug")

            await self._session.initialize()
            perf.log_section("Session initialization", level="debug")

            self._connected = True
            perf.log_complete(level="debug")

        except Exception as e:
            logger.exception("Failed to connect to MCP server %s: %s", self.server_name, e)
            self._connected = False
            raise

    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        List available tools from the MCP server and convert to OpenAI function format.

        Returns:
            List of tool definitions in OpenAI function format.
        """
        if not self._connected or self._session is None:
            await self.connect()

        perf = PerformanceLogger(f"MCP List Tools ({self.server_name})")
        perf.start()

        try:
            tools_result = await self._session.list_tools()
            self._tools = tools_result.tools
            perf.log_section("MCP API call", level="debug")

            openai_tools = []
            for tool in self._tools:
                openai_tool = {
                    "type": "function",
                    "function": {
                        "name": f"mcp_{self.server_name}_{tool.name}",
                        "description": tool.description or f"Tool from MCP server {self.server_name}",
                        "parameters": self._convert_schema(tool.inputSchema) if tool.inputSchema else {
                            "type": "object",
                            "properties": {},
                        },
                    },
                }
                openai_tools.append(openai_tool)

            perf.log_section("Tool conversion", extra_info={"tools": len(openai_tools)}, level="debug")
            perf.log_complete(extra_info={"tools": len(openai_tools)}, level="debug")
            logger.debug(
                "Discovered %d tools from MCP server %s",
                len(openai_tools),
                self.server_name,
            )
            return openai_tools

        except Exception as e:
            logger.exception("Failed to list tools from MCP server %s: %s", self.server_name, e)
            return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool (with or without mcp_ prefix).
            arguments: Tool arguments.

        Returns:
            Tool result dictionary.

        Raises:
            RuntimeError: If not connected or tool call fails.
        """
        if not self._connected or self._session is None:
            await self.connect()

        actual_tool_name = tool_name
        if tool_name.startswith(f"mcp_{self.server_name}_"):
            actual_tool_name = tool_name[len(f"mcp_{self.server_name}_"):]

        perf = PerformanceLogger(f"MCP Tool Call ({self.server_name}/{actual_tool_name})")
        perf.start()

        try:
            result = await self._session.call_tool(actual_tool_name, arguments)
            perf.log_section("MCP API call", level="debug")
            
            # Convert MCP result object to dict if needed
            if hasattr(result, "content"):
                content_list = []
                for item in result.content:
                    if hasattr(item, "text"):
                        content_list.append({"type": "text", "text": item.text})
                    elif hasattr(item, "type") and hasattr(item, "text"):
                        content_list.append({"type": item.type, "text": item.text})
                    else:
                        content_list.append({"type": "text", "text": str(item)})
                perf.log_section("Result conversion", level="debug")
                perf.log_complete(extra_info={"is_error": getattr(result, "isError", False)}, level="debug")
                return {
                    "content": content_list,
                    "isError": getattr(result, "isError", False),
                }
            elif isinstance(result, dict):
                perf.log_section("Result conversion", level="debug")
                perf.log_complete(level="debug")
                return result
            else:
                perf.log_section("Result conversion", level="debug")
                perf.log_complete(level="debug")
                return {"content": [{"type": "text", "text": str(result)}]}
        except Exception as e:
            logger.exception(
                "Failed to call tool %s on MCP server %s: %s",
                tool_name,
                self.server_name,
                e,
            )
            raise RuntimeError(f"MCP tool call failed: {e}") from e

    def _convert_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert JSON Schema to OpenAI function parameters format.

        Args:
            schema: MCP tool input schema (JSON Schema format).

        Returns:
            OpenAI function parameters format.
        """
        if "type" in schema and schema["type"] == "object":
            return {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            }
        elif "properties" in schema:
            return {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            }
        else:
            return {
                "type": "object",
                "properties": schema,
                "required": [],
            }

    async def close(self) -> None:
        """Close the MCP connection."""
        # Skip if already closed
        if self._closed:
            return

        # Check if we're in the same task where contexts were entered
        # If not, contexts are already cancelled by run_until_complete() and we should skip cleanup
        try:
            current_task = asyncio.current_task()
            if self._entry_task is not None and current_task is not self._entry_task:
                # Different task - contexts were cancelled when previous run_until_complete() completed
                # Just mark as closed, let OS clean up the subprocess
                self._closed = True
                self._connected = False
                self._session = None
                self._read_stream = None
                self._write_stream = None
                return
        except RuntimeError:
            # No current task - contexts are already cancelled
            self._closed = True
            self._connected = False
            self._session = None
            self._read_stream = None
            self._write_stream = None
            return

        # Only attempt to exit contexts if we're still connected
        if not self._connected:
            self._closed = True
            return

        # Close session if it exists
        if self._session is not None:
            await self._session.__aexit__(None, None, None)
            self._session = None

        # Close stdio context if it exists
        if hasattr(self, "_stdio_context"):
            await self._stdio_context.__aexit__(None, None, None)

        self._closed = True
        self._connected = False
        self._read_stream = None
        self._write_stream = None
        self._entry_task = None

