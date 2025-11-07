"""LLM provider wrapper using LiteLLM."""

import json
import os
import re
from typing import Any, Dict, Generator, List, Optional, Union

from whai.configuration.user_config import WhaiConfig
from whai.constants import DEFAULT_PROVIDER, get_default_model_for_provider
from whai.llm.streaming import handle_complete_response, handle_streaming_response
from whai.logging_setup import get_logger
from whai.utils import PerformanceLogger

logger = get_logger(__name__)

# Tool definition for shell command execution
EXECUTE_SHELL_TOOL = {
    "type": "function",
    "function": {
        "name": "execute_shell",
        "description": "Execute a shell command in the terminal. Use this when you need to run commands to help the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute (e.g., 'ls -la', 'grep error log.txt')",
                }
            },
            "required": ["command"],
        },
    },
}


class LLMProvider:
    """
    Wrapper for LiteLLM to provide a consistent interface for LLM interactions.
    """

    def __init__(
        self, config: WhaiConfig, model: str = None, temperature: float = None, perf_logger: PerformanceLogger = None, provider: Optional[str] = None
    ) -> None:
        """
        Initialize the LLM provider.

        Args:
            config: WhaiConfig instance containing LLM settings.
            model: Optional model override (uses config default if not provided).
            temperature: Optional temperature override (if None, temperature is not set).
            perf_logger: PerformanceLogger for tracking performance from program start.
            provider: Optional provider override (uses config default if not provided).
        """
        if perf_logger is None:
            raise ValueError("perf_logger is required")
        self.config = config
        self.perf_logger = perf_logger
        
        # Use provided provider or fall back to default
        provider_name = provider if provider is not None else config.llm.default_provider
        if provider_name is None:
            raise ValueError("No provider specified and no default provider configured")
        
        provider_cfg = config.llm.get_provider(provider_name)
        if not provider_cfg:
            available = list(config.llm.providers.keys())
            raise RuntimeError(
                f"Provider '{provider_name}' is not configured. "
                f"Available providers: {available if available else 'none'}. "
                "Run 'whai --interactive-config' to set up a provider."
            )
        
        self.default_provider = provider_name
        # Resolve model: CLI override > provider-level default > built-in fallback
        # If model is None, use provider's default model
        model_to_use = model if model is not None else provider_cfg.default_model
        
        # Sanitize model name for provider-specific formatting (if needed)
        self.model = provider_cfg.sanitize_model_name(model_to_use) if model_to_use else None
            

        # Store custom API base for providers that need it
        self.api_base = provider_cfg.api_base if provider_cfg else None

        # Only set temperature when explicitly provided; many models (e.g., gpt-5*)
        # do not support it and should omit it entirely by default.
        self.temperature = temperature

        # Set API keys for LiteLLM
        self._configure_api_keys()
        logger.debug(
            "LLMProvider initialized: provider=%s model=%s temp=%s api_base=%s",
            self.default_provider,
            self.model,
            self.temperature if self.temperature is not None else "default",
            self.api_base or "default",
            extra={"category": "config"},
        )

    def _configure_api_keys(self):
        """Configure API keys and endpoints from config for LiteLLM."""
        # Set OpenAI key if present
        openai_cfg = self.config.llm.get_provider("openai")
        if openai_cfg and openai_cfg.api_key:
            os.environ["OPENAI_API_KEY"] = openai_cfg.api_key

        # Set Anthropic key if present
        anthropic_cfg = self.config.llm.get_provider("anthropic")
        if anthropic_cfg and anthropic_cfg.api_key:
            os.environ["ANTHROPIC_API_KEY"] = anthropic_cfg.api_key

        # Set Gemini key if present
        gemini_cfg = self.config.llm.get_provider("gemini")
        if gemini_cfg and gemini_cfg.api_key:
            os.environ["GEMINI_API_KEY"] = gemini_cfg.api_key

        # Set Azure OpenAI configuration if present
        azure_cfg = self.config.llm.get_provider("azure_openai")
        if azure_cfg:
            if azure_cfg.api_key:
                os.environ["AZURE_API_KEY"] = azure_cfg.api_key
            if azure_cfg.api_base:
                os.environ["AZURE_API_BASE"] = azure_cfg.api_base
            if azure_cfg.api_version:
                os.environ["AZURE_API_VERSION"] = azure_cfg.api_version

        # Set Ollama base URL if present
        ollama_cfg = self.config.llm.get_provider("ollama")
        if ollama_cfg and ollama_cfg.api_base:
            os.environ["OLLAMA_API_BASE"] = ollama_cfg.api_base

        # Note: LM Studio uses custom api_base passed directly to completion() call
        # No environment variable needed

    def send_message(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]] = None,
        stream: bool = True,
        tool_choice: Any = None,
    ) -> Union[Generator[Dict[str, Any], None, None], Dict[str, Any]]:
        """
        Send a message to the LLM and get a response.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            tools: Optional list of tool definitions. Defaults to execute_shell tool.
                   Pass an empty list [] to explicitly disable tools.
            stream: Whether to stream the response (default True).
            tool_choice: Optional tool selection directive (e.g., 'auto', 'none', or
                a function spec). Passed through to the underlying provider when set.

        Returns:
            If stream=True: Generator yielding response chunks.
            If stream=False: Complete response dict.

        Yields:
            Dicts with 'type' key:
            - {'type': 'text', 'content': str} for text chunks
            - {'type': 'tool_call', 'id': str, 'name': str, 'arguments': dict} for tool calls
        """
        # Default to using the execute_shell tool
        if tools is None:
            tools = [EXECUTE_SHELL_TOOL]

        try:
            # Only pass tools parameter if tools list is not empty
            # Passing an empty tools list can confuse some APIs
            completion_kwargs = {
                "model": self.model,
                "messages": messages,
                "stream": stream,
                "drop_params": True,  # Automatically drop unsupported params for the model
            }

            # Add custom API base if configured (for LM Studio, Ollama, etc.)
            if self.api_base:
                completion_kwargs["api_base"] = self.api_base

            # Only include temperature if explicitly set AND model supports it
            if self.temperature is not None and self.model and not self.model.startswith("gpt-5"):
                completion_kwargs["temperature"] = self.temperature

            if tools:  # Only add tools if list is not empty
                completion_kwargs["tools"] = tools

            # Pass through tool_choice only when provided to avoid confusing providers
            if tool_choice is not None:
                completion_kwargs["tool_choice"] = tool_choice

            logger.info(
                "Sending message to LLM: stream=%s tools_enabled=%s tool_count=%d temp=%s",
                stream,
                bool(tools),
                len(tools) if tools else 0,
                self.temperature if self.temperature is not None else "default",
                extra={"category": "api"},
            )
            # Log the exact payload the model will see for debug purposes
            try:
                pretty_payload = json.dumps(
                    {
                        "model": self.model,
                        "messages": messages,
                        "tools": tools or [],
                        "tool_choice": tool_choice,
                        **(
                            {"temperature": self.temperature}
                            if self.temperature is not None
                            else {}
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                logger.debug("LLM request payload:\n%s", pretty_payload)
                # Also log human-readable prompts (system/user) with natural line breaks
                try:
                    for m in messages:
                        role = m.get("role")
                        if role in ("system", "user"):
                            heading = (
                                "LLM system prompt"
                                if role == "system"
                                else "LLM user message"
                            )
                            content = m.get("content", "")
                            logger.debug(
                                "%s:\n%s",
                                heading,
                                content,
                                extra={
                                    "category": "llm_system" if role == "system" else "llm_user"
                                },
                            )
                except Exception:
                    # Never fail on diagnostic logging
                    pass
            except Exception:
                # Payload logging must never break execution
                logger.debug("LLM request payload: <unserializable>")
            if tools:
                logger.debug(
                    "Tool definitions: %s",
                    [t.get("function", {}).get("name") for t in tools],
                    extra={"category": "api"},
                )
            # Lazy import to keep CLI startup fast
            import time as _t

            # Measure import time for LiteLLM for diagnostics
            t_import_start = _t.perf_counter()

            # Apply SSL cache optimization before importing litellm
            # This significantly improves import performance
            from whai.llm.ssl_cache import apply as apply_ssl_cache

            apply_ssl_cache()

            from litellm import completion  # type: ignore

            t_import_end = _t.perf_counter()
            # Update last_section_time to track import duration, then log using perf logger
            self.perf_logger.last_section_time = t_import_start
            self.perf_logger.log_section("LiteLLM import")

            t_start = _t.perf_counter()
            logger.info("LLM API call started")

            response = completion(**completion_kwargs)

            if stream:
                underlying = handle_streaming_response(response)

                def _perf_wrapped_stream():
                    first = True
                    t_first = None
                    text_len = 0
                    tool_calls = 0
                    try:
                        for chunk in underlying:
                            if first:
                                first = False
                                t_first = _t.perf_counter()
                                # Update last_section_time to track time to first chunk, then log using perf logger
                                self.perf_logger.last_section_time = t_start
                                self.perf_logger.log_section("LLM API first chunk")
                            if chunk.get("type") == "text":
                                text = chunk.get("content") or ""
                                text_len += len(text)
                            elif chunk.get("type") == "tool_call":
                                tool_calls += 1
                            yield chunk
                    finally:
                        t_end = _t.perf_counter()
                        # Update last_section_time to track stream duration, then log using perf logger
                        self.perf_logger.last_section_time = t_start
                        self.perf_logger.log_section(
                            "LLM API stream completed",
                            extra_info={"text_len": text_len, "tool_calls": tool_calls},
                        )

                return _perf_wrapped_stream()
            else:
                result = handle_complete_response(response)
                t_end = _t.perf_counter()
                self.perf_logger.last_section_time = t_start
                self.perf_logger.log_section("LLM API call (non-stream)")
                return result

        except Exception as e:
            # Map LiteLLM/provider errors to concise, actionable messages.
            def _sanitize(secret: str) -> str:
                try:
                    # Redact API key-like tokens (e.g., sk-..., ,sk-...)
                    return re.sub(
                        r"[,]*\b[prsu]?k[-_][A-Za-z0-9]{8,}\b",
                        "<redacted>",
                        str(secret),
                    )
                except Exception:
                    return str(secret)

            def _friendly_message(exc: Exception) -> str:
                name = type(exc).__name__
                text = _sanitize(str(exc))
                # Import lazily to avoid hard dependency at import-time
                try:
                    from litellm.exceptions import (
                        APIConnectionError,
                        AuthenticationError,
                        InvalidRequestError,
                        NotFoundError,
                        PermissionDeniedError,
                        RateLimitError,
                        ServiceUnavailableError,
                        Timeout,
                    )
                except Exception:  # pragma: no cover - fallback if import shape changes
                    AuthenticationError = RateLimitError = ServiceUnavailableError = (
                        APIConnectionError
                    ) = Timeout = PermissionDeniedError = NotFoundError = (
                        InvalidRequestError
                    ) = tuple()  # type: ignore

                if (
                    isinstance(exc, AuthenticationError)
                    or "AuthenticationError" in name
                ):
                    return (
                        f"Authentication failed. Check your API key for provider '{self.default_provider}'. "
                        "Run 'whai --interactive-config' to update your configuration."
                    )
                # Check for "LLM Provider NOT provided" error - this happens when model name format is wrong
                if "llm provider not provided" in text.lower() or "provider not provided" in text.lower():
                    return (
                        f"Model '{self.model}' is not recognized for provider '{self.default_provider}'. "
                        "The model name may be invalid or incorrectly formatted. "
                        "Choose a valid model with --model or run 'whai --interactive-config' to pick one."
                    )
                if (
                    isinstance(exc, (NotFoundError, InvalidRequestError))
                    or "model" in text.lower()
                    and (
                        "not found" in text.lower()
                        or "does not exist" in text.lower()
                        or "unknown" in text.lower()
                    )
                ):
                    return (
                        f"Model '{self.model}' is invalid or unavailable for provider '{self.default_provider}'. "
                        "Choose a valid model with --model or run 'whai --interactive-config' to pick one."
                    )
                if (
                    isinstance(exc, PermissionDeniedError)
                    or "permission" in text.lower()
                ):
                    return (
                        f"Permission denied for model '{self.model}' with provider '{self.default_provider}'. "
                        "Verify access for your account or pick another model via 'whai --interactive-config'."
                    )
                if isinstance(exc, RateLimitError) or "rate limit" in text.lower():
                    return (
                        f"Rate limit reached for provider '{self.default_provider}'. "
                        "Try again later or switch model/provider."
                    )
                if isinstance(
                    exc, (APIConnectionError, ServiceUnavailableError, Timeout)
                ) or any(
                    k in text.lower()
                    for k in ["timeout", "temporarily unavailable", "connection"]
                ):
                    return (
                        f"Network or service error connecting to provider '{self.default_provider}'. "
                        "Check your connection or try again."
                    )
                # Default fallback
                return f"LLM API error with provider '{self.default_provider}' and model '{self.model}': {_sanitize(text)}"

            friendly = _friendly_message(e)
            raise RuntimeError(friendly)
