"""Centralized defaults and constants for whai.

Keep all cross-module default values here to avoid duplication.
"""

# ============================================================================
# LLM Provider Defaults
# ============================================================================

# Default query when calling whai only
DEFAULT_QUERY = "I am confused about what you can see in the most recent command(s) in the terminal context, provide assistance"

# Default provider for quick setup
DEFAULT_PROVIDER = "openai"

# Default models per provider (stored without provider prefixes)
DEFAULT_MODEL_OPENAI = "gpt-5-mini"
DEFAULT_MODEL_ANTHROPIC = "claude-3-5-sonnet-20241022"
DEFAULT_MODEL_GEMINI = "gemini-2.5-flash"
DEFAULT_MODEL_AZURE_OPENAI = "gpt-4"
DEFAULT_MODEL_OLLAMA = "mistral"
DEFAULT_MODEL_LM_STUDIO = "llama-3-8b-instruct"

# API defaults
DEFAULT_AZURE_API_VERSION = "2023-05-15"
DEFAULT_OLLAMA_API_BASE = "http://localhost:11434"
DEFAULT_LM_STUDIO_API_BASE = "http://localhost:1234/v1"

# Provider configuration defaults
PROVIDER_DEFAULTS = {
    "openai": {
        "fields": ["api_key", "default_model"],
        "defaults": {"default_model": DEFAULT_MODEL_OPENAI},
    },
    "anthropic": {
        "fields": ["api_key", "default_model"],
        "defaults": {"default_model": DEFAULT_MODEL_ANTHROPIC},
    },
    "gemini": {
        "fields": ["api_key", "default_model"],
        "defaults": {"default_model": DEFAULT_MODEL_GEMINI},
    },
    "azure_openai": {
        "fields": ["api_key", "api_base", "api_version", "default_model"],
        "defaults": {
            "api_version": DEFAULT_AZURE_API_VERSION,
            "default_model": DEFAULT_MODEL_AZURE_OPENAI,
        },
    },
    "ollama": {
        "fields": ["api_base", "default_model"],
        "defaults": {
            "api_base": DEFAULT_OLLAMA_API_BASE,
            "default_model": DEFAULT_MODEL_OLLAMA,
        },
    },
    "lm_studio": {
        "fields": ["api_base", "default_model"],
        "defaults": {
            "api_base": DEFAULT_LM_STUDIO_API_BASE,
            "default_model": DEFAULT_MODEL_LM_STUDIO,
        },
    },
}


def get_default_model_for_provider(provider: str) -> str:
    """Get the default model for a given provider.

    Args:
        provider: Provider name (e.g., 'openai', 'anthropic').

    Returns:
        Default model name for the provider, or fallback to openai default if unknown.
    """
    provider_config = PROVIDER_DEFAULTS.get(provider)
    if provider_config:
        return provider_config["defaults"].get("default_model", DEFAULT_MODEL_OPENAI)
    return DEFAULT_MODEL_OPENAI


# ============================================================================
# Timeout Defaults (seconds)
# ============================================================================

DEFAULT_COMMAND_TIMEOUT = 60  # Per-command timeout for execute_command
CONTEXT_CAPTURE_TIMEOUT = 5  # Timeout for tmux/history context capture
WSL_CHECK_TIMEOUT = 2  # Timeout for WSL availability check

# ============================================================================
# Context Capture Limits
# ============================================================================

TMUX_SCROLLBACK_LINES = 500  # Number of lines to capture from tmux scrollback
HISTORY_MAX_COMMANDS = 50  # Maximum number of commands from shell history

# Token limits for truncation (to prevent exceeding model context limits)
CONTEXT_MAX_TOKENS = 200_000  # Maximum tokens for terminal context
TOOL_OUTPUT_MAX_TOKENS = 50_000  # Maximum tokens for individual command outputs

# Terminal output limits (for display truncation)
TERMINAL_OUTPUT_MAX_LINES = 500  # Maximum lines to display in terminal (0 = no limit)

# ============================================================================
# UI Styling
# ============================================================================

UI_THEME = "ansi_dark"  # Rich syntax theme
UI_BORDER_COLOR_COMMAND = "cyan"
UI_BORDER_COLOR_OUTPUT = "green"
UI_BORDER_COLOR_ERROR = "red"
UI_BORDER_COLOR_STATUS_SUCCESS = "green"
UI_BORDER_COLOR_STATUS_ERROR = "yellow"
UI_TEXT_STYLE_PROMPT = "yellow"
UI_TEXT_STYLE_WARNING = "yellow"
UI_TEXT_STYLE_ERROR = "bold red"

# ============================================================================
# Configuration File Names
# ============================================================================

CONFIG_FILENAME = "config.toml"
DEFAULT_ROLE_NAME = "default"
DEFAULT_ROLE_FILENAME = "default.md"

# ============================================================================
# Environment Variable Names
# ============================================================================

ENV_WHAI_ROLE = "WHAI_ROLE"
ENV_WHAI_PLAIN = "WHAI_PLAIN"
ENV_WHAI_TEST_MODE = "WHAI_TEST_MODE"
ENV_WHAI_LOG_LEVEL = "WHAI_LOG_LEVEL"
ENV_WHAI_VERBOSE_DEPS = "WHAI_VERBOSE_DEPS"
ENV_WHAI_MOCK_TOOLCALL = "WHAI_MOCK_TOOLCALL"
