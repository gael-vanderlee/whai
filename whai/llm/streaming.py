"""Streaming response handling for LLM providers."""

import json
from typing import Any, Dict, Generator, Optional

from whai.logging_setup import get_logger

logger = get_logger(__name__)


def handle_streaming_response(response) -> Generator[Dict[str, Any], None, None]:
    """
    Handle streaming response from LiteLLM.

    Args:
        response: Streaming response from litellm.completion

    Yields:
        Parsed response chunks.
    """
    # Buffer partial tool call data across chunks by id
    # Stores: {call_id: {"name": str, "args": str}}
    partial_tool_calls: Dict[str, Dict[str, str]] = {}
    # Track the last known call_id to handle None ids in subsequent chunks
    last_call_id: Optional[str] = None

    for chunk in response:
        delta = chunk.choices[0].delta

        # Check for text content
        if hasattr(delta, "content") and delta.content:
            # logger.debug(
            #     "Streaming text chunk: len=%d",
            #     len(delta.content),
            #     extra={"category": "api"},
            # )
            yield {"type": "text", "content": delta.content}

        # Check for tool calls
        if hasattr(delta, "tool_calls") and delta.tool_calls:
            # logger.debug(
            #     "Streaming tool_calls chunk: count=%d",
            #     len(delta.tool_calls),
            #     extra={"category": "api"},
            # )
            for tool_call in delta.tool_calls:
                if not hasattr(tool_call, "function"):
                    continue

                raw_call_id = getattr(tool_call, "id", "unknown")
                name = tool_call.function.name
                arg_chunk = tool_call.function.arguments or ""

                # logger.debug(
                #     "Processing tool_call chunk: id=%s (type=%s), name=%s (type=%s), args_len=%d",
                #     raw_call_id,
                #     type(raw_call_id).__name__,
                #     name,
                #     type(name).__name__,
                #     len(arg_chunk) if arg_chunk else 0,
                #     extra={"category": "api"},
                # )

                # Handle None ids by using the last known call_id
                # OpenAI sends id and name in first chunk, then None for both in subsequent chunks
                if raw_call_id is not None:
                    call_id = raw_call_id
                    last_call_id = call_id
                elif last_call_id is not None:
                    call_id = last_call_id
                else:
                    # No known call_id yet, skip this chunk
                    logger.warning(
                        "Received tool_call chunk with no id and no previous id"
                    )
                    continue

                # Initialize buffer for this call_id if needed
                if call_id not in partial_tool_calls:
                    partial_tool_calls[call_id] = {"name": None, "args": ""}
                    logger.debug(
                        "Initialized buffer for tool call id=%s",
                        call_id,
                        extra={"category": "api"},
                    )

                # Store name if present (usually only in first chunk)
                if name:
                    partial_tool_calls[call_id]["name"] = name
                    logger.debug(
                        "Stored tool name=%s for id=%s",
                        name,
                        call_id,
                        extra={"category": "api"},
                    )

                # Accumulate arguments
                if arg_chunk:
                    partial_tool_calls[call_id]["args"] += arg_chunk
                    # logger.debug(
                    #     "Accumulated args for id=%s, total_len=%d",
                    #     call_id,
                    #     len(partial_tool_calls[call_id]["args"]),
                    #     extra={"category": "api"},
                    # )

                # Try to parse when we have arguments
                raw_args = partial_tool_calls[call_id]["args"]
                if not raw_args:
                    continue

                try:
                    parsed = json.loads(raw_args)
                except json.JSONDecodeError:
                    # Still incomplete, wait for more chunks
                    continue

                # Only emit once we have a non-empty command and a name
                stored_name = partial_tool_calls[call_id]["name"]
                if isinstance(parsed, dict) and parsed.get("command") and stored_name:
                    yield {
                        "type": "tool_call",
                        "id": call_id,
                        "name": stored_name,
                        "arguments": parsed,
                    }
                    logger.debug(
                        "Emitted tool_call from stream: name=%s id=%s",
                        stored_name,
                        call_id,
                        extra={"category": "api"},
                    )
                    # Prevent duplicate emits for same id
                    partial_tool_calls.pop(call_id, None)


def handle_complete_response(response) -> Dict[str, Any]:
    """
    Handle complete (non-streaming) response from LiteLLM.

    Args:
        response: Complete response from litellm.completion

    Returns:
        Parsed response dict.
    """
    choice = response.choices[0]
    message = choice.message

    result = {"content": message.content or "", "tool_calls": []}

    # Extract tool calls if present
    if hasattr(message, "tool_calls") and message.tool_calls:
        for tool_call in message.tool_calls:
            # Parse tool arguments defensively; some providers may return
            # incomplete or malformed JSON strings.
            try:
                raw_args = tool_call.function.arguments or "{}"
                parsed_args = json.loads(raw_args)
            except Exception as e:
                logger.warning(
                    "Failed to parse tool arguments for %s: %s; raw=%r",
                    getattr(tool_call.function, "name", "<unknown>"),
                    e,
                    getattr(tool_call.function, "arguments", None),
                )
                # Skip this tool call rather than crashing the whole response
                continue

            result["tool_calls"].append(
                {
                    "id": tool_call.id,
                    "name": tool_call.function.name,
                    "arguments": parsed_args,
                }
            )

    return result
