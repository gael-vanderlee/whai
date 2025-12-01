"""Conversation loop execution for whai."""

import asyncio
import json
import sys
from typing import List, Optional

from whai import ui
from whai.constants import TOOL_OUTPUT_MAX_TOKENS
from whai.core.session_logger import SessionLogger
from whai.interaction import approval_loop, approve_tool, execute_command
from whai.llm import LLMProvider
from whai.llm.token_utils import truncate_text_with_tokens
from whai.logging_setup import get_logger
from whai.utils import PerformanceLogger

logger = get_logger(__name__)


def run_conversation_loop(
    llm_provider: LLMProvider, messages: List[dict], timeout: int, command_string: Optional[str] = None
) -> None:
    """
    Run the main conversation loop with the LLM.

    Args:
        llm_provider: Configured LLM provider instance.
        messages: Initial conversation messages.
        timeout: Command timeout in seconds.
        command_string: Optional full command string for logging (e.g., "whai -vv 'query'").
    """
    # Initialize session logger for context capture in whai shell
    session_logger = SessionLogger(console=ui.console)
    
    # Log the whai command itself if provided
    if command_string and session_logger.enabled:
        session_logger.log_command(command_string)
    
    # Initialize MCP manager if enabled
    # Try to reuse the provider's MCP manager if it exists, otherwise create a new one
    from whai.mcp.manager import MCPManager
    from whai.mcp.executor import handle_mcp_tool_call_sync
    
    mcp_manager = None
    mcp_loop = None
    
    # Create a persistent event loop for MCP operations to keep connections alive
    if hasattr(llm_provider, "_mcp_manager") and llm_provider._mcp_manager is not None:
        mcp_manager = llm_provider._mcp_manager
        logger.debug("Reusing LLM provider's MCP manager instance")
    else:
        mcp_manager = MCPManager()
        # Store on provider so _get_mcp_tools() can reuse it
        llm_provider._mcp_manager = mcp_manager
    
    if mcp_manager.is_enabled():
        # Create a persistent event loop for MCP operations to keep connections alive
        # We use a separate loop to avoid interfering with any existing event loop
        mcp_loop = asyncio.new_event_loop()
        try:
            if not mcp_manager._initialized:
                errors = mcp_loop.run_until_complete(mcp_manager.initialize())
                
                if errors:
                    ui.error("MCP server initialization failed:")
                    for server_name, error_msg in errors:
                        ui.error(error_msg)
                    ui.error("\nPlease fix the errors in your mcp.json configuration and try again.")
                    mcp_loop.close()
                    sys.exit(1)
        except Exception as e:
            logger.exception("Failed to initialize MCP manager: %s", e)
            mcp_loop.close()
            mcp_loop = None
            mcp_manager = None
    
    loop_iteration = 0
    try:
        while True:
            loop_iteration += 1
            loop_perf = PerformanceLogger(f"Conversation Loop (iteration {loop_iteration})")
            loop_perf.start()
            
            try:
                # Send to LLM with streaming; show spinner until first chunk arrives
                with ui.spinner("Thinking"):
                    try:
                        # Pass the persistent MCP event loop to send_message so it can
                        # use the same loop for MCP tool discovery, avoiding duplicate initialization
                        response_stream = llm_provider.send_message(messages, stream=True, mcp_loop=mcp_loop)
                    except RuntimeError as e:
                        # Check if it's an MCP error (from get_all_tools)
                        error_msg = str(e)
                        if "MCP server" in error_msg or "mcp.json" in error_msg.lower():
                            ui.error("MCP error:")
                            ui.error(error_msg)
                            ui.error("\nPlease fix the errors in your mcp.json configuration and try again.")
                            sys.exit(1)
                        raise
                    response_chunks = []
                    first_chunk = None
                    for chunk in response_stream:
                        first_chunk = chunk
                        break
                loop_perf.log_section("LLM API call (streaming)")

                # Print first chunk and continue streaming
                if first_chunk is not None:
                    response_chunks.append(first_chunk)
                    if first_chunk["type"] == "text":
                        session_logger.print(first_chunk["content"], end="", soft_wrap=True)
                for chunk in response_stream:
                    response_chunks.append(chunk)
                    if chunk["type"] == "text":
                        session_logger.print(chunk["content"], end="", soft_wrap=True)
                if any(c["type"] == "text" for c in response_chunks):
                    session_logger.print()

                # Extract tool calls from chunks
                tool_calls = [c for c in response_chunks if c["type"] == "tool_call"]
                logger.debug(
                    "Received %d tool calls from stream",
                    len(tool_calls),
                    extra={"category": "api"},
                )
                loop_perf.log_section("Response parsing", extra_info={"tool_calls": len(tool_calls)})

                if not tool_calls:
                    # No tool calls, conversation is done
                    loop_perf.log_complete(extra_info={"ended": "no_tool_calls"})
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
                        loop_perf.log_section("Command approval")

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
                            
                            # Log command to session for context
                            session_logger.log_command(approved_command)
                            
                            with ui.spinner("Executing command..."):
                                stdout, stderr, returncode = execute_command(
                                    approved_command, timeout=timeout
                                )
                            loop_perf.log_section(
                                "Command execution",
                                extra_info={"command": approved_command, "exit_code": returncode},
                            )
                            
                            # Log command output to session for context
                            session_logger.log_command_output(stdout, stderr, returncode)

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
                            truncated_result, was_truncated = truncate_text_with_tokens(
                                result, TOOL_OUTPUT_MAX_TOKENS
                            )
                            loop_perf.log_section(
                                "Tool output truncation",
                                extra_info={"truncated": was_truncated},
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

                            # Log failure to session for deep context capture
                            # This ensures subsequent commands will have context about the failure
                            if "timed out" in error_text.lower():
                                session_logger.log_command_failure(error_text, timeout=timeout)
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
                                session_logger.log_command_failure(error_text)
                                tool_results.append(
                                    {
                                        "tool_call_id": tool_call["id"],
                                        "output": f"Failed to execute command: {error_text}",
                                    }
                                )
                    elif tool_call["name"].startswith("mcp_") and mcp_manager:
                        # Handle MCP tool call
                        tool_name = tool_call["name"]
                        tool_args = tool_call.get("arguments", {})
                        
                        # Parse server name from tool name (mcp_<server>_<tool>)
                        parts = tool_name.split("_", 2)
                        if len(parts) >= 3:
                            server_name = parts[1]
                            server_config = mcp_manager.get_server_config(server_name)
                            
                            # Check if approval is required (default to True for safety)
                            requires_approval = (
                                server_config.requires_approval if server_config else True
                            )
                            
                            # Get tool description from cached tool definitions
                            tool_description = mcp_manager.get_tool_description(tool_name)
                            
                            if requires_approval:
                                # Compute display name only when approval is needed
                                display_name = (
                                    server_config.name if server_config and server_config.name else server_name
                                )
                                # Get user approval with description
                                approved = approve_tool(
                                    tool_name, tool_args, display_name=display_name, description=tool_description
                                )
                                loop_perf.log_section("Tool approval")
                                
                                if not approved:
                                    # User rejected
                                    tool_results.append(
                                        {
                                            "tool_call_id": tool_call["id"],
                                            "output": "Tool call rejected by user.",
                                        }
                                    )
                                    continue
                            
                            # Execute the tool call
                            try:
                                result = handle_mcp_tool_call_sync(tool_call, mcp_manager, mcp_loop)
                                
                                # Display the output (pretty formatted, like shell commands)
                                output_text = result.get("output", "")
                                if output_text:
                                    ui.console.print()
                                    # Format MCP output similar to shell command output
                                    # print_output expects (stdout, stderr, returncode)
                                    # For MCP tools, we treat output as stdout with no errors
                                    ui.print_output(output_text, "", 0)
                                    ui.console.print()
                                
                                tool_results.append(result)
                            except Exception as e:
                                logger.exception("Error handling MCP tool call: %s", e)
                                tool_results.append(
                                    {
                                        "tool_call_id": tool_call["id"],
                                        "output": f"MCP tool call error: {str(e)}",
                                    }
                                )
                        else:
                            # Invalid tool name format
                            logger.warning("Invalid MCP tool name format: %s", tool_name)
                            tool_results.append(
                                {
                                    "tool_call_id": tool_call["id"],
                                    "output": f"Invalid MCP tool name format: {tool_name}",
                                }
                            )

                # Decide whether to end the conversation
                all_rejected = tool_results and all(
                    "rejected" in r["output"].lower() for r in tool_results
                )

                if not tool_results and tool_calls:
                    # Tool calls existed but none were runnable (e.g., empty/missing command)
                    ui.info("No runnable tool calls were produced (missing command).")
                    loop_perf.log_complete(extra_info={"ended": "no_runnable_tool_calls"})
                    break

                if not tool_results or all_rejected:
                    ui.console.print("\nConversation ended.")
                    loop_perf.log_complete(extra_info={"ended": "all_rejected"})
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

                loop_perf.log_section("Message history update", extra_info={"tool_results": len(tool_results)})
                loop_perf.log_complete(extra_info={"tool_calls": len(tool_calls), "tool_results": len(tool_results)})

                # Continue loop to get LLM's next response

            except KeyboardInterrupt:
                ui.console.print("\n\nInterrupted by user.")
                loop_perf.log_complete(extra_info={"ended": "keyboard_interrupt"})
                break
            except Exception as e:
                import traceback

                text = str(e)
                # Check for LLM-related errors (API errors, model errors, auth errors, etc.)
                if (
                    "LLM API error" in text
                    or "Model" in text and "provider" in text
                    or "Authentication failed" in text
                    or "Permission denied" in text
                    or "Rate limit" in text
                    or "Network or service error" in text
                ):
                    # Show concise, helpful message for provider/model/auth errors
                    ui.error(text)
                    ui.info(
                        "Run 'whai --interactive-config' to review your keys and model."
                    )
                    # Keep full details in logs only
                    logger.exception("LLM error in conversation loop: %s", e)
                    loop_perf.log_complete(extra_info={"ended": "llm_error"})
                    break
                else:
                    ui.error(f"Unexpected error: {e}")
                    ui.error(f"Details: {traceback.format_exc()}")
                    logger.exception("Unexpected error in conversation loop: %s", e)
                    loop_perf.log_complete(extra_info={"ended": "unexpected_error"})
                    break
    finally:
        # Clean up MCP connections
        # Only close if we created our own manager (not if we reused the provider's)
        if mcp_manager and not (hasattr(llm_provider, "_mcp_manager") and llm_provider._mcp_manager is mcp_manager):
            try:
                if mcp_loop and not mcp_loop.is_closed():
                    # Use the persistent loop to close connections in the same context
                    # This ensures AnyIO cancel scopes are exited in the same task they were entered
                    mcp_loop.run_until_complete(mcp_manager.close_all())
                else:
                    # Loop is closed - connections are effectively dead anyway
                    # Skip cleanup to avoid AnyIO cancel scope errors from different task context
                    logger.debug("MCP loop is closed, skipping cleanup (connections already dead)")
            except Exception as e:
                logger.debug("Error during MCP cleanup: %s", e)
            finally:
                if mcp_loop and not mcp_loop.is_closed():
                    mcp_loop.close()
