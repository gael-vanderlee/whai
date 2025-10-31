"""Tests for shell detection and proper spawning."""

import os
import subprocess
from unittest.mock import patch

import pytest

from terma.context import _get_shell_from_env, get_shell_executable
from terma.interaction import ShellSession


class TestShellDetection:
    """Test shell detection from environment variables."""

    def test_detect_bash_from_shell_env(self):
        """Test detection of bash from SHELL environment variable."""
        with patch.dict(os.environ, {"SHELL": "/bin/bash"}):
            assert _get_shell_from_env() == "bash"

    def test_detect_zsh_from_shell_env(self):
        """Test detection of zsh from SHELL environment variable."""
        with patch.dict(os.environ, {"SHELL": "/usr/bin/zsh"}):
            assert _get_shell_from_env() == "zsh"

    @pytest.mark.skipif(os.name != "nt", reason="Windows-specific test")
    def test_detect_powershell_from_psmodulepath(self):
        """Test detection of PowerShell from PSModulePath environment variable."""
        with patch.dict(os.environ, {"PSModulePath": "C:\\some\\path", "SHELL": ""}):
            assert _get_shell_from_env() == "powershell"

    @pytest.mark.skipif(os.name != "nt", reason="Windows-specific test")
    def test_detect_cmd_fallback_on_windows(self):
        """Test fallback to cmd.exe on Windows when no shell is detected."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("os.name", "nt"):
                detected = _get_shell_from_env()
                # Should fallback to cmd on Windows
                assert detected == "cmd"

    def test_detect_unknown_on_unix(self):
        """Test unknown detection on Unix when no shell markers present."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("os.name", "posix"):
                detected = _get_shell_from_env()
                assert detected == "unknown"


class TestShellExecutable:
    """Test shell executable path resolution."""

    def test_bash_executable_path(self):
        """Test bash executable path resolution."""
        assert get_shell_executable("bash") == "/bin/bash"

    def test_zsh_executable_path(self):
        """Test zsh executable path resolution."""
        assert get_shell_executable("zsh") == "/bin/zsh"

    def test_cmd_executable_path(self):
        """Test cmd.exe executable path resolution."""
        assert get_shell_executable("cmd") == "cmd.exe"

    @pytest.mark.skipif(os.name != "nt", reason="Windows-specific test")
    def test_powershell_executable_found(self):
        """Test that PowerShell executable can be found on Windows."""
        exe_path = get_shell_executable("powershell")
        # Should return either pwsh.exe or powershell.exe (whichever is available)
        assert "powershell" in exe_path.lower() or "pwsh" in exe_path.lower()

    def test_unknown_shell_fallback(self):
        """Test fallback for unknown shell types."""
        result = get_shell_executable("unknown_shell")
        if os.name == "nt":
            assert result == "cmd.exe"
        else:
            assert result == "/bin/bash"


class TestShellSessionSpawning:
    """Test ShellSession spawning with different shells."""

    def test_shell_session_respects_shell_parameter(self):
        """Test that ShellSession uses the provided shell parameter."""
        if os.name == "nt":
            # On Windows, test with cmd.exe
            session = ShellSession(shell="cmd.exe")
            assert session.shell == "cmd.exe"
            session.close()
        else:
            # On Unix, test with bash
            session = ShellSession(shell="/bin/bash")
            assert session.shell == "/bin/bash"
            session.close()

    @pytest.mark.skipif(os.name != "nt", reason="Windows-specific test")
    def test_powershell_session_spawns(self):
        """Test that PowerShell session can be spawned."""
        # Try to find PowerShell
        pwsh_path = None
        for pwsh in ["pwsh.exe", "powershell.exe"]:
            try:
                result = subprocess.run(
                    [pwsh, "-Command", "echo test"],
                    capture_output=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    pwsh_path = pwsh
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

        if pwsh_path:
            session = ShellSession(shell=pwsh_path)
            assert session.shell == pwsh_path
            assert session.process is not None
            assert session.process.poll() is None  # Process is running
            session.close()
        else:
            pytest.skip("PowerShell not found on system")

    @pytest.mark.skipif(os.name != "nt", reason="Windows-specific test")
    def test_powershell_command_execution(self):
        """Test that PowerShell commands can be executed."""
        # Try to find PowerShell
        pwsh_path = None
        for pwsh in ["pwsh.exe", "powershell.exe"]:
            try:
                result = subprocess.run(
                    [pwsh, "-Command", "echo test"],
                    capture_output=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    pwsh_path = pwsh
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

        if pwsh_path:
            session = ShellSession(shell=pwsh_path)
            try:
                # Execute a simple PowerShell command
                stdout, stderr, _ = session.execute_command(
                    "Get-ChildItem -Directory | Select-Object -First 1", timeout=5
                )
                # Should not timeout and should produce some output
                assert len(stdout) > 0 or len(stderr) == 0
            finally:
                session.close()
        else:
            pytest.skip("PowerShell not found on system")

    def test_shell_session_default_spawning(self):
        """Test that ShellSession spawns appropriate default shell."""
        session = ShellSession()
        if os.name == "nt":
            # On Windows, default should be cmd.exe
            assert session.shell == "cmd.exe"
        else:
            # On Unix, default should be bash
            assert session.shell == "/bin/bash"
        session.close()


class TestShellMismatchBug:
    """Regression tests for the shell mismatch bug."""

    @pytest.mark.skipif(os.name != "nt", reason="Windows-specific regression test")
    def test_no_shell_mismatch_on_windows(self):
        """
        Regression test: Ensure detected shell matches spawned shell.

        This test verifies the fix for the bug where terma would detect PowerShell
        from the environment but spawn cmd.exe for command execution, causing
        PowerShell commands to fail or timeout.
        """
        # Simulate PowerShell environment
        with patch.dict(os.environ, {"PSModulePath": "C:\\some\\path"}):
            # Detect shell
            detected_shell_name = _get_shell_from_env()
            assert detected_shell_name == "powershell"

            # Get executable path
            shell_executable = get_shell_executable(detected_shell_name)
            assert (
                "powershell" in shell_executable.lower()
                or "pwsh" in shell_executable.lower()
            )

            # Spawn session with detected shell
            session = ShellSession(shell=shell_executable)
            try:
                # Verify the spawned shell matches
                assert session.shell == shell_executable
                assert (
                    "powershell" in session.shell.lower()
                    or "pwsh" in session.shell.lower()
                )
            finally:
                session.close()
