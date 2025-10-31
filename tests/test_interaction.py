"""Tests for interaction module."""

from unittest.mock import MagicMock, patch

import pytest

from terma import interaction


def test_shell_session_init_unix():
    """Test ShellSession initialization on Unix."""
    with (
        patch("os.name", "posix"),
        patch("subprocess.Popen") as mock_popen,
        patch("time.sleep"),
    ):
        mock_popen.return_value = MagicMock()

        session = interaction.ShellSession("/bin/bash")

        assert session.shell == "/bin/bash"
        assert session.process is not None
        mock_popen.assert_called_once()


def test_shell_session_init_windows():
    """Test ShellSession initialization on Windows."""
    with patch("os.name", "nt"), patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()

        session = interaction.ShellSession("cmd.exe")

        assert session.shell == "cmd.exe"
        assert session.process is not None


def test_shell_session_default_shell_unix():
    """Test default shell selection on Unix."""
    with (
        patch("os.name", "posix"),
        patch("subprocess.Popen") as mock_popen,
        patch("time.sleep"),
    ):
        mock_popen.return_value = MagicMock()

        session = interaction.ShellSession()

        assert session.shell == "/bin/bash"


def test_shell_session_default_shell_windows():
    """Test default shell selection on Windows."""
    with patch("os.name", "nt"), patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()

        session = interaction.ShellSession()

        assert session.shell == "cmd.exe"


def test_execute_command_success():
    """Test successful command execution."""
    with (
        patch("os.name", "posix"),
        patch("subprocess.Popen") as mock_popen,
        patch("time.sleep"),
        patch("random.randint", return_value=123456),
    ):
        # Mock process
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running

        # Mock stdin
        mock_process.stdin = MagicMock()

        # Mock stdout and stderr
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()

        mock_popen.return_value = mock_process

        with patch.object(
            interaction.ShellSession, "_read_line_with_timeout"
        ) as mock_read:
            # Simulate reading lines from stdout, then marker
            # Alternate between stdout and stderr calls
            def side_effect_func(stream, timeout):
                # Track which call this is
                if not hasattr(side_effect_func, "call_count"):
                    side_effect_func.call_count = 0
                    side_effect_func.stdout_lines = [
                        "file1.txt\n",
                        "file2.txt\n",
                        "___TERMA_CMD_DONE_123456___\n",
                    ]

                if stream == mock_process.stdout and side_effect_func.stdout_lines:
                    result = side_effect_func.stdout_lines.pop(0)
                    return result
                else:
                    return None

            mock_read.side_effect = side_effect_func

            session = interaction.ShellSession()
            stdout, stderr, code = session.execute_command("ls")

            assert "file1.txt" in stdout
            assert "file2.txt" in stdout
            assert "___TERMA_CMD_DONE_123456___" not in stdout


def test_execute_command_dead_process():
    """Test that execute_command raises error if process is dead."""
    with (
        patch("os.name", "posix"),
        patch("subprocess.Popen") as mock_popen,
        patch("time.sleep"),
    ):
        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # Process has exited
        mock_popen.return_value = mock_process

        session = interaction.ShellSession()

        with pytest.raises(RuntimeError, match="Shell process is not running"):
            session.execute_command("ls")


def test_execute_command_timeout():
    """Test that execute_command times out appropriately."""
    with (
        patch("os.name", "posix"),
        patch("subprocess.Popen") as mock_popen,
        patch("time.sleep"),
        patch("random.randint", return_value=123456),
    ):
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_popen.return_value = mock_process

        with (
            patch.object(
                interaction.ShellSession, "_read_line_with_timeout"
            ) as mock_read,
            patch("time.time") as mock_time,
        ):
            # Simulate timeout by making time advance rapidly
            mock_time.side_effect = [0, 0, 31]  # Start, loop iteration, timeout check
            mock_read.return_value = None  # Never finds the marker

            session = interaction.ShellSession()

            with pytest.raises(RuntimeError, match="timed out"):
                session.execute_command("sleep 100", timeout=30)


def test_shell_session_close():
    """Test closing the shell session."""
    with (
        patch("os.name", "posix"),
        patch("subprocess.Popen") as mock_popen,
        patch("time.sleep"),
    ):
        mock_process = MagicMock()
        mock_popen.return_value = mock_process

        session = interaction.ShellSession()
        session.close()

        mock_process.stdin.close.assert_called_once()
        mock_process.terminate.assert_called_once()


def test_shell_session_context_manager():
    """Test ShellSession as context manager."""
    with (
        patch("os.name", "posix"),
        patch("subprocess.Popen") as mock_popen,
        patch("time.sleep"),
    ):
        mock_process = MagicMock()
        mock_popen.return_value = mock_process

        with interaction.ShellSession() as session:
            assert session.process is not None

        mock_process.stdin.close.assert_called_once()
        mock_process.terminate.assert_called_once()


def test_approval_loop_approve():
    """Test approval loop with approval."""
    with patch("builtins.input", return_value="a"):
        result = interaction.approval_loop("ls -la")
        assert result == "ls -la"


def test_approval_loop_reject():
    """Test approval loop with rejection."""
    with patch("builtins.input", return_value="r"):
        result = interaction.approval_loop("echo 'test command'")
        assert result is None


def test_approval_loop_modify():
    """Test approval loop with modification."""
    with patch("builtins.input", side_effect=["m", "ls -lh"]):
        result = interaction.approval_loop("ls -la")
        assert result == "ls -lh"


def test_approval_loop_invalid_then_approve():
    """Test approval loop with invalid input then approval."""
    with patch("builtins.input", side_effect=["x", "invalid", "a"]):
        result = interaction.approval_loop("pwd")
        assert result == "pwd"


def test_approval_loop_modify_empty_retry():
    """Test approval loop modify with empty command."""
    with patch("builtins.input", side_effect=["m", "", "a"]):
        result = interaction.approval_loop("echo test")
        assert result == "echo test"


def test_approval_loop_keyboard_interrupt():
    """Test approval loop handles keyboard interrupt."""
    with patch("builtins.input", side_effect=KeyboardInterrupt()):
        result = interaction.approval_loop("ls")
        assert result is None


def test_approval_loop_eof():
    """Test approval loop handles EOF."""
    with patch("builtins.input", side_effect=EOFError()):
        result = interaction.approval_loop("ls")
        assert result is None


def test_parse_tool_calls_empty():
    """Test parsing empty tool calls list."""
    chunks = []
    result = interaction.parse_tool_calls(chunks)
    assert result == []


def test_parse_tool_calls_no_tools():
    """Test parsing chunks with no tool calls."""
    chunks = [
        {"type": "text", "content": "Hello"},
        {"type": "text", "content": " world"},
    ]
    result = interaction.parse_tool_calls(chunks)
    assert result == []


def test_parse_tool_calls_single_tool():
    """Test parsing a single tool call."""
    chunks = [
        {"type": "text", "content": "Let me run that."},
        {
            "type": "tool_call",
            "id": "call_123",
            "name": "execute_shell",
            "arguments": {"command": "ls -la"},
        },
    ]
    result = interaction.parse_tool_calls(chunks)

    assert len(result) == 1
    assert result[0]["name"] == "execute_shell"
    assert result[0]["arguments"]["command"] == "ls -la"
    assert result[0]["id"] == "call_123"


def test_parse_tool_calls_multiple_tools():
    """Test parsing multiple tool calls."""
    chunks = [
        {
            "type": "tool_call",
            "id": "call_1",
            "name": "execute_shell",
            "arguments": {"command": "pwd"},
        },
        {"type": "text", "content": "Now checking files..."},
        {
            "type": "tool_call",
            "id": "call_2",
            "name": "execute_shell",
            "arguments": {"command": "ls"},
        },
    ]
    result = interaction.parse_tool_calls(chunks)

    assert len(result) == 2
    assert result[0]["arguments"]["command"] == "pwd"
    assert result[1]["arguments"]["command"] == "ls"


def test_read_line_with_timeout_windows(monkeypatch):
    """Test reading line with timeout on Windows."""
    monkeypatch.setattr("os.name", "nt")

    with (
        patch("os.name", "nt"),
        patch("subprocess.Popen") as mock_popen,
        patch("threading.Thread") as mock_thread,
        patch("queue.Queue") as mock_queue_class,
    ):
        mock_process = MagicMock()
        mock_popen.return_value = mock_process

        # Mock queue
        mock_queue = MagicMock()
        mock_queue.get.return_value = "test line\n"
        mock_queue_class.return_value = mock_queue

        session = interaction.ShellSession()

        # Mock stream
        mock_stream = MagicMock()
        session._read_line_with_timeout(mock_stream, 0.1)

        # Verify thread was created
        mock_thread.assert_called_once()
