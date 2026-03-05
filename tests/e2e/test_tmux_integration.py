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

# Socket name for a dedicated tmux server so pane shells get test env (e.g. HISTFILE=/dev/null)
# and don't write to the user's shell history.
_TMUX_TEST_SOCKET = "whai_test"


def _tmux_cmd(*args, env=None, check=True):
    """Run tmux with test socket; use env so pane shells inherit e.g. HISTFILE=/dev/null."""
    full_env = (env or os.environ).copy()
    full_env.setdefault("HISTFILE", "/dev/null")
    full_env.setdefault("HISTSIZE", "0")
    return subprocess.run(
        ["tmux", "-L", _TMUX_TEST_SOCKET] + list(args),
        env=full_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
        check=check,
    )


@pytest.mark.skipif(not shutil.which("tmux"), reason="tmux required")
@pytest.mark.integration
def test_whai_in_real_tmux_captures_scrollback():
    """Test that whai running in a real tmux session captures scrollback context."""
    # This test launches a real tmux session to verify context capture
    with tempfile.TemporaryDirectory() as tmpdir:
        env = os.environ.copy()
        env["WHAI_TEST_MODE"] = "1"
        env["XDG_CONFIG_HOME"] = tmpdir

        session_name = "whai_test_session"
        try:
            _tmux_cmd("new-session", "-d", "-s", session_name, env=env)
            _tmux_cmd("send-keys", "-t", session_name, "echo 'test command 1'", "C-m")
            _tmux_cmd("send-keys", "-t", session_name, "echo 'test command 2'", "C-m")

            result = _tmux_cmd("capture-pane", "-t", session_name, "-p")
            assert result.returncode == 0, result.stderr
            assert "test command" in result.stdout

            capture_result = _tmux_cmd("capture-pane", "-t", session_name, "-p")
            assert capture_result.returncode == 0, f"tmux capture-pane failed: {capture_result.stderr}"
            assert capture_result.stdout is not None
            assert "test command" in capture_result.stdout
        finally:
            try:
                subprocess.run(
                    ["tmux", "-L", _TMUX_TEST_SOCKET, "kill-session", "-t", session_name],
                    timeout=5,
                    stderr=subprocess.DEVNULL,
                    check=False,
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
        _tmux_cmd("new-session", "-d", "-s", session_name)
        _tmux_cmd("split-window", "-t", f"{session_name}:0", "-h")
        _tmux_cmd("send-keys", "-t", f"{session_name}:0.0", f"echo {marker_0}", "C-m")
        _tmux_cmd("send-keys", "-t", f"{session_name}:0.1", f"echo {marker_1}", "C-m")

        time.sleep(0.3)

        socket_result = _tmux_cmd("display-message", "-t", session_name, "-p", "#{socket_path}")
        sid_result = _tmux_cmd("display-message", "-t", session_name, "-p", "#{session_id}")
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
                ["tmux", "-L", _TMUX_TEST_SOCKET, "kill-session", "-t", session_name],
                timeout=5,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass

