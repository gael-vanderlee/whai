"""Test to verify the context capture fix works end-to-end.

This test simulates the exact scenario reported in the issue:
- Run whai command in a whai shell
- LLM response is generated
- Second whai command should have the first response in context
"""

import os
import tempfile
from pathlib import Path

import pytest

from whai.core.session_logger import SessionLogger
from whai.context.session_reader import read_session_context


@pytest.fixture
def simulated_whai_shell(monkeypatch):
    """Simulate a whai shell session."""
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
            "PowerShell transcript\n",
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


def test_context_capture_fix_reproduces_original_issue(simulated_whai_shell):
    """Reproduce the original issue and verify it's fixed."""
    sess_dir, _ = simulated_whai_shell
    
    # Simulate first whai command
    logger = SessionLogger()
    
    first_response = """Short answer — here's what I can see and what it means.

What I can see (from the scrollback you pasted)
- You ran: git asd
  - Git replied: "git: 'asd' is not a git command. ... The most similar command is add"
  - Meaning: you typed a non-existent git subcommand (likely a typo). Git suggests "add".

Commands I can run for you (I will execute them if you want):
1) Inspect Git status and recent commits
2) Show directory contents in PowerShell "long" style"""
    
    for line in first_response.split('\n'):
        logger.print(line)
    
    # Verify the response was logged
    context_after_first_command = read_session_context()
    assert context_after_first_command is not None
    assert "what I can see and what it means" in context_after_first_command
    assert "Commands I can run for you" in context_after_first_command
    
    # Simulate second whai command reading context
    logger.print("\nI'll run option 2 for you.")
    logger.log_command("Get-ChildItem -Force | Format-Table Mode,Length,LastWriteTime,Name -AutoSize")
    logger.log_command_output("Mode  Length  LastWriteTime  Name\n", "", 0)
    
    # Verify both responses are in context
    context_after_second_command = read_session_context()
    assert context_after_second_command is not None
    
    # First response should still be there
    assert "what I can see and what it means" in context_after_second_command
    assert "Commands I can run for you" in context_after_second_command
    
    # Second response should also be there
    assert "I'll run option 2" in context_after_second_command
    assert "Get-ChildItem" in context_after_second_command


def test_multiple_sequential_whai_calls(simulated_whai_shell):
    """Test multiple sequential whai calls maintain complete context."""
    sess_dir, _ = simulated_whai_shell
    
    logger = SessionLogger()
    
    # First call
    logger.print("Response 1: Here's the status")
    logger.log_command("git status")
    logger.log_command_output("On branch main\n", "", 0)
    
    # Second call (should see first)
    context_before_second = read_session_context()
    assert "Response 1" in context_before_second
    assert "git status" in context_before_second
    
    logger.print("Response 2: Now let's check files")
    logger.log_command("ls")
    logger.log_command_output("README.md\n", "", 0)
    
    # Third call (should see both)
    context_before_third = read_session_context()
    assert "Response 1" in context_before_third
    assert "Response 2" in context_before_third
    assert "git status" in context_before_third
    assert "ls" in context_before_third
    
    logger.print("Response 3: Everything looks good!")
    
    # Final context should have all three
    final_context = read_session_context()
    assert "Response 1" in final_context
    assert "Response 2" in final_context
    assert "Response 3" in final_context


def test_context_capture_with_commands_only_no_tool_calls(simulated_whai_shell):
    """Test that LLM responses without tool calls are still captured."""
    sess_dir, _ = simulated_whai_shell
    
    logger = SessionLogger()
    
    # Pure informational response (no commands executed)
    logger.print("This is a response explaining something to the user.")
    logger.print("It spans multiple lines.")
    logger.print("But doesn't execute any commands.")
    
    context = read_session_context()
    
    assert "explaining something to the user" in context
    assert "spans multiple lines" in context
    assert "doesn't execute any commands" in context


def test_multiple_whai_calls_capture_story_output(simulated_whai_shell):
    """Test that first whai call output (like a story) is captured for second call."""
    sess_dir, transcript_log = simulated_whai_shell
    
    # Verify transcript log exists (created by fixture)
    assert transcript_log.exists(), f"Transcript log should exist at {transcript_log}"
    
    # First whai call: user asks for a story
    logger1 = SessionLogger()
    assert logger1.enabled, "SessionLogger should be enabled in active session"
    assert logger1._log_path is not None, "SessionLogger should have a log path"
    
    story_response = """I'll tell you a short story.

Whai and the Midnight Terminal

Whai was born in a quiet folder on a developer's machine, a tiny executable with a curious prompt and a fondness for good instructions. By day it answered simple requests — list files, run tests, fetch help — but at night, when the IDEs dimmed and the terminals quieted, Whai liked to wander the filesystem and listen to the other programs.

One evening, a soft error message drifted up from the logs: a forgotten script named Lumen had stopped printing its last line."""
    
    # Print the story response
    for line in story_response.split('\n'):
        logger1.print(line)
    
    # Verify the story was logged to the whai log file
    whai_log = sess_dir / "session_20250101_120000_whai.log"
    assert whai_log.exists(), f"Whai log should exist at {whai_log}. SessionLogger log path: {logger1._log_path}"
    logged_content = whai_log.read_text(encoding='utf-8')
    assert "Whai and the Midnight Terminal" in logged_content
    assert "forgotten script named Lumen" in logged_content
    
    # Second whai call: should see the story in context
    context = read_session_context()
    assert context is not None
    assert "Whai and the Midnight Terminal" in context
    assert "forgotten script named Lumen" in context
    
    # Second call responds
    logger2 = SessionLogger()
    logger2.print("Would you like another story?")
    
    # Verify both responses are in context
    final_context = read_session_context()
    assert "Whai and the Midnight Terminal" in final_context
    assert "Would you like another story?" in final_context
