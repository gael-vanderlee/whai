"""Command execution for whai."""

import os
import queue
import re
import shutil
import subprocess
import threading
import time
from typing import Callable, List, Optional, Tuple

from whai.constants import DEFAULT_COMMAND_TIMEOUT
from whai.logging_setup import get_logger
from whai.utils import detect_shell, is_windows

logger = get_logger(__name__)

# Patterns that indicate the command is waiting for user input.
INPUT_PROMPT_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\[y/n\]",
        r"\[Y/n\]",
        r"\[y/N\]",
        r"\(y/n\)",
        r"[Pp]assword\s*:",
        r"[Pp]assphrase\s*:",
        r"Continue\?",
        r"Proceed\?",
        r"Are you sure\?",
        r"Press Enter",
        r"Press any key",
        r"Do you want to continue",
        r"(?:^|[\r\n])[^\r\n]{1,80}\?",
    ]
]
PROMPT_SEARCH_WINDOW = 200


def _stream_chars(
    stream, stream_name: str, output_queue: "queue.Queue[tuple[str, str]]"
) -> None:
    """Read a stream one character at a time into a queue."""
    try:
        while True:
            chunk = stream.read(1)
            if chunk == "":
                break
            output_queue.put((stream_name, chunk))
    except (ValueError, OSError):
        pass


def _build_shell_args(command: str) -> List[str]:
    """Build the shell command args list based on platform."""
    if is_windows():
        shell_type = detect_shell()
        if shell_type in ("pwsh", "powershell"):
            shell_exe = (
                shutil.which(shell_type)
                or shutil.which("powershell")
                or "powershell.exe"
            )
            return [shell_exe, "-Command", command]
        else:
            return ["cmd.exe", "/c", command]
    else:
        shell = os.environ.get("SHELL", "/bin/sh")
        return [shell, "-c", command]


def execute_command(
    command: str,
    timeout: float = DEFAULT_COMMAND_TIMEOUT,
    on_input_needed: Optional[Callable[[str], Optional[str]]] = None,
) -> Tuple[str, str, int]:
    """
    Execute a shell command and return its output.

    Each command runs independently in a fresh subprocess.
    State like cd or export does NOT persist between commands.

    Args:
        command: The command to execute.
        timeout: Maximum time to wait for command completion (seconds).
                 Use 0 for infinite timeout (no limit).
        on_input_needed: Optional callback invoked when the command appears to be
                         waiting for user input (detected via prompt patterns).
                         Receives the output so far, returns user input string
                         (should include newline) or None to skip.

    Returns:
        Tuple of (stdout, stderr, return_code).

    Raises:
        RuntimeError: If command times out or encounters other errors.
    """
    timeout_for_wait = None if timeout == 0 else timeout
    shell_args = _build_shell_args(command)
    timeout_msg = f"{timeout} seconds" if timeout > 0 else "infinite timeout"

    try:
        proc = subprocess.Popen(
            shell_args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.stdout is None or proc.stderr is None or proc.stdin is None:
            raise RuntimeError("Failed to open command pipes")

        if on_input_needed is None:
            try:
                stdout, stderr = proc.communicate(timeout=timeout_for_wait)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                raise RuntimeError(
                    f"Command timed out after {timeout_msg}. "
                    "You can change timeout limits with the --timeout flag"
                )
            logger.debug(
                "Command completed; stdout_len=%d stderr_len=%d rc=%d",
                len(stdout),
                len(stderr),
                proc.returncode,
                extra={"category": "cmd"},
            )
            return stdout, stderr, proc.returncode

        stdout_buf: List[str] = []
        stderr_buf: List[str] = []
        combined_buf: List[str] = []
        recent_output = ""
        recent_output_offset = 0
        output_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
        threads = [
            threading.Thread(
                target=_stream_chars,
                args=(proc.stdout, "stdout", output_queue),
                daemon=True,
            ),
            threading.Thread(
                target=_stream_chars,
                args=(proc.stderr, "stderr", output_queue),
                daemon=True,
            ),
        ]
        for thread in threads:
            thread.start()

        start_time = time.monotonic()
        last_handled_prompt_end = -1

        try:
            while True:
                if (
                    timeout_for_wait is not None
                    and (time.monotonic() - start_time) > timeout_for_wait
                ):
                    proc.kill()
                    proc.wait()
                    raise RuntimeError(
                        f"Command timed out after {timeout_msg}. "
                        "You can change timeout limits with the --timeout flag"
                    )

                try:
                    stream_name, chunk = output_queue.get(timeout=0.05)
                except queue.Empty:
                    if (
                        proc.poll() is not None
                        and output_queue.empty()
                        and not any(thread.is_alive() for thread in threads)
                    ):
                        break
                    continue

                if stream_name == "stdout":
                    stdout_buf.append(chunk)
                else:
                    stderr_buf.append(chunk)
                combined_buf.append(chunk)
                recent_output += chunk
                if len(recent_output) > PROMPT_SEARCH_WINDOW:
                    trim = len(recent_output) - PROMPT_SEARCH_WINDOW
                    recent_output = recent_output[trim:]
                    recent_output_offset += trim

                latest_prompt_end = None
                for pattern in INPUT_PROMPT_PATTERNS:
                    for match in pattern.finditer(recent_output):
                        abs_end = recent_output_offset + match.end()
                        if abs_end > last_handled_prompt_end:
                            latest_prompt_end = abs_end

                if latest_prompt_end is None:
                    continue

                output_so_far = "".join(combined_buf)
                user_input = on_input_needed(output_so_far)
                last_handled_prompt_end = latest_prompt_end
                if user_input is None:
                    proc.kill()
                    proc.wait()
                    raise RuntimeError("Command input was cancelled.")

                try:
                    proc.stdin.write(user_input)
                    proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
        except RuntimeError:
            raise
        except (ValueError, OSError):
            pass

        elapsed = time.monotonic() - start_time
        remaining = None
        if timeout_for_wait is not None:
            remaining = max(0, timeout_for_wait - elapsed)

        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise RuntimeError(
                f"Command timed out after {timeout_msg}. "
                "You can change timeout limits with the --timeout flag"
            )

        for thread in threads:
            thread.join(timeout=1)

        while True:
            try:
                stream_name, chunk = output_queue.get_nowait()
            except queue.Empty:
                break
            if stream_name == "stdout":
                stdout_buf.append(chunk)
            else:
                stderr_buf.append(chunk)

        stdout_text = "".join(stdout_buf)
        stderr_text = "".join(stderr_buf)

        logger.debug(
            "Command completed; stdout_len=%d stderr_len=%d rc=%d",
            len(stdout_text),
            len(stderr_text),
            proc.returncode,
            extra={"category": "cmd"},
        )
        return stdout_text, stderr_text, proc.returncode

    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Error executing command: {e}")
