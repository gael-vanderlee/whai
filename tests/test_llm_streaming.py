from typing import Any

from whai.llm import LLMProvider


class _DeltaFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _DeltaToolCall:
    def __init__(self, call_id: str, name: str, arguments: str):
        self.id = call_id
        self.function = _DeltaFunction(name, arguments)


class _Delta:
    def __init__(self, content: str = None, tool_calls: list[Any] = None):
        self.content = content
        self.tool_calls = tool_calls or []


class _Choice:
    def __init__(self, delta):
        self.delta = delta


class _Chunk:
    def __init__(self, delta):
        self.choices = [_Choice(delta)]


def _make_provider() -> LLMProvider:
    # Minimal config for constructor; keys won't be used here
    config = {
        "llm": {
            "default_provider": "openai",
            "default_model": "gpt-5-mini",
        }
    }
    return LLMProvider(config=config)


def test_streaming_buffers_tool_call_until_complete_json():
    provider = _make_provider()

    # Build a simulated stream where arguments arrive in two chunks
    # First chunk: partial JSON (invalid)
    part1 = _Chunk(
        _Delta(tool_calls=[_DeltaToolCall("call_1", "execute_shell", '{\n  "comm')])
    )
    # Second chunk: remaining JSON (valid with command)
    part2 = _Chunk(
        _Delta(
            tool_calls=[_DeltaToolCall("call_1", "execute_shell", 'and": "echo hi"\n}')]
        )
    )

    stream = [part1, part2]

    emissions = list(provider._handle_streaming_response(stream))

    # Should emit exactly one tool_call, and it should contain the command
    tool_calls = [e for e in emissions if e.get("type") == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["name"] == "execute_shell"
    assert tool_calls[0]["arguments"].get("command") == "echo hi"


def test_streaming_preserves_tool_name_across_chunks():
    """Test that tool name and id are captured from first chunk even if both become None later."""
    provider = _make_provider()

    # Simulate REAL OpenAI streaming behavior:
    # First chunk has id and name, but no args
    part1 = _Chunk(_Delta(tool_calls=[_DeltaToolCall("call_1", "execute_shell", "")]))
    # Second chunk has BOTH id and name as None, only partial args
    part2 = _Chunk(_Delta(tool_calls=[_DeltaToolCall(None, None, '{"command":')]))
    # Third chunk completes args, BOTH id and name are None
    part3 = _Chunk(_Delta(tool_calls=[_DeltaToolCall(None, None, ' "pwd"}')]))

    stream = [part1, part2, part3]

    emissions = list(provider._handle_streaming_response(stream))

    tool_calls = [e for e in emissions if e.get("type") == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["id"] == "call_1"
    assert tool_calls[0]["name"] == "execute_shell"
    assert tool_calls[0]["arguments"]["command"] == "pwd"
