from terma.main import _extract_inline_overrides


def test_extract_inline_overrides_parses_all_supported_flags():
    tokens = [
        "find",
        "big",
        "files",
        "--no-context",
        "--model",
        "gpt-5",
        "--temperature",
        "0.2",
        "--role",
        "debug",
        "--timeout",
        "45",
        "here",
    ]

    cleaned, overrides = _extract_inline_overrides(
        tokens,
        role="assistant",
        no_context=False,
        model=None,
        temperature=None,
        timeout=60,
    )

    assert cleaned == ["find", "big", "files", "here"]
    assert overrides["no_context"] is True
    assert overrides["model"] == "gpt-5"
    assert overrides["temperature"] == 0.2
    assert overrides["role"] == "debug"
    assert overrides["timeout"] == 45


def test_extract_inline_overrides_short_flags_and_defaults():
    tokens = [
        "what",
        "now",
        "-m",
        "gpt-5-mini",
        "-t",
        "0.7",
        "-r",
        "assistant",
    ]

    cleaned, overrides = _extract_inline_overrides(
        tokens,
        role=None,
        no_context=False,
        model=None,
        temperature=None,
        timeout=60,
    )

    assert cleaned == ["what", "now"]
    assert overrides["model"] == "gpt-5-mini"
    assert overrides["temperature"] == 0.7
    assert overrides["role"] == "assistant"
    assert overrides["no_context"] is False
    assert overrides["timeout"] == 60
