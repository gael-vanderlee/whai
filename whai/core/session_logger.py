"""Session logging for whai shell deep context capture.

When running inside a whai shell session, this module ensures that whai's
LLM responses and command outputs are logged to the session file for context
in subsequent commands.
"""

import os
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console

from whai.configuration.user_config import get_config_dir
from whai.logging_setup import get_logger

logger = get_logger(__name__)


class SessionLogger:
    """
    Logs whai output to both console and session log file.
    
    When a whai shell session is active (WHAI_SESSION_ACTIVE=1), this logger
    writes all output to both the Rich console (for user display) and the
    session log file (for context capture in subsequent commands).
    
    If no session is active, behaves like a normal console.
    """
    
    def __init__(self, console: Optional[Console] = None):
        """
        Initialize session logger.
        
        Args:
            console: Rich Console instance to use. If None, creates a new one.
        """
        self.console = console or Console()
        self._log_path = self._get_log_path()
        self.enabled = self._log_path is not None
        
        if self.enabled:
            logger.debug("SessionLogger enabled, logging to %s", self._log_path)
    
    def _get_log_path(self) -> Optional[Path]:
        """Get whai output log path from session directory."""
        if os.environ.get("WHAI_SESSION_ACTIVE") != "1":
            return None

        if os.name != "nt":
            logger.debug("SessionLogger disabled on non-Windows platform")
            return None

        sess_dir = get_config_dir() / "sessions"

        session_logs = [
            log for log in sess_dir.glob("session_*.log")
            if not log.name.endswith("_whai.log")
        ]
        if not session_logs:
            return None

        transcript_log = sorted(session_logs, reverse=True)[0]
        return transcript_log.parent / f"{transcript_log.stem}_whai{transcript_log.suffix}"
    
    def _append_to_log(self, text: str) -> None:
        """
        Append text to session log file.
        
        Errors are logged but don't break execution.
        """
        if not self.enabled or not self._log_path:
            return
        
        try:
            with open(self._log_path, 'a', encoding='utf-8') as f:
                f.write(text)
                f.flush()
        except Exception as e:
            # Log error but don't crash whai if session logging fails
            logger.error(
                "Failed to write to session log %s: %s",
                self._log_path,
                e
            )
    
    def print(self, text: str = "", end: str = "\n", **kwargs) -> None:
        """
        Print to console and log to session file.
        
        Args:
            text: Text to print.
            end: String appended after text (default newline).
            **kwargs: Additional arguments passed to Rich console.print().
        """
        # Always print to console for user
        self.console.print(text, end=end, **kwargs)
        
        # Also log to session file if enabled
        if self.enabled:
            self._append_to_log(text + end)
    
    def log_command(self, command: str) -> None:
        """
        Log an executed command to the session file.
        
        This provides context about what command was run, helping the LLM
        understand the command-output pairing in subsequent queries.
        
        Args:
            command: The shell command that was executed.
        """
        if not self.enabled:
            return
        
        # Format: blank line, then "$ command" like shell history
        self._append_to_log(f"\n$ {command}\n")
    
    def log_command_output(
        self, stdout: str, stderr: str, returncode: int
    ) -> None:
        """
        Log command output to session file.
        
        Args:
            stdout: Command's standard output.
            stderr: Command's standard error.
            returncode: Command's exit code.
        """
        if not self.enabled:
            return
        
        parts = []
        
        if stdout:
            parts.append(stdout)
            # Ensure trailing newline
            if not stdout.endswith('\n'):
                parts.append('\n')
        
        if stderr:
            parts.append(f"[stderr]: {stderr}\n")
        
        # Log exit code for non-zero returns
        if returncode != 0:
            parts.append(f"[exit code: {returncode}]\n")
        
        if parts:
            self._append_to_log(''.join(parts))
    
    def log_command_failure(self, error_message: str, timeout: Optional[int] = None) -> None:
        """
        Log command execution failure to session file.
        
        This ensures that failures (timeouts, crashes, etc.) are recorded in the
        session transcript for deep context capture, so subsequent queries can see
        what went wrong.
        
        Args:
            error_message: Description of the failure.
            timeout: Timeout value in seconds if this was a timeout failure.
        """
        if not self.enabled:
            return
        
        if timeout is not None and "timed out" in error_message.lower():
            # Standardized timeout marker for LLM context
            self._append_to_log(f"[COMMAND TIMED OUT after {timeout}s]\n")
        else:
            # General failure marker
            self._append_to_log(f"[COMMAND FAILED: {error_message}]\n")


