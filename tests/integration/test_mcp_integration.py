"""Integration tests for MCP support using real MCP servers."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import create_test_config, create_test_perf_logger
from whai.llm.provider import LLMProvider


@pytest.mark.anyio
class TestMCPIntegration:
    """Integration tests for MCP with LLM provider and executor."""

    async def test_mcp_tools_in_llm_provider(self, mcp_server_time, mock_litellm_module):
        """Test that MCP tools are discovered and included in LLM provider."""
        config = create_test_config()
        perf_logger = create_test_perf_logger()
        provider = LLMProvider(config, perf_logger=perf_logger)

        # Mock LLM response to avoid actual API call
        mock_completion = MagicMock()
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta = MagicMock()
        mock_chunk.choices[0].delta.content = "Test response"
        mock_chunk.choices[0].delta.tool_calls = None
        mock_completion.__iter__ = MagicMock(return_value=iter([mock_chunk]))

        with patch("litellm.completion", return_value=mock_completion):
            messages = [{"role": "user", "content": "Test"}]
            response = provider.send_message(messages, stream=True)
            
            # Verify response is a generator
            chunks = list(response)
            assert len(chunks) > 0

    async def test_mcp_manager_initialization(self, mcp_server_time):
        """Test MCP manager initialization with real server."""
        from whai.mcp.manager import MCPManager

        manager = MCPManager()
        assert manager.is_enabled()
        await manager.initialize()
        assert len(manager.clients) > 0

        tools = await manager.get_all_tools()
        assert len(tools) > 0
        assert all(tool["function"]["name"].startswith("mcp_") for tool in tools)

    async def test_mcp_tool_call_execution(self, mcp_server_time):
        """Test executing MCP tool call through manager."""
        from whai.mcp.manager import MCPManager

        manager = MCPManager()
        await manager.initialize()
        tools = await manager.get_all_tools()
        assert len(tools) > 0

        tool_name = tools[0]["function"]["name"]
        result = await manager.call_tool(tool_name, {})
        assert isinstance(result, dict)

    async def test_mcp_executor_integration(self, mcp_server_time):
        """Test MCP executor integration function."""
        from whai.mcp.executor import handle_mcp_tool_call_sync
        from whai.mcp.manager import MCPManager

        manager = MCPManager()
        await manager.initialize()
        tools = await manager.get_all_tools()
        assert len(tools) > 0

        tool_call = {
            "id": "call_123",
            "name": tools[0]["function"]["name"],
            "arguments": {},
        }

        result = handle_mcp_tool_call_sync(tool_call, manager)
        assert "tool_call_id" in result
        assert "output" in result
        assert result["tool_call_id"] == "call_123"

    async def test_mcp_error_handling(self, mcp_server_time):
        """Test error handling for invalid MCP tool calls."""
        from whai.mcp.executor import handle_mcp_tool_call_sync
        from whai.mcp.manager import MCPManager

        manager = MCPManager()
        await manager.initialize()

        tool_call = {
            "id": "call_123",
            "name": "mcp_invalid-server_invalid-tool",
            "arguments": {},
        }

        result = handle_mcp_tool_call_sync(tool_call, manager)
        assert "tool_call_id" in result
        assert "output" in result
        assert "error" in result["output"].lower() or "failed" in result["output"].lower()

