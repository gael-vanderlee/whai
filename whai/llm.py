"""LLM provider wrapper using LiteLLM."""

import json
from importlib.resources import files
from typing import Any, Dict, Generator, List, Optional, Union

from whai.constants import DEFAULT_LLM_MODEL
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


def get_base_system_prompt(is_deep_context: bool) -> str:
    """
    Get the base system prompt that is prepended to all conversations.

    Args:
        is_deep_context: Whether we have deep context (tmux) or shallow (history).

    Returns:
        The base system prompt string.

    Raises:
        FileNotFoundError: If the system prompt template file doesn't exist.
    """
    import os
    import platform
    from pathlib import Path

    # Build context note with system information
    context_parts = []

    # Terminal history context
    if is_deep_context:
        context_parts.append(
            "You will be given the recent terminal scrollback (commands and their output) along with the user message."
        )
    else:
        context_parts.append(
            "You will be given the recent command history of the user (commands only, not their outputs). This also means that after you finish your message, you will not be able to see it once the user responds. So don't finish with a question or suggestions that would require the context of the your current response once the user responds."
        )

    # System information
    system_info = []

    # Operating system
    os_name = platform.system()
    os_release = platform.release()
    system_info.append(f"OS: {os_name} {os_release}")

    # Shell (from environment or detect)
    shell_path = os.environ.get("SHELL", "")
    if shell_path:
        shell_name = Path(shell_path).name
        system_info.append(f"Shell: {shell_name}")
    elif os.name == "nt":
        # Windows detection
        if "PSModulePath" in os.environ:
            system_info.append("Shell: PowerShell")
        else:
            system_info.append("Shell: cmd.exe")

    # Current working directory
    try:
        cwd = os.getcwd()
        system_info.append(f"CWD: {cwd}")
    except Exception:
        pass

    if system_info:
        context_parts.append("System: " + " | ".join(system_info))

    context_note = " ".join(context_parts)

    # Read from packaged defaults file
    system_prompt_file = files("whai").joinpath("defaults", "system_prompt.txt")

    if not system_prompt_file.exists():
        raise FileNotFoundError(
            f"System prompt template not found at {system_prompt_file}. "
            "This indicates a broken installation. Please reinstall whai."
        )

    template = system_prompt_file.read_text()
    logger.info(
        "Loaded system prompt template from %s",
        system_prompt_file,
        extra={"category": "perf"},
    )
    return template.format(context_note=context_note)


class LLMProvider:
    """
    Wrapper for LiteLLM to provide a consistent interface for LLM interactions.
    """

    def __init__(
        self, config: Dict[str, Any], model: str = None, temperature: float = None
    ):
        """
        Initialize the LLM provider.

        Args:
            config: Configuration dictionary containing LLM settings.
            model: Optional model override (uses config default if not provided).
            temperature: Optional temperature override (if None, temperature is not set).
        """
        self.config = config
        self.default_provider = config["llm"]["default_provider"]
        # Resolve model: CLI override > provider-level default > built-in fallback
        provider_cfg = config.get("llm", {}).get(self.default_provider, {})
        provider_default_model = provider_cfg.get("default_model")
        self.model = model or provider_default_model or DEFAULT_LLM_MODEL

        # Store custom API base for providers that need it
        self.api_base = provider_cfg.get("api_base")

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
        import os

        llm_config = self.config.get("llm", {})

        # Set OpenAI key if present
        if "openai" in llm_config and "api_key" in llm_config["openai"]:
            os.environ["OPENAI_API_KEY"] = llm_config["openai"]["api_key"]

        # Set Anthropic key if present
        if "anthropic" in llm_config and "api_key" in llm_config["anthropic"]:
            os.environ["ANTHROPIC_API_KEY"] = llm_config["anthropic"]["api_key"]

        # Set Azure OpenAI configuration if present
        if "azure_openai" in llm_config:
            azure_config = llm_config["azure_openai"]
            if "api_key" in azure_config:
                os.environ["AZURE_API_KEY"] = azure_config["api_key"]
            if "api_base" in azure_config:
                os.environ["AZURE_API_BASE"] = azure_config["api_base"]
            if "api_version" in azure_config:
                os.environ["AZURE_API_VERSION"] = azure_config["api_version"]

        # Set Ollama base URL if present
        if "ollama" in llm_config and "api_base" in llm_config["ollama"]:
            os.environ["OLLAMA_API_BASE"] = llm_config["ollama"]["api_base"]

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
                            logger.debug("%s:\n%s", heading, content)
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
                underlying = self._handle_streaming_response(response)

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
                result = self._handle_complete_response(response)
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
                    import re

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

    def _handle_streaming_response(
        self, response
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Handle streaming response from LiteLLM.

        Args:
            response: Streaming response from litellm.completion

        Yields:
            Parsed response chunks.
        """
        # Buffer partial tool call data across chunks by id
        # Stores: {call_id: {"name": str, "args": str}}
        partial_tool_calls: Dict[str, Dict[str, str]] = {}
        # Track the last known call_id to handle None ids in subsequent chunks
        last_call_id: Optional[str] = None

        for chunk in response:
            delta = chunk.choices[0].delta

            # Check for text content
            if hasattr(delta, "content") and delta.content:
                # logger.debug(
                #     "Streaming text chunk: len=%d",
                #     len(delta.content),
                #     extra={"category": "api"},
                # )
                yield {"type": "text", "content": delta.content}

            # Check for tool calls
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                # logger.debug(
                #     "Streaming tool_calls chunk: count=%d",
                #     len(delta.tool_calls),
                #     extra={"category": "api"},
                # )
                for tool_call in delta.tool_calls:
                    if not hasattr(tool_call, "function"):
                        continue

                    import json

                    raw_call_id = getattr(tool_call, "id", "unknown")
                    name = tool_call.function.name
                    arg_chunk = tool_call.function.arguments or ""

                    # logger.debug(
                    #     "Processing tool_call chunk: id=%s (type=%s), name=%s (type=%s), args_len=%d",
                    #     raw_call_id,
                    #     type(raw_call_id).__name__,
                    #     name,
                    #     type(name).__name__,
                    #     len(arg_chunk) if arg_chunk else 0,
                    #     extra={"category": "api"},
                    # )

                    # Handle None ids by using the last known call_id
                    # OpenAI sends id and name in first chunk, then None for both in subsequent chunks
                    if raw_call_id is not None:
                        call_id = raw_call_id
                        last_call_id = call_id
                    elif last_call_id is not None:
                        call_id = last_call_id
                    else:
                        # No known call_id yet, skip this chunk
                        logger.warning(
                            "Received tool_call chunk with no id and no previous id"
                        )
                        continue

                    # Initialize buffer for this call_id if needed
                    if call_id not in partial_tool_calls:
                        partial_tool_calls[call_id] = {"name": None, "args": ""}
                        logger.debug(
                            "Initialized buffer for tool call id=%s",
                            call_id,
                            extra={"category": "api"},
                        )

                    # Store name if present (usually only in first chunk)
                    if name:
                        partial_tool_calls[call_id]["name"] = name
                        logger.debug(
                            "Stored tool name=%s for id=%s",
                            name,
                            call_id,
                            extra={"category": "api"},
                        )

                    # Accumulate arguments
                    if arg_chunk:
                        partial_tool_calls[call_id]["args"] += arg_chunk
                        # logger.debug(
                        #     "Accumulated args for id=%s, total_len=%d",
                        #     call_id,
                        #     len(partial_tool_calls[call_id]["args"]),
                        #     extra={"category": "api"},
                        # )

                    # Try to parse when we have arguments
                    raw_args = partial_tool_calls[call_id]["args"]
                    if not raw_args:
                        continue

                    try:
                        parsed = json.loads(raw_args)
                    except json.JSONDecodeError:
                        # Still incomplete, wait for more chunks
                        continue

                    # Only emit once we have a non-empty command and a name
                    stored_name = partial_tool_calls[call_id]["name"]
                    if (
                        isinstance(parsed, dict)
                        and parsed.get("command")
                        and stored_name
                    ):
                        yield {
                            "type": "tool_call",
                            "id": call_id,
                            "name": stored_name,
                            "arguments": parsed,
                        }
                        logger.debug(
                            "Emitted tool_call from stream: name=%s id=%s",
                            stored_name,
                            call_id,
                            extra={"category": "api"},
                        )
                        # Prevent duplicate emits for same id
                        partial_tool_calls.pop(call_id, None)

    def _handle_complete_response(self, response) -> Dict[str, Any]:
        """
        Handle complete (non-streaming) response from LiteLLM.

        Args:
            response: Complete response from litellm.completion

        Returns:
            Parsed response dict.
        """
        choice = response.choices[0]
        message = choice.message

        result = {"content": message.content or "", "tool_calls": []}

        # Extract tool calls if present
        if hasattr(message, "tool_calls") and message.tool_calls:
            import json

            for tool_call in message.tool_calls:
                # Parse tool arguments defensively; some providers may return
                # incomplete or malformed JSON strings.
                try:
                    raw_args = tool_call.function.arguments or "{}"
                    parsed_args = json.loads(raw_args)
                except Exception as e:
                    logger.warning(
                        "Failed to parse tool arguments for %s: %s; raw=%r",
                        getattr(tool_call.function, "name", "<unknown>"),
                        e,
                        getattr(tool_call.function, "arguments", None),
                    )
                    # Skip this tool call rather than crashing the whole response
                    continue

                result["tool_calls"].append(
                    {
                        "id": tool_call.id,
                        "name": tool_call.function.name,
                        "arguments": parsed_args,
                    }
                )

        return result
