"""Performance tests for whai.

These tests validate that critical operations complete within acceptable time limits.
They focus on observable performance characteristics, not implementation details.

Note: These tests use generous thresholds to avoid flakiness on different hardware.
They're meant to catch major performance regressions, not micro-optimizations.
"""

import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import MagicMock, patch

import pytest

from whai.configuration.user_config import load_config
from whai.context import get_context
from whai.llm.token_utils import truncate_text_with_tokens


@pytest.fixture
def large_text_content():
    """Create large text content for truncation testing."""
    # 100KB of text
    return "Lorem ipsum dolor sit amet. " * 3500


@pytest.mark.performance
def test_token_truncation_performance(large_text_content):
    """Token truncation on large text completes in under 100ms.
    
    Token truncation uses tiktoken which is fast, but we want to ensure
    it stays fast even with large context (100KB text).
    """
    start_time = time.time()
    truncated, was_truncated = truncate_text_with_tokens(large_text_content, max_tokens=1000)
    elapsed = time.time() - start_time
    
    assert elapsed < 0.1, f"Token truncation took {elapsed:.3f}s, expected < 0.1s"
    assert len(truncated) < len(large_text_content)
    assert was_truncated is True


@pytest.mark.performance
def test_config_loading_performance(tmp_path, monkeypatch):
    """Configuration loads in under 50ms.
    
    Config loading happens on every whai invocation, so it must be fast.
    """
    # Create minimal config
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[llm]
default_provider = "openai"

[[llm.providers]]
name = "openai"
default_model = "gpt-4"
api_key = "test-key"
""")
    
    monkeypatch.setattr("whai.configuration.user_config.get_config_dir", lambda: tmp_path)
    
    start_time = time.time()
    config = load_config()
    elapsed = time.time() - start_time
    
    assert elapsed < 0.05, f"Config loading took {elapsed:.3f}s, expected < 0.05s"
    assert config.llm.default_provider == "openai"


@pytest.mark.performance
def test_context_capture_history_fallback_performance(monkeypatch, tmp_path):
    """Context capture with history fallback completes in under 300ms.
    
    When tmux is not available, whai falls back to parsing shell history.
    This should still be fast enough for interactive use.
    """
    # Create a reasonably large history file
    history_file = tmp_path / ".bash_history"
    with open(history_file, "w") as f:
        for i in range(1000):
            f.write(f"command_{i}\n")
    
    # Mock environment: no tmux, bash shell
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setenv("HOME", str(tmp_path))
    
    start_time = time.time()
    with patch("whai.utils.detect_shell", return_value="bash"):
        context, is_deep = get_context()
    elapsed = time.time() - start_time
    
    assert elapsed < 0.3, f"Context capture took {elapsed:.3f}s, expected < 0.3s"
    assert is_deep is False  # History fallback, not deep context


@pytest.mark.performance
def test_large_tmux_pane_capture_performance(monkeypatch):
    """Capturing large tmux panes completes in under 500ms.
    
    Tmux panes can have thousands of lines of scrollback.
    Capture should still be reasonably fast.
    """
    # Create mock tmux output with 5000 lines
    large_tmux_output = "\n".join([f"line {i}: some command output here" for i in range(5000)])
    
    monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1,0")
    
    def mock_run(*args, **kwargs):
        """Mock subprocess.run to return large tmux output."""
        mock_result = MagicMock()
        mock_result.stdout = large_tmux_output
        mock_result.returncode = 0
        return mock_result
    
    start_time = time.time()
    with patch("subprocess.run", side_effect=mock_run):
        from whai.context.tmux import _get_tmux_context
        context = _get_tmux_context()
    elapsed = time.time() - start_time
    
    assert elapsed < 0.5, f"Tmux capture took {elapsed:.3f}s, expected < 0.5s"
    assert context is not None
    assert len(context) > 0


@pytest.mark.performance
def test_llm_message_preparation_performance():
    """Message preparation for LLM completes in under 50ms.
    
    Building the message dict with system prompt, context, and user query
    should be nearly instantaneous.
    """
    system_prompt = "You are a helpful assistant." * 100  # ~3KB
    context = "command output\n" * 1000  # ~15KB
    user_query = "explain this error"
    
    start_time = time.time()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"TERMINAL CONTEXT:\n```\n{context}\n```\n\nUSER QUERY: {user_query}"},
    ]
    elapsed = time.time() - start_time
    
    assert elapsed < 0.05, f"Message preparation took {elapsed:.3f}s, expected < 0.05s"
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


@pytest.mark.performance
def test_role_file_loading_performance(tmp_path, monkeypatch):
    """Role file loading completes in under 20ms.
    
    Role loading happens on every whai invocation and should be very fast.
    """
    # Create a role file
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()
    role_file = roles_dir / "default.md"
    role_file.write_text("""---
model: gpt-4
temperature: 0.7
---

You are a helpful terminal assistant.""")
    
    monkeypatch.setattr("whai.configuration.user_config.get_config_dir", lambda: tmp_path)
    
    from whai.configuration.roles import load_role
    
    start_time = time.time()
    role = load_role("default")
    elapsed = time.time() - start_time
    
    assert elapsed < 0.02, f"Role loading took {elapsed:.3f}s, expected < 0.02s"
    assert role.name == "default"
    assert role.model == "gpt-4"


@pytest.mark.performance
def test_command_exclusion_from_context_performance(tmp_path, monkeypatch):
    """Excluding current command from context is fast (under 50ms).
    
    When whai captures context, it needs to exclude the current 'whai ...' command.
    This regex matching should be fast even with large context.
    """
    # Create large history with the command to exclude appearing once
    history_file = tmp_path / ".bash_history"
    with open(history_file, "w") as f:
        for i in range(5000):
            f.write(f"command_{i}\n")
        f.write("whai what is the biggest folder here?\n")
    
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setenv("HOME", str(tmp_path))
    
    start_time = time.time()
    with patch("whai.utils.detect_shell", return_value="bash"):
        context, _ = get_context(exclude_command="whai what is the biggest folder here?")
    elapsed = time.time() - start_time
    
    assert elapsed < 0.3, f"Context with exclusion took {elapsed:.3f}s, expected < 0.3s"
    # Verify exclusion worked
    assert "whai what is the biggest folder here?" not in context

