"""Tests for context module."""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whai import context
from whai.context.history import (
    BashHandler,
    CMDHandler,
    PowerShellHandler,
    ZshHandler,
    _get_handler_for_shell,
    get_additional_context,
)


def test_get_context_prefers_tmux():
    """Test that get_context prefers tmux over history."""
    with (
        patch("whai.context.capture._get_tmux_context", return_value="tmux output"),
        patch("whai.context.capture._get_history_context", return_value="history output"),
        patch("whai.context.capture.get_additional_context", return_value=None),
    ):
        context_str, is_deep = context.get_context()

        assert context_str == "tmux output"
        assert is_deep is True


def test_get_context_falls_back_to_history():
    """Test that get_context falls back to history when tmux is unavailable."""
    with (
        patch("whai.context.capture._get_tmux_context", return_value=None),
        patch("whai.context.capture._get_history_context", return_value="history output"),
        patch("whai.context.capture.get_additional_context", return_value=None),
        patch.dict(os.environ, {}, clear=True),
    ):
        context_str, is_deep = context.get_context()

        assert context_str == "history output"
        assert is_deep is False


def test_get_context_combines_history_and_additional_context():
    """Test that get_context combines history and additional context."""
    with (
        patch("whai.context.capture._get_tmux_context", return_value=None),
        patch("whai.context.capture._get_history_context", return_value="history output"),
        patch("whai.context.capture.get_additional_context", return_value="error output"),
    ):
        context_str, is_deep = context.get_context()

        assert "history output" in context_str
        assert "error output" in context_str
        assert is_deep is False


def test_get_context_no_context_available():
    """Test get_context when no context is available."""
    with (
        patch("whai.context.capture._get_tmux_context", return_value=None),
        patch("whai.context.capture._get_history_context", return_value=None),
        patch("whai.context.capture.get_additional_context", return_value=None),
        patch.dict(os.environ, {}, clear=True),
    ):
        context_str, is_deep = context.get_context()

        assert context_str == ""
        assert is_deep is False


def test_get_context_tmux_active_but_empty():
    """Test get_context when tmux is active but capture is empty (new session)."""
    with (
        patch("whai.context.capture._get_tmux_context", return_value=""),
        patch("whai.context.capture._get_history_context", return_value="history output"),
        patch("whai.context.capture.get_additional_context", return_value=None),
        patch.dict(os.environ, {"TMUX": "/tmp/tmux-1000/default,123,456"}),
    ):
        context_str, is_deep = context.get_context()

        # Should return empty string with is_deep=True to indicate tmux is active
        assert context_str == ""
        assert is_deep is True


def test_bash_handler_get_history_context(tmp_path, monkeypatch):
    """Test BashHandler.get_history_context()."""
    handler = BashHandler(shell_name="bash")
    
    # Create a mock bash history file
    history_file = tmp_path / ".bash_history"
    history_file.write_text("git status\nls -la\ngit push\n")
    
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    
    result = handler.get_history_context(max_commands=3)
    
    assert result is not None
    assert "Recent command history:" in result
    assert "git status" in result
    assert "ls -la" in result
    assert "git push" in result


def test_bash_handler_get_history_context_no_file(tmp_path, monkeypatch):
    """Test BashHandler when history file doesn't exist."""
    handler = BashHandler(shell_name="bash")
    
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    
    result = handler.get_history_context()
    
    assert result is None


def test_bash_handler_exclude_command(tmp_path, monkeypatch):
    """Test BashHandler excludes matching command."""
    handler = BashHandler(shell_name="bash")
    
    history_file = tmp_path / ".bash_history"
    history_file.write_text("git status\nls -la\nwhai test query\n")
    
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    
    result = handler.get_history_context(exclude_command="whai test query")
    
    assert result is not None
    assert "whai test query" not in result
    assert "git status" in result
    assert "ls -la" in result


def test_zsh_handler_get_history_context(tmp_path, monkeypatch):
    """Test ZshHandler.get_history_context()."""
    handler = ZshHandler(shell_name="zsh")
    
    # Create a mock zsh history file with timestamp format
    history_file = tmp_path / ".zsh_history"
    history_file.write_text(": 1234567890:0;git status\n: 1234567891:0;ls -la\n")
    
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    
    result = handler.get_history_context(max_commands=2)
    
    assert result is not None
    assert "Recent command history:" in result
    assert "git status" in result
    assert "ls -la" in result


def test_zsh_handler_simple_format(tmp_path, monkeypatch):
    """Test ZshHandler handles simple command format."""
    handler = ZshHandler(shell_name="zsh")
    
    history_file = tmp_path / ".zsh_history"
    history_file.write_text("git status\nls -la\n")
    
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    
    result = handler.get_history_context(max_commands=2)
    
    assert result is not None
    assert "git status" in result
    assert "ls -la" in result


@pytest.mark.skipif("posix" in __import__("os").name, reason="Windows-only test; skipped on Linux")
def test_powershell_handler_get_history_context(tmp_path, monkeypatch):
    """Test PowerShellHandler.get_history_context()."""
    handler = PowerShellHandler(shell_name="pwsh")
    
    # Create a mock PSReadLine history file
    appdata_path = tmp_path / "Microsoft" / "PowerShell" / "PSReadLine"
    appdata_path.mkdir(parents=True)
    history_file = appdata_path / "ConsoleHost_history.txt"
    history_file.write_text("Get-Process\nGet-ChildItem\n")
    
    monkeypatch.setattr("os.name", "nt")
    monkeypatch.setattr("os.environ", {"APPDATA": str(tmp_path)})
    
    result = handler.get_history_context(max_commands=2)
    
    assert result is not None
    assert "Recent command history:" in result
    assert "Get-Process" in result
    assert "Get-ChildItem" in result


## PowerShell additional context tests removed (feature deprecated)


## (removed)


## (removed)


## (removed)


## (removed)


## (removed)


## (removed)


## (removed)


def test_powershell_handler_get_additional_context_non_windows(monkeypatch):
    """Test PowerShellHandler.get_additional_context() returns None on non-Windows."""
    handler = PowerShellHandler(shell_name="pwsh")
    
    monkeypatch.setattr("os.name", "posix")
    
    result = handler.get_additional_context()
    
    assert result is None


def test_cmd_handler_get_history_context(monkeypatch):
    """Test CMDHandler.get_history_context() via doskey."""
    handler = CMDHandler(shell_name="cmd")
    
    mock_output = "dir\ncd projects\necho hello\n"
    
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output
        mock_run.return_value = mock_result
        
        monkeypatch.setattr("os.name", "nt")
        
        result = handler.get_history_context(max_commands=3)
        
        assert result is not None
        assert "Recent command history:" in result
        assert "dir" in result
        assert "cd projects" in result
        assert "echo hello" in result
        mock_run.assert_called_once_with(
            ["doskey", "/history"],
            capture_output=True,
            text=True,
            timeout=5,
        )


def test_cmd_handler_non_windows(monkeypatch):
    """Test CMDHandler returns None on non-Windows."""
    handler = CMDHandler(shell_name="cmd")
    
    monkeypatch.setattr("os.name", "posix")
    
    result = handler.get_history_context()
    
    assert result is None


def test_get_handler_for_shell_bash():
    """Test _get_handler_for_shell() returns BashHandler for bash."""
    handler = _get_handler_for_shell("bash")
    
    assert handler is not None
    assert isinstance(handler, BashHandler)
    assert handler.shell_name == "bash"


def test_get_handler_for_shell_zsh():
    """Test _get_handler_for_shell() returns ZshHandler for zsh."""
    handler = _get_handler_for_shell("zsh")
    
    assert handler is not None
    assert isinstance(handler, ZshHandler)
    assert handler.shell_name == "zsh"


def test_get_handler_for_shell_pwsh():
    """Test _get_handler_for_shell() returns PowerShellHandler for pwsh."""
    handler = _get_handler_for_shell("pwsh")
    
    assert handler is not None
    assert isinstance(handler, PowerShellHandler)
    assert handler.shell_name == "pwsh"


def test_get_handler_for_shell_cmd(monkeypatch):
    """Test _get_handler_for_shell() returns CMDHandler for cmd on Windows."""
    monkeypatch.setattr("os.name", "nt")
    
    handler = _get_handler_for_shell("cmd")
    
    assert handler is not None
    assert isinstance(handler, CMDHandler)
    assert handler.shell_name == "cmd"


def test_get_handler_for_shell_windows_fallback(monkeypatch):
    """Test _get_handler_for_shell() falls back to CMD on Windows for unknown shell."""
    monkeypatch.setattr("os.name", "nt")
    
    handler = _get_handler_for_shell("unknown")
    
    assert handler is not None
    assert isinstance(handler, CMDHandler)


def test_get_additional_context_powershell(monkeypatch):
    """Test get_additional_context() for PowerShell."""
    with patch("whai.context.history._get_handler_for_shell") as mock_get_handler:
        handler = PowerShellHandler(shell_name="pwsh")
        mock_get_handler.return_value = handler
        
        with patch.object(handler, "get_additional_context", return_value="error context"):
            result = get_additional_context(shell="pwsh")
            
            assert result == "error context"


def test_get_additional_context_no_handler(monkeypatch):
    """Test get_additional_context() returns None when no handler found."""
    with patch("whai.context.history._get_handler_for_shell", return_value=None):
        result = get_additional_context(shell="unknown")
        
        assert result is None


def test_get_additional_context_no_additional_context(monkeypatch):
    """Test get_additional_context() returns None when handler has no additional context."""
    with patch("whai.context.history._get_handler_for_shell") as mock_get_handler:
        handler = BashHandler(shell_name="bash")
        mock_get_handler.return_value = handler
        
        result = get_additional_context(shell="bash")
        
        assert result is None


# PowerShell history tests removed - they were reading actual user history
# instead of being properly isolated. The core PowerShell history parsing
# is covered by other tests.
