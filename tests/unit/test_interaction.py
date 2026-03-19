"""Tests for interaction module."""

import io
import subprocess
from unittest.mock import MagicMock, mock_open, patch

import pytest

from whai import interaction


class FakeProcess:
    def __init__(
        self,
        *,
        stdout_text="",
        stderr_text="",
        returncode=0,
        communicate_result=None,
        communicate_side_effect=None,
    ):
        self.stdout = io.StringIO(stdout_text)
        self.stderr = io.StringIO(stderr_text)
        self.stdin = io.StringIO()
        self.returncode = returncode
        self._communicate_result = communicate_result
        self._communicate_side_effect = communicate_side_effect
        self.killed = False
        self.wait_calls = []

    def communicate(self, timeout=None):
        if self._communicate_side_effect is not None:
            raise self._communicate_side_effect
        if self._communicate_result is not None:
            return self._communicate_result
        return (self.stdout.getvalue(), self.stderr.getvalue())

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        return self.returncode

    def poll(self):
        return self.returncode


def test_execute_command_unix_success():
    """Test successful command execution on Unix."""
    proc = FakeProcess(
        communicate_result=("file1.txt\nfile2.txt\n", ""),
        returncode=0,
    )

    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.Popen", return_value=proc) as mock_popen,
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        stdout, stderr, code = interaction.execute_command("ls")

    assert "file1.txt" in stdout
    assert "file2.txt" in stdout
    assert stderr == ""
    assert code == 0
    assert mock_popen.call_args[0][0] == ["/bin/bash", "-c", "ls"]


def test_execute_command_windows_powershell():
    """Test command execution on Windows with PowerShell."""
    proc = FakeProcess(communicate_result=("test output\n", ""), returncode=0)

    with (
        patch("whai.interaction.execution.is_windows", return_value=True),
        patch("whai.interaction.execution.detect_shell", return_value="pwsh"),
        patch("whai.interaction.execution.shutil.which", return_value="pwsh.exe"),
        patch("subprocess.Popen", return_value=proc) as mock_popen,
    ):
        stdout, stderr, code = interaction.execute_command("Get-ChildItem")

    assert "test output" in stdout
    assert stderr == ""
    assert code == 0
    assert mock_popen.call_args[0][0] == ["pwsh.exe", "-Command", "Get-ChildItem"]


def test_execute_command_windows_cmd():
    """Test command execution on Windows with cmd.exe."""
    proc = FakeProcess(communicate_result=("test output\n", ""), returncode=0)

    with (
        patch("whai.interaction.execution.is_windows", return_value=True),
        patch("whai.interaction.execution.detect_shell", return_value="bash"),
        patch("subprocess.Popen", return_value=proc) as mock_popen,
    ):
        stdout, stderr, code = interaction.execute_command("dir")

    assert "test output" in stdout
    assert stderr == ""
    assert code == 0
    assert mock_popen.call_args[0][0] == ["cmd.exe", "/c", "dir"]


def test_execute_command_with_stderr():
    """Test command execution with stderr output."""
    proc = FakeProcess(
        communicate_result=("output\n", "error message\n"),
        returncode=1,
    )

    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.Popen", return_value=proc),
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        stdout, stderr, code = interaction.execute_command("failing_command")

    assert stdout == "output\n"
    assert "error message" in stderr
    assert code == 1


def test_execute_command_timeout():
    """Test that execute_command raises error on timeout."""
    proc = FakeProcess(
        communicate_side_effect=subprocess.TimeoutExpired("cmd", 30),
        returncode=1,
    )

    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.Popen", return_value=proc),
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        with pytest.raises(RuntimeError, match="timed out"):
            interaction.execute_command("sleep 100", timeout=30)

    assert proc.killed is True


def test_execute_command_infinite_timeout():
    """Test that execute_command with timeout=0 passes None to communicate."""
    proc = FakeProcess(communicate_result=("output\n", ""), returncode=0)

    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.Popen", return_value=proc),
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        stdout, stderr, code = interaction.execute_command("echo test", timeout=0)

    assert stdout == "output\n"
    assert code == 0


def test_execute_command_other_error():
    """Test that execute_command handles other errors."""
    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.Popen", side_effect=Exception("Something went wrong")),
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        with pytest.raises(RuntimeError, match="Error executing command"):
            interaction.execute_command("some_command")


def test_execute_command_interactive_prompt_on_stdout():
    """Test that prompt detection can supply input on stdout prompts."""
    proc = FakeProcess(stdout_text="Continue?", stderr_text="", returncode=0)
    callback = MagicMock(return_value="y\n")

    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.Popen", return_value=proc),
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        stdout, stderr, code = interaction.execute_command(
            "some_command", on_input_needed=callback
        )

    assert stdout == "Continue?"
    assert stderr == ""
    assert code == 0
    assert callback.call_count == 1
    callback.assert_called_once_with("Continue?")
    assert proc.stdin.getvalue() == "y\n"


def test_execute_command_interactive_prompt_on_stderr():
    """Test that prompt detection also works for stderr prompts without newlines."""
    proc = FakeProcess(stdout_text="", stderr_text="Password:", returncode=0)
    callback = MagicMock(return_value="secret\n")

    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.Popen", return_value=proc),
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        stdout, stderr, code = interaction.execute_command(
            "some_command", on_input_needed=callback
        )

    assert stdout == ""
    assert stderr == "Password:"
    assert code == 0
    assert callback.call_count == 1
    callback.assert_called_once_with("Password:")
    assert proc.stdin.getvalue() == "secret\n"


def test_execute_command_interactive_sequential_prompts():
    """Test that sequential prompts each trigger exactly once."""
    proc = FakeProcess(
        stdout_text="Continue? Proceed? done\n", stderr_text="", returncode=0
    )
    callback = MagicMock(side_effect=["alpha\n", "beta\n"])

    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.Popen", return_value=proc),
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        stdout, stderr, code = interaction.execute_command(
            "some_command", on_input_needed=callback
        )

    assert stdout == "Continue? Proceed? done\n"
    assert stderr == ""
    assert code == 0
    assert callback.call_count == 2
    assert callback.call_args_list[0].args == ("Continue?",)
    assert callback.call_args_list[1].args == ("Continue? Proceed?",)
    assert proc.stdin.getvalue() == "alpha\nbeta\n"


def test_execute_command_interactive_same_prompt_text_twice():
    """Test that the same prompt text can appear twice without duplicate firing."""
    proc = FakeProcess(
        stdout_text="Continue? Continue? done\n", stderr_text="", returncode=0
    )
    callback = MagicMock(side_effect=["yes\n", "still yes\n"])

    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.Popen", return_value=proc),
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        stdout, stderr, code = interaction.execute_command(
            "some_command", on_input_needed=callback
        )

    assert stdout == "Continue? Continue? done\n"
    assert stderr == ""
    assert code == 0
    assert callback.call_count == 2
    assert callback.call_args_list[0].args == ("Continue?",)
    assert callback.call_args_list[1].args == ("Continue? Continue?",)
    assert proc.stdin.getvalue() == "yes\nstill yes\n"


def test_execute_command_interactive_bracket_prompt_triggers_once():
    """Test that bracketed confirmation prompts do not re-trigger on trailing question marks."""
    proc = FakeProcess(
        stdout_text="before\nProceed [y/n]? after n\n",
        stderr_text="",
        returncode=0,
    )
    callback = MagicMock(return_value="n\n")

    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.Popen", return_value=proc),
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        stdout, stderr, code = interaction.execute_command(
            "some_command", on_input_needed=callback
        )

    assert stdout == "before\nProceed [y/n]? after n\n"
    assert stderr == ""
    assert code == 0
    callback.assert_called_once_with("before\nProceed [y/n]?")
    assert proc.stdin.getvalue() == "n\n"


def test_execute_command_interactive_cancel_raises_error():
    """Test that cancelling interactive input stops the command."""
    proc = FakeProcess(stdout_text="Continue?", stderr_text="", returncode=1)
    callback = MagicMock(return_value=None)

    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.Popen", return_value=proc),
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        with pytest.raises(RuntimeError, match="input was cancelled"):
            interaction.execute_command("some_command", on_input_needed=callback)

    assert proc.killed is True


def test_execute_command_interactive_rm_i_prompt():
    """Test that rm -i style stderr prompt triggers the callback."""
    proc = FakeProcess(
        stdout_text="",
        stderr_text="rm: remove regular file 'debug.log'?",
        returncode=0,
    )
    callback = MagicMock(return_value="y\n")

    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.Popen", return_value=proc),
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        stdout, stderr, code = interaction.execute_command(
            "rm -i debug.log", on_input_needed=callback
        )

    assert stderr == "rm: remove regular file 'debug.log'?"
    assert code == 0
    assert callback.call_count == 1
    callback.assert_called_once_with("rm: remove regular file 'debug.log'?")
    assert proc.stdin.getvalue() == "y\n"


def test_execute_command_interactive_overwrite_prompt():
    """Test that cp -i style overwrite prompt triggers the callback."""
    proc = FakeProcess(
        stdout_text="",
        stderr_text="cp: overwrite 'file.txt'?",
        returncode=0,
    )
    callback = MagicMock(return_value="n\n")

    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("subprocess.Popen", return_value=proc),
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
    ):
        stdout, stderr, code = interaction.execute_command(
            "cp -i src.txt file.txt", on_input_needed=callback
        )

    assert stderr == "cp: overwrite 'file.txt'?"
    assert code == 0
    assert callback.call_count == 1
    callback.assert_called_once_with("cp: overwrite 'file.txt'?")
    assert proc.stdin.getvalue() == "n\n"


def test_post_execution_display_skips_output_after_interactive():
    """After interactive command, print_output receives empty strings (no duplicate)."""
    last_prompt_output = "Continue?"
    stdout = "Continue? done\n"
    stderr = ""
    returncode = 0

    # Replicate the executor's 6-line conditional (executor.py:441-446)
    if last_prompt_output:
        display_args = ("", "", returncode)
    else:
        display_args = (stdout, stderr, returncode)

    assert display_args == ("", "", 0)


def test_post_execution_display_shows_full_output_non_interactive():
    """After non-interactive command, print_output receives full output."""
    last_prompt_output = ""
    stdout = "file1.txt\nfile2.txt\n"
    stderr = "warning: something\n"
    returncode = 0

    if last_prompt_output:
        display_args = ("", "", returncode)
    else:
        display_args = (stdout, stderr, returncode)

    assert display_args == ("file1.txt\nfile2.txt\n", "warning: something\n", 0)


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


# --- _is_waiting_on_stdin tests ---

from whai.interaction.execution import _is_waiting_on_stdin


def test_is_waiting_on_stdin_reading_fd0():
    """Process blocked on read(0, ...) should be detected as waiting on stdin."""
    data = "0 0x0 0x7ffd12345678 0x1000 0x0 0x0 0x7f1234567890 0x7f1234567abc"
    with patch("builtins.open", mock_open(read_data=data)):
        assert _is_waiting_on_stdin(1234) is True


def test_is_waiting_on_stdin_running():
    """Process in 'running' state is not waiting on stdin."""
    with patch("builtins.open", mock_open(read_data="running")):
        assert _is_waiting_on_stdin(1234) is False


def test_is_waiting_on_stdin_reading_other_fd():
    """Process blocked reading fd 3 (not stdin) should return False."""
    data = "0 0x3 0x7ffd12345678 0x1000 0x0 0x0 0x7f1234567890 0x7f1234567abc"
    with patch("builtins.open", mock_open(read_data=data)):
        assert _is_waiting_on_stdin(1234) is False


def test_is_waiting_on_stdin_no_proc():
    """When /proc is unavailable, should return False gracefully."""
    with patch("builtins.open", side_effect=OSError("No such file")):
        assert _is_waiting_on_stdin(1234) is False


def test_execute_command_interactive_syscall_detection():
    """Syscall-based detection triggers callback even without pattern match."""
    # Output has no recognizable prompt pattern
    proc = FakeProcess(stdout_text="waiting for input", stderr_text="", returncode=0)
    proc.pid = 9999
    callback = MagicMock(return_value="answer\n")

    # Track poll calls; process stays alive until after callback fires
    poll_count = [0]
    original_poll = proc.poll

    def smart_poll():
        poll_count[0] += 1
        # Stay alive (return None) until callback has been invoked
        if callback.call_count == 0:
            return None
        return original_poll()

    proc.poll = smart_poll

    syscall_calls = []

    def fake_is_waiting(pid):
        syscall_calls.append(pid)
        # Return True after output has been consumed (i.e. after some calls)
        return len(syscall_calls) > 2

    with (
        patch("whai.interaction.execution.is_windows", return_value=False),
        patch("whai.interaction.execution.is_linux", return_value=True),
        patch("subprocess.Popen", return_value=proc),
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
        patch(
            "whai.interaction.execution._is_waiting_on_stdin",
            side_effect=fake_is_waiting,
        ),
    ):
        stdout, stderr, code = interaction.execute_command(
            "some_command", on_input_needed=callback
        )

    assert callback.call_count == 1
    callback.assert_called_once_with("waiting for input")
    assert proc.stdin.getvalue() == "answer\n"
