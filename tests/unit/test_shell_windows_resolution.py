"""Tests for Windows shell resolution and fallback logic."""

import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whai.shell.session import _launch_windows


@pytest.mark.skipif(
    not hasattr(_launch_windows, "__name__"),
    reason="Windows-specific test"
)
def test_launch_windows_falls_back_when_pwsh_not_available(tmp_path):
    """Test that _launch_windows falls back to powershell.exe when pwsh is not available."""
    log_path = tmp_path / "test.log"
    
    # Mock shutil.which to simulate pwsh not being available
    def mock_which(cmd):
        if cmd == "pwsh":
            return None  # pwsh not available
        elif cmd == "powershell":
            return r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        return None
    
    with patch("shutil.which", side_effect=mock_which):
        with patch("subprocess.call") as mock_call:
            mock_call.return_value = 0
            
            # Call with shell type "pwsh" (what detect_shell() returns)
            exit_code = _launch_windows("pwsh", log_path)
            
            # Should succeed
            assert exit_code == 0
            
            # Verify it called subprocess with powershell.exe (the fallback)
            mock_call.assert_called_once()
            call_args = mock_call.call_args[0][0]
            
            # First argument should be the resolved powershell.exe path
            assert "powershell.exe" in call_args[0].lower()
            assert call_args[0] == r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


@pytest.mark.skipif(
    not hasattr(_launch_windows, "__name__"),
    reason="Windows-specific test"
)
def test_launch_windows_resolves_shell_types_to_paths(tmp_path):
    """Test that shell type names are resolved to full executable paths."""
    log_path = tmp_path / "test.log"
    
    # Mock shutil.which to return full paths
    def mock_which(cmd):
        if cmd == "pwsh":
            return r"C:\Program Files\PowerShell\7\pwsh.exe"
        elif cmd == "powershell":
            return r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        return None
    
    test_cases = [
        ("pwsh", r"C:\Program Files\PowerShell\7\pwsh.exe"),
        ("powershell", r"C:\Program Files\PowerShell\7\pwsh.exe"),  # Still prefers pwsh if available
    ]
    
    for shell_type, expected_path in test_cases:
        with patch("shutil.which", side_effect=mock_which):
            with patch("subprocess.call") as mock_call:
                mock_call.return_value = 0
                
                exit_code = _launch_windows(shell_type, log_path)
                
                assert exit_code == 0
                call_args = mock_call.call_args[0][0]
                assert call_args[0] == expected_path


@pytest.mark.skipif(
    not hasattr(_launch_windows, "__name__"),
    reason="Windows-specific test"
)
def test_launch_windows_raises_error_when_no_powershell_available(tmp_path):
    """Test that _launch_windows raises error when neither pwsh nor powershell is available."""
    log_path = tmp_path / "test.log"
    
    # Mock shutil.which to return None for both pwsh and powershell
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError) as exc_info:
            _launch_windows("pwsh", log_path)
        
        # Should mention both PowerShell versions in error
        error_msg = str(exc_info.value)
        assert "powershell" in error_msg.lower()
        assert "pwsh" in error_msg.lower() or "powershell 7" in error_msg.lower()


@pytest.mark.skipif(
    not hasattr(_launch_windows, "__name__"),
    reason="Windows-specific test"
)
def test_launch_windows_handles_full_path_input(tmp_path):
    """Test that _launch_windows handles full executable paths correctly."""
    log_path = tmp_path / "test.log"
    full_path = r"C:\Program Files\PowerShell\7\pwsh.exe"
    
    with patch("subprocess.call") as mock_call:
        mock_call.return_value = 0
        
        # When given a full path that contains "pwsh", should use it directly
        exit_code = _launch_windows(full_path, log_path)
        
        assert exit_code == 0
        call_args = mock_call.call_args[0][0]
        # Should use the provided path
        assert full_path in call_args[0] or "pwsh" in call_args[0].lower()


@pytest.mark.skipif(
    not hasattr(_launch_windows, "__name__"),
    reason="Windows-specific test"
)
def test_launch_windows_cmd_fallback(tmp_path):
    """Test that _launch_windows handles cmd.exe correctly."""
    log_path = tmp_path / "test.log"
    
    with patch("subprocess.call") as mock_call:
        mock_call.return_value = 0
        
        # Call with cmd
        exit_code = _launch_windows("cmd", log_path)
        
        assert exit_code == 0
        call_args = mock_call.call_args[0][0]
        # Should use cmd.exe
        assert "cmd.exe" in call_args[0].lower()

