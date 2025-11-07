"""LLM provider wrapper using LiteLLM."""

import json
import os
import re
from typing import Any, Dict, Generator, List, Union

from whai.configuration.user_config import WhaiConfig
from whai.constants import DEFAULT_PROVIDER, get_default_model_for_provider
from whai.llm.streaming import handle_complete_response, handle_streaming_response
from whai.logging_setup import get_logger

logger = get_logger(__name__)

def validate_model(model_name: str) -> None:
    """
    Log the model name for debugging purposes.

    Note: LiteLLM doesn't provide reliable upfront model validation.
    Invalid models will be caught when the actual API call is made.

    Args:
        model_name: The model name to use.
    """
    logger.debug("Using model: %s", model_name)
    # LiteLLM is very lenient with model names and will attempt to route
    # any model name to an appropriate provider. Invalid models will be
    # caught when making the actual API call, with a clear error message.


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
        self, config: WhaiConfig, model: str = None, temperature: float = None
    ):
        """
        Initialize the LLM provider.

        Args:
            config: WhaiConfig instance containing LLM settings.
            model: Optional model override (uses config default if not provided).
            temperature: Optional temperature override (if None, temperature is not set).
        """
        self.config = config
        self.default_provider = config.llm.default_provider
        # Resolve model: CLI override > provider-level default > built-in fallback
        provider_cfg = config.llm.get_provider(self.default_provider)
        provider_default_model = provider_cfg.default_model if provider_cfg else None
        fallback_model = get_default_model_for_provider(
            self.default_provider or DEFAULT_PROVIDER
        )
        raw_model = model or provider_default_model or fallback_model

        # Sanitize model name for provider-specific formatting (if needed)
        if provider_cfg:
            self.model = provider_cfg.sanitize_model_name(raw_model)
        else:
            # Fallback if provider config is missing (should not happen in normal usage)
            self.model = raw_model

        # Store custom API base for providers that need it
        self.api_base = provider_cfg.api_base if provider_cfg else None

        # Validate model exists
        validate_model(self.model)

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
            if self.temperature is not None and not self.model.startswith("gpt-5"):
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
            logger.info(
                "LiteLLM import completed in %.3f ms",
                (t_import_end - t_import_start) * 1000,
                extra={"category": "perf"},
            )

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
                                logger.info(
                                    "LLM API first chunk in %.3f ms",
                                    (t_first - t_start) * 1000,
                                    extra={"category": "perf"},
                                )
                            if chunk.get("type") == "text":
                                text = chunk.get("content") or ""
                                text_len += len(text)
                            elif chunk.get("type") == "tool_call":
                                tool_calls += 1
                            yield chunk
                    finally:
                        t_end = _t.perf_counter()
                        logger.info(
                            "LLM API stream completed in %.3f ms (text_len=%d, tool_calls=%d)",
                            (t_end - t_start) * 1000,
                            text_len,
                            tool_calls,
                            extra={"category": "perf"},
                        )

                return _perf_wrapped_stream()
            else:
                result = handle_complete_response(response)
                t_end = _t.perf_counter()
                logger.info(
                    "LLM API call (non-stream) completed in %.3f ms",
                    (t_end - t_start) * 1000,
                    extra={"category": "perf"},
                )
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
                base = f"provider={self.default_provider} model={self.model}"
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
                        "LLM API error: Authentication failed. "
                        f"{base}. Check your API key. "
                        "Run 'whai --interactive-config' to update your configuration."
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
                        "LLM API error: Model is invalid or unavailable. "
                        f"{base}. Choose a valid model with --model or run 'whai --interactive-config' to pick one."
                    )
                if (
                    isinstance(exc, PermissionDeniedError)
                    or "permission" in text.lower()
                ):
                    return (
                        "LLM API error: Permission denied for this model with the current API key. "
                        f"{base}. Verify access for your account or pick another model via 'whai --interactive-config'."
                    )
                if isinstance(exc, RateLimitError) or "rate limit" in text.lower():
                    return (
                        "LLM API error: Rate limit reached. "
                        f"{base}. Try again later or switch model/provider."
                    )
                if isinstance(
                    exc, (APIConnectionError, ServiceUnavailableError, Timeout)
                ) or any(
                    k in text.lower()
                    for k in ["timeout", "temporarily unavailable", "connection"]
                ):
                    return (
                        "LLM API error: Network or service error talking to the provider. "
                        f"{base}. Check your connection or try again."
                    )
                # Default fallback
                return f"LLM API error: {base}. {_sanitize(text)}"

            friendly = _friendly_message(e)
            raise RuntimeError(friendly)
