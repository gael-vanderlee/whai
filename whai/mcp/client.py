"""MCP client for connecting to MCP servers."""

import asyncio
from typing import Any, Dict, List, Optional

from whai.logging_setup import get_logger

logger = get_logger(__name__)

from mcp import ClientSession
from mcp.client.stdio import stdio_client
from mcp.types import Tool

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

    async def connect(self) -> None:
        """Connect to the MCP server."""
        if self._connected:
            return

        try:
            from mcp import StdioServerParameters

            server_params = StdioServerParameters(
                command=self.command,
                args=self.args,
                env=self.env,
            )

            self._stdio_context = stdio_client(server_params)
            self._read_stream, self._write_stream = await self._stdio_context.__aenter__()

            self._session = ClientSession(self._read_stream, self._write_stream)
            await self._session.__aenter__()

            await self._session.initialize()

            self._connected = True
            logger.info("Connected to MCP server: %s", self.server_name)

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

        try:
            tools_result = await self._session.list_tools()
            self._tools = tools_result.tools

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

        try:
            result = await self._session.call_tool(actual_tool_name, arguments)
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
                return {
                    "content": content_list,
                    "isError": getattr(result, "isError", False),
                }
            elif isinstance(result, dict):
                return result
            else:
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
        if self._session is not None:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception as e:
                logger.warning("Error closing MCP session: %s", e)

        if hasattr(self, "_stdio_context"):
            try:
                await self._stdio_context.__aexit__(None, None, None)
            except Exception as e:
                logger.warning("Error closing stdio context: %s", e)

        self._connected = False
        self._session = None
        self._read_stream = None
        self._write_stream = None

