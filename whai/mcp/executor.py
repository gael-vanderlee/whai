"""MCP tool call handling for executor integration."""

import asyncio
import json
from typing import Any, Dict

from whai.mcp.manager import MCPManager
from whai.logging_setup import get_logger

logger = get_logger(__name__)


def handle_mcp_tool_call_sync(
    tool_call: Dict[str, Any], mcp_manager: MCPManager
) -> Dict[str, Any]:
    """
    Handle an MCP tool call synchronously (bridges async MCP to sync executor).

    This function bridges async MCP calls into the sync executor conversation loop.
    It uses asyncio.run() to bridge the async MCP calls.

    Args:
        tool_call: Tool call dictionary with 'name' and 'arguments' keys.
        mcp_manager: Initialized MCPManager instance.

    Returns:
        Tool result dictionary with 'tool_call_id' and 'output' keys.
    """
    tool_name = tool_call.get("name", "")
    tool_id = tool_call.get("id", "")
    arguments = tool_call.get("arguments", {})

    try:
        result = asyncio.run(mcp_manager.call_tool(tool_name, arguments))

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
        error_msg = f"MCP tool error: {str(e)}"
        logger.warning(error_msg, extra={"category": "mcp"})
        return {
            "tool_call_id": tool_id,
            "output": error_msg,
        }

    except Exception as e:
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

