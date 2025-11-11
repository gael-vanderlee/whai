"""Tests for interaction module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from whai import interaction


def test_execute_command_unix_success():
    """Test successful command execution on Unix."""
    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.run") as mock_run,
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        mock_result = MagicMock()
        mock_result.stdout = "file1.txt\nfile2.txt\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        stdout, stderr, code = interaction.execute_command("ls")

        assert "file1.txt" in stdout
        assert "file2.txt" in stdout
        assert stderr == ""
        assert code == 0
        mock_run.assert_called_once()


def test_execute_command_windows_powershell():
    """Test command execution on Windows with PowerShell."""
    with (
        patch("whai.interaction.execution.is_windows", return_value=True),
        patch("whai.interaction.execution.detect_shell", return_value="pwsh"),
        patch("subprocess.run") as mock_run,
    ):
        mock_result = MagicMock()
        mock_result.stdout = "test output\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        stdout, stderr, code = interaction.execute_command("Get-ChildItem")

        assert "test output" in stdout
        assert code == 0
        # Verify PowerShell was used
        call_args = mock_run.call_args[0][0]
        assert "powershell.exe" in call_args


def test_execute_command_windows_cmd():
    """Test command execution on Windows with cmd.exe."""
    with (
        patch("whai.interaction.execution.is_windows", return_value=True),
        patch("whai.interaction.execution.detect_shell", return_value="bash"),  # Not pwsh
        patch("subprocess.run") as mock_run,
    ):
        mock_result = MagicMock()
        mock_result.stdout = "test output\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        stdout, stderr, code = interaction.execute_command("dir")

        assert "test output" in stdout
        assert code == 0
        # Verify cmd.exe was used
        call_args = mock_run.call_args[0][0]
        assert "cmd.exe" in call_args


def test_execute_command_with_stderr():
    """Test command execution with stderr output."""
    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.run") as mock_run,
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        mock_result = MagicMock()
        mock_result.stdout = "output\n"
        mock_result.stderr = "error message\n"
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        stdout, stderr, code = interaction.execute_command("failing_command")

        assert stdout == "output\n"
        assert "error message" in stderr
        assert code == 1


def test_execute_command_timeout():
    """Test that execute_command raises error on timeout."""
    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.run") as mock_run,
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)

        with pytest.raises(RuntimeError, match="timed out"):
            interaction.execute_command("sleep 100", timeout=30)


def test_execute_command_other_error():
    """Test that execute_command handles other errors."""
    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.run") as mock_run,
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        mock_run.side_effect = Exception("Something went wrong")

        with pytest.raises(RuntimeError, match="Error executing command"):
            interaction.execute_command("some_command")


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


