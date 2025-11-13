"""Nox sessions for testing across multiple Python versions."""

import nox

nox.options.sessions = ["tests"]
PYTHON_VERSIONS = ["3.10", "3.11", "3.12", "3.13", "3.14"]
# Use uv for all sessions
nox.options.default_venv_backend = "uv"
# Don't reuse virtual environments - create fresh ones each time
nox.options.reuse_venv = "no"


@nox.session(python=PYTHON_VERSIONS)
def tests(session):
    """Run the test suite against multiple Python versions."""
    # Use uv to install dependencies
    session.run("uv", "sync", "--active", external=True)

    # Run tests
    session.run("pytest", "tests/", "-v")


@nox.session(python=PYTHON_VERSIONS)
def lint(session):
    """Run linters across Python versions."""
    session.install("ruff")
    session.run("ruff", "check", "whai/")
