"""Integration tests for multi-turn conversations.

These tests validate that whai maintains context across multiple interactions
in a session, allowing for conversational back-and-forth.
"""

import os
import platform
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from whai.context.capture import get_context
from whai.core.session_logger import SessionLogger


@pytest.fixture
def conversation_session(monkeypatch):
    """Set up a whai shell session for multi-turn conversation testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        sess_dir = config_dir / "whai" / "sessions"
        sess_dir.mkdir(parents=True)
        
        # Create initial session log
        log_file = sess_dir / "session_20250101_120000.log"
        log_file.write_text(
            "PowerShell transcript start\n"
            "$ ls\nfile1.txt  file2.txt\n",
            encoding="utf-8",
        )
        
        # Mock get_config_dir
        def mock_get_config_dir():
            return config_dir / "whai"
        
        monkeypatch.setattr("whai.context.session_reader.get_config_dir", mock_get_config_dir)
        monkeypatch.setattr("whai.configuration.user_config.get_config_dir", mock_get_config_dir)
        monkeypatch.setattr("whai.core.session_logger.get_config_dir", mock_get_config_dir)
        monkeypatch.setattr("whai.shell.session.get_config_dir", mock_get_config_dir)
        
        monkeypatch.setenv("WHAI_SESSION_ACTIVE", "1")
        
        yield sess_dir, log_file


@pytest.mark.skipif(platform.system() != "Windows", reason="SessionLogger is Windows-only")
def test_multi_turn_conversation_accumulates_context(conversation_session):
    """Test that multiple whai calls in a session see each other's history."""
    sess_dir, log_file = conversation_session
    
    # Turn 1: User asks about files
    logger1 = SessionLogger()
    logger1.print("I see you have file1.txt and file2.txt in this directory.")
    
    # Verify first response is captured
    context_after_turn1 = get_context()
    assert context_after_turn1[0] is not None
    assert "file1.txt and file2.txt" in context_after_turn1[0]
    
    # Turn 2: User asks about the previous response
    # Context should include both the ls output AND the first whai response
    context_before_turn2 = get_context()
    assert "file1.txt and file2.txt" in context_before_turn2[0]
    assert "I see you have" in context_before_turn2[0]
    
    logger2 = SessionLogger()
    logger2.print("Would you like me to show you the contents of these files?")
    
    # Turn 3: User responds
    context_before_turn3 = get_context()
    assert "I see you have" in context_before_turn3[0]
    assert "Would you like me to show" in context_before_turn3[0]
    
    logger3 = SessionLogger()
    logger3.print("Sure, I'll read file1.txt for you.")
    logger3.log_command("cat file1.txt")
    logger3.log_command_output("Contents of file1\n", "", 0)
    
    # Final context should have all three turns
    final_context = get_context()
    assert "I see you have" in final_context[0]
    assert "Would you like me to show" in final_context[0]
    assert "Sure, I'll read" in final_context[0]
    assert "cat file1.txt" in final_context[0]
    assert "Contents of file1" in final_context[0]


def test_multi_turn_with_command_outputs(conversation_session):
    """Test that commands executed between whai calls are visible in context."""
    sess_dir, log_file = conversation_session
    
    # Turn 1: whai suggests a command
    if platform.system() == "Windows":
        logger1 = SessionLogger()
        logger1.print("Try running: Get-Process")
        
        # Simulate user running the command (append to log)
        log_file.write_text(
            log_file.read_text() + "$ Get-Process\nProcessName  PID\nsvchost      1234\n",
            encoding="utf-8",
        )
        
        # Turn 2: whai should see the command output
        context_with_process = get_context()
        assert "Get-Process" in context_with_process[0]
        assert "svchost" in context_with_process[0]
        
        logger2 = SessionLogger()
        logger2.print("I can see svchost is running with PID 1234.")
        
        # Final context has both whai responses and command output
        final_context = get_context()
        assert "Try running: Get-Process" in final_context[0]
        assert "svchost" in final_context[0]
        assert "I can see svchost is running" in final_context[0]
    else:
        # Non-Windows: similar test with Unix commands
        log_file.write_text(
            log_file.read_text() + "$ ps aux\nUSER  PID\nroot  1234\n",
            encoding="utf-8",
        )
        
        context_with_process = get_context()
        assert "ps aux" in context_with_process[0]
        assert "root" in context_with_process[0] or "1234" in context_with_process[0]


def test_conversation_context_excludes_current_whai_command(conversation_session):
    """Test that the current whai command is excluded from context sent to LLM."""
    sess_dir, log_file = conversation_session
    
    if platform.system() == "Windows":
        logger = SessionLogger()
        logger.print("Previous response")
        
        # Append whai command to log
        log_file.write_text(
            log_file.read_text() + "$ whai what are the biggest files here?\n",
            encoding="utf-8",
        )
        
        # Get context with exclusion
        context_excluded = get_context(exclude_command="whai what are the biggest files here?")
        
        # Should have previous response but not the current command
        assert "Previous response" in context_excluded[0]
        assert "what are the biggest files here?" not in context_excluded[0]
        
        # Without exclusion, command should be present
        context_included = get_context(exclude_command=None)
        assert "what are the biggest files here?" in context_included[0]


@pytest.mark.skipif(platform.system() != "Windows", reason="SessionLogger is Windows-only")
def test_long_conversation_maintains_coherence(conversation_session):
    """Test that a long conversation (10+ turns) maintains context coherence."""
    sess_dir, log_file = conversation_session
    
    # Simulate 10 turns
    for i in range(10):
        logger = SessionLogger()
        logger.print(f"Response {i+1}: This is turn number {i+1}.")
        
        # Every 3rd turn, verify all previous turns are in context
        if (i + 1) % 3 == 0:
            context = get_context()
            for j in range(i + 1):
                assert f"Response {j+1}" in context[0], f"Turn {j+1} should be in context at turn {i+1}"
    
    # Final verification: all 10 turns should be in context
    final_context = get_context()
    for i in range(10):
        assert f"Response {i+1}" in final_context[0]

