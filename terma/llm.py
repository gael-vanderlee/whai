"""LLM provider wrapper using LiteLLM."""

from typing import Any, Dict, Generator, List, Optional, Union

from terma.constants import DEFAULT_LLM_MODEL
from terma.logging_setup import get_logger

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
    from pathlib import Path

    context_note = (
        "You have access to the full terminal scrollback (commands and their output)."
        if is_deep_context
        else "You have access to recent command history only (no command output). "
        "You cannot see why commands failed without running them again."
    )

    # Read from defaults file
    defaults_dir = Path(__file__).parent.parent / "defaults"
    system_prompt_file = defaults_dir / "system_prompt.txt"

    if not system_prompt_file.exists():
        raise FileNotFoundError(
            f"System prompt template not found at {system_prompt_file}. "
            "This indicates a broken installation. Please reinstall terma."
        )

    template = system_prompt_file.read_text()
    logger.debug(
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
        self.model = model or config["llm"].get("default_model", DEFAULT_LLM_MODEL)

        # Validate model exists
        validate_model(self.model)

        # Only set temperature when explicitly provided; many models (e.g., gpt-5*)
        # do not support it and should omit it entirely by default.
        self.temperature = temperature

        # Set API keys for LiteLLM
        self._configure_api_keys()
        logger.debug(
            "LLMProvider initialized: provider=%s model=%s temp=%s",
            self.default_provider,
            self.model,
            self.temperature if self.temperature is not None else "default",
        )

    def _configure_api_keys(self):
        """Configure API keys from config for LiteLLM."""
        llm_config = self.config.get("llm", {})

        # Set OpenAI key if present
        if "openai" in llm_config and "api_key" in llm_config["openai"]:
            import os

            os.environ["OPENAI_API_KEY"] = llm_config["openai"]["api_key"]

        # Set Anthropic key if present
        if "anthropic" in llm_config and "api_key" in llm_config["anthropic"]:
            import os

            os.environ["ANTHROPIC_API_KEY"] = llm_config["anthropic"]["api_key"]

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

            # Only include temperature if explicitly set AND model supports it
            if self.temperature is not None and not self.model.startswith("gpt-5"):
                completion_kwargs["temperature"] = self.temperature

            if tools:  # Only add tools if list is not empty
                completion_kwargs["tools"] = tools

            # Pass through tool_choice only when provided to avoid confusing providers
            if tool_choice is not None:
                completion_kwargs["tool_choice"] = tool_choice

            logger.debug(
                "Sending message to LLM: stream=%s tools_enabled=%s tool_count=%d temp=%s",
                stream,
                bool(tools),
                len(tools) if tools else 0,
                self.temperature if self.temperature is not None else "default",
                extra={"category": "api"},
            )
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
            logger.debug(
                "LiteLLM import completed in %.3f ms",
                (t_import_end - t_import_start) * 1000,
                extra={"category": "perf"},
            )

            t_start = _t.perf_counter()
            logger.debug("LLM API call started", extra={"category": "perf"})

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
                                logger.debug(
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
                        logger.debug(
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
                logger.debug(
                    "LLM API call (non-stream) completed in %.3f ms",
                    (t_end - t_start) * 1000,
                    extra={"category": "perf"},
                )
                return result

        except Exception as e:
            # Re-raise with more context
            raise RuntimeError(f"LLM API error: {e}")

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
                logger.debug(
                    "Streaming tool_calls chunk: count=%d",
                    len(delta.tool_calls),
                    extra={"category": "api"},
                )
                for tool_call in delta.tool_calls:
                    if not hasattr(tool_call, "function"):
                        continue

                    import json

                    raw_call_id = getattr(tool_call, "id", "unknown")
                    name = tool_call.function.name
                    arg_chunk = tool_call.function.arguments or ""

                    logger.debug(
                        "Processing tool_call chunk: id=%s (type=%s), name=%s (type=%s), args_len=%d",
                        raw_call_id,
                        type(raw_call_id).__name__,
                        name,
                        type(name).__name__,
                        len(arg_chunk) if arg_chunk else 0,
                        extra={"category": "api"},
                    )

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
                        logger.debug(
                            "Accumulated args for id=%s, total_len=%d",
                            call_id,
                            len(partial_tool_calls[call_id]["args"]),
                            extra={"category": "api"},
                        )

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
