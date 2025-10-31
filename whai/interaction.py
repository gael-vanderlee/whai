"""Shell session management and command approval loop."""

import base64
import os
import queue
import random
import subprocess
import threading
import time
from typing import Optional, Tuple

from whai import ui
from whai.logging_setup import get_logger

logger = get_logger(__name__)


class ShellSession:
    """
    Manages a persistent shell subprocess for executing commands.

    This allows stateful operations (cd, export) to persist across multiple commands.
    """

    def __init__(self, shell: str = None):
        """
        Initialize a new shell session.

        Args:
            shell: Path to shell binary. If None, uses bash or cmd.exe based on platform.
        """
        if shell is None:
            # Default shell based on platform
            if os.name == "nt":
                shell = "cmd.exe"
            else:
                shell = "/bin/bash"

        self.shell = shell
        self.process = None
        self._start_shell()

    def _start_shell(self):
        """Start the shell subprocess."""
        try:
            shell_lower = self.shell.lower()

            # PowerShell (Windows only, typically)
            if "powershell" in shell_lower or "pwsh" in shell_lower:
                # Start interactive PowerShell
                self.process = subprocess.Popen(
                    [self.shell, "-NoProfile", "-NoLogo"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,  # Line buffered
                )
                # Initialize PowerShell: suppress prompt and progress bars
                # Send multiple init commands then drain all output
                init_script = (
                    "function prompt {''}\r\n"
                    "$ProgressPreference='SilentlyContinue'\r\n"
                    "Set-PSReadLineOption -HistorySaveStyle SaveNothing -ErrorAction SilentlyContinue 2>$null\r\n"
                    "$null\r\n"  # Emit something to force a flush
                )
                self.process.stdin.write(init_script)
                self.process.stdin.flush()
                # Drain all initialization output for up to 0.5s
                time.sleep(0.2)
                drain_deadline = time.time() + 0.5
                while time.time() < drain_deadline:
                    line = self._read_line_with_timeout(self.process.stdout, 0.02)
                    if line is None:
                        break
            # Windows cmd.exe
            elif os.name == "nt" and "cmd" in shell_lower:
                self.process = subprocess.Popen(
                    [self.shell],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=0,  # Unbuffered
                )
            # Unix-like shells (bash, zsh)
            else:
                self.process = subprocess.Popen(
                    [self.shell, "-i"],  # Interactive mode
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=0,  # Unbuffered
                    env={**os.environ, "PS1": ""},  # Disable prompt to avoid confusion
                )

            # Give the shell a moment to start
            time.sleep(0.1)

        except Exception as e:
            raise RuntimeError(f"Failed to start shell: {e}")
        else:
            logger.debug(
                "Started shell process pid=%s using shell=%s",
                getattr(self.process, "pid", None),
                self.shell,
                extra={"category": "cmd"},
            )

    def execute_command(self, command: str, timeout: int = 60) -> Tuple[str, str, int]:
        """
        Execute a command in the shell session.

        Args:
            command: The command to execute.
            timeout: Maximum time to wait for command completion (seconds). Defaults to 60.

        Returns:
            Tuple of (stdout, stderr, return_code).
            Note: return_code is always 0 for now (not reliably captured).

        Raises:
            RuntimeError: If the shell process has died or command times out.
        """
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("Shell process is not running")

        # Generate a unique marker for this command
        # Use a random number to make it unique
        marker = f"___WHAI_CMD_DONE_{random.randint(100000, 999999)}___"

        try:
            # Normalize Windows 'cd' to allow drive changes in cmd.exe
            if os.name == "nt" and "cmd" in self.shell.lower():
                stripped = command.strip()
                # In cmd.exe, `cd C:\` does not switch drives; `cd /d C:\` does
                if stripped.lower().startswith("cd ") and "/d" not in stripped.lower():
                    # Insert /d after cd
                    parts = stripped.split(maxsplit=1)
                    if len(parts) == 2:
                        command = f"cd /d {parts[1]}"
                    else:
                        command = stripped
            # Write the command and marker
            shell_lower = self.shell.lower()
            if os.name == "nt" and "cmd" in shell_lower:
                # Windows cmd.exe
                full_command = f"{command}\necho {marker}\n"
            elif "powershell" in shell_lower or "pwsh" in shell_lower:
                # Execute PowerShell non-interactively using -EncodedCommand to avoid
                # interactive stdin echo/reflow causes issues and to force materialized output.
                ps_script = f"& {{ {command} }} | Out-String -Width 4096"
                encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
                try:
                    result = subprocess.run(
                        [
                            self.shell,
                            "-NoProfile",
                            "-NoLogo",
                            "-NonInteractive",
                            "-EncodedCommand",
                            encoded,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                    )
                except subprocess.TimeoutExpired:
                    raise RuntimeError(f"Command timed out after {timeout} seconds")

                stdout = result.stdout or ""
                stderr_text = result.stderr or ""
                # Filter CLIXML progress noise sometimes emitted on stderr
                if stderr_text.lstrip().startswith("#< CLIXML"):
                    stderr_text = ""

                logger.debug(
                    "Command completed (non-interactive PS); stdout_len=%d stderr_len=%d rc=%d",
                    len(stdout),
                    len(stderr_text),
                    result.returncode,
                    extra={"category": "cmd"},
                )
                return stdout, stderr_text, result.returncode
            else:
                # Unix shells
                full_command = f"{command}\necho {marker}\n"

            self.process.stdin.write(full_command)
            self.process.stdin.flush()
            logger.debug(
                "Command submitted; awaiting marker=%s",
                marker,
                extra={"category": "cmd"},
            )

            # Read output until we see the marker
            stdout_lines = []
            stderr_lines = []
            marker_found = False
            start_time = time.time()

            while not marker_found:
                # Check timeout
                if time.time() - start_time > timeout:
                    raise RuntimeError(f"Command timed out after {timeout} seconds")

                # Read from stdout with a small timeout
                if self.process.stdout:
                    line = self._read_line_with_timeout(self.process.stdout, 0.1)
                    if line is not None:
                        if marker in line:
                            marker_found = True
                        else:
                            stdout_lines.append(line)

                # Also check stderr
                if self.process.stderr:
                    line = self._read_line_with_timeout(self.process.stderr, 0.01)
                    if line is not None:
                        stderr_lines.append(line)

            stdout = "".join(stdout_lines)
            stderr = "".join(stderr_lines)

            logger.debug(
                "Command completed; stdout_len=%d stderr_len=%d",
                len(stdout),
                len(stderr),
                extra={"category": "cmd"},
            )
            return stdout, stderr, 0

        except Exception as e:
            raise RuntimeError(f"Error executing command: {e}")

    def _read_line_with_timeout(self, stream, timeout: float) -> Optional[str]:
        """
        Read a line from a stream with a timeout.

        Args:
            stream: The stream to read from.
            timeout: Timeout in seconds.

        Returns:
            The line read, or None if timeout occurred.
        """
        if os.name == "nt":
            # Windows doesn't support select on file objects
            # Use threading approach
            result_queue = queue.Queue()

            def read_line():
                try:
                    line = stream.readline()
                    result_queue.put(line)
                except Exception:
                    result_queue.put(None)

            thread = threading.Thread(target=read_line, daemon=True)
            thread.start()

            try:
                return result_queue.get(timeout=timeout)
            except queue.Empty:
                return None
        else:
            # Unix: use select
            import select

            ready, _, _ = select.select([stream], [], [], timeout)
            if ready:
                return stream.readline()
            return None

    def close(self):
        """Close the shell session."""
        if self.process:
            try:
                self.process.stdin.close()
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
            finally:
                self.process = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def approval_loop(command: str) -> Optional[str]:
    """
    Present a command to the user for approval.

    Args:
        command: The command to approve.

    Returns:
        The approved command (possibly modified), or None if rejected.
    """
    ui.console.print()
    ui.print_command(command)

    while True:
        try:
            from rich.text import Text

            ui.console.print(
                Text("[a]pprove / [r]eject / [m]odify: ", style="yellow"), end=""
            )
            response = input().strip().lower()

            if response == "a" or response == "approve":
                logger.debug("Command approved as-is", extra={"category": "cmd"})
                return command
            elif response == "r" or response == "reject":
                ui.console.print("Command rejected.")
                logger.debug("Command rejected by user", extra={"category": "cmd"})
                return None
            elif response == "m" or response == "modify":
                modified = input("Enter modified command: ").strip()
                if modified:
                    logger.debug(
                        "Command modified by user: %s",
                        modified,
                        extra={"category": "cmd"},
                    )
                    return modified
                else:
                    ui.console.print("No command entered. Please try again.")
            else:
                ui.console.print("Invalid response. Please enter 'a', 'r', or 'm'.")
        except (EOFError, KeyboardInterrupt):
            ui.console.print("\nRejected.")
            logger.debug(
                "Command rejected via interrupt/EOF", extra={"category": "cmd"}
            )
            return None


def parse_tool_calls(response_chunks: list) -> list:
    """
    Parse tool calls from LLM response chunks.

    Args:
        response_chunks: List of response chunks from LLM.

    Returns:
        List of tool call dicts with 'name' and 'arguments' keys.
    """
    tool_calls = []

    for chunk in response_chunks:
        if chunk.get("type") == "tool_call":
            tool_calls.append(
                {
                    "id": chunk.get("id"),
                    "name": chunk.get("name"),
                    "arguments": chunk.get("arguments", {}),
                }
            )

    logger.debug(
        "parse_tool_calls extracted %d tool calls",
        len(tool_calls),
        extra={"category": "api"},
    )
    return tool_calls
