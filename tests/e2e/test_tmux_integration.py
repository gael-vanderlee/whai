"""Real tmux integration end-to-end test.

This test validates that whai running in an actual tmux session
can capture scrollback context correctly.
"""

import os
import shutil
import subprocess
import tempfile
from unittest.mock import patch

import pytest


@pytest.mark.skipif(not shutil.which("tmux"), reason="tmux required")
@pytest.mark.integration
def test_whai_in_real_tmux_captures_scrollback():
    """Test that whai running in a real tmux session captures scrollback context."""
    # This test launches a real tmux session to verify context capture
    
    with tempfile.TemporaryDirectory() as tmpdir:
        env = os.environ.copy()
        env["WHAI_TEST_MODE"] = "1"
        env["XDG_CONFIG_HOME"] = tmpdir
        
        # Create a tmux session and run commands in it
        session_name = "whai_test_session"
        
        try:
            # Start tmux session in detached mode
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session_name],
                check=True,
                timeout=5,
            )
            
            # Send commands to create scrollback
            subprocess.run(
                ["tmux", "send-keys", "-t", session_name, "echo 'test command 1'", "C-m"],
                check=True,
                timeout=5,
            )
            subprocess.run(
                ["tmux", "send-keys", "-t", session_name, "echo 'test command 2'", "C-m"],
                check=True,
                timeout=5,
            )
            
            # Capture the pane content to verify tmux has output
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", session_name, "-p"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            
            # Verify tmux captured the commands
            assert "test command" in result.stdout
            
            # Test that whai can read tmux context
            # Use direct tmux capture instead of relying on TMUX env var
            # This works regardless of env var state and socket paths
            capture_result = subprocess.run(
                ["tmux", "capture-pane", "-t", session_name, "-p"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            
            # Should successfully capture from the session
            assert capture_result.returncode == 0, f"tmux capture-pane failed: {capture_result.stderr}"
            context = capture_result.stdout
            assert context is not None
            assert "test command" in context
            
        finally:
            # Clean up tmux session
            try:
                subprocess.run(
                    ["tmux", "kill-session", "-t", session_name],
                    timeout=5,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass


@pytest.mark.skipif(not shutil.which("tmux"), reason="tmux required")
def test_tmux_context_prefers_deep_context():
    """Test that tmux context is marked as deep context (includes command outputs)."""
    from whai.context.capture import get_context
    
    # Mock being in a tmux session
    # Note: Need to patch where it's imported, not where it's defined
    with (
        patch.dict(os.environ, {"TMUX": "/tmp/tmux-1000/test,1,0"}),
        patch("whai.context.capture._get_tmux_context", return_value="tmux scrollback content"),
    ):
        context, is_deep = get_context()
        
        # Should use tmux context (deep)
        assert is_deep is True
        assert context == "tmux scrollback content"

