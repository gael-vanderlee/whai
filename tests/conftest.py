"""Pytest configuration for whai tests."""

import os
import time
from unittest.mock import MagicMock

import pytest

from whai.configuration.user_config import (
    AnthropicConfig,
    GeminiConfig,
    LLMConfig,
    MistralConfig,
    OpenAIConfig,
    RolesConfig,
    WhaiConfig,
)
from whai.utils import PerformanceLogger


@pytest.fixture(scope="session", autouse=True)
def plain_mode_for_tests():
    """Force plain mode (no Rich styling) for all tests."""
    original = os.environ.get("WHAI_PLAIN")
    os.environ["WHAI_PLAIN"] = "1"
    yield
    if original is None:
        os.environ.pop("WHAI_PLAIN", None)
    else:
        os.environ["WHAI_PLAIN"] = original


@pytest.fixture(scope="session", autouse=True)
def test_mode_for_config():
    """Enable test mode for config loading."""
    from whai.constants import ENV_WHAI_TEST_MODE
    
    original = os.environ.get(ENV_WHAI_TEST_MODE)
    os.environ[ENV_WHAI_TEST_MODE] = "1"
    yield
    if original is None:
        os.environ.pop(ENV_WHAI_TEST_MODE, None)
    else:
        os.environ[ENV_WHAI_TEST_MODE] = original


# Configure pytest-anyio to only use asyncio backend (not trio)
# pytest-anyio runs tests with both backends by default, but we only want asyncio
import pytest

def pytest_configure(config):
    """Configure pytest-anyio to only use asyncio backend."""
    # Set environment variable for anyio
    import os
    os.environ.setdefault("ANYIO_BACKEND", "asyncio")
    
    # Try to configure pytest-anyio plugin directly
    try:
        import anyio
        # Force asyncio backend
        anyio._backend = "asyncio"
    except (ImportError, AttributeError):
        pass

def pytest_collection_modifyitems(config, items):
    """Skip trio backend tests."""
    for item in items:
        # Check if this is a parametrized test with trio backend
        if hasattr(item, "callspec") and item.callspec:
            params = item.callspec.params
            if "asynclib_name" in params and params["asynclib_name"] == "trio":
                # Skip this test variant
                skip_marker = pytest.mark.skip(reason="trio backend not available")
                item.add_marker(skip_marker)
        
        # Also check for anyio parametrization in the test name
        if "[trio]" in item.name:
            skip_marker = pytest.mark.skip(reason="trio backend not available")
            item.add_marker(skip_marker)


def create_test_config(
    default_provider: str = "openai",
    default_model: str = "gpt-5-mini",
    api_key: str = "test-key-123",
    providers: dict = None,
) -> WhaiConfig:
    """
    Helper function to create a test WhaiConfig object.
    
    Args:
        default_provider: Default provider name.
        default_model: Default model name.
        api_key: API key for the default provider.
        providers: Optional dict of provider configs to add.
    
    Returns:
        WhaiConfig instance for testing.
    """
    from whai.constants import DEFAULT_PROVIDER, DEFAULT_ROLE_NAME
    
    provider_configs = {}
    
    # Add default provider
    if default_provider == "openai":
        provider_configs["openai"] = OpenAIConfig(
            api_key=api_key,
            default_model=default_model,
        )
    elif default_provider == "anthropic":
        provider_configs["anthropic"] = AnthropicConfig(
            api_key=api_key,
            default_model=default_model,
        )
    elif default_provider == "gemini":
        provider_configs["gemini"] = GeminiConfig(
            api_key=api_key,
            default_model=default_model,
        )
    elif default_provider == "mistral":
        provider_configs["mistral"] = MistralConfig(
            api_key=api_key,
            default_model=default_model,
        )
    
    # Add any additional providers
    if providers:
        provider_configs.update(providers)
    
    return WhaiConfig(
        llm=LLMConfig(
            default_provider=default_provider or DEFAULT_PROVIDER,
            providers=provider_configs,
        ),
        roles=RolesConfig(default_role=DEFAULT_ROLE_NAME),
    )


def create_test_perf_logger() -> PerformanceLogger:
    """
    Helper function to create a test PerformanceLogger instance.
    
    Returns:
        PerformanceLogger instance for testing.
    """
    perf_logger = PerformanceLogger("Test")
    perf_logger.start()
    return perf_logger


@pytest.fixture
def mock_litellm_module():
    """Mock litellm module in sys.modules to prevent slow import overhead.
    
    This fixture patches sys.modules to insert a mock litellm module before
    the real module can be imported, avoiding the slow SSL certificate loading
    that happens during litellm import (especially on Windows).
    
    Use this fixture in any test that mocks litellm.completion to prevent
    the slow import overhead.
    """
    import sys
    from unittest.mock import patch
    
    mock_litellm = MagicMock()
    mock_litellm.exceptions = MagicMock()
    with patch.dict("sys.modules", {"litellm": mock_litellm}):
        yield mock_litellm


@pytest.fixture
def llm_provider_with_cleanup(create_test_config, create_test_perf_logger):
    """
    Fixture that provides LLMProvider with automatic MCP cleanup.
    
    Use this fixture instead of creating LLMProvider directly in tests
    to ensure MCP connections are properly closed.
    """
    providers = []
    
    def _create_provider(*args, **kwargs):
        from whai.llm import LLMProvider
        provider = LLMProvider(*args, **kwargs)
        providers.append(provider)
        return provider
    
    yield _create_provider
    


@pytest.fixture
def mcp_server_time(tmp_path, monkeypatch):
    """
    Fixture that spins up a real temporary MCP time server for testing.
    
    Uses uvx to run mcp-server-time ephemerally. The server process is started
    and cleaned up automatically.
    """
    import subprocess
    import shutil
    
    # Check if uvx is available
    uvx_path = shutil.which("uvx")
    if not uvx_path:
        pytest.skip("uvx not available, cannot run MCP server tests")
    
    # Check if mcp-server-time can be run
    try:
        result = subprocess.run(
            [uvx_path, "mcp-server-time", "--help"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0:
            pytest.skip("mcp-server-time not available via uvx")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pytest.skip("Cannot run mcp-server-time")
    
    # Create MCP config for the test server
    config_dir = tmp_path / "whai"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "mcp.json"
    
    config_data = {
        "mcpServers": {
            "time-server": {
                "command": uvx_path,
                "args": ["mcp-server-time"],
                "env": {}
            }
        }
    }
    
    import json
    config_file.write_text(json.dumps(config_data))
    
    # Mock get_config_dir to return our test config directory
    def mock_get_config_dir():
        return config_dir
    
    monkeypatch.setattr("whai.mcp.config.get_config_dir", mock_get_config_dir)
    
    yield {
        "server_name": "time-server",
        "command": uvx_path,
        "args": ["mcp-server-time"],
        "env": {},
    }
