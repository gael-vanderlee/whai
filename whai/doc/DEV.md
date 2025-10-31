# terma Dev Cheatsheet

Compact commands for Windows, macOS, and Linux.

## uv venv

### Install (editable, with dev deps)
```bash
uv venv
uv pip install -e ".[dev]"
```

### Add packages
- Edit `pyproject.toml` and add the dependency under `[project]` or `[project.optional-dependencies].dev`, then:
```bash
uv pip install -e ".[dev]"
```

### Delete and recreate venv
```bash
# macOS/Linux
rm -rf .venv && uv venv && uv pip install -e ".[dev]"

# Windows PowerShell
Remove-Item .venv -Recurse -Force; uv venv; uv pip install -e ".[dev]"

# Windows CMD
rmdir /s /q .venv & uv venv & uv pip install -e ".[dev]"
```

### Activate venv
```bash
# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows CMD
.venv\Scripts\activate.bat
```

### Run scripts/CLI via uv
```bash
# Run terma
uv run terma "your question"

# Run a module/script
uv run python -m terma "your question"
uv run python path/to/script.py
```

## Tests
```bash
uv run pytest
# Optional
uv run pytest -v
uv run pytest --cov=terma --cov-report=term-missing
```

### Subprocess CLI E2E tests
The test suite includes end-to-end tests that invoke `python -m terma` in a subprocess. These tests avoid network calls by placing a mock `litellm` module under `tests/mocks` and prepending that directory to `PYTHONPATH` inside the test harness. You can force a tool-call flow by setting `TERMA_MOCK_TOOLCALL=1` in the subprocess environment. No test-related code lives in the `terma/` package.

## Flags

### Logging and output
```bash
# Default logging level is ERROR
uv run terma "test query"

# Increase verbosity to INFO (timings and key stages)
uv run terma "test query" -v INFO

# Full debug (payloads, prompts, detailed traces)
uv run terma "test query" -v DEBUG

# Plain output (reduced styling)
TERMA_PLAIN=1 uv run terma "test query"
```

### CLI flags
```bash
uv run terma "explain git rebase" --no-context
uv run terma "why did my command fail?" --role debug
uv run terma "list files" --dry-run
```
