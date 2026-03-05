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

        monkeypatch.setattr("whai.configuration.user_config.get_config_dir", mock_get_config_dir)

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
            with pytest.raises(ValueError, match="Invalid MCP tool name or server not found"):
                await manager.call_tool("invalid_name", {})
        finally:
            await manager.close_all()

    async def test_call_tool_wrong_server(self, mcp_server_time):
        """Test calling tool from non-existent server."""
        manager = MCPManager()
        await manager.initialize()
        try:
            with pytest.raises(ValueError, match="Invalid MCP tool name or server not found"):
                await manager.call_tool("mcp_nonexistent_server_tool", {})
        finally:
            await manager.close_all()

    async def test_clear_cache_refreshes_tools(self, mcp_server_time):
        """Test that clearing cache causes tools to be rediscovered."""
        manager = MCPManager()
        await manager.initialize()
        try:
            tools1 = await manager.get_all_tools()
            manager.clear_cache()
            tools2 = await manager.get_all_tools()
            assert len(tools1) == len(tools2)
        finally:
            await manager.close_all()

    async def test_close_all_then_reinitialize(self, mcp_server_time):
        """Test that closing all connections allows reinitialization."""
        manager = MCPManager()
        await manager.initialize()
        tools_before = await manager.get_all_tools()
        await manager.close_all()

        # After close, reinitialize should work
        await manager.initialize()
        try:
            tools_after = await manager.get_all_tools()
            assert len(tools_after) == len(tools_before)
        finally:
            await manager.close_all()

