"""Logging configuration for terma.

This module centralizes logging setup so we can be very verbose during
development and completely quiet during normal user usage.
"""

import logging
import os
from typing import Optional


def configure_logging(mode: Optional[str] = None) -> None:
    """Configure root logging handlers/levels for terma.

    Behavior:
    - Development (mode == "dev" OR TERMA_DEBUG=1 OR TERMA_ENV=dev):
      Root logger level DEBUG with a concise console handler to stderr.
    - Production (default):
      Remove stream handlers and set a NullHandler at root to avoid printing.
    """
    # Detect mode from env if not explicitly provided
    if mode is None:
        env_flag = os.environ.get("TERMA_DEBUG", "")
        env_mode = os.environ.get("TERMA_ENV", "").lower()
        if env_flag in {"1", "true", "True"} or env_mode == "dev":
            mode = "dev"
        else:
            mode = "prod"

    root_logger = logging.getLogger()

    # Always start from a clean slate for predictable behavior
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    if mode == "dev":
        root_logger.setLevel(logging.DEBUG)

        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG)

        # Time-only with milliseconds, include filename and line number
        # Color-aware formatter that uses 'category' extra or name prefixes
        console.setFormatter(_get_dev_color_formatter())

        root_logger.addHandler(console)

        # Tame noisy third-party loggers by default in dev, unless explicitly requested
        if os.environ.get("TERMA_VERBOSE_DEPS", "").lower() not in {"1", "true", "yes"}:
            noisy_names = (
                "litellm",
                "LiteLLM",
                "openai",
                "openai._base_client",
                "httpcore",
                "httpx",
                "asyncio",
                "urllib3",
                "aiohttp",
            )

            def clamp_logger(name: str) -> None:
                lg = logging.getLogger(name)
                lg.setLevel(logging.CRITICAL)
                lg.propagate = False
                for h in list(lg.handlers):
                    lg.removeHandler(h)

            for noisy in noisy_names:
                clamp_logger(noisy)

            # Also sweep existing registered loggers and clamp by prefix
            for existing_name in list(logging.root.manager.loggerDict.keys()):
                if any(existing_name.startswith(n) for n in noisy_names):
                    clamp_logger(existing_name)
    else:
        # Production: be silent by default. Keep errors available to integrators
        # via NullHandler to avoid "No handler" warnings if someone imports us.
        root_logger.setLevel(logging.WARNING)
        root_logger.addHandler(logging.NullHandler())


def get_logger(name: str) -> logging.Logger:
    """Convenience to create module loggers with consistent naming."""
    return logging.getLogger(name)


# --- Internal helpers for development logging formatting ---


def _supports_color() -> bool:
    """Basic TTY color support detection; color is dev-only so keep it simple."""
    try:
        return os.isatty(2)  # stderr
    except Exception:
        return False


class _ColorFormatter(logging.Formatter):
    """Colorize log lines based on category or logger name."""

    COLOR_RESET = "\x1b[0m"
    COLORS = {
        "perf": "\x1b[38;5;39m",  # blue
        "api": "\x1b[38;5;208m",  # orange
        "cmd": "\x1b[38;5;129m",  # magenta
        "default": "\x1b[38;5;245m",  # gray for other debug
        "level.DEBUG": "\x1b[38;5;245m",  # gray for debug
        "level.INFO": "\x1b[38;5;34m",
        "level.WARNING": "\x1b[38;5;214m",
        "level.ERROR": "\x1b[38;5;196m",
        "level.CRITICAL": "\x1b[48;5;196;38;5;231m",
    }

    def __init__(
        self, fmt: str, datefmt: Optional[str] = None, enable_color: bool = True
    ):
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.enable_color = enable_color

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        if not self.enable_color:
            return base

        # Determine category: explicit extra > logger name contains segment
        category = getattr(record, "category", None)
        if not category:
            name_parts = (record.name or "").split(".")
            for segment in ("perf", "api", "cmd"):
                if segment in name_parts:
                    category = segment
                    break

        color = None
        if category and category in self.COLORS:
            color = self.COLORS[category]
        else:
            # Fallback on level colors
            color = self.COLORS.get(f"level.{record.levelname}", self.COLORS["default"])

        return f"{color}{base}{self.COLOR_RESET}"


def _get_dev_color_formatter() -> logging.Formatter:
    """Create the dev formatter with color when supported."""
    # Tabs for alignment; use logger name with line number: terma.llm:289
    fmt = "[%(levelname)s]\t%(asctime)s.%(msecs)03d\t%(name)s:%(lineno)d\t%(message)s"
    datefmt = "%H:%M:%S"

    enable_color = _supports_color()

    # Try colorama on Windows for better ANSI support (optional)
    if enable_color and os.name == "nt":
        try:
            import colorama  # type: ignore

            colorama.just_fix_windows_console()  # no-op on newer consoles
        except Exception:
            # Proceed without colorama; Windows 10+ generally supports ANSI
            pass

    return _ColorFormatter(fmt=fmt, datefmt=datefmt, enable_color=enable_color)
