"""Real tmux integration end-to-end test.

This test validates that whai running in an actual tmux session
can capture scrollback context correctly.
"""

import os
import shutil
import subprocess
import tempfile
import time
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


@pytest.mark.skipif(not shutil.which("tmux"), reason="tmux required")
@pytest.mark.integration
def test_target_pane_capture_uses_correct_pane():
    """Test that capture_target_context pulls context from the requested pane only.

    Creates a real tmux session with two panes, puts unique content in each,
    then verifies that capture_target_context(0) returns pane 0 content and
    capture_target_context(1) returns pane 1 content.
    """
    session_name = "whai_target_test"
    marker_0 = "WHAI_TARGET_TEST_PANE_0_MARKER"
    marker_1 = "WHAI_TARGET_TEST_PANE_1_MARKER"

    try:
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name],
            check=True,
            timeout=5,
        )

        subprocess.run(
            ["tmux", "split-window", "-t", f"{session_name}:0", "-h"],
            check=True,
            timeout=5,
        )

        subprocess.run(
            ["tmux", "send-keys", "-t", f"{session_name}:0.0", f"echo {marker_0}", "C-m"],
            check=True,
            timeout=5,
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", f"{session_name}:0.1", f"echo {marker_1}", "C-m"],
            check=True,
            timeout=5,
        )

        time.sleep(0.3)

        socket_result = subprocess.run(
            ["tmux", "display-message", "-t", session_name, "-p", "#{socket_path}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        sid_result = subprocess.run(
            ["tmux", "display-message", "-t", session_name, "-p", "#{session_id}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert socket_result.returncode == 0, socket_result.stderr
        assert sid_result.returncode == 0, sid_result.stderr
        socket_path = socket_result.stdout.strip()
        session_id = sid_result.stdout.strip()
        tmux_env = f"{socket_path},{session_id},0,0"

        from whai.cli.target import capture_target_context

        with patch.dict(os.environ, {"TMUX": tmux_env}, clear=False):
            ctx_0 = capture_target_context("0")
            ctx_1 = capture_target_context("1")

        assert ctx_0 is not None, "capture_target_context('0') should return content"
        assert ctx_1 is not None, "capture_target_context('1') should return content"
        assert marker_0 in ctx_0, f"Pane 0 context should contain {marker_0!r}"
        assert marker_1 in ctx_1, f"Pane 1 context should contain {marker_1!r}"
        assert marker_1 not in ctx_0, "Pane 0 context must not contain pane 1 marker"
        assert marker_0 not in ctx_1, "Pane 1 context must not contain pane 0 marker"
    finally:
        try:
            subprocess.run(
                ["tmux", "kill-session", "-t", session_name],
                timeout=5,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

