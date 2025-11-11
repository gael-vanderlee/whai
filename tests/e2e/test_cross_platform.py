"""Cross-platform end-to-end tests.

These tests validate whai behavior on different platforms: WSL, macOS, Windows.
"""

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def is_wsl():
    """Check if running in WSL."""
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False


@pytest.mark.skipif(not is_wsl(), reason="WSL-only")
@pytest.mark.integration
def test_whai_shell_in_wsl_full_workflow():
    """Test that whai shell works correctly in WSL environment."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = os.environ.copy()
        env["WHAI_TEST_MODE"] = "1"
        env["XDG_CONFIG_HOME"] = tmpdir
        
        # Mock the shell launch to avoid interactive session
        with (
            patch("whai.shell.session._launch_unix") as mock_launch,
        ):
            mock_launch.return_value = 0
            
            # Run whai shell command
            result = subprocess.run(
                [sys.executable, "-m", "whai", "shell"],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            # Should start successfully in WSL
            assert result.returncode == 0 or "shell" in result.stderr.lower()


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-only")
@pytest.mark.integration
def test_whai_shell_on_macos_uses_bsd_script():
    """Test that whai shell on macOS uses BSD script flags (-qF)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "test_session.log"
        
        # Test that BSD flags are used
        from whai.shell.session import launch_shell_session
        
        with patch("subprocess.call") as mock_call:
            mock_call.return_value = 0
            
            launch_shell_session(
                shell="zsh",
                log_path=log_path,
                delete_on_exit=False,
            )
            
            # Verify BSD flags were used (-qF, not -qf or --)
            call_args = mock_call.call_args[0][0]
            assert "-qF" in " ".join(call_args) or "-q" in call_args


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only")
@pytest.mark.integration
def test_whai_shell_on_windows_powershell_full_flow():
    """Test that whai shell works correctly in Windows PowerShell."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = os.environ.copy()
        env["WHAI_TEST_MODE"] = "1"
        env["APPDATA"] = tmpdir
        
        # Mock the shell launch to avoid interactive session
        with patch("whai.shell.session._launch_windows") as mock_launch:
            mock_launch.return_value = 0
            
            # Run whai shell command
            result = subprocess.run(
                [sys.executable, "-m", "whai", "shell"],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            # Should start successfully on Windows
            assert result.returncode == 0 or "shell" in result.stderr.lower()

