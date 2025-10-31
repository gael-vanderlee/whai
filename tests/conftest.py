"""Pytest configuration for whai tests."""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def plain_mode_for_tests():
    """Force plain mode (no Rich styling) for all tests."""
    original = os.environ.get("WHAI_PLAIN")
    os.environ["WHAI_PLAIN"] = "1"
    yield
    if original is None:
        os.environ.pop("WHAI_PLAIN", None)
    else:
        os.environ["WHAI_PLAIN"] = original
