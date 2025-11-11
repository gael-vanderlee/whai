"""Tests for token truncation utilities."""

import pytest

from whai.llm import token_utils


def test_truncate_empty_text():
    """Test that empty text returns unchanged."""
    result, was_truncated = token_utils.truncate_text_with_tokens("", 1000)
    
    assert result == ""
    assert was_truncated is False


def test_truncate_text_within_limit():
    """Test that text within token limit returns unchanged."""
    # Small text: 40 chars = ~10 tokens, well under 1000 limit
    text = "This is a short text that fits."
    result, was_truncated = token_utils.truncate_text_with_tokens(text, 1000)
    
    assert result == text
    assert was_truncated is False


def test_truncate_text_exceeds_limit():
    """Test that text exceeding limit gets truncated, keeping the end."""
    # Create text that exceeds limit: 400 chars = ~100 tokens
    # Limit: 50 tokens = ~200 chars, but notice takes some tokens
    text = "A" * 400
    
    result, was_truncated = token_utils.truncate_text_with_tokens(text, 50)
    
    assert was_truncated is True
    # Should have truncation notice at beginning
    assert "CHARACTERS REMOVED TO RESPECT TOKEN LIMITS" in result
    # Should preserve some end portion of original text (the "A" characters)
    assert "A" in result
    # Should start with truncation notice showing removed count
    assert result.startswith("2")
    # The notice should be followed by blank lines and then the preserved content
    assert "\n\n" in result


def test_truncate_preserves_end():
    """Test that truncation preserves the end (most recent content)."""
    # Create text where end is distinct
    text = "BEGINNING " * 50 + "END " * 50
    
    result, was_truncated = token_utils.truncate_text_with_tokens(text, 50)
    
    assert was_truncated is True
    # Should contain the end portion
    assert "END" in result
    # The end portion should appear after the truncation notice
    assert "END" in result.split("CHARACTERS REMOVED")[1]


def test_truncate_notice_format():
    """Test that truncation notice has correct format."""
    text = "A" * 1000  # Large text
    result, was_truncated = token_utils.truncate_text_with_tokens(text, 50)
    
    assert was_truncated is True
    # Notice should be: "{num} CHARACTERS REMOVED TO RESPECT TOKEN LIMITS\n\n"
    lines = result.split("\n")
    assert "CHARACTERS REMOVED TO RESPECT TOKEN LIMITS" in lines[0]
    assert lines[1] == ""  # Blank line after notice


def test_truncate_notice_includes_removed_count():
    """Test that truncation notice includes correct character count."""
    text = "A" * 500  # 500 chars
    # With limit of 50 tokens (~200 chars), we remove ~300 chars
    result, was_truncated = token_utils.truncate_text_with_tokens(text, 50)
    
    assert was_truncated is True
    # Notice should contain the number of removed characters
    notice_line = result.split("\n")[0]
    assert notice_line.startswith("3")  # Should start with 3 (300+ chars)


def test_truncate_very_small_limit():
    """Test truncation when limit is too small to fit truncation notice."""
    text = "This is a test string that is longer than the limit."
    
    result, was_truncated = token_utils.truncate_text_with_tokens(text, 5)
    
    # When limit is smaller than truncation notice, returns empty string
    assert was_truncated is True
    assert result == ""


def test_truncate_extremely_small_limit():
    """Test truncation when limit is smaller than truncation notice."""
    text = "Some text"
    # Very small limit that won't fit the truncation notice
    result, was_truncated = token_utils.truncate_text_with_tokens(text, 1)
    
    # Should return empty string when notice itself exceeds limit
    assert result == ""
    assert was_truncated is True


def test_truncate_consistency():
    """Test that truncation produces consistent results."""
    text = "A" * 400
    
    result1, _ = token_utils.truncate_text_with_tokens(text, 50)
    result2, _ = token_utils.truncate_text_with_tokens(text, 50)
    
    # Should produce identical results
    assert result1 == result2


def test_truncate_exact_boundary():
    """Test truncation at exact token boundary."""
    # Text exactly at 50 tokens: 200 chars (200 // 4 = 50 tokens)
    text = "A" * 200
    
    # At limit: should not truncate
    result, was_truncated = token_utils.truncate_text_with_tokens(text, 50)
    assert result == text
    assert was_truncated is False
    
    # Significantly over: 300 chars = 75 tokens, should truncate
    text_over = "A" * 300
    result, was_truncated = token_utils.truncate_text_with_tokens(text_over, 50)
    assert was_truncated is True
    assert "CHARACTERS REMOVED" in result


def test_truncate_large_text():
    """Test truncation with very large text."""
    # 10,000 chars = ~2,500 tokens
    text = "A" * 10000
    
    # Limit to 100 tokens (~400 chars, less after accounting for notice)
    result, was_truncated = token_utils.truncate_text_with_tokens(text, 100)
    
    assert was_truncated is True
    # Should have removed most of the text
    assert "CHARACTERS REMOVED" in result
    # Should preserve some end portion (less than 400 chars due to notice)
    content_after_notice = result.split("CHARACTERS REMOVED")[1].strip()
    assert "A" in content_after_notice
    # Notice should indicate large removal (thousands)
    removed_count = result.split("CHARACTERS")[0].strip()
    assert int(removed_count) > 9000


def test_truncate_preserves_structure():
    """Test that truncation preserves the structure of the end content."""
    # Create text with structure at end
    text = "OLD CONTENT\n" * 100 + "NEW CONTENT\n" * 10
    
    result, was_truncated = token_utils.truncate_text_with_tokens(text, 50)
    
    assert was_truncated is True
    # Should preserve the "NEW CONTENT" lines at the end
    assert "NEW CONTENT" in result
    # Should appear after truncation notice
    new_content_part = result.split("CHARACTERS REMOVED")[1]
    assert "NEW CONTENT" in new_content_part
