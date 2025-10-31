"""Tests for context module."""

import os
import subprocess
from unittest.mock import MagicMock, patch

from terma import context


def test_is_wsl_on_windows():
    """Test WSL detection on Windows."""
    with patch("os.name", "nt"), patch("subprocess.run") as mock_run:
        # Simulate WSL available
        mock_run.return_value = MagicMock(returncode=0)
        assert context._is_wsl() is True

        # Simulate WSL not available
        mock_run.return_value = MagicMock(returncode=1)
        assert context._is_wsl() is False


def test_is_wsl_on_unix():
    """Test WSL detection on Unix (should always be False)."""
    with patch("os.name", "posix"):
        assert context._is_wsl() is False


def test_is_wsl_timeout():
    """Test WSL detection handles timeouts gracefully."""
    with (
        patch("os.name", "nt"),
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired("wsl", 2)),
    ):
        assert context._is_wsl() is False


def test_get_tmux_context_not_in_tmux():
    """Test that tmux context returns None when not in tmux."""
    with patch.dict("os.environ", {}, clear=True):
        result = context._get_tmux_context()
        assert result is None


def test_get_tmux_context_unix():
    """Test tmux context capture on Unix."""
    mock_output = "command output line 1\ncommand output line 2\n"

    with (
        patch.dict("os.environ", {"TMUX": "/tmp/tmux-1000/default,12345,0"}),
        patch("os.name", "posix"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)

        result = context._get_tmux_context()

        assert result == mock_output
        mock_run.assert_called_once()
        assert "tmux" in mock_run.call_args[0][0]


def test_get_tmux_context_windows_wsl():
    """Test tmux context capture on Windows with WSL."""
    mock_output = "command output from WSL\n"

    with (
        patch.dict("os.environ", {"TMUX": "/tmp/tmux-1000/default,12345,0"}),
        patch("os.name", "nt"),
        patch("terma.context._is_wsl", return_value=True),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)

        result = context._get_tmux_context()

        assert result == mock_output
        mock_run.assert_called_once()
        # Should call wsl tmux
        assert mock_run.call_args[0][0][0] == "wsl"


def test_get_tmux_context_failure():
    """Test tmux context returns None on command failure."""
    with (
        patch.dict("os.environ", {"TMUX": "/tmp/tmux-1000/default,12345,0"}),
        patch("os.name", "posix"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=1, stdout="")

        result = context._get_tmux_context()
        assert result is None


def test_get_shell_from_env():
    """Test shell detection from environment."""
    with patch.dict("os.environ", {"SHELL": "/bin/zsh"}, clear=True):
        assert context._get_shell_from_env() == "zsh"

    with patch.dict("os.environ", {"SHELL": "/bin/bash"}, clear=True):
        assert context._get_shell_from_env() == "bash"

    with patch.dict("os.environ", {"SHELL": "/usr/bin/fish"}, clear=True):
        # Unknown shell, should fallback based on platform
        detected = context._get_shell_from_env()
        if os.name == "nt":
            assert detected == "cmd"
        else:
            assert detected == "unknown"

    # Explicit PowerShell detection on Windows when PS markers are present
    with patch.dict(
        "os.environ",
        {"PSModulePath": "C\\Windows\\System32\\WindowsPowerShell\\v1.0"},
        clear=True,
    ):
        if os.name == "nt":
            assert context._get_shell_from_env() == "powershell"

    with patch.dict("os.environ", {}, clear=True):
        # With no environment markers, should fallback based on platform
        detected = context._get_shell_from_env()
        if os.name == "nt":
            assert detected == "cmd"
        else:
            assert detected == "unknown"


def test_parse_zsh_history(tmp_path):
    """Test parsing zsh history file."""
    history_file = tmp_path / ".zsh_history"
    history_file.write_text(
        ": 1234567890:0;ls -la\n"
        ": 1234567891:0;cd /tmp\n"
        ": 1234567892:0;echo 'hello world'\n"
    )

    commands = context._parse_zsh_history(history_file, max_commands=10)

    assert len(commands) == 3
    assert commands[0] == "ls -la"
    assert commands[1] == "cd /tmp"
    assert commands[2] == "echo 'hello world'"


def test_parse_zsh_history_max_commands(tmp_path):
    """Test that zsh history respects max_commands."""
    history_file = tmp_path / ".zsh_history"
    history_content = "\n".join([f": {i}:0;command{i}" for i in range(100)])
    history_file.write_text(history_content)

    commands = context._parse_zsh_history(history_file, max_commands=5)

    assert len(commands) == 5
    assert commands[-1] == "command99"


def test_parse_zsh_history_nonexistent(tmp_path):
    """Test parsing nonexistent zsh history file."""
    history_file = tmp_path / "nonexistent.history"
    commands = context._parse_zsh_history(history_file)
    assert commands == []


def test_parse_bash_history(tmp_path):
    """Test parsing bash history file."""
    history_file = tmp_path / ".bash_history"
    history_file.write_text("ls -la\ncd /tmp\necho 'hello world'\n")

    commands = context._parse_bash_history(history_file, max_commands=10)

    assert len(commands) == 3
    assert commands[0] == "ls -la"
    assert commands[1] == "cd /tmp"
    assert commands[2] == "echo 'hello world'"


def test_parse_bash_history_max_commands(tmp_path):
    """Test that bash history respects max_commands."""
    history_file = tmp_path / ".bash_history"
    history_content = "\n".join([f"command{i}" for i in range(100)])
    history_file.write_text(history_content)

    commands = context._parse_bash_history(history_file, max_commands=5)

    assert len(commands) == 5
    assert commands[-1] == "command99"


def test_parse_bash_history_nonexistent(tmp_path):
    """Test parsing nonexistent bash history file."""
    history_file = tmp_path / "nonexistent.history"
    commands = context._parse_bash_history(history_file)
    assert commands == []


def test_get_history_context_zsh(tmp_path):
    """Test getting history context for zsh."""
    history_file = tmp_path / ".zsh_history"
    history_file.write_text(": 1234567890:0;ls\n: 1234567891:0;cd /tmp\n")

    with (
        patch("terma.context._get_shell_from_env", return_value="zsh"),
        patch("pathlib.Path.home", return_value=tmp_path),
    ):
        result = context._get_history_context(max_commands=10)

        assert result is not None
        assert "ls" in result
        assert "cd /tmp" in result
        assert "Recent command history:" in result


def test_get_history_context_bash(tmp_path):
    """Test getting history context for bash."""
    history_file = tmp_path / ".bash_history"
    history_file.write_text("ls\ncd /tmp\n")

    with (
        patch("terma.context._get_shell_from_env", return_value="bash"),
        patch("pathlib.Path.home", return_value=tmp_path),
    ):
        result = context._get_history_context(max_commands=10)

        assert result is not None
        assert "ls" in result
        assert "cd /tmp" in result


def test_get_history_context_no_history(tmp_path):
    """Test getting history context when no history file exists."""
    with (
        patch("terma.context._get_shell_from_env", return_value="bash"),
        patch("pathlib.Path.home", return_value=tmp_path),
    ):
        result = context._get_history_context(max_commands=10)
        assert result is None


def test_get_context_prefers_tmux():
    """Test that get_context prefers tmux over history."""
    with (
        patch("terma.context._get_tmux_context", return_value="tmux output"),
        patch("terma.context._get_history_context", return_value="history output"),
    ):
        context_str, is_deep = context.get_context()

        assert context_str == "tmux output"
        assert is_deep is True


def test_get_context_falls_back_to_history():
    """Test that get_context falls back to history when tmux is unavailable."""
    with (
        patch("terma.context._get_tmux_context", return_value=None),
        patch("terma.context._get_history_context", return_value="history output"),
    ):
        context_str, is_deep = context.get_context()

        assert context_str == "history output"
        assert is_deep is False


def test_get_context_no_context_available():
    """Test get_context when no context is available."""
    with (
        patch("terma.context._get_tmux_context", return_value=None),
        patch("terma.context._get_history_context", return_value=None),
    ):
        context_str, is_deep = context.get_context()

        assert context_str == ""
        assert is_deep is False


def test_get_history_context_powershell_on_windows(tmp_path):
    """Test getting history context from PowerShell PSReadLine on Windows."""
    # Simulate %APPDATA% structure
    appdata = tmp_path / "Roaming"
    psrl1 = appdata / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine"
    psrl1.mkdir(parents=True)
    history_file = psrl1 / "ConsoleHost_history.txt"
    history_file.write_text("dir\ncd C:\\\\\Temp\n")

    with (
        patch("os.name", "nt"),
        patch.dict("os.environ", {"APPDATA": str(appdata)}),
    ):
        result = context._get_history_context(max_commands=10)

    assert result is not None
    assert "Recent command history:" in result
    assert "dir" in result
    assert "cd C:\\Temp" in result


def test_get_history_context_powershell_core_on_windows(tmp_path):
    """Test getting history context from PowerShell Core PSReadLine on Windows."""
    appdata = tmp_path / "Roaming"
    psrl2 = appdata / "Microsoft" / "PowerShell" / "PSReadLine"
    psrl2.mkdir(parents=True)
    history_file = psrl2 / "ConsoleHost_history.txt"
    history_file.write_text("Get-ChildItem\n$PSVersionTable\n")

    with (
        patch("os.name", "nt"),
        patch.dict("os.environ", {"APPDATA": str(appdata)}),
    ):
        result = context._get_history_context(max_commands=10)

    assert result is not None
    assert "Get-ChildItem" in result
    assert "$PSVersionTable" in result
