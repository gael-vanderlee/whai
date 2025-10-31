"""Mock litellm module for subprocess-based E2E tests.

Placed under tests/mocks and injected via PYTHONPATH from tests to avoid
network calls during `python -m terma` subprocess runs. This file is only
used in tests and never shipped with the package.
"""

from unittest.mock import MagicMock
import os


def completion(**kwargs):  # pragma: no cover - exercised via subprocess
    """Return a deterministic mock completion response.

    Behavior is controlled by environment variables:
    - TERMA_MOCK_TOOLCALL=1: emit a single execute_shell tool call.
    - otherwise: emit text-only streaming response.
    """
    stream = kwargs.get("stream", True)

    if os.getenv("TERMA_MOCK_TOOLCALL") == "1":
        # Emit a tool call to execute an echo
        import json as _json

        tool = MagicMock()
        tool.id = "call_e2e_1"
        tool.function = MagicMock()
        tool.function.name = "execute_shell"
        tool.function.arguments = _json.dumps({"command": 'echo "e2e-subprocess"'})

        if stream:
            chunks = [
                MagicMock(
                    choices=[
                        MagicMock(
                            delta=MagicMock(content="Let me run that.", tool_calls=None)
                        )
                    ]
                ),
                MagicMock(
                    choices=[MagicMock(delta=MagicMock(content=None, tool_calls=[tool]))]
                ),
            ]
            return iter(chunks)
        else:
            resp = MagicMock()
            resp.choices = [MagicMock()]
            resp.choices[0].message = MagicMock()
            resp.choices[0].message.content = "Let me run that."
            resp.choices[0].message.tool_calls = [tool]
            return resp

    # Default: text-only reply
    if stream:
        chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="This ", tool_calls=None))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content="is a ", tool_calls=None))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content="subprocess test.", tool_calls=None))]),
        ]
        return iter(chunks)
    else:
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message = MagicMock()
        resp.choices[0].message.content = "This is a subprocess test."
        resp.choices[0].message.tool_calls = None
        return resp


