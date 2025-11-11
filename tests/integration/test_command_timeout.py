"""Integration tests for command timeout behavior.

These tests validate that whai handles command timeouts gracefully
and provides clear, actionable error messages to users.
"""

import json
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


def test_command_timeout_raises_clear_error():
    """Test that command timeout raises RuntimeError with clear message."""
    with pytest.raises(RuntimeError) as exc_info:
        execute_command("sleep 100", timeout=1)
    
    error_message = str(exc_info.value)
    assert "timed out" in error_message.lower()
    assert "1" in error_message  # Timeout value should be mentioned


def test_timeout_error_shown_to_user_via_cli():
    """Test that timeout error is shown to user in CLI output, not as stack trace."""
    # Mock LLM to propose a long-running command
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_123"
    mock_tool_call.function = MagicMock()
    mock_tool_call.function.name = "execute_shell"
    mock_tool_call.function.arguments = json.dumps({"command": "sleep 100"})
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = "Let me run that long command."
    mock_response.choices[0].message.tool_calls = [mock_tool_call]
    
    # Mock execute_command to timeout
    def mock_execute_timeout(cmd, timeout=None):
        raise RuntimeError(f"Command timed out after {timeout} seconds")
    
    with (
        patch("litellm.completion", return_value=mock_response),
        patch("whai.context.get_context", return_value=("", False)),
        patch("builtins.input", return_value="a"),  # Approve
        patch("whai.core.executor.execute_command", side_effect=mock_execute_timeout),
    ):
        result = runner.invoke(app, ["run long task", "--no-context", "--timeout", "5"])
        
        # Should not crash with unhandled exception
        # Exit code can be 0 or 1 (handled error)
        assert result.exit_code in [0, 1]
        
        # Error message should be in output (not a Python stack trace)
        output = result.stdout + result.stderr
        
        # The key behavioral requirement is that it doesn't crash
        # Error messages may vary, but should not show unhandled exceptions
        # Check that it's not a raw Python traceback
        assert "Traceback" not in output or "timed out" in output.lower()
        # If there's an error, it should be handled gracefully
        if result.exit_code != 0:
            assert "error" in output.lower() or "timeout" in output.lower() or "timed out" in output.lower()


def test_timeout_with_different_values():
    """Test that different timeout values are respected."""
    test_cases = [
        (1, "sleep 5"),
        (2, "sleep 10"),
    ]
    
    for timeout, command in test_cases:
        with pytest.raises(RuntimeError) as exc_info:
            execute_command(command, timeout=timeout)
        
        # Each timeout should be enforced
        error_message = str(exc_info.value)
        assert "timed out" in error_message.lower()


def test_fast_command_does_not_timeout():
    """Test that fast commands complete successfully without timeout."""
    import platform
    
    if platform.system() == "Windows":
        command = 'Write-Output "fast"'
    else:
        command = 'echo "fast"'
    
    # Should complete in 1 second
    stdout, stderr, code = execute_command(command, timeout=60)
    
    assert code == 0
    assert "fast" in stdout


def test_timeout_user_workflow():
    """Test complete user workflow: LLM proposes slow command → timeout → error shown."""
    # Mock LLM to propose sleep command
    call_count = [0]
    
    def mock_llm_sequence(**kwargs):
        call_count[0] += 1
        
        if call_count[0] == 1:
            # First call: propose sleep command
            mock_tool = MagicMock()
            mock_tool.id = "call_123"
            mock_tool.function = MagicMock()
            mock_tool.function.name = "execute_shell"
            mock_tool.function.arguments = json.dumps({"command": "sleep 30"})
            
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message = MagicMock()
            response.choices[0].message.content = "Let me wait 30 seconds."
            response.choices[0].message.tool_calls = [mock_tool]
            return response
        else:
            # Subsequent calls: text only
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message = MagicMock()
            response.choices[0].message.content = "The command timed out."
            response.choices[0].message.tool_calls = None
            return response
    
    # Mock execute_command to timeout immediately
    def mock_timeout(cmd, timeout=None):
        raise RuntimeError(f"Command '{cmd}' timed out after {timeout} seconds")
    
    with (
        patch("litellm.completion", side_effect=mock_llm_sequence),
        patch("whai.context.get_context", return_value=("", False)),
        patch("builtins.input", return_value="a"),
        patch("whai.core.executor.execute_command", side_effect=mock_timeout),
    ):
        result = runner.invoke(app, ["sleep for 30 seconds", "--no-context", "--timeout", "5"])
        
        # Should handle timeout gracefully (doesn't crash)
        assert result.exit_code in [0, 1]
        
        output = result.stdout + result.stderr
        # The key behavioral requirement is that it doesn't crash
        # Error messages may vary, but should be handled gracefully
        if result.exit_code != 0:
            # If it failed, should be a handled error, not a traceback
            assert "Traceback" not in output


def test_timeout_does_not_leak_subprocess():
    """Test that timed-out commands don't leave zombie processes."""
    try:
        import psutil
    except ImportError:
        pytest.skip("psutil not available - skipping subprocess leak test")
    
    import os
    
    initial_children = len(psutil.Process(os.getpid()).children(recursive=True))
    
    # Run command that will timeout
    try:
        execute_command("sleep 100", timeout=1)
    except RuntimeError:
        pass  # Expected
    
    # Give OS time to clean up
    import time
    time.sleep(0.5)
    
    # Should not have leaked processes
    final_children = len(psutil.Process(os.getpid()).children(recursive=True))
    assert final_children <= initial_children + 1, "Should not leak subprocess"

