"""MCP configuration management using dataclasses."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from whai.configuration.user_config import get_config_dir
from whai.logging_setup import get_logger
from whai.utils import PerformanceLogger

logger = get_logger(__name__)

MCP_CONFIG_FILENAME = "mcp.json"


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    command: str
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    name: Optional[str] = None
    requires_approval: bool = True

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not isinstance(self.command, str) or not self.command.strip():
            raise ValueError("MCP server 'command' must be a non-empty string")
        if self.args is not None and not isinstance(self.args, list):
            raise ValueError("MCP server 'args' must be a list if provided")
        if self.env is not None and not isinstance(self.env, dict):
            raise ValueError("MCP server 'env' must be a dictionary if provided")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: Dict[str, Any] = {"command": self.command}
        if self.args is not None:
            result["args"] = self.args
        if self.env is not None:
            result["env"] = self.env
        if self.name is not None:
            result["name"] = self.name
        if not self.requires_approval:
            result["requires_approval"] = False
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPServerConfig":
        """Create MCPServerConfig from dictionary."""
        return cls(
            command=data["command"],
            args=data.get("args"),
            env=data.get("env"),
            name=data.get("name"),
            requires_approval=data.get("requires_approval", True),
        )


@dataclass
class MCPConfig:
    """Configuration for MCP servers."""

    mcp_servers: Dict[str, MCPServerConfig] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "mcpServers": {
                name: server_config.to_dict()
                for name, server_config in self.mcp_servers.items()
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPConfig":
        """Create MCPConfig from dictionary."""
        mcp_servers_data = data.get("mcpServers", {})
        if not isinstance(mcp_servers_data, dict):
            raise ValueError("'mcpServers' must be a JSON object")

        mcp_servers: Dict[str, MCPServerConfig] = {}
        for server_name, server_data in mcp_servers_data.items():
            if not isinstance(server_data, dict):
                raise ValueError(f"Server '{server_name}' configuration must be a JSON object")
            if "command" not in server_data:
                raise ValueError(f"Server '{server_name}' missing required 'command' field")
            mcp_servers[server_name] = MCPServerConfig.from_dict(server_data)

        return cls(mcp_servers=mcp_servers)

    @classmethod
    def from_file(cls, path: Path) -> "MCPConfig":
        """Load configuration from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_file(self, path: Path) -> None:
        """Save configuration to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


def get_mcp_config_path() -> Path:
    """Get the path to the MCP configuration file."""
    return get_config_dir() / MCP_CONFIG_FILENAME


def load_mcp_config() -> Optional[MCPConfig]:
    """
    Load MCP server configuration from JSON file.

    Returns:
        MCPConfig instance if file exists, None if file doesn't exist (opt-in behavior).

    Raises:
        ValueError: If the JSON file exists but is invalid.
    """
    perf = PerformanceLogger("MCP Config")
    perf.start()
    
    config_path = get_mcp_config_path()

    if not config_path.exists():
        logger.debug("MCP config file not found at %s (MCP support is opt-in)", config_path)
        perf.log_section("Config file check (not found)")
        return None

    try:
        config = MCPConfig.from_file(config_path)
        perf.log_section("Config file loading", extra_info={"servers": len(config.mcp_servers)})
        logger.info("Loaded MCP config with %d server(s)", len(config.mcp_servers))
        return config
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in MCP config file: {e}")
    except Exception as e:
        raise ValueError(f"Error loading MCP config: {e}")

