"""Target pane utilities for whai - remote pane control via tmux."""

import os
import subprocess
import time
from typing import Optional, Tuple

from whai.constants import CONTEXT_CAPTURE_TIMEOUT, TMUX_SCROLLBACK_LINES
from whai.logging_setup import get_logger

logger = get_logger(__name__)

# Default timeout for waiting for command completion in target pane
TARGET_COMMAND_WAIT_TIMEOUT = 30  # seconds
TARGET_COMMAND_POLL_INTERVAL = 0.5  # seconds


def is_in_tmux() -> bool:
    """Check if we're running inside a tmux session."""
    return "TMUX" in os.environ


def pane_exists(pane_id: str) -> bool:
    """Check if a tmux pane exists.
    
    Args:
        pane_id: Pane number (e.g., "1") or pane ID (e.g., "%5")
    """
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-t", pane_id, "-p", "#{pane_id}"],
            capture_output=True,
            text=True,
            timeout=CONTEXT_CAPTURE_TIMEOUT,
        )
        return result.returncode == 0 and result.stdout.strip() != ""
    except Exception:
        return False


def capture_target_context(pane_id: str, scrollback_lines: int = TMUX_SCROLLBACK_LINES) -> Optional[str]:
    """Capture the terminal context from a target pane.
    
    Args:
        pane_id: Pane number (e.g., "1") or pane ID (e.g., "%5")
        scrollback_lines: Number of scrollback lines to capture (default: same as local tmux capture).
        
    Returns:
        The captured pane content, or None on failure.
    """
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", pane_id, "-p", "-S", f"-{scrollback_lines}"],
            capture_output=True,
            text=True,
            timeout=CONTEXT_CAPTURE_TIMEOUT,
        )
        
        if result.returncode == 0:
            output = result.stdout
            logger.info(f"Captured target pane {pane_id} context ({len(output)} chars)")
            return output
        else:
            logger.error(f"Failed to capture pane {pane_id}: {result.stderr}")
            return None
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout capturing pane {pane_id}")
        return None
    except FileNotFoundError:
        logger.error("tmux not found")
        return None
    except Exception as e:
        logger.error(f"Error capturing pane {pane_id}: {e}")
        return None


def get_last_line(pane_id: str) -> Optional[str]:
    """Get the last non-empty line from a pane (useful for detecting prompt).
    
    Args:
        pane_id: Pane number or pane ID
        
    Returns:
        The last non-empty line, or None on failure.
    """
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", pane_id, "-p"],
            capture_output=True,
            text=True,
            timeout=CONTEXT_CAPTURE_TIMEOUT,
        )
        
        if result.returncode == 0:
            lines = [l for l in result.stdout.split('\n') if l.strip()]
            return lines[-1] if lines else None
        return None
    except Exception:
        return None


def wait_for_command_completion(
    pane_id: str, 
    timeout: int = TARGET_COMMAND_WAIT_TIMEOUT,
    poll_interval: float = TARGET_COMMAND_POLL_INTERVAL
) -> Tuple[bool, str]:
    """Wait for a command to complete in target pane by detecting prompt return.
    
    This works by:
    1. Capturing initial last line (should be the command being executed)
    2. Polling until the last line changes and looks like a prompt (ends with $, #, >, etc.)
    
    Args:
        pane_id: The target pane ID
        timeout: Maximum seconds to wait
        poll_interval: Seconds between polls
        
    Returns:
        Tuple of (completed: bool, output: str)
        - completed: True if command finished, False if timeout
        - output: The captured output after command completion
    """
    start_time = time.time()
    
    # Common prompt endings
    prompt_endings = ('$', '#', '>', '%', '»', '❯', '➜')
    
    # Wait a moment for command to start
    time.sleep(0.3)
    
    # Get initial state (small capture just to track changes)
    initial_capture = capture_target_context(pane_id, scrollback_lines=20)
    
    while (time.time() - start_time) < timeout:
        time.sleep(poll_interval)
        
        last_line = get_last_line(pane_id)
        if last_line:
            stripped = last_line.rstrip()
            # Check if it looks like a prompt (ends with common prompt chars)
            # and is not empty
            if stripped and any(stripped.endswith(end) for end in prompt_endings):
                # Additional check: the line should be relatively short (prompts usually are)
                # or contain @ or : which are common in prompts like user@host:~$
                if len(stripped) < 200 or '@' in stripped or ':' in stripped:
                    logger.info(f"Detected prompt return in pane {pane_id}")
                    # Capture with full scrollback for context
                    final_output = capture_target_context(pane_id)
                    return True, final_output or ""
    
    # Timeout - return whatever we have with full scrollback
    logger.warning(f"Timeout waiting for command completion in pane {pane_id}")
    final_output = capture_target_context(pane_id)
    return False, final_output or ""


def send_command_to_target(pane_id: str, command: str) -> bool:
    """Send a command to a target pane for execution.
    
    Args:
        pane_id: Pane number (e.g., "1") or pane ID (e.g., "%5")
        command: The command to execute.
        
    Returns:
        True if successful, False otherwise.
    """
    try:
        # Send the command text followed by Enter
        result = subprocess.run(
            ["tmux", "send-keys", "-t", pane_id, command, "Enter"],
            capture_output=True,
            text=True,
            timeout=CONTEXT_CAPTURE_TIMEOUT,
        )
        
        if result.returncode == 0:
            logger.info(f"Sent command to pane {pane_id}: {command[:50]}...")
            return True
        else:
            logger.error(f"Failed to send to pane {pane_id}: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout sending to pane {pane_id}")
        return False
    except FileNotFoundError:
        logger.error("tmux not found")
        return False
    except Exception as e:
        logger.error(f"Error sending to pane {pane_id}: {e}")
        return False


def send_command_and_wait(
    pane_id: str, 
    command: str, 
    timeout: int = TARGET_COMMAND_WAIT_TIMEOUT
) -> Tuple[bool, bool, str]:
    """Send a command and wait for it to complete.
    
    Args:
        pane_id: Target pane ID
        command: Command to execute
        timeout: Max seconds to wait for completion
        
    Returns:
        Tuple of (send_success, completed, output)
        - send_success: True if command was sent
        - completed: True if command completed within timeout
        - output: Captured output from pane
    """
    if not send_command_to_target(pane_id, command):
        return False, False, ""
    
    completed, output = wait_for_command_completion(pane_id, timeout=timeout)
    return True, completed, output


def parse_target_from_query(query_parts: list) -> Tuple[Optional[str], list]:
    """Parse @<pane> target from query parts.
    
    Args:
        query_parts: List of query tokens
        
    Returns:
        Tuple of (target_pane_id or None, remaining query parts)
    """
    if not query_parts:
        return None, query_parts
    
    first = query_parts[0]
    
    # Check for @<pane> syntax
    if first.startswith("@") and len(first) > 1:
        target = first[1:]  # Remove @ prefix
        return target, query_parts[1:]
    
    return None, query_parts
