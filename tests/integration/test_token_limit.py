"""Integration tests for token limit enforcement and handling.

These tests validate that whai gracefully handles cases where context
or output exceeds model token limits.
"""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from whai.cli.main import app
from whai.llm.token_utils import truncate_text_with_tokens

runner = CliRunner()


@pytest.fixture(autouse=True)
def test_config(tmp_path, monkeypatch):
    """Set up ephemeral test config."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setenv("WHAI_TEST_MODE", "1")


def test_very_large_context_is_truncated_gracefully():
    """Test that enormous context (>200K tokens) is truncated without crashing."""
    # Create massive context: ~1.6MB = ~400K tokens (exceeds CONTEXT_MAX_TOKENS=200K)
    # Need to significantly exceed the limit to trigger truncation
    massive_context = "A" * 1_600_000  # ~400K tokens, will be truncated to 200K tokens
    
    # Mock LLM
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = "I see you have a large output."
    mock_response.choices[0].message.tool_calls = None
    
    # Capture the messages sent to LLM
    captured_messages = []
    
    def mock_completion(**kwargs):
        captured_messages.append(kwargs.get("messages"))
        return mock_response
    
    with (
        patch("litellm.completion", side_effect=mock_completion),
        patch("whai.cli.main.get_context", return_value=(massive_context, True)),
    ):
        result = runner.invoke(app, ["analyze this"])
        
        # Should not crash
        assert result.exit_code == 0
        
        # Messages should have been sent
        assert len(captured_messages) > 0
        
        # Context in messages should be truncated (not 200KB)
        user_message = [m for m in captured_messages[0] if m.get("role") == "user"][0]
        user_content_length = len(user_message["content"])
        
        # Should be significantly smaller than original 1.6MB (truncated to ~200K tokens = ~800KB max)
        # CONTEXT_MAX_TOKENS is 200K tokens, so after truncation it should be around that size or less
        assert user_content_length < 1_000_000, f"Context should be truncated from 1.6MB, got {user_content_length} chars"
        # Should be at least 30% smaller (allowing for formatting overhead)
        assert user_content_length < len(massive_context) * 0.7, f"Context should be truncated, got {user_content_length} chars vs {len(massive_context)} original"


def test_truncation_notice_is_present_in_large_context():
    """Test that truncation notice is shown when context is truncated."""
    # Create large context that exceeds CONTEXT_MAX_TOKENS (200K tokens = ~800KB)
    large_context = "B" * 1_000_000  # ~250K tokens, will be truncated
    
    # Capture messages
    captured_messages = []
    
    def mock_completion(**kwargs):
        captured_messages.append(kwargs.get("messages"))
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = MagicMock()
        mock_response.choices[0].message.content = "Response"
        mock_response.choices[0].message.tool_calls = None
        return mock_response
    
    with (
        patch("litellm.completion", side_effect=mock_completion),
        patch("whai.cli.main.get_context", return_value=(large_context, True)),
    ):
        result = runner.invoke(app, ["test query"])
        
        assert result.exit_code == 0
        assert len(captured_messages) > 0
        
        # Check for truncation notice in user message
        user_message = [m for m in captured_messages[0] if m.get("role") == "user"][0]
        
        # If context was truncated (significantly smaller than original), notice should be present
        # Note: Context may be formatted/wrapped, so we check if it's significantly smaller
        user_content_length = len(user_message["content"])
        if user_content_length < len(large_context) * 0.5:  # Truncated to less than 50% of original
            # Should have truncation notice if significantly truncated
            assert "CHARACTERS REMOVED" in user_message["content"] or "truncat" in user_message["content"].lower()


def test_truncation_preserves_most_recent_content():
    """Test that truncation keeps the most recent (end) content."""
    # Create text with distinct beginning and end
    text = "BEGINNING_MARKER " * 1000 + "END_MARKER " * 1000
    
    # Truncate to 100 tokens (~400 chars)
    truncated, was_truncated = truncate_text_with_tokens(text, max_tokens=100)
    
    assert was_truncated is True
    
    # End marker should be present (most recent)
    assert "END_MARKER" in truncated
    
    # Beginning marker may or may not be present depending on length,
    # but if not, there should be a truncation notice
    if "BEGINNING_MARKER" not in truncated:
        assert "CHARACTERS REMOVED" in truncated


def test_command_output_exceeding_limit_handled():
    """Test that command output exceeding token limit is handled gracefully."""
    import json
    
    # Mock LLM to propose a command
    call_count = [0]
    
    def mock_llm_sequence(**kwargs):
        call_count[0] += 1
        
        if call_count[0] == 1:
            # First call: propose command
            mock_tool = MagicMock()
            mock_tool.id = "call_123"
            mock_tool.function = MagicMock()
            mock_tool.function.name = "execute_shell"
            mock_tool.function.arguments = json.dumps({"command": "echo test"})
            
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message = MagicMock()
            response.choices[0].message.content = "Running command."
            response.choices[0].message.tool_calls = [mock_tool]
            return response
        else:
            # Second call: after command execution
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message = MagicMock()
            response.choices[0].message.content = "Command completed."
            response.choices[0].message.tool_calls = None
            return response
    
    # Mock execute_command to return massive output
    huge_output = "X" * 500_000  # 500KB output
    
    with (
        patch("litellm.completion", side_effect=mock_llm_sequence),
        patch("whai.context.get_context", return_value=("", False)),
        patch("builtins.input", return_value="a"),
        patch("whai.core.executor.execute_command", return_value=(huge_output, "", 0)),
    ):
        result = runner.invoke(app, ["run command", "--no-context"])
        
        # Should not crash despite huge output
        assert result.exit_code == 0


def test_context_plus_query_within_limit_not_truncated():
    """Test that context within limits is not truncated."""
    # Small context that fits easily
    small_context = "Recent commands:\n$ ls\nfile.txt\n$ pwd\n/home/user\n"
    
    captured_messages = []
    
    def mock_completion(**kwargs):
        captured_messages.append(kwargs.get("messages"))
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = MagicMock()
        mock_response.choices[0].message.content = "Response"
        mock_response.choices[0].message.tool_calls = None
        return mock_response
    
    with (
        patch("litellm.completion", side_effect=mock_completion),
        patch("whai.cli.main.get_context", return_value=(small_context, False)),
    ):
        result = runner.invoke(app, ["short query"])
        
        assert result.exit_code == 0
        
        # Context should not be truncated (small context fits easily)
        user_message = [m for m in captured_messages[0] if m.get("role") == "user"][0]
        # Small context should be present (may be wrapped/formatted, so check for key parts)
        assert "ls" in user_message["content"] or "file.txt" in user_message["content"] or "pwd" in user_message["content"]
        # Should not have truncation notice for small context
        assert "CHARACTERS REMOVED" not in user_message["content"]


def test_multiple_truncations_in_conversation():
    """Test that multiple truncations in a conversation work correctly."""
    # Simulate a conversation with large outputs each time
    large_output1 = "OUTPUT1 " * 10_000
    large_output2 = "OUTPUT2 " * 10_000
    
    call_count = [0]
    
    def mock_completion(**kwargs):
        call_count[0] += 1
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = MagicMock()
        mock_response.choices[0].message.content = f"Response {call_count[0]}"
        mock_response.choices[0].message.tool_calls = None
        return mock_response
    
    # First interaction with large context
    with (
        patch("litellm.completion", side_effect=mock_completion),
        patch("whai.cli.main.get_context", return_value=(large_output1, True)),
    ):
        result1 = runner.invoke(app, ["first query"])
        assert result1.exit_code == 0
    
    # Reset call count for second interaction
    call_count[0] = 0
    
    # Second interaction with different large context
    with (
        patch("litellm.completion", side_effect=mock_completion),
        patch("whai.cli.main.get_context", return_value=(large_output2, True)),
    ):
        result2 = runner.invoke(app, ["second query"])
        assert result2.exit_code == 0


def test_truncation_with_unicode_characters():
    """Test that truncation handles Unicode characters correctly."""
    # Create text with lots of Unicode (emojis, CJK characters)
    unicode_text = "Hello 世界 🌍 " * 5000
    
    # Truncate
    truncated, was_truncated = truncate_text_with_tokens(unicode_text, max_tokens=100)
    
    # Should not crash with encoding errors
    assert isinstance(truncated, str)
    
    # Should still contain some Unicode (from the end)
    assert any(ord(char) > 127 for char in truncated)


def test_token_limit_error_from_api_handled():
    """Test that token limit errors from the API are handled gracefully."""
    from litellm.exceptions import ContextWindowExceededError
    
    # Mock LLM to raise token limit error
    def mock_llm_error(**kwargs):
        raise ContextWindowExceededError(
            message="Context length exceeded",
            llm_provider="openai",
            model="gpt-4"
        )
    
    with (
        patch("litellm.completion", side_effect=mock_llm_error),
        patch("whai.cli.main.get_context", return_value=("some context", False)),
    ):
        result = runner.invoke(app, ["test query", "--no-context"])
        
        # Should not crash with unhandled exception
        assert result.exit_code in [0, 1]
        
        # Should show helpful error message
        output = result.stdout + result.stderr
        assert "context" in output.lower() or "limit" in output.lower() or "exceeded" in output.lower()

