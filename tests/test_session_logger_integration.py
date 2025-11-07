"""Integration tests for SessionLogger with context capture."""

import os
import tempfile
from pathlib import Path

import pytest

from whai.context.session_reader import read_session_context


@pytest.fixture
def session_directory(monkeypatch):
    """Set up a mock whai shell session directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        sess_dir = config_dir / "whai" / "sessions"
        sess_dir.mkdir(parents=True)
        
        # Create a transcript log file (as PowerShell would)
        transcript_log = sess_dir / "session_20250101_120000.log"
        transcript_log.write_text(
            "**********************\n"
            "PowerShell transcript start\n"
            "Start time: 20250101120000\n"
            "**********************\n"
            "PowerShell transcript content\n",
            encoding='utf-8',
        )
        
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
        
        if old_active is None:
            os.environ.pop("WHAI_SESSION_ACTIVE", None)
        else:
            os.environ["WHAI_SESSION_ACTIVE"] = old_active


def test_context_capture_reads_whai_log(session_directory):
    """Context capture reads whai's self-logged output."""
    sess_dir, _ = session_directory
    
    from whai.core.session_logger import SessionLogger
    
    logger = SessionLogger()
    logger.print("LLM response")
    
    context = read_session_context()
    
    assert context is not None
    assert "LLM response" in context


def test_context_capture_merges_transcript_and_whai_log(session_directory):
    """Context capture merges both transcript and whai log."""
    sess_dir, transcript_log = session_directory
    
    from whai.core.session_logger import SessionLogger
    
    # Write to transcript (simulating PowerShell)
    transcript_log.write_text(
            "**********************\n"
            "PowerShell transcript start\n"
            "Start time: 20250101120000\n"
            "**********************\n"
            "PowerShell: command output\n",
            encoding='utf-8',
        )
    
    # Write to whai log
    logger = SessionLogger()
    logger.print("LLM: response")
    
    context = read_session_context()
    
    assert context is not None
    assert "PowerShell: command output" in context
    assert "LLM: response" in context


def test_context_capture_handles_missing_whai_log(session_directory):
    """Context capture works even if whai log doesn't exist yet."""
    sess_dir, transcript_log = session_directory
    
    # Only transcript exists
    transcript_log.write_text(
            "**********************\n"
            "PowerShell transcript start\n"
            "Start time: 20250101120000\n"
            "**********************\n"
            "PowerShell content\n",
            encoding='utf-8',
        )
    
    context = read_session_context()
    
    assert context is not None
    assert "PowerShell content" in context


def test_context_capture_handles_missing_transcript(session_directory):
    """Context capture works even if transcript doesn't exist."""
    sess_dir, transcript_log = session_directory
    
    from whai.core.session_logger import SessionLogger
    
    # Create whai log first (while transcript exists)
    logger = SessionLogger()
    logger.print("LLM response")
    
    # Now remove transcript
    transcript_log.unlink()
    
    # Context capture should still work with just whai log
    context = read_session_context()
    
    assert context is not None
    assert "LLM response" in context


def test_context_capture_preserves_ordering(session_directory):
    """Context capture preserves chronological order of events."""
    sess_dir, transcript_log = session_directory
    
    from whai.core.session_logger import SessionLogger
    
    # Write transcript content first
    transcript_log.write_text(
            "**********************\n"
            "PowerShell transcript start\n"
            "Start time: 20250101120000\n"
            "**********************\n"
            "Transcript: event 1\n",
            encoding='utf-8',
        )
    
    # Then whai content
    logger = SessionLogger()
    logger.print("LLM: event 2")
    
    # More transcript
    transcript_log.write_text(
            "**********************\n"
            "PowerShell transcript start\n"
            "Start time: 20250101120000\n"
            "**********************\n"
            "Transcript: event 1\nTranscript: event 3\n",
            encoding='utf-8',
        )
    
    # More whai
    logger.print("LLM: event 4")
    
    context = read_session_context()
    
    # Both should be present
    assert "event 1" in context
    assert "event 2" in context
    assert "event 3" in context
    assert "event 4" in context
