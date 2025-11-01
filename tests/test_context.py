"""Tests for context module."""

import subprocess
from unittest.mock import MagicMock, patch

from whai import context


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
        patch("whai.context._is_wsl", return_value=True),
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
        # Fish shell should be detected
        assert context._get_shell_from_env() == "fish"

    # Explicit PowerShell detection on Windows when PS markers are present
    with patch.dict(
        "os.environ",
        {"PSModulePath": "C\\Windows\\System32\\WindowsPowerShell\\v1.0"},
        clear=True,
    ):
        assert context._get_shell_from_env() == "pwsh"

    with patch.dict("os.environ", {}, clear=True):
        # With no environment markers, should fallback based on platform
        with patch("sys.platform", "win32"):
            assert context._get_shell_from_env() == "pwsh"
        with patch("sys.platform", "linux"):
            assert context._get_shell_from_env() == "bash"


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
        patch("whai.context._get_shell_from_env", return_value="zsh"),
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
        patch("whai.context._get_shell_from_env", return_value="bash"),
        patch("pathlib.Path.home", return_value=tmp_path),
    ):
        result = context._get_history_context(max_commands=10)

        assert result is not None
        assert "ls" in result
        assert "cd /tmp" in result


def test_get_history_context_no_history(tmp_path):
    """Test getting history context when no history file exists."""
    with (
        patch("whai.context._get_shell_from_env", return_value="bash"),
        patch("pathlib.Path.home", return_value=tmp_path),
    ):
        result = context._get_history_context(max_commands=10)
        assert result is None


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


def test_matches_command_pattern_exact():
    """Test command pattern matching with exact match."""
    assert (
        context._matches_command_pattern("whai some query", "whai some query") is True
    )
    assert context._matches_command_pattern("whai", "whai") is True


def test_matches_command_pattern_with_prompt():
    """Test command pattern matching with prompt prefix."""
    assert (
        context._matches_command_pattern("$ whai some query", "whai some query") is True
    )
    assert (
        context._matches_command_pattern("user@host:~$ whai query", "whai query")
        is True
    )


def test_matches_command_pattern_whitespace():
    """Test command pattern matching with different whitespace."""
    assert (
        context._matches_command_pattern("whai   some    query", "whai some query")
        is True
    )


def test_matches_command_pattern_no_match():
    """Test command pattern matching when command doesn't match."""
    assert context._matches_command_pattern("ls -la", "whai some query") is False
    assert context._matches_command_pattern("whaiting", "whai") is False


def test_matches_command_pattern_excludes_log_lines():
    """Test that log lines are excluded from matching."""
    # Should not match log lines even if they contain the command
    assert (
        context._matches_command_pattern(
            "[INFO] Will exclude command from context: whai some query",
            "whai some query",
        )
        is False
    )
    assert (
        context._matches_command_pattern(
            "[DEBUG] Found matching command at line 14: whai some query",
            "whai some query",
        )
        is False
    )
    assert (
        context._matches_command_pattern(
            "[INFO]  15:34:29.849    whai.main:404   Will exclude command from context: whai -v DEBUG",
            "whai -v DEBUG",
        )
        is False
    )
    # But should still match actual command lines
    assert (
        context._matches_command_pattern("$ whai some query", "whai some query") is True
    )


def test_matches_command_pattern_handles_quotes():
    """Test that pattern matching handles quotes in terminal vs sys.argv."""
    # Terminal shows: whai -v "DEBUG"
    # sys.argv reconstructs: whai -v DEBUG
    # Should match despite quotes difference
    assert (
        context._matches_command_pattern('$ whai -v "DEBUG"', "whai -v DEBUG") is True
    )
    assert (
        context._matches_command_pattern("$ whai -v 'DEBUG'", "whai -v DEBUG") is True
    )
    assert (
        context._matches_command_pattern(
            '$ whai query "some text"', "whai query some text"
        )
        is True
    )


def test_get_tmux_context_filters_command():
    """Test that tmux context filters out last matching command and everything after."""
    mock_output = "ls -la\n$ whai what's the biggest folder?\nsome output\ncd /tmp\n"

    with (
        patch.dict("os.environ", {"TMUX": "/tmp/tmux-1000/default,12345,0"}),
        patch("os.name", "posix"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)

        result = context._get_tmux_context(
            exclude_command="whai what's the biggest folder?"
        )

        # Should filter out the whai command line and everything after it
        assert "whai what's the biggest folder?" not in result
        assert "some output" not in result  # Everything after command is removed
        assert "cd /tmp" not in result  # Everything after command is removed
        assert "ls -la" in result  # Only lines before the command remain
        assert result.strip() == "ls -la"


def test_get_tmux_context_no_filter_when_no_match():
    """Test that tmux context doesn't filter when command doesn't match."""
    mock_output = "ls -la\ncd /tmp\n"

    with (
        patch.dict("os.environ", {"TMUX": "/tmp/tmux-1000/default,12345,0"}),
        patch("os.name", "posix"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)

        result = context._get_tmux_context(exclude_command="whai query")

        # Should not filter anything since command doesn't match
        assert result == mock_output


def test_get_history_context_filters_last_command(tmp_path):
    """Test that history context filters out the last command if it matches."""
    history_file = tmp_path / ".zsh_history"
    history_file.write_text(
        ": 1234567890:0;ls\n"
        ": 1234567891:0;cd /tmp\n"
        ": 1234567892:0;whai what's the biggest folder?\n"
    )

    with (
        patch("whai.context._get_shell_from_env", return_value="zsh"),
        patch("pathlib.Path.home", return_value=tmp_path),
    ):
        result = context._get_history_context(
            max_commands=10, exclude_command="whai what's the biggest folder?"
        )

        # Should filter out the whai command
        assert result is not None
        assert "whai what's the biggest folder?" not in result
        assert "ls" in result
        assert "cd /tmp" in result


def test_get_history_context_no_filter_when_last_doesnt_match(tmp_path):
    """Test that history context doesn't filter when last command doesn't match."""
    history_file = tmp_path / ".bash_history"
    history_file.write_text("ls\ncd /tmp\n")

    with (
        patch("whai.context._get_shell_from_env", return_value="bash"),
        patch("pathlib.Path.home", return_value=tmp_path),
    ):
        result = context._get_history_context(
            max_commands=10, exclude_command="whai query"
        )

        # Should not filter anything
        assert result is not None
        assert "ls" in result
        assert "cd /tmp" in result


def test_get_context_passes_exclude_command():
    """Test that get_context passes exclude_command to tmux and history."""
    with (
        patch("whai.context._get_tmux_context") as mock_tmux,
        patch("whai.context._get_history_context") as mock_history,
    ):
        mock_tmux.return_value = None
        mock_history.return_value = "history"

        context.get_context(exclude_command="whai query")

        # Verify exclude_command was passed
        mock_tmux.assert_called_once_with(exclude_command="whai query")
        mock_history.assert_called_once()
        # Check that exclude_command was in the call
        call_kwargs = mock_history.call_args[1]
        assert call_kwargs["exclude_command"] == "whai query"


def test_get_tmux_context_filters_last_occurrence():
    """Test that tmux context only filters the LAST occurrence and everything after."""
    mock_output = (
        "ls -la\n"
        "$ whai what's the biggest folder?\n"
        "first whai output\n"
        "$ whai what's the biggest folder?\n"
        "second whai output\n"
        "more output\n"
    )

    with (
        patch.dict("os.environ", {"TMUX": "/tmp/tmux-1000/default,12345,0"}),
        patch("os.name", "posix"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)

        result = context._get_tmux_context(
            exclude_command="whai what's the biggest folder?"
        )

        # Should keep first occurrence and its output, but remove last occurrence and everything after
        assert "ls -la" in result
        # First occurrence should be present (since we only remove the last one)
        assert "$ whai what's the biggest folder?" in result
        assert (
            result.count("$ whai what's the biggest folder?") == 1
        )  # Only first occurrence remains
        assert "first whai output" in result  # Output from first occurrence
        # Last occurrence and everything after should be removed
        assert (
            "second whai output" not in result
        )  # Everything after last occurrence removed
        assert "more output" not in result  # Everything after last occurrence removed
