"""LLM provider functionality for whai."""

from whai.llm.prompts import get_base_system_prompt
from whai.llm.provider import EXECUTE_SHELL_TOOL, LLMProvider

__all__ = [
    "LLMProvider",
    "get_base_system_prompt",
    "EXECUTE_SHELL_TOOL",
]

