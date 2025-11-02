"""Conversation loop execution for whai."""

import json
import time
from typing import List

from whai import ui
from whai.constants import TOOL_OUTPUT_MAX_TOKENS
from whai.interaction import approval_loop, execute_command
from whai.llm import LLMProvider
from whai.llm.token_utils import truncate_text_with_tokens
from whai.logging_setup import get_logger

logger = get_logger(__name__)


def run_conversation_loop(
    llm_provider: LLMProvider, messages: List[dict], timeout: int
) -> None:
    """
    Run the main conversation loop with the LLM.

    Args:
        llm_provider: Configured LLM provider instance.
        messages: Initial conversation messages.
        timeout: Command timeout in seconds.
    """
    while True:
        try:
            # Send to LLM with streaming; show spinner until first chunk arrives
            import time

            start_spinner = time.perf_counter()
            with ui.spinner("Thinking"):
                response_stream = llm_provider.send_message(messages, stream=True)
                response_chunks = []
                first_chunk = None
                for chunk in response_stream:
                    first_chunk = chunk
                    break
            elapsed_spinner = time.perf_counter() - start_spinner
            logger.info(
                f"Spinner duration before first chunk: {elapsed_spinner:.3f}s",
                extra={"category": "ui"},
            )

            # Print first chunk and continue streaming
            if first_chunk is not None:
                response_chunks.append(first_chunk)
                if first_chunk["type"] == "text":
                    ui.console.print(first_chunk["content"], end="", soft_wrap=True)
            for chunk in response_stream:
                response_chunks.append(chunk)
                if chunk["type"] == "text":
                    ui.console.print(chunk["content"], end="", soft_wrap=True)
            if any(c["type"] == "text" for c in response_chunks):
                ui.console.print()

            # Extract tool calls from chunks
            tool_calls = [c for c in response_chunks if c["type"] == "tool_call"]
            logger.debug(
                "Received %d tool calls from stream",
                len(tool_calls),
                extra={"category": "api"},
            )

            if not tool_calls:
                # No tool calls, conversation is done
                break

            # Process each tool call
            tool_results = []
            for tool_call in tool_calls:
                if tool_call["name"] == "execute_shell":
                    command = tool_call["arguments"].get("command", "")

                    if not command:
                        continue

                    # Get user approval
                    approved_command = approval_loop(command)

                    if approved_command is None:
                        # User rejected
                        tool_results.append(
                            {
                                "tool_call_id": tool_call["id"],
                                "output": "Command rejected by user.",
                            }
                        )
                        continue

                    # Execute the command
                    try:
                        logger.debug(
                            "Executing approved command: %s",
                            approved_command,
                            extra={"category": "cmd"},
                        )
                        stdout, stderr, returncode = execute_command(
                            approved_command, timeout=timeout
                        )

                        # Format the result for LLM (plain text)
                        result = f"Command: {approved_command}\n"
                        result += f"Exit code: {returncode}\n"
                        if stdout:
                            result += f"\nOutput:\n{stdout}"
                        if stderr:
                            result += f"\nErrors:\n{stderr}"
                        if not stdout and not stderr:
                            result += "\nOutput: (empty - command produced no output)"

                        # Truncate tool output if needed to respect token limits
                        t_trunc0 = time.perf_counter()
                        truncated_result, was_truncated = truncate_text_with_tokens(
                            result, TOOL_OUTPUT_MAX_TOKENS
                        )
                        t_trunc1 = time.perf_counter()
                        logger.info(
                            "Tool output truncation completed in %.3f ms (truncated=%s)",
                            (t_trunc1 - t_trunc0) * 1000,
                            was_truncated,
                            extra={"category": "perf"},
                        )
                        if was_truncated:
                            ui.warn(
                                f"Command output for '{approved_command}' was truncated to fit token limits. "
                                "Recent output has been preserved."
                            )

                        tool_results.append(
                            {"tool_call_id": tool_call["id"], "output": truncated_result}
                        )

                        # Display the output (pretty formatted)
                        ui.console.print()
                        ui.print_output(stdout, stderr, returncode)
                        ui.console.print()

                    except Exception as e:
                        error_text = str(e)
                        logger.exception("Command execution failed: %s", e)
                        # Surface error to user
                        ui.error(f"Failed to execute command: {error_text}")

                        # If this was a timeout, include a clear, standardized marker
                        # in the tool result content so the LLM can react appropriately.
                        if "timed out" in error_text.lower():
                            timeout_note = (
                                f"Command: {approved_command}\n\n"
                                f"OUTPUT: NO OUTPUT, {timeout}s TIMEOUT EXCEEDED"
                            )
                            tool_results.append(
                                {
                                    "tool_call_id": tool_call["id"],
                                    "output": timeout_note,
                                }
                            )
                        else:
                            tool_results.append(
                                {
                                    "tool_call_id": tool_call["id"],
                                    "output": f"Failed to execute command: {error_text}",
                                }
                            )

            # Decide whether to end the conversation
            all_rejected = tool_results and all(
                "rejected" in r["output"].lower() for r in tool_results
            )

            if not tool_results and tool_calls:
                # Tool calls existed but none were runnable (e.g., empty/missing command)
                ui.info("No runnable tool calls were produced (missing command).")
                break

            if not tool_results or all_rejected:
                ui.console.print("\nConversation ended.")
                break

            # Build assistant message for history
            # Collect text content
            assistant_content = "".join(
                c["content"] for c in response_chunks if c["type"] == "text"
            )

            assistant_message = {
                "role": "assistant",
                "content": assistant_content,
            }

            # Add tool_calls to assistant message if present
            if tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                    for tc in tool_calls
                ]

            messages.append(assistant_message)

            # Add tool results to messages
            for result in tool_results:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": result["tool_call_id"],
                        "content": result["output"],
                    }
                )

            # Continue loop to get LLM's next response

        except KeyboardInterrupt:
            ui.console.print("\n\nInterrupted by user.")
            break
        except Exception as e:
            import traceback

            text = str(e)
            if "LLM API error" in text:
                # Show concise, helpful message for provider/model/auth errors
                ui.error(text)
                ui.info(
                    "Run 'whai --interactive-config' to review your keys and model."
                )
                # Keep full details in logs only
                logger.exception("LLM error in conversation loop: %s", e)
                break
            else:
                ui.error(f"Unexpected error: {e}")
                ui.error(f"Details: {traceback.format_exc()}")
                logger.exception("Unexpected error in conversation loop: %s", e)
                break
