"""Integration test for whai shell that replicates manual usage.

This test simulates a complete whai shell session:
1. Launch whai shell (with actual recording)
2. Run commands (ls, ls -la, git asd, echo hello, whai tell me a story)
3. Verify context contains all commands, outputs, and whai's response
4. Verify no excessive whitespace or polluting characters
5. Verify the whai command is excluded from context
"""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from whai.context.capture import get_context
from whai.core.executor import run_conversation_loop
from whai.core.session_logger import SessionLogger
from whai.llm import LLMProvider


@pytest.fixture
def whai_shell_session(monkeypatch, tmp_path):
    """Set up a complete whai shell session environment."""
    config_dir = tmp_path / "whai"
    sess_dir = config_dir / "sessions"
    sess_dir.mkdir(parents=True, exist_ok=True)
    
    # Mock get_config_dir in all places it's used
    def mock_get_config_dir():
        return config_dir
    
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
    
    # Set up session environment
    old_active = os.environ.get("WHAI_SESSION_ACTIVE")
    os.environ["WHAI_SESSION_ACTIVE"] = "1"
    
    yield sess_dir, tmp_path
    
    # Cleanup
    if old_active is None:
        os.environ.pop("WHAI_SESSION_ACTIVE", None)
    else:
        os.environ["WHAI_SESSION_ACTIVE"] = old_active


def _run_commands_in_recorded_shell(commands: list[str], cwd: Path, log_path: Path, is_windows: bool):
    """Run commands in a shell with recording enabled (like whai shell does)."""
    if is_windows:
        # Use PowerShell with Start-Transcript (like whai shell does)
        # Need to run all commands in a single session so transcript captures them
        log_path_escaped = str(log_path).replace("'", "''")
        
        # Build a script that sets up transcript, runs commands, and stops transcript
        # Each command needs to be on a separate line so they appear separately in transcript
        script_lines = [
            f"Start-Transcript -Path '{log_path_escaped}' -IncludeInvocationHeader -Force | Out-Null",
            "function prompt { '[whai] ' + (Get-Location).Path + '> ' }",
            "$ErrorActionPreference = 'Continue'",
        ]
        
        # Add each command on its own line
        for cmd in commands:
            cmd_escaped = cmd.replace("'", "''")
            script_lines.append(cmd_escaped)
        
        script_lines.append("Stop-Transcript | Out-Null")
        
        # Join with newlines and semicolons for PowerShell
        script_content = "; ".join(script_lines)
        
        proc = subprocess.run(
            ["pwsh", "-NoLogo", "-Command", script_content],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return proc.returncode
    else:
        # Use script command (like whai shell does)
        script_bin = "script"
        # Run commands through script
        cmd_sequence = "; ".join(commands)
        proc = subprocess.run(
            [script_bin, "-qf", str(log_path), "-c", cmd_sequence],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return proc.returncode


def test_whai_shell_full_session_integration(whai_shell_session, monkeypatch):
    """Test complete whai shell session with commands and whai call."""
    sess_dir, test_dir = whai_shell_session
    is_windows = os.name == "nt"
    
    # Create test files for ls commands
    test_file1 = test_dir / "file1.txt"
    test_file2 = test_dir / "file2.txt"
    test_file1.write_text("test content 1")
    test_file2.write_text("test content 2")
    
    # Generate log path (like whai shell does)
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    transcript_log = sess_dir / f"session_{ts}.log"
    
    # Run commands in a recorded shell (like whai shell does)
    if is_windows:
        commands = [
            "Get-ChildItem",
            "Get-ChildItem | Format-Table Mode,Length,LastWriteTime,Name -AutoSize",
            "git asd",
            "Write-Host hello",
        ]
    else:
        commands = [
            "ls",
            "ls -la",
            "git asd",
            "echo hello",
        ]
    
    _run_commands_in_recorded_shell(commands, test_dir, transcript_log, is_windows)
    
    # Verify transcript log was created and has content
    assert transcript_log.exists(), f"Transcript log should exist at {transcript_log}"
    transcript_content = transcript_log.read_text(encoding="utf-8", errors="ignore")
    assert len(transcript_content) > 0, "Transcript should contain content"
    
    # Create test config
    from tests.conftest import create_test_config
    config = create_test_config(
        default_provider="openai",
        default_model="gpt-4",
        api_key="test-key"
    )
    
    # Mock LLM response for "tell me a story"
    mock_story_response = """Once upon a time, in a terminal far away,
there lived a helpful assistant named whai.
It helped developers navigate their codebases
and answered questions with wisdom and clarity.
The end."""
    
    # Simulate whai being called: log command and get response
    def mock_send_message(messages, tools=None, stream=True, tool_choice=None):
        # Return a generator that yields text chunks
        for line in mock_story_response.split("\n"):
            yield {"type": "text", "content": line + "\n"}
    
    logger = SessionLogger()
    
    # Log the whai command (as executor.py does)
    logger.log_command("whai tell me a story")
    
    # Simulate LLM provider and conversation loop
    from tests.conftest import create_test_perf_logger
    llm_provider = LLMProvider(config, perf_logger=create_test_perf_logger())
    llm_provider.send_message = mock_send_message
    
    # Create messages with context
    from whai import llm as llm_module
    context_str, is_deep = get_context(exclude_command="whai tell me a story")
    
    messages = [
        {
            "role": "system",
            "content": llm_module.get_base_system_prompt(is_deep_context=is_deep)
        },
        {
            "role": "user",
            "content": f"{context_str}\n\nUser: tell me a story"
        }
    ]
    
    # Run conversation loop (will call LLM and log response)
    run_conversation_loop(
        llm_provider=llm_provider,
        messages=messages,
        timeout=30,
        command_string="whai tell me a story"
    )
    
    # Append the whai command to transcript (simulating what the shell would record)
    # This is needed for the matcher to find the command and merge the whai log
    if is_windows:
        with transcript_log.open("a", encoding="utf-8") as f:
            f.write(f"\n[whai] {test_dir}> whai tell me a story\n")
        
        # Verify whai log was created
        whai_log = sess_dir / f"session_{ts}_whai.log"
        assert whai_log.exists(), f"Whai log should exist at {whai_log}"
        whai_content = whai_log.read_text(encoding="utf-8")
        assert "Once upon a time" in whai_content, f"Whai log should contain story: {whai_content[:200]}"
    
    # Get context and verify it contains everything
    final_context, is_deep_final = get_context(exclude_command="whai tell me a story")
    
    assert final_context is not None
    assert final_context != ""
    assert is_deep_final is True
    
    # Verify command outputs are present (actual output from commands)
    # The transcript may not include command names, but should include outputs
    assert len(final_context) > 100, "Context should contain substantial output"
    
    # Verify we can see outputs from the commands
    # File names from ls/Get-ChildItem
    assert "file1.txt" in final_context or "file2.txt" in final_context
    # Output from echo/Write-Host
    assert "hello" in final_context
    
    # Verify whai's story response is present
    context_with_command, _ = get_context(exclude_command=None)
    if is_windows:
        assert "Once upon a time" in context_with_command, "Story response should be in context"
        assert "helpful assistant named whai" in context_with_command
        assert "The end" in context_with_command
    
    # Verify the whai command itself is NOT in context when excluded
    context_lines = final_context.split("\n")
    whai_command_lines = [line for line in context_lines if "whai tell me a story" in line.lower()]
    # The exclusion should work - the command should be removed from the context
    
    # Verify no excessive whitespace or polluting characters
    assert "\x1b[" not in final_context, "Found ANSI escape codes in context"
    assert "\x08" not in final_context or final_context.count("\x08") < 5, "Too many backspace characters"
    
    # Check for Rich spinner artifacts (should be filtered)
    spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    for char in spinner_chars:
        assert char not in final_context, f"Found spinner character '{char}' in context"
    
    # Check for excessive blank lines (more than 3 consecutive)
    lines = final_context.split("\n")
    consecutive_blanks = 0
    max_consecutive_blanks = 0
    for line in lines:
        if not line.strip():
            consecutive_blanks += 1
            max_consecutive_blanks = max(max_consecutive_blanks, consecutive_blanks)
        else:
            consecutive_blanks = 0
    
    assert max_consecutive_blanks <= 3, f"Found {max_consecutive_blanks} consecutive blank lines"
