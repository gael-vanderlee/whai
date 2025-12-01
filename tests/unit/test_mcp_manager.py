"""Tests for MCP manager using real MCP servers."""

import asyncio

import pytest

from whai.mcp.manager import MCPManager


@pytest.mark.anyio
class TestMCPManager:
    """Tests for MCP manager with real MCP servers."""

    async def test_manager_no_config(self, tmp_path, monkeypatch):
        """Test manager when no config exists."""
        def mock_get_config_dir():
            return tmp_path

        monkeypatch.setattr("whai.mcp.config.get_config_dir", mock_get_config_dir)

        manager = MCPManager()
        assert not manager.is_enabled()
        await manager.initialize()
        assert len(manager.clients) == 0

    async def test_get_server_config(self, mcp_server_time):
        """Test getting server config by name."""
        manager = MCPManager()
        await manager.initialize()
        try:
            # Should be able to get config for initialized server
            config = manager.get_server_config("time-server")
            assert config is not None
            assert config.command is not None
            
            # Non-existent server should return None
            assert manager.get_server_config("non-existent") is None
        finally:
            await manager.close_all()

    async def test_manager_with_config(self, mcp_server_time):
        """Test manager with valid config."""
        manager = MCPManager()
        assert manager.is_enabled()
        await manager.initialize()
        try:
            assert len(manager.clients) > 0
        finally:
            await manager.close_all()

    async def test_get_all_tools(self, mcp_server_time):
        """Test getting all tools from manager."""
        manager = MCPManager()
        await manager.initialize()
        try:
            tools = await manager.get_all_tools()
            assert len(tools) > 0
            assert all(tool["type"] == "function" for tool in tools)
            assert all(tool["function"]["name"].startswith("mcp_") for tool in tools)
        finally:
            await manager.close_all()

    async def test_call_tool(self, mcp_server_time):
        """Test calling tool through manager."""
        manager = MCPManager()
        await manager.initialize()
        try:
            tools = await manager.get_all_tools()
            assert len(tools) > 0

            tool_name = tools[0]["function"]["name"]
            result = await manager.call_tool(tool_name, {})
            assert isinstance(result, dict)
            assert "content" in result or "isError" in result
        finally:
            await manager.close_all()

    async def test_call_tool_invalid_name(self, mcp_server_time):
        """Test calling tool with invalid name format."""
        manager = MCPManager()
        await manager.initialize()
        try:
            with pytest.raises(ValueError, match="Invalid MCP tool name format"):
                await manager.call_tool("invalid_name", {})
        finally:
            await manager.close_all()

    async def test_call_tool_wrong_server(self, mcp_server_time):
        """Test calling tool from non-existent server."""
        manager = MCPManager()
        await manager.initialize()
        try:
            with pytest.raises(ValueError, match="MCP server.*not found"):
                await manager.call_tool("mcp_nonexistent_server_tool", {})
        finally:
            await manager.close_all()

    async def test_tool_name_parsing(self):
        """Test parsing tool names to route to correct server."""
        tool_name = "mcp_test-server_tool-name"
        parts = tool_name.split("_", 2)
        assert len(parts) == 3
        assert parts[0] == "mcp"
        assert parts[1] == "test-server"
        assert parts[2] == "tool-name"

    async def test_clear_cache(self, mcp_server_time):
        """Test clearing tools cache."""
        manager = MCPManager()
        await manager.initialize()
        try:
            tools1 = await manager.get_all_tools()
            assert manager._tools_cache is not None

            manager.clear_cache()
            assert manager._tools_cache is None

            tools2 = await manager.get_all_tools()
            assert len(tools1) == len(tools2)
        finally:
            await manager.close_all()

    async def test_close_all(self, mcp_server_time):
        """Test closing all connections."""
        manager = MCPManager()
        await manager.initialize()
        assert len(manager.clients) > 0

        await manager.close_all()
        assert len(manager.clients) == 0
        assert not manager._initialized

