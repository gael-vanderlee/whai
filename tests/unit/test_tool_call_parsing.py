"""Behavioral tests for tool call parsing and response handling.

Tests parse_tool_calls, handle_streaming_response, and handle_complete_response
as black boxes: provide inputs, assert outputs.
"""

import json
from unittest.mock import MagicMock

from whai.interaction.tool_calls import parse_tool_calls
from whai.llm.streaming import handle_complete_response, handle_streaming_response


# ---------- parse_tool_calls ----------


def test_parse_single_tool_call():
    chunks = [
        {"type": "tool_call", "id": "c1", "name": "execute_shell", "arguments": {"command": "ls"}},
    ]
    result = parse_tool_calls(chunks)
    assert len(result) == 1
    assert result[0] == {"id": "c1", "name": "execute_shell", "arguments": {"command": "ls"}}


def test_parse_multiple_tool_calls():
    chunks = [
        {"type": "text", "content": "Running commands..."},
        {"type": "tool_call", "id": "c1", "name": "execute_shell", "arguments": {"command": "ls"}},
        {"type": "tool_call", "id": "c2", "name": "execute_shell", "arguments": {"command": "pwd"}},
    ]
    result = parse_tool_calls(chunks)
    assert len(result) == 2
    assert result[0]["id"] == "c1"
    assert result[1]["id"] == "c2"


def test_parse_no_tool_calls():
    chunks = [
        {"type": "text", "content": "Just text."},
    ]
    assert parse_tool_calls(chunks) == []


def test_parse_empty_input():
    assert parse_tool_calls([]) == []


def test_parse_missing_arguments_defaults_to_empty_dict():
    chunks = [{"type": "tool_call", "id": "c1", "name": "foo"}]
    result = parse_tool_calls(chunks)
    assert result[0]["arguments"] == {}


def test_parse_skips_non_tool_call_types():
    chunks = [
        {"type": "text", "content": "hello"},
        {"type": "unknown", "data": "abc"},
        {"type": "tool_call", "id": "c1", "name": "execute_shell", "arguments": {"command": "ls"}},
    ]
    result = parse_tool_calls(chunks)
    assert len(result) == 1


# ---------- handle_streaming_response ----------


def _make_stream_chunk(content=None, tool_calls=None):
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = tool_calls
    chunk = MagicMock()
    chunk.choices = [MagicMock(delta=delta)]
    return chunk


def _make_tool_call_delta(call_id, name, arguments):
    tc = MagicMock()
    tc.id = call_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


def test_streaming_text_only():
    stream = [
        _make_stream_chunk(content="Hello "),
        _make_stream_chunk(content="world"),
    ]
    chunks = list(handle_streaming_response(iter(stream)))
    assert len(chunks) == 2
    assert all(c["type"] == "text" for c in chunks)
    assert chunks[0]["content"] == "Hello "
    assert chunks[1]["content"] == "world"


def test_streaming_tool_call_single_chunk():
    """Tool call where id, name, and full arguments arrive in one chunk."""
    tc = _make_tool_call_delta("c1", "execute_shell", json.dumps({"command": "ls"}))
    stream = [_make_stream_chunk(tool_calls=[tc])]
    chunks = list(handle_streaming_response(iter(stream)))
    tool_calls = [c for c in chunks if c["type"] == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["name"] == "execute_shell"
    assert tool_calls[0]["arguments"] == {"command": "ls"}


def test_streaming_tool_call_split_arguments():
    """Arguments arrive across multiple chunks (realistic OpenAI behavior)."""
    tc1 = _make_tool_call_delta("c1", "execute_shell", '{"comma')
    tc2 = _make_tool_call_delta(None, None, 'nd": "ls"}')
    stream = [
        _make_stream_chunk(tool_calls=[tc1]),
        _make_stream_chunk(tool_calls=[tc2]),
    ]
    chunks = list(handle_streaming_response(iter(stream)))
    tool_calls = [c for c in chunks if c["type"] == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["arguments"] == {"command": "ls"}


def test_streaming_text_then_tool_call():
    tc = _make_tool_call_delta("c1", "execute_shell", json.dumps({"command": "ls"}))
    stream = [
        _make_stream_chunk(content="Let me run that."),
        _make_stream_chunk(tool_calls=[tc]),
    ]
    chunks = list(handle_streaming_response(iter(stream)))
    assert chunks[0]["type"] == "text"
    assert chunks[1]["type"] == "tool_call"


def test_streaming_empty_arguments():
    tc = _make_tool_call_delta("c1", "execute_shell", "")
    stream = [_make_stream_chunk(tool_calls=[tc])]
    chunks = list(handle_streaming_response(iter(stream)))
    tool_calls = [c for c in chunks if c["type"] == "tool_call"]
    assert len(tool_calls) == 0


def test_streaming_no_function_attribute_skipped():
    tc = MagicMock(spec=[])  # no 'function' attribute
    stream = [_make_stream_chunk(tool_calls=[tc])]
    chunks = list(handle_streaming_response(iter(stream)))
    assert len(chunks) == 0


# ---------- handle_complete_response ----------


def _make_complete_response(content="", tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    resp = MagicMock()
    resp.choices = [MagicMock(message=msg)]
    return resp


def _make_tool_call_obj(call_id, name, arguments_json):
    tc = MagicMock()
    tc.id = call_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments_json
    return tc


def test_complete_text_only():
    resp = _make_complete_response(content="Hello world")
    result = handle_complete_response(resp)
    assert result["content"] == "Hello world"
    assert result["tool_calls"] == []


def test_complete_with_tool_call():
    tc = _make_tool_call_obj("c1", "execute_shell", json.dumps({"command": "ls"}))
    resp = _make_complete_response(content="Running:", tool_calls=[tc])
    result = handle_complete_response(resp)
    assert result["content"] == "Running:"
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0] == {
        "id": "c1",
        "name": "execute_shell",
        "arguments": {"command": "ls"},
    }


def test_complete_malformed_json_skips_tool_call():
    tc = _make_tool_call_obj("c1", "execute_shell", "{bad json}")
    resp = _make_complete_response(content="Running:", tool_calls=[tc])
    result = handle_complete_response(resp)
    assert result["tool_calls"] == []


def test_complete_multiple_tool_calls():
    tc1 = _make_tool_call_obj("c1", "execute_shell", json.dumps({"command": "ls"}))
    tc2 = _make_tool_call_obj("c2", "execute_shell", json.dumps({"command": "pwd"}))
    resp = _make_complete_response(tool_calls=[tc1, tc2])
    result = handle_complete_response(resp)
    assert len(result["tool_calls"]) == 2


def test_complete_none_content():
    resp = _make_complete_response(content=None)
    result = handle_complete_response(resp)
    assert result["content"] == ""


def test_complete_empty_arguments():
    tc = _make_tool_call_obj("c1", "execute_shell", "")
    resp = _make_complete_response(tool_calls=[tc])
    result = handle_complete_response(resp)
    assert result["tool_calls"] == [{"id": "c1", "name": "execute_shell", "arguments": {}}]
