"""Pytest configuration for terma tests."""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def plain_mode_for_tests():
    """Force plain mode (no Rich styling) for all tests."""
    original = os.environ.get("TERMA_PLAIN")
    os.environ["TERMA_PLAIN"] = "1"
    yield
    if original is None:
        os.environ.pop("TERMA_PLAIN", None)
    else:
        os.environ["TERMA_PLAIN"] = original
