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

## Flags

### Environment flags
```bash
# macOS/Linux
TERMA_DEBUG=1 TERMA_PLAIN=1 uv run terma "test query"

# Windows PowerShell
$env:TERMA_DEBUG=1; $env:TERMA_PLAIN=1; uv run terma "test query"

# Windows CMD
set TERMA_DEBUG=1 & set TERMA_PLAIN=1 & uv run terma "test query"
```

### CLI flags
```bash
uv run terma "explain git rebase" --no-context
uv run terma "why did my command fail?" --role debug
uv run terma "list files" --dry-run
```
