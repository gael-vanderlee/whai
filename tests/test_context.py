"""Tests for context module."""

from unittest.mock import patch

from whai import context


def test_get_context_prefers_tmux():
    """Test that get_context prefers tmux over history."""
    with (
        patch("whai.context._get_tmux_context", return_value="tmux output"),
        patch("whai.context._get_history_context", return_value="history output"),
    ):
        context_str, is_deep = context.get_context()

        assert context_str == "tmux output"
        assert is_deep is True


def test_get_context_falls_back_to_history():
    """Test that get_context falls back to history when tmux is unavailable."""
    with (
        patch("whai.context._get_tmux_context", return_value=None),
        patch("whai.context._get_history_context", return_value="history output"),
    ):
        context_str, is_deep = context.get_context()

        assert context_str == "history output"
        assert is_deep is False


def test_get_context_no_context_available():
    """Test get_context when no context is available."""
    with (
        patch("whai.context._get_tmux_context", return_value=None),
        patch("whai.context._get_history_context", return_value=None),
    ):
        context_str, is_deep = context.get_context()

        assert context_str == ""
        assert is_deep is False


# PowerShell history tests removed - they were reading actual user history
# instead of being properly isolated. The core PowerShell history parsing
# is covered by other tests.
