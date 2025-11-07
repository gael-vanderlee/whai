"""Token counting and truncation utilities for whai."""

import time
from typing import Tuple

from whai.logging_setup import get_logger

logger = get_logger(__name__)

# Simple character-to-token ratio (approximate, works for all models)
# 1 token ≈ 4 characters (common estimate for most LLMs)
CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    """
    Estimate token count from character count.

    Uses a simple ratio: 1 token ≈ 4 characters.
    This is a fast approximation that works for all models.
    """
    return len(text) // CHARS_PER_TOKEN


def truncate_text_with_tokens(text: str, max_tokens: int) -> Tuple[str, bool]:
    """
    Truncate text to fit within token limit, keeping the end (most recent content).

    Args:
        text: Text to truncate.
        max_tokens: Maximum number of tokens allowed.

    Returns:
        Tuple of (truncated_text, was_truncated).
        - truncated_text: Original text if within limit, or truncated text with notice
        - was_truncated: True if truncation occurred, False otherwise.
    """
    if not text:
        return text, False

    t0 = time.perf_counter()

    try:
        # Estimate token count using simple character ratio
        token_count = _estimate_tokens(text)

        # If within limit, return original text
        if token_count <= max_tokens:
            logger.debug(
                "Text within token limit (tokens=%d, limit=%d)", token_count, max_tokens, extra={"category": "config"}
            )
            return text, False

        # Need to truncate - calculate how many characters to keep
        logger.info(
            "Text exceeds token limit (tokens=%d, limit=%d), truncating...",
            token_count,
            max_tokens,
        )

        # Calculate target characters (accounting for truncation notice)
        placeholder_notice = "0 CHARACTERS REMOVED TO RESPECT TOKEN LIMITS\n\n"
        notice_tokens = _estimate_tokens(placeholder_notice)
        target_tokens = max_tokens - notice_tokens

        if target_tokens <= 0:
            logger.warning(
                "Truncation notice alone exceeds token limit, using empty text"
            )
            return "", True

        # Calculate how many characters to keep (target_tokens * chars_per_token)
        target_chars = target_tokens * CHARS_PER_TOKEN

        t_trunc_start = time.perf_counter()

        # Truncate from start, keeping the end
        if len(text) <= target_chars:
            # Already fits (shouldn't happen, but safe check)
            return text, False

        chars_removed = len(text) - target_chars
        truncated_text = text[chars_removed:]

        # Build final text with truncation notice
        final_notice = (
            f"{chars_removed} CHARACTERS REMOVED TO RESPECT TOKEN LIMITS\n\n"
        )
        final_text = final_notice + truncated_text

        # Verify estimated token count
        final_tokens = _estimate_tokens(final_text)

        t_trunc_end = time.perf_counter()
        # Performance logging is handled by the caller (main.py or executor.py)
        # This internal log is kept for debugging but uses comma formatting
        from whai.utils import _format_ms
        logger.debug(
            "Token truncation completed in %s ms (removed=%d chars, final_tokens=%d, limit=%d)",
            _format_ms((t_trunc_end - t_trunc_start) * 1000),
            chars_removed,
            final_tokens,
            max_tokens,
            extra={"category": "perf"},
        )

        return final_text, True

    except Exception as e:
        logger.exception("Error during token truncation: %s", e)
        # On error, return original text rather than failing
        return text, False