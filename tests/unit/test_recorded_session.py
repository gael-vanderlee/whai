"""Tests for recorded shell session context capture."""

import os
from pathlib import Path

import pytest

from whai.context.capture import get_context
from whai.context.session_reader import read_session_context


def test_session_log_context_from_env(tmp_path, monkeypatch):
    """Test session log context is captured from session directory."""
    # Create session directory structure
    sess_dir = tmp_path / "whai" / "sessions"
    sess_dir.mkdir(parents=True)
    
    # Create a session log file
    log_file = sess_dir / "session_20250101_120000.log"
    log_file.write_text(
        "Script started on 2025-01-01 12:00:00+00:00\n"
        "$ ls -la\ntotal 100\ndrwxr-xr-x 5 user user 4096\n"
        "$ echo hello\nhello\n"
        "$ pwd\n/home/user/project\n",
        encoding="utf-8",
    )
    
    # Mock get_config_dir in all places it's used
    def mock_get_config_dir():
        return tmp_path / "whai"
    
    monkeypatch.setattr(
        "whai.context.session_reader.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.core.session_logger.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.shell.session.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setenv("WHAI_SESSION_ACTIVE", "1")
    
    # Get context
    context = read_session_context()
    
    assert context is not None
    assert "echo hello" in context
    assert "pwd" in context


@pytest.mark.skip(reason="Session logs are ephemeral by default; cache lookup is not applicable")
def test_session_log_context_from_cache_dir_unix(tmp_path, monkeypatch):
    pass


@pytest.mark.skip(reason="Session logs are ephemeral by default; cache lookup is not applicable")
def test_session_log_context_from_cache_dir_windows(tmp_path, monkeypatch):
    pass


def test_session_log_context_no_log_available(monkeypatch):
    """Test session log context returns None when no log is available."""
    from pathlib import Path
    # Mock get_config_dir in all places it's used
    def mock_get_config_dir():
        return Path("/nonexistent/path") / "whai"
    
    monkeypatch.setattr(
        "whai.context.session_reader.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.core.session_logger.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.shell.session.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setenv("WHAI_SESSION_ACTIVE", "1")
    
    context = read_session_context()
    
    assert context is None


def test_session_log_context_empty_log(tmp_path, monkeypatch):
    """Test session log context returns None for empty log files."""
    sess_dir = tmp_path / "whai" / "sessions"
    sess_dir.mkdir(parents=True)
    
    log_file = sess_dir / "session_20250101_120000.log"
    log_file.write_text("", encoding="utf-8")
    
    # Mock get_config_dir in all places it's used
    def mock_get_config_dir():
        return tmp_path / "whai"
    
    monkeypatch.setattr(
        "whai.context.session_reader.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.core.session_logger.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.shell.session.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setenv("WHAI_SESSION_ACTIVE", "1")
    
    context = read_session_context()
    
    assert context is None


def test_session_log_context_tail_limit(tmp_path, monkeypatch):
    """Test session log context respects max_bytes limit."""
    sess_dir = tmp_path / "whai" / "sessions"
    sess_dir.mkdir(parents=True)
    
    # Create a large log file
    log_file = sess_dir / "session_20250101_120000.log"
    large_content = "Script started on 2025-01-01 12:00:00+00:00\n" + "x" * 300_000  # 300KB
    recent_marker = "\n$ recent command\nrecent output\n"
    log_file.write_text(large_content + recent_marker, encoding="utf-8")
    
    # Mock get_config_dir in all places it's used
    def mock_get_config_dir():
        return tmp_path / "whai"
    
    monkeypatch.setattr(
        "whai.context.session_reader.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.core.session_logger.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.shell.session.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setenv("WHAI_SESSION_ACTIVE", "1")
    
    # Get context with default max_bytes (200KB)
    context = read_session_context()
    
    assert context is not None
    # Should contain recent content
    assert "recent command" in context
    # Context should be smaller than full file
    assert len(context) < len(large_content) + len(recent_marker)


def test_get_context_prefers_session_over_history(tmp_path, monkeypatch):
    """Test that get_context prefers session log over shell history."""
    sess_dir = tmp_path / "whai" / "sessions"
    sess_dir.mkdir(parents=True)
    
    # Create a session log
    log_file = sess_dir / "session_20250101_120000.log"
    log_file.write_text(
        "Script started on 2025-01-01 12:00:00+00:00\n"
        "$ session command\nsession output\n",
        encoding="utf-8",
    )
    
    # Mock get_config_dir in all places it's used
    def mock_get_config_dir():
        return tmp_path / "whai"
    
    monkeypatch.setattr(
        "whai.context.session_reader.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.core.session_logger.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.shell.session.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setenv("WHAI_SESSION_ACTIVE", "1")
    # Mock tmux to not be available
    monkeypatch.delenv("TMUX", raising=False)
    
    # Get context
    context, is_deep = get_context()
    
    # Should get session context (deep)
    assert is_deep is True
    assert "session command" in context


def test_get_context_session_is_deep_context(tmp_path, monkeypatch):
    """Test that session log context is marked as deep context."""
    sess_dir = tmp_path / "whai" / "sessions"
    sess_dir.mkdir(parents=True)
    
    # Create a session log
    log_file = sess_dir / "session_20250101_120000.log"
    log_file.write_text(
        "Script started on 2025-01-01 12:00:00+00:00\n"
        "$ test\noutput\n",
        encoding="utf-8",
    )
    
    # Mock get_config_dir in all places it's used
    def mock_get_config_dir():
        return tmp_path / "whai"
    
    monkeypatch.setattr(
        "whai.context.session_reader.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.core.session_logger.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.shell.session.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setenv("WHAI_SESSION_ACTIVE", "1")
    monkeypatch.delenv("TMUX", raising=False)
    
    context, is_deep = get_context()
    
    # Session context should be deep (includes outputs)
    assert is_deep is True


def test_session_log_invalid_utf8(tmp_path, monkeypatch):
    """Test session log handles invalid UTF-8 gracefully."""
    sess_dir = tmp_path / "whai" / "sessions"
    sess_dir.mkdir(parents=True)
    
    log_file = sess_dir / "session_20250101_120000.log"
    # Write some binary data mixed with text
    log_file.write_bytes(
        b"Script started on 2025-01-01 12:00:00+00:00\n"
        b"$ command\n\xff\xfe invalid bytes \n$ another command\noutput\n"
    )
    
    # Mock get_config_dir in all places it's used
    def mock_get_config_dir():
        return tmp_path / "whai"
    
    monkeypatch.setattr(
        "whai.context.session_reader.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.core.session_logger.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setattr(
        "whai.shell.session.get_config_dir",
        mock_get_config_dir
    )
    monkeypatch.setenv("WHAI_SESSION_ACTIVE", "1")
    
    # Should not crash, uses errors='ignore'
    context = read_session_context()
    
    # Should still capture some content
    assert context is not None
    assert "command" in context
