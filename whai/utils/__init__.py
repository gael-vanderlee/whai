"""Shared utility functions for whai."""

import os
import platform
import sys
from typing import Literal

from whai.utils.perf_logger import PerformanceLogger, _format_ms

ShellType = Literal["bash", "zsh", "fish", "pwsh"]

# List of supported shells
SUPPORTED_SHELLS = ["bash", "zsh", "fish", "pwsh"]


def detect_shell() -> ShellType:
    """
    Detect the current shell type.

    Returns:
        One of: "bash", "zsh", "fish", or "pwsh"
    """
    # Check if in PowerShell (PSModulePath is PowerShell-specific)
    if os.environ.get("PSModulePath"):
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

    # Fallback to PowerShell on Windows, bash elsewhere
    if sys.platform.startswith("win"):
        return "pwsh"
    else:
        return "bash"


def get_os_name() -> str:
    """
    Get a user-friendly OS name.

    Returns:
        OS name like "Windows 11", "macOS 14.1", "Ubuntu 22.04", etc.
    """
    system = platform.system()

    if system == "Windows":
        release = platform.release()
        # Try to get Windows version name
        version = platform.version()
        if "10.0.22" in version or release == "11":
            return "Windows 11"
        elif release == "10":
            return "Windows 10"
        else:
            return f"Windows {release}"

    elif system == "Darwin":
        # macOS
        mac_version = platform.mac_ver()[0]
        return f"macOS {mac_version}"

    elif system == "Linux":
        # Try to get distro info
        try:
            with open("/etc/os-release") as f:
                lines = f.readlines()
                distro_info = {}
                for line in lines:
                    if "=" in line:
                        key, value = line.strip().split("=", 1)
                        distro_info[key] = value.strip('"')

                name = distro_info.get("PRETTY_NAME") or distro_info.get("NAME")
                if name:
                    return name
        except (FileNotFoundError, PermissionError):
            pass

        # Fallback
        return f"Linux {platform.release()}"

    else:
        return f"{system} {platform.release()}"


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
    "get_os_name",
    "is_windows",
    "is_macos",
    "is_linux",
]

