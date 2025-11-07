"""Unit tests for SessionLogger."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from whai.core.session_logger import SessionLogger


@pytest.fixture
def session_directory(monkeypatch):
    """Create a temporary session directory with a transcript log file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        sess_dir = config_dir / "whai" / "sessions"
        sess_dir.mkdir(parents=True)
        
        # Create a transcript log file (as PowerShell would)
        transcript_log = sess_dir / "session_20250101_120000.log"
        transcript_log.write_text("PowerShell transcript content\n", encoding='utf-8')
        
        # Mock get_config_dir in all places it's used
        def mock_get_config_dir():
            return config_dir / "whai"
        
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
        
        old_active = os.environ.get("WHAI_SESSION_ACTIVE")
        os.environ["WHAI_SESSION_ACTIVE"] = "1"
        
        yield sess_dir, transcript_log
        
        # Restore environment
        if old_active is None:
            os.environ.pop("WHAI_SESSION_ACTIVE", None)
        else:
            os.environ["WHAI_SESSION_ACTIVE"] = old_active


def test_session_logger_disabled_when_not_in_session():
    """SessionLogger does not log when not in a whai session."""
    os.environ.pop("WHAI_SESSION_ACTIVE", None)
    
    mock_console = MagicMock()
    logger = SessionLogger(console=mock_console)
    
    logger.print("Test message")
    
    assert logger.enabled is False
    mock_console.print.assert_called_once()


def test_session_logger_writes_to_separate_file(session_directory):
    """SessionLogger writes to a separate whai log file, not the transcript."""
    sess_dir, transcript_log = session_directory
    
    mock_console = MagicMock()
    logger = SessionLogger(console=mock_console)
    
    assert logger.enabled is True
    
    logger.print("LLM response")
    
    # Verify whai log file was created
    whai_log = sess_dir / "session_20250101_120000_whai.log"
    assert whai_log.exists()
    
    # Verify content was written
    content = whai_log.read_text(encoding='utf-8')
    assert "LLM response\n" in content
    
    # Verify transcript file was not modified
    transcript_content = transcript_log.read_text(encoding='utf-8')
    assert "LLM response" not in transcript_content


def test_session_logger_logs_commands(session_directory):
    """SessionLogger logs executed commands to the whai log file."""
    sess_dir, _ = session_directory
    
    logger = SessionLogger()
    
    logger.log_command("git status")
    
    whai_log = sess_dir / "session_20250101_120000_whai.log"
    assert whai_log.exists()
    
    content = whai_log.read_text(encoding='utf-8')
    assert "$ git status\n" in content


def test_session_logger_logs_command_output(session_directory):
    """SessionLogger logs command output to the whai log file."""
    sess_dir, _ = session_directory
    
    logger = SessionLogger()
    
    logger.log_command_output("output line\n", "error line", 1)
    
    whai_log = sess_dir / "session_20250101_120000_whai.log"
    content = whai_log.read_text(encoding='utf-8')
    
    assert "output line\n" in content
    assert "[stderr]: error line\n" in content
    assert "[exit code: 1]\n" in content


def test_session_logger_handles_write_errors_gracefully(session_directory):
    """SessionLogger does not crash if writing to log file fails."""
    sess_dir, _ = session_directory
    
    logger = SessionLogger()
    
    # Make the whai log file read-only
    whai_log = sess_dir / "session_20250101_120000_whai.log"
    whai_log.touch()
    whai_log.chmod(0o444)
    
    try:
        # Should not raise an exception
        logger.print("Test message")
        logger.log_command("test command")
    finally:
        whai_log.chmod(0o644)


def test_session_logger_prints_to_console(session_directory):
    """SessionLogger always prints to console regardless of logging."""
    mock_console = MagicMock()
    logger = SessionLogger(console=mock_console)
    
    logger.print("Test message", soft_wrap=True)
    
    mock_console.print.assert_called_once_with(
        "Test message", end="\n", soft_wrap=True
    )


def test_session_logger_logs_multiple_interactions(session_directory):
    """SessionLogger captures multiple whai interactions in sequence."""
    sess_dir, _ = session_directory
    
    logger = SessionLogger()
    
    logger.print("Response 1")
    logger.log_command("command1")
    logger.log_command_output("output1\n", "", 0)
    logger.print("Response 2")
    logger.log_command("command2")
    logger.log_command_output("output2\n", "", 0)
    
    whai_log = sess_dir / "session_20250101_120000_whai.log"
    content = whai_log.read_text(encoding='utf-8')
    
    # Verify all content is present in order
    assert "Response 1\n" in content
    assert "$ command1\n" in content
    assert "output1\n" in content
    assert "Response 2\n" in content
    assert "$ command2\n" in content
    assert "output2\n" in content


def test_session_logger_handles_unicode(session_directory):
    """SessionLogger handles Unicode characters correctly."""
    sess_dir, _ = session_directory
    
    logger = SessionLogger()
    
    logger.print("Hello 世界 🌍")
    logger.log_command("echo 'Café'")
    logger.log_command_output("Café ☕\n", "", 0)
    
    whai_log = sess_dir / "session_20250101_120000_whai.log"
    content = whai_log.read_text(encoding='utf-8')
    
    assert "Hello 世界 🌍" in content
    assert "echo 'Café'" in content
    assert "Café ☕" in content


def test_session_logger_uses_most_recent_session_log(session_directory):
    """SessionLogger uses the most recent session log when multiple exist."""
    sess_dir, _ = session_directory
    
    # Create an older session log
    older_log = sess_dir / "session_20250101_110000.log"
    older_log.write_text("older content\n", encoding='utf-8')
    
    logger = SessionLogger()
    
    logger.print("new content")
    
    # Should write to whai log for the most recent session
    recent_whai_log = sess_dir / "session_20250101_120000_whai.log"
    older_whai_log = sess_dir / "session_20250101_110000_whai.log"
    
    assert recent_whai_log.exists()
    assert "new content\n" in recent_whai_log.read_text(encoding='utf-8')
    assert not older_whai_log.exists()
