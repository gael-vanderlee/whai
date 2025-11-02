"""Tool call parsing for whai."""

from whai.logging_setup import get_logger

logger = get_logger(__name__)


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
