"""Performance logging utility for tracking execution time and elapsed time since start."""

import time
from typing import Optional

from whai.logging_setup import get_logger

logger = get_logger(__name__)


def _format_ms(ms: float) -> str:
    """
    Format milliseconds with comma separators for readability.
    
    Args:
        ms: Milliseconds value
        
    Returns:
        Formatted string with commas (e.g., "1,234.567 ms")
    """
    # Split into integer and decimal parts
    parts = f"{ms:.3f}".split(".")
    integer_part = parts[0]
    decimal_part = parts[1] if len(parts) > 1 else ""
    
    # Add commas to integer part
    if len(integer_part) > 3:
        # Reverse, add commas every 3 digits, reverse back
        reversed_int = integer_part[::-1]
        formatted_int = ",".join(
            reversed_int[i : i + 3] for i in range(0, len(reversed_int), 3)
        )[::-1]
    else:
        formatted_int = integer_part
    
    if decimal_part:
        return f"{formatted_int}.{decimal_part}"
    return formatted_int


class PerformanceLogger:
    """
    Tracks performance metrics with both elapsed time and time since start.
    
    Usage:
        perf = PerformanceLogger("Setup")
        perf.start()
        # ... do work ...
        perf.log_section("Config loading")
        # ... do more work ...
        perf.log_section("Role loading")
    """
    
    def __init__(self, stage_name: str):
        """
        Initialize performance logger.
        
        Args:
            stage_name: Name of the overall stage (e.g., "Setup", "LLM API Call")
        """
        self.stage_name = stage_name
        self.start_time: Optional[float] = None
        self.last_section_time: Optional[float] = None
        self.section_count = 0
    
    def start(self) -> None:
        """Start timing. Must be called before logging any sections."""
        self.start_time = time.perf_counter()
        self.last_section_time = self.start_time
        self.section_count = 0
    
    def log_section(
        self,
        section_name: str,
        extra_info: Optional[dict] = None,
        level: str = "info",
    ) -> None:
        """
        Log a section with elapsed time and time since start.
        
        Args:
            section_name: Name of the section being logged
            extra_info: Optional dict of additional info to include in log
            level: Log level ("info", "debug", etc.)
        """
        if self.start_time is None:
            raise RuntimeError("PerformanceLogger.start() must be called before log_section()")
        
        now = time.perf_counter()
        elapsed_ms = (now - self.last_section_time) * 1000
        total_ms = (now - self.start_time) * 1000
        self.last_section_time = now
        self.section_count += 1
        
        # Build log message - always show both elapsed and total time with comma formatting
        msg = f"[{self.stage_name}] {section_name}: {_format_ms(elapsed_ms)} ms (total: {_format_ms(total_ms)} ms)"
        
        # Add extra info if provided
        if extra_info:
            extra_str = ", ".join(f"{k}={v}" for k, v in extra_info.items())
            msg = f"{msg} ({extra_str})"
        
        # Log with appropriate level
        log_func = getattr(logger, level, logger.info)
        log_func(msg, extra={"category": "perf"})
    
    def log_complete(self, extra_info: Optional[dict] = None) -> None:
        """
        Log completion of the entire stage.
        
        Args:
            extra_info: Optional dict of additional info to include in log
        """
        if self.start_time is None:
            raise RuntimeError("PerformanceLogger.start() must be called before log_complete()")
        
        total_ms = (time.perf_counter() - self.start_time) * 1000
        
        msg = f"[{self.stage_name}] Complete: {_format_ms(total_ms)} ms"
        if extra_info:
            extra_str = ", ".join(f"{k}={v}" for k, v in extra_info.items())
            msg = f"{msg} ({extra_str})"
        
        logger.info(msg, extra={"category": "perf"})

