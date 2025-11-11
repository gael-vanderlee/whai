"""Shell session recording for deep context capture."""

import os
import platform
import shlex
import shutil
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import time

from whai.configuration.user_config import get_config_dir
from whai.logging_setup import get_logger
from whai.utils import detect_shell

logger = get_logger(__name__)

# Global variable to track log path for signal handlers
_current_log_path: Optional[Path] = None


def _session_dir() -> Path:
    """Get the directory for storing session logs."""
    sess_dir = get_config_dir() / "sessions"
    sess_dir.mkdir(parents=True, exist_ok=True)
    return sess_dir


def _default_log_path() -> Path:
    """Generate a default log path with timestamp."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _session_dir() / f"session_{ts}.log"


def _cleanup_existing_logs() -> None:
    """Clean up any existing session log files on shell start."""
    sess_dir = _session_dir()
    try:
        for log_file in sess_dir.glob("session_*.log"):
            try:
                log_file.unlink()
                logger.debug("Cleaned up existing log file: %s", log_file)
            except Exception as e:
                logger.warning("Failed to clean up log file %s: %s", log_file, e)
    except Exception as e:
        logger.warning("Failed to clean up existing logs: %s", e)


def _cleanup_log(log_path: Path) -> None:
    """Clean up log file and its companion whai log."""
    try:
        if log_path.exists():
            log_path.unlink(missing_ok=True)
            logger.debug("Cleaned up log file: %s", log_path)
        
        # Also clean up companion whai log if it exists
        whai_log = log_path.parent / f"{log_path.stem}_whai{log_path.suffix}"
        if whai_log.exists():
            whai_log.unlink(missing_ok=True)
            logger.debug("Cleaned up whai log file: %s", whai_log)
    except Exception as e:
        logger.warning("Failed to clean up log file %s: %s", log_path, e)


def _signal_handler(signum, frame):
    """Handle signals (Ctrl-C, etc.) to ensure log cleanup."""
    global _current_log_path
    if _current_log_path:
        _cleanup_log(_current_log_path)
    # Re-raise the signal to allow normal exit handling
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def launch_shell_session(
    shell: Optional[str] = None,
    log_path: Optional[Path] = None,
    delete_on_exit: bool = True,
) -> int:
    """
    Launch an interactive shell session with full recording.
    
    The session is recorded to a log file that can be used as deep context
    by whai when tmux is not available.
    
    Args:
        shell: Optional shell binary to launch. If None, detects current shell.
        log_path: Optional path for session log. If None, generates a timestamped path.
        delete_on_exit: Whether to delete log files on exit (default: True).
    
    Returns:
        Exit code from the shell process.
    """
    global _current_log_path
    
    shell = shell or detect_shell()
    log_path = log_path or _default_log_path()
    _current_log_path = log_path
    
    # Clean up any existing logs on shell start
    _cleanup_existing_logs()
    
    # Set up signal handlers for cleanup on Ctrl-C and similar
    if delete_on_exit:
        if sys.platform != "win32":
            # Unix signal handlers
            signal.signal(signal.SIGINT, _signal_handler)
            signal.signal(signal.SIGTERM, _signal_handler)
        # On Windows, we rely on finally block and atexit
    
    # Set environment variable to mark this as a whai session
    # Log path is derived from session directory, no need to pass via env var
    os.environ["WHAI_SESSION_ACTIVE"] = "1"
    
    logger.info(
        "Starting recorded shell session: shell=%s log=%s",
        shell,
        log_path,
    )
    
    system = platform.system().lower()
    try:
        if system in ("linux", "darwin"):
            return _launch_unix(shell, log_path)
        elif system == "windows":
            return _launch_windows(shell, log_path)
        else:
            logger.error("Unsupported OS: %s", system)
            raise RuntimeError(f"Unsupported OS: {system}")
    finally:
        if delete_on_exit:
            _cleanup_log(log_path)
        _current_log_path = None


def _detect_script_variant(script_bin: str) -> str:
    """
    Detect which script variant is available (util-linux or BSD).
    
    Args:
        script_bin: Path to script binary.
    
    Returns:
        "util-linux", "bsd", or "unknown"
    """
    try:
        result = subprocess.run(
            [script_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if "util-linux" in result.stdout:
            return "util-linux"
        elif "BSD" in result.stdout or "FreeBSD" in result.stdout:
            return "bsd"
    except Exception:
        pass
    
    # Fall back to syntax testing
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".log") as tmp:
            test_log = Path(tmp.name)
        
        # Test util-linux syntax (with -c flag)
        result = subprocess.run(
            [script_bin, "-qf", str(test_log), "-c", "echo test"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0 and "unexpected" not in result.stderr.lower():
            test_log.unlink(missing_ok=True)
            return "util-linux"
        
        # Test BSD syntax (no -- separator, capital -F for flush on BSD)
        result = subprocess.run(
            [script_bin, "-qF", str(test_log), "sh", "-c", "echo test"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        test_log.unlink(missing_ok=True)
        if result.returncode == 0 and "unexpected" not in result.stderr.lower():
            return "bsd"
    except Exception:
        pass
    
    return "unknown"


def _launch_unix(shell: str, log_path: Path) -> int:
    """
    Launch a Unix shell with full session recording using script.
    
    Args:
        shell: Shell binary path or name.
        log_path: Path for session log.
    
    Returns:
        Exit code from the shell.
    """
    # Prefer system 'script' for full TTY fidelity
    script_bin = shutil.which("script")
    if script_bin:
        # Detect script variant to use appropriate syntax
        variant = _detect_script_variant(script_bin)
        
        # Set up environment
        env = os.environ.copy()
        current_ps1 = env.get("PS1", "")
        env["PS1"] = f"[whai] {current_ps1}" if current_ps1 else "[whai] $ "
        
        # Use appropriate syntax based on script variant
        if variant == "util-linux":
            # util-linux script: use interactive mode with SHELL env var
            # Set SHELL environment variable to desired shell
            env["SHELL"] = shell
            cmd: List[str] = [script_bin, "-qf", str(log_path)]
            logger.info(
                "Starting recorded shell via script (util-linux): %s (SHELL=%s)",
                shlex.join(cmd),
                shell,
            )
        elif variant == "bsd":
            # BSD script: do not use --, use capital -F (flush) if available
            cmd: List[str] = [script_bin, "-qF", str(log_path), shell, "-l"]
            logger.info("Starting recorded shell via script (BSD): %s", shlex.join(cmd))
        else:
            # Unknown variant, try BSD-compatible syntax first (more common on macOS)
            logger.warning("Unknown script variant, trying BSD syntax")
            cmd = [script_bin, "-qF", str(log_path), shell, "-l"]
            logger.info("Starting recorded shell via script: %s", shlex.join(cmd))
        
        try:
            return subprocess.call(cmd, env=env)
        except Exception as e:
            logger.error("Failed to launch recorded shell: %s", e)
            logger.warning("Falling back to unrecorded shell")
            # Fall through to fallback
    else:
        logger.warning("'script' command not found; session will not be recorded")
    
    # Fallback: run shell directly without recording
    logger.info("Starting unrecorded shell: %s", shell)
    return subprocess.call([shell, "-l"])


def _launch_windows(shell: str, log_path: Path) -> int:
    """
    Launch a Windows PowerShell session with transcript recording.
    
    Args:
        shell: Shell binary path or name.
        log_path: Path for session log.
    
    Returns:
        Exit code from the shell.
    """
    # Normalize shell name - prefer pwsh over powershell
    if "powershell" in shell.lower():
        pwsh = shutil.which("pwsh")
        if pwsh:
            shell = pwsh
        else:
            # Fall back to Windows PowerShell if pwsh not found
            powershell = shutil.which("powershell")
            if powershell:
                shell = powershell
    
    if "pwsh" in shell.lower() or "powershell" in shell.lower():
        # Use PowerShell transcript for recording
        # Start-Transcript captures stdout by default, but not stderr
        # Write errors to whai log file instead of appending to transcript
        # to avoid ordering issues and ensure chronological merging
        # Also modify prompt to show a subtle whai indicator
        # Escape single quotes in log_path for PowerShell
        log_path_escaped = str(log_path).replace("'", "''")
        whai_log_path = log_path.parent / f"{log_path.stem}_whai{log_path.suffix}"
        whai_log_path_escaped = str(whai_log_path).replace("'", "''")
        setup_cmd = (
            f"Start-Transcript -Path '{log_path_escaped}' -IncludeInvocationHeader -Force | Out-Null; "
            f"function prompt {{ '[whai] ' + (Get-Location).Path + '> ' }}; "
            f"$ErrorActionPreference = 'Continue'; "
            f"$PSDefaultParameterValues['*:ErrorAction'] = 'Continue'; "
            f"function Out-Default {{ $input | ForEach-Object {{ if ($_ -is [System.Management.Automation.ErrorRecord]) {{ Write-Host $_; $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'; $_ | Out-String | Out-File -Append '{whai_log_path_escaped}' -Encoding utf8 }} else {{ Write-Host $_ }} }} }}"
        )
        
        # Launch PowerShell with transcript running
        # -NoLogo: suppress startup banner
        # -NoExit: keep shell open after command
        pwsh_cmd = [
            shell,
            "-NoLogo",
            "-NoExit",
            "-Command",
            setup_cmd,
        ]
        
        logger.info(
            "Starting recorded PowerShell with transcript at %s",
            log_path,
        )
        
        try:
            rc = subprocess.call(pwsh_cmd)
            return rc
        except Exception as e:
            logger.error("Failed to launch recorded PowerShell: %s", e)
            logger.warning("Falling back to unrecorded shell")
            # Fall through to fallback
    
    # Fallback for CMD or when PowerShell failed
    if shell.lower().endswith("cmd.exe") or shell.lower() == "cmd":
        logger.warning(
            "CMD capture is limited; launching cmd without reliable output recording"
        )
        return subprocess.call(["cmd.exe"])
    
    # Unknown shell on Windows
    logger.warning("Unknown shell '%s'; attempting to launch directly", shell)
    return subprocess.call([shell])

