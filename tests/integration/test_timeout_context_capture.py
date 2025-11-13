"""Integration tests for timeout context capture in session logs.

These tests verify that command timeouts are properly logged to the session
transcript, enabling deep context capture for subsequent whai queries.
"""

import os
import platform
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whai.core.executor import run_conversation_loop
from whai.core.session_logger import SessionLogger
from whai.llm import LLMProvider


@pytest.fixture
def session_directory(monkeypatch):
    """Create a temporary session directory with a transcript log file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        sess_dir = config_dir / "whai" / "sessions"
        sess_dir.mkdir(parents=True)
        
        # Create a transcript log file (as PowerShell would)
        transcript_log = sess_dir / "session_20250101_120000.log"
        transcript_log.write_text("PowerShell transcript content\n", encoding='utf-8')
        
        # Mock get_config_dir
        def mock_get_config_dir():
            return config_dir / "whai"
        
        monkeypatch.setattr(
            "whai.core.session_logger.get_config_dir",
            mock_get_config_dir
        )
        
        # Enable session
        old_active = os.environ.get("WHAI_SESSION_ACTIVE")
        os.environ["WHAI_SESSION_ACTIVE"] = "1"
        
        yield sess_dir, transcript_log
        
        # Restore environment
        if old_active is None:
            os.environ.pop("WHAI_SESSION_ACTIVE", None)
        else:
            os.environ["WHAI_SESSION_ACTIVE"] = old_active


@pytest.mark.skipif(platform.system() != "Windows", reason="SessionLogger is Windows-only")
def test_timeout_is_logged_to_session(session_directory):
    """Test that command timeout is logged to session for deep context."""
    sess_dir, _ = session_directory
    
    # Create a mock LLM provider that proposes a long-running command
    mock_provider = MagicMock(spec=LLMProvider)
    
    # First LLM call: propose command
    mock_provider.send_message.return_value = iter([
        {"type": "text", "content": "I'll run a long command."},
        {
            "type": "tool_call",
            "id": "call_123",
            "name": "execute_shell",
            "arguments": {"command": "Start-Sleep -Seconds 70"}
        }
    ])
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Run a command that takes 70 seconds"}
    ]
    
    # Mock approval (user approves)
    with patch("whai.core.executor.approval_loop", return_value="Start-Sleep -Seconds 70"):
        # Mock execute_command to timeout
        with patch("whai.core.executor.execute_command") as mock_exec:
            mock_exec.side_effect = RuntimeError(
                "Command timed out after 60 seconds. You can change timeout limits with the --timeout flag"
            )
            
            # Run conversation loop (it should handle timeout gracefully)
            try:
                run_conversation_loop(mock_provider, messages, timeout=60)
            except Exception:
                pass  # Expected to end after one iteration
    
    # Check that timeout was logged to session file
    whai_log = sess_dir / "session_20250101_120000_whai.log"
    assert whai_log.exists()
    
    content = whai_log.read_text(encoding='utf-8')
    
    # Verify that the command and timeout are logged
    assert "$ Start-Sleep -Seconds 70\n" in content
    assert "[COMMAND TIMED OUT after 60s]\n" in content


@pytest.mark.skipif(platform.system() != "Windows", reason="SessionLogger is Windows-only")
def test_general_failure_is_logged_to_session(session_directory):
    """Test that general command failures are logged to session."""
    sess_dir, _ = session_directory
    
    mock_provider = MagicMock(spec=LLMProvider)
    
    # LLM proposes a command
    mock_provider.send_message.return_value = iter([
        {"type": "text", "content": "Running command."},
        {
            "type": "tool_call",
            "id": "call_456",
            "name": "execute_shell",
            "arguments": {"command": "invalid-command"}
        }
    ])
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Run invalid-command"}
    ]
    
    with patch("whai.core.executor.approval_loop", return_value="invalid-command"):
        with patch("whai.core.executor.execute_command") as mock_exec:
            mock_exec.side_effect = RuntimeError("Command not found: invalid-command")
            
            try:
                run_conversation_loop(mock_provider, messages, timeout=60)
            except Exception:
                pass
    
    whai_log = sess_dir / "session_20250101_120000_whai.log"
    content = whai_log.read_text(encoding='utf-8')
    
    assert "$ invalid-command\n" in content
    assert "[COMMAND FAILED: Command not found: invalid-command]\n" in content


@pytest.mark.skipif(platform.system() != "Windows", reason="SessionLogger is Windows-only")
def test_session_logger_captures_sequence_with_timeout_then_success(session_directory):
    """Test that session log captures a sequence: timeout → success."""
    sess_dir, _ = session_directory
    
    logger = SessionLogger()
    
    # First command times out
    logger.log_command("whai run a command that takes 70 seconds")
    logger.print("I'll run this command:")
    logger.log_command("Start-Sleep -Seconds 70")
    logger.log_command_failure("Command timed out after 60 seconds", timeout=60)
    logger.print("The command timed out.")
    
    # Second command succeeds
    logger.log_command("whai show me the current time")
    logger.print("I'll show you the time:")
    logger.log_command("Get-Date")
    logger.log_command_output("Friday, January 1, 2025 12:00:00\n", "", 0)
    logger.print("Here's the current time.")
    
    whai_log = sess_dir / "session_20250101_120000_whai.log"
    content = whai_log.read_text(encoding='utf-8')
    
    # Verify full sequence is captured
    assert content.index("$ Start-Sleep -Seconds 70") < content.index("[COMMAND TIMED OUT after 60s]")
    assert content.index("[COMMAND TIMED OUT after 60s]") < content.index("$ Get-Date")
    assert content.index("$ Get-Date") < content.index("Friday, January 1, 2025 12:00:00")


def test_session_logger_disabled_on_non_windows():
    """SessionLogger should be disabled on non-Windows platforms."""
    if platform.system() == "Windows":
        pytest.skip("This test is for non-Windows platforms only")
    
    os.environ["WHAI_SESSION_ACTIVE"] = "1"
    
    logger = SessionLogger()
    
    # Should be disabled
    assert logger.enabled is False
    
    # Calls should not crash
    logger.log_command("test")
    logger.log_command_failure("test error", timeout=60)

