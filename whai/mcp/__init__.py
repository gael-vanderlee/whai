"""MCP (Model Context Protocol) support for whai."""

from whai.mcp.config import MCPConfig, MCPServerConfig, load_mcp_config
from whai.mcp.manager import MCPManager

__all__ = [
    "MCPConfig",
    "MCPServerConfig",
    "MCPManager",
    "load_mcp_config",
]

