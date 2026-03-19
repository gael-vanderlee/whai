"""Shared utility functions for whai."""

import os
import sys
from typing import Literal

from whai.utils.perf_logger import PerformanceLogger, _format_ms

ShellType = Literal["bash", "zsh", "fish", "pwsh", "powershell", "cmd"]

# List of supported shells
SUPPORTED_SHELLS = ["bash", "zsh", "fish", "pwsh", "powershell", "cmd"]


def detect_shell() -> ShellType:
    """
    Detect the current shell type.

    Returns:
        One of: "bash", "zsh", "fish", "pwsh", "powershell", or "cmd"
        
    Shell types:
        - "pwsh": PowerShell 7+ (modern, cross-platform)
        - "powershell": Windows PowerShell 5.x (legacy, Windows-only)
        - "cmd": Windows Command Prompt
        - "bash", "zsh", "fish": Unix shells
    """
    # Check if in PowerShell (PSModulePath is PowerShell-specific)
    if os.environ.get("PSModulePath"):
        # Determine which PowerShell version is available
        import shutil
        if shutil.which("pwsh"):
            return "pwsh"
        elif shutil.which("powershell"):
            return "powershell"
        # If neither found, return pwsh as fallback (will be handled at launch)
        return "pwsh"

    # Check SHELL environment variable (Unix-like systems)
    shell_path = os.environ.get("SHELL", "")
    if shell_path:
        shell_name = os.path.basename(shell_path).lower()

        if "fish" in shell_name:
            return "fish"
        elif "zsh" in shell_name:
            return "zsh"
        elif "bash" in shell_name:
            return "bash"

    # Fallback: detect what's available on Windows, bash elsewhere
    if sys.platform.startswith("win"):
        import shutil
        if shutil.which("pwsh"):
            return "pwsh"
        elif shutil.which("powershell"):
            return "powershell"
        elif shutil.which("cmd"):
            return "cmd"
        # Last resort fallback
        return "powershell"
    else:
        return "bash"



def is_windows() -> bool:
    """Check if running on Windows."""
    return sys.platform.startswith("win")


def is_macos() -> bool:
    """Check if running on macOS."""
    return sys.platform == "darwin"


def is_linux() -> bool:
    """Check if running on Linux."""
    return sys.platform.startswith("linux")


__all__ = [
    "PerformanceLogger",
    "_format_ms",
    "ShellType",
    "SUPPORTED_SHELLS",
    "detect_shell",
    "is_windows",
    "is_macos",
    "is_linux",
]

