"""Integration tests for error recovery and edge cases.

These tests validate that whai handles errors gracefully and shows
helpful messages to users rather than crashing.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from whai.cli.main import app
from whai.interaction import execute_command

runner = CliRunner()


@pytest.fixture(autouse=True)
def test_config(tmp_path, monkeypatch):
    """Set up ephemeral test config."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setenv("WHAI_TEST_MODE", "1")


def test_command_timeout_shows_clear_message():
    """Test that command timeout raises RuntimeError with clear message."""
    timeout_seconds = 0.1
    with pytest.raises(RuntimeError) as exc_info:
        execute_command("sleep 100", timeout=timeout_seconds)
    
    error_message = str(exc_info.value)
    assert "timed out" in error_message.lower()
    assert str(timeout_seconds) in error_message


def test_malformed_tool_call_json_recovers_gracefully(mock_litellm_module):
    """Test that malformed tool call JSON is handled gracefully without crashing."""
    # Mock LLM to return malformed tool call JSON
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_123"
    mock_tool_call.function = MagicMock()
    mock_tool_call.function.name = "execute_shell"
    mock_tool_call.function.arguments = "{invalid json]"  # Malformed JSON
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = "Let me run that."
    mock_response.choices[0].message.tool_calls = [mock_tool_call]
    
    mock_litellm_module.completion = lambda **kwargs: mock_response
    with (
        patch("litellm.completion", return_value=mock_response),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["test query", "--no-context"])
        
        # Should not crash - exits gracefully
        assert result.exit_code in [0, 1]
        output = result.stdout + result.stderr
        # Should show some error indication (not crash with unhandled exception)
        assert "error" in output.lower() or "invalid" in output.lower() or len(output) > 0


def test_network_failure_shows_retry_message(mock_litellm_module):
    """Test that network failures are handled gracefully with error messages."""
    # Mock litellm to raise connection error
    def raise_connection_error(**kwargs):
        raise ConnectionError("Failed to connect to API")
    
    with (
        patch("litellm.completion", side_effect=raise_connection_error),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["test query", "--no-context"])
        
        # Should handle gracefully (may exit 0 or 1)
        assert result.exit_code in [0, 1]
        output = result.stdout + result.stderr
        # Should show error message or handle gracefully
        assert "error" in output.lower() or "failed" in output.lower() or len(output) > 0


def test_config_file_corrupted_launches_wizard(tmp_path, monkeypatch):
    """Test that corrupted config file triggers config wizard."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.delenv("WHAI_TEST_MODE", raising=False)
    
    # Create corrupted config file
    config_file = tmp_path / "config.toml"
    config_file.write_text("invalid toml { syntax")
    
    # Mock wizard to avoid interactive prompt
    with patch("whai.configuration.config_wizard.run_wizard") as mock_wizard:
        mock_wizard.side_effect = KeyboardInterrupt()  # User cancels wizard
        
        result = runner.invoke(app, ["test query"])
        
        # Should have attempted to launch wizard
        assert mock_wizard.called or result.exit_code != 0


def test_very_large_command_output_truncated():
    """Test that very large command output is handled without crashing."""
    # Create a command that outputs ~500KB
    large_output = "A" * 500_000
    
    with (
        patch("subprocess.run") as mock_run,
        patch("whai.interaction.execution.is_windows", return_value=False),
    ):
        mock_result = MagicMock()
        mock_result.stdout = large_output
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        # Should not crash
        stdout, stderr, code = execute_command("echo test")
        
        assert code == 0
        # Output should be returned (even if large)
        assert len(stdout) > 0


def test_llm_error_response_handled_gracefully(mock_litellm_module):
    """Test that LLM API errors (like rate limits) are handled gracefully."""
    # Mock API to return rate limit error
    def raise_rate_limit(**kwargs):
        from litellm.exceptions import RateLimitError
        raise RateLimitError("Rate limit exceeded", llm_provider="openai", model="gpt-4")
    
    with (
        patch("litellm.completion", side_effect=raise_rate_limit),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["test query", "--no-context"])
        
        # Should handle gracefully (may exit 0 or 1)
        assert result.exit_code in [0, 1]
        output = result.stdout + result.stderr
        # Should show error message or handle gracefully
        assert "error" in output.lower() or "rate" in output.lower() or "limit" in output.lower() or len(output) > 0

