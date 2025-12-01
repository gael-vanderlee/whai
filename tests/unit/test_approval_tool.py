"""Tests for MCP tool approval function."""

from unittest.mock import patch

import pytest

from whai.interaction.approval import approve_tool


class TestApproveTool:
    """Tests for approve_tool function."""

    def test_approve_tool_approve(self):
        """Test approving a tool call returns True."""
        with patch("builtins.input", return_value="a"):
            result = approve_tool(
                "mcp_time-server_get_current_time",
                {"timezone": "UTC"},
                display_name="time-server/get_current_time",
            )
            assert result is True

    def test_approve_tool_reject(self):
        """Test rejecting a tool call returns False."""
        with patch("builtins.input", return_value="r"):
            result = approve_tool(
                "mcp_time-server_get_current_time",
                {},
                display_name="time-server/get_current_time",
            )
            assert result is False

    def test_approve_tool_invalid_then_approve(self):
        """Test invalid input followed by approval returns True."""
        with patch("builtins.input", side_effect=["x", "a"]):
            result = approve_tool(
                "mcp_file-server_read_file",
                {"path": "test.txt"},
            )
            assert result is True

    def test_approve_tool_keyboard_interrupt(self):
        """Test keyboard interrupt rejects tool call and returns False."""
        with patch("builtins.input", side_effect=KeyboardInterrupt()):
            result = approve_tool(
                "mcp_time-server_get_current_time",
                {},
            )
            assert result is False

    def test_approve_tool_eof(self):
        """Test EOF rejects tool call and returns False."""
        with patch("builtins.input", side_effect=EOFError()):
            result = approve_tool(
                "mcp_time-server_get_current_time",
                {},
            )
            assert result is False

    def test_approve_tool_empty_args(self):
        """Test approval with empty arguments returns True."""
        with patch("builtins.input", return_value="a"):
            result = approve_tool(
                "mcp_time-server_get_current_time",
                {},
            )
            assert result is True

    def test_approve_tool_nested_args(self):
        """Test approval with nested arguments returns True."""
        nested_args = {
            "config": {
                "timezone": "UTC",
                "format": "iso",
            },
            "options": ["verbose", "debug"],
        }
        with patch("builtins.input", return_value="a"):
            result = approve_tool(
                "mcp_complex-server_process",
                nested_args,
            )
            assert result is True

