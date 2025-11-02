# whai Dev Cheatsheet

Compact commands for Windows, macOS, and Linux.

## uv venv

### Install (editable, with dev deps)
```bash
uv venv
uv sync
```

### Add packages
```bash
uv add package
```
or 
```bash
uv add --dev package
```

### Delete and recreate venv
```bash
# macOS/Linux
rm -rf .venv && uv venv && uv sync

# Windows PowerShell
Remove-Item .venv -Recurse -Force; uv venv; uv sync

# Windows CMD
rmdir /s /q .venv & uv venv & uv sync
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
# Run whai
uv run whai "your question"

# Run a module/script
uv run python -m whai "your question"
uv run python path/to/script.py
```

## Tests

### Quick test run (current Python version)
```bash
uv run pytest
# Optional
uv run pytest -v
uv run pytest --cov=whai --cov-report=term-missing
```

### Testing across multiple Python versions (recommended)

Use `nox` to test against Python 3.8, 3.9, 3.10, 3.11, 3.12, and 3.13:
First time setup:
```bash
# One-time setup: Install Python versions with uv
uv python install 3.10 3.11 3.12 3.13

# Install nox
uv tool install nox[uv]
```

Run the tests
```bash
nox
```

Other useful commands
```bash
# Test specific Python version
nox -s tests-3.11

# Run linting across all versions
nox -s lint

# List all available sessions
nox -l
```

## Publish to TestPyPI, verify, then publish to PyPI

The following commands work on Windows PowerShell. They bump the version, build artifacts, publish to TestPyPI, verify in a clean venv, then publish to PyPI.

### 1) Bump version

- Edit `pyproject.toml` and change `[project] version = "..."`, or use:

```powershell
# Options: major | minor | patch | stable | alpha | beta | rc | post | dev
uv version --bump patch
```

### 2) Build artifacts

```powershell
# Clean previous builds to avoid PyPI errors about duplicate files
Remove-Item -Recurse .\dist
uv build
```

### 3) Publish to TestPyPI

```powershell
$env:UV_PUBLISH_TOKEN = "pypi-XXXXXXXXXXXXXXXX"  # TestPyPI token
uv publish --publish-url https://test.pypi.org/legacy/
```

### 4) Verify the TestPyPI upload in a clean venv

```powershell
# Create a temp venv for verification
uv venv .venv_testpypi

# Read current version from pyproject.toml without editing commands for each release
$ver = uv run --no-project -- python -c "import tomllib,sys;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
$ver = $ver.Trim()
echo $ver

# Check if version is available on TestPyPI (before attempting install)
# Note: It could take 2-5 minutes for TestPyPI to index after upload
uv run --no-project -- pip index versions whai --index-url https://test.pypi.org/simple/

# Actiavte the venv and install
.\.venv_testpypi\Scripts\activate  
uv pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple "whai==$ver" --index-strategy unsafe-best-match

# Smoke tests (module and console script)
python -c "import whai; print('import ok')"
python -m whai --help

# Test the installed console script directly (crucial for CLI verification)
.\.venv_testpypi\Scripts\whai --help
.\.venv_testpypi\Scripts\whai --version

# Clean up
Remove-Item -Recurse .\dist
Remove-Item -Recurse .\.venv_testpypi
```

### 5) Publish to PyPI

```powershell
# Bump again if needed (e.g., from 0.1.1 -> 0.1.2), then rebuild
uv version --bump patch

# Clean previous builds to avoid PyPI errors about duplicate files
Remove-Item -Recurse .\dist
uv build

# Publish to PyPI (regular repository)
$env:UV_PUBLISH_TOKEN = "pypi-YYYYYYYYYYYYYYYY"  # PyPI token
uv publish
```

Notes:
- Keep `[project.scripts] whai = "whai.cli.main:app"` so the installed command remains `whai`.
- The `--index-strategy unsafe-best-match` flag is required when the package name exists on both TestPyPI and PyPI but the requested version is only on TestPyPI.
- Always test from outside the repo root or use the console script; running `python -m whai` from the repo can import local sources instead of the installed wheel.

### Subprocess CLI E2E tests
The test suite includes end-to-end tests that invoke `python -m whai` in a subprocess. These tests avoid network calls by placing a mock `litellm` module under `tests/mocks` and prepending that directory to `PYTHONPATH` inside the test harness. You can force a tool-call flow by setting `WHAI_MOCK_TOOLCALL=1` in the subprocess environment. No test-related code lives in the `whai/` package.

## Flags

### Logging and output
```bash
# Default logging level is ERROR
uv run whai "test query"

# Increase verbosity to INFO (timings and key stages)
uv run whai "test query" -v INFO

# Full debug (payloads, prompts, detailed traces)
uv run whai "test query" -v DEBUG

# Plain output (reduced styling)
WHAI_PLAIN=1 uv run whai "test query"
```

### CLI flags
```bash
uv run whai "explain git rebase" --no-context
uv run whai "why did my command fail?" --role debug
```
