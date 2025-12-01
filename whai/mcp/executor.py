"""MCP tool call handling for executor integration."""

import asyncio
import json
from typing import Any, Dict, Optional

from whai.mcp.manager import MCPManager
from whai.logging_setup import get_logger
from whai.utils import PerformanceLogger
from whai import ui

logger = get_logger(__name__)


def handle_mcp_tool_call_sync(
    tool_call: Dict[str, Any], mcp_manager: MCPManager, loop: Optional[asyncio.AbstractEventLoop] = None
) -> Dict[str, Any]:
    """
    Handle an MCP tool call synchronously (bridges async MCP to sync executor).

    This function bridges async MCP calls into the sync executor conversation loop.
    It uses the provided event loop or creates a new one if needed.

    Args:
        tool_call: Tool call dictionary with 'name' and 'arguments' keys.
        mcp_manager: Initialized MCPManager instance.
        loop: Optional event loop to use. If None, creates a new one (closes connections).

    Returns:
        Tool result dictionary with 'tool_call_id' and 'output' keys.
    """
    tool_name = tool_call.get("name", "")
    tool_id = tool_call.get("id", "")
    arguments = tool_call.get("arguments", {})

    # Parse tool name to show server/tool format (mcp_<server>_<tool>)
    display_name = tool_name
    if tool_name.startswith("mcp_") and "_" in tool_name[4:]:
        parts = tool_name.split("_", 2)
        if len(parts) >= 3:
            server_name = parts[1]
            actual_tool = parts[2]
            display_name = f"{server_name}/{actual_tool}"
    
    ui.info(f"🔧 Calling MCP tool: {display_name}")

    # Performance logging for total tool call time
    perf = PerformanceLogger(f"MCP Tool Call ({display_name})")
    perf.start()

    try:
        if loop is not None:
            # Reuse existing loop to keep connections alive
            if loop.is_closed():
                # Loop is closed - cannot create new one as it would violate AnyIO cancel scope requirements
                raise RuntimeError(
                    f"MCP event loop is closed. Cannot call tool {tool_name} - connections are dead."
                )
            else:
                # Use existing loop
                # Detailed performance logging is handled inside client.call_tool() at DEBUG level
                result = loop.run_until_complete(mcp_manager.call_tool(tool_name, arguments))
        else:
            # No loop provided - cannot use asyncio.run() as it creates a new event loop
            # which violates AnyIO's requirement that context managers are entered/exited
            # in the same task. Tool calls must use the persistent loop from the executor.
            raise RuntimeError(
                f"No event loop provided for MCP tool call {tool_name}. "
                "Tool calls must use the persistent loop from the executor."
            )

        if isinstance(result, dict):
            if "content" in result:
                content = result.get("content", [])
                if content and isinstance(content, list):
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                    output = "\n".join(text_parts) if text_parts else str(result)
                else:
                    output = str(result)
            else:
                output = json.dumps(result, indent=2)
        else:
            output = str(result)

        perf.log_complete()
        logger.debug(
            "MCP tool call %s completed successfully",
            tool_name,
            extra={"category": "mcp"},
        )

        return {
            "tool_call_id": tool_id,
            "output": output,
        }

    except ValueError as e:
        perf.log_complete()
        error_msg = f"MCP tool error: {str(e)}"
        logger.warning(error_msg, extra={"category": "mcp"})
        return {
            "tool_call_id": tool_id,
            "output": error_msg,
        }

    except Exception as e:
        perf.log_complete()
        error_msg = f"MCP tool call failed: {str(e)}"
        logger.exception(
            "MCP tool call %s failed: %s",
            tool_name,
            e,
            extra={"category": "mcp"},
        )
        return {
            "tool_call_id": tool_id,
            "output": error_msg,
        }

