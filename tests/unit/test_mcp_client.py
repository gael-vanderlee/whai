"""Tests for MCP client using real MCP servers."""

import asyncio

import pytest

from whai.mcp.client import MCPClient


@pytest.mark.anyio
class TestMCPClient:
    """Tests for MCP client with real MCP server."""

    async def test_client_initialization(self, mcp_server_time):
        """Test MCP client can be initialized."""
        client = MCPClient(
            server_name=mcp_server_time["server_name"],
            command=mcp_server_time["command"],
            args=mcp_server_time["args"],
            env=mcp_server_time["env"],
        )
        assert client.server_name == mcp_server_time["server_name"]
        assert client.command == mcp_server_time["command"]

    async def test_connect_to_server(self, mcp_server_time):
        """Test connecting to real MCP server."""
        client = MCPClient(
            server_name=mcp_server_time["server_name"],
            command=mcp_server_time["command"],
            args=mcp_server_time["args"],
            env=mcp_server_time["env"],
        )
        await client.connect()
        try:
            assert client._connected
        finally:
            await client.close()

    async def test_list_tools(self, mcp_server_time):
        """Test discovering tools from real MCP server."""
        client = MCPClient(
            server_name=mcp_server_time["server_name"],
            command=mcp_server_time["command"],
            args=mcp_server_time["args"],
            env=mcp_server_time["env"],
        )
        await client.connect()
        try:
            tools = await client.list_tools()
            assert len(tools) > 0
            assert all(tool["type"] == "function" for tool in tools)
            assert all("function" in tool for tool in tools)
            assert all(tool["function"]["name"].startswith("mcp_") for tool in tools)
        finally:
            await client.close()

    async def test_call_tool(self, mcp_server_time):
        """Test calling a tool on real MCP server."""
        client = MCPClient(
            server_name=mcp_server_time["server_name"],
            command=mcp_server_time["command"],
            args=mcp_server_time["args"],
            env=mcp_server_time["env"],
        )
        await client.connect()
        try:
            tools = await client.list_tools()
            assert len(tools) > 0

            # Find a tool that doesn't require arguments (or use appropriate args)
            tool_name = tools[0]["function"]["name"]
            # Some tools require arguments, so we test with empty dict and handle validation errors
            result = await client.call_tool(tool_name, {})
            assert isinstance(result, dict)
            assert "content" in result or "isError" in result
        finally:
            await client.close()

    async def test_call_tool_with_prefix(self, mcp_server_time):
        """Test calling tool with mcp_ prefix."""
        client = MCPClient(
            server_name=mcp_server_time["server_name"],
            command=mcp_server_time["command"],
            args=mcp_server_time["args"],
            env=mcp_server_time["env"],
        )
        await client.connect()
        try:
            tools = await client.list_tools()
            assert len(tools) > 0

            tool_name = tools[0]["function"]["name"]
            result = await client.call_tool(tool_name, {})
            assert isinstance(result, dict)
            assert "content" in result or "isError" in result
        finally:
            await client.close()

    async def test_invalid_tool_name(self, mcp_server_time):
        """Test calling invalid tool name raises error."""
        client = MCPClient(
            server_name=mcp_server_time["server_name"],
            command=mcp_server_time["command"],
            args=mcp_server_time["args"],
            env=mcp_server_time["env"],
        )
        await client.connect()
        try:
            # MCP server may return error result instead of raising, so check for error in result
            result = await client.call_tool("invalid_tool_name", {})
            assert isinstance(result, dict)
            # Result should indicate an error (either isError flag or error in content)
            assert result.get("isError", False) or any(
                "error" in str(item).lower() for item in result.get("content", [])
            )
        finally:
            await client.close()

    async def test_close_connection(self, mcp_server_time):
        """Test closing connection."""
        client = MCPClient(
            server_name=mcp_server_time["server_name"],
            command=mcp_server_time["command"],
            args=mcp_server_time["args"],
            env=mcp_server_time["env"],
        )
        await client.connect()
        assert client._connected

        await client.close()
        assert not client._connected

    async def test_schema_conversion(self, mcp_server_time):
        """Test JSON Schema to OpenAI function format conversion."""
        client = MCPClient(
            server_name=mcp_server_time["server_name"],
            command=mcp_server_time["command"],
            args=mcp_server_time["args"],
            env=mcp_server_time["env"],
        )

        schema = {
            "type": "object",
            "properties": {"arg1": {"type": "string"}},
            "required": ["arg1"],
        }
        converted = client._convert_schema(schema)
        assert converted["type"] == "object"
        assert "properties" in converted
        assert "arg1" in converted["properties"]
        assert "required" in converted

