# terma Development Guide

This guide covers everything you need to develop, test, and contribute to terma on Windows, macOS, and Linux.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Configuration](#configuration)
- [Running the Project](#running-the-project)
- [Testing](#testing)
- [Development Workflow](#development-workflow)
- [Troubleshooting](#troubleshooting)
- [Additional Tips](#additional-tips)

## Prerequisites

- **Python 3.10 or higher**
- **uv** - Fast Python package installer and resolver
  - Install on Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
  - Install on macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - See https://github.com/astral-sh/uv for more options
- **Git** for cloning the repository

## Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/terma.git
cd terma
```

### 2. Create Virtual Environment with uv

```bash
# Create a virtual environment in .venv directory
uv venv
```

### 3. Install Dependencies

```bash
# Install the project in editable mode with dev dependencies
uv pip install -e ".[dev]"
```

This installs:
- The `terma` package in editable mode (changes reflect immediately)
- All runtime dependencies (litellm, typer, pyyaml)
- Development dependencies (pytest, pytest-mock, pytest-cov)

### 4. Activate the Virtual Environment

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
.venv\Scripts\activate.bat
```

**macOS/Linux:**
```bash
source .venv/bin/activate
```

After activation, you should see `(.venv)` in your terminal prompt.

## Configuration

### Config File Location

terma stores its configuration in:

- **Windows**: `%APPDATA%\terma\config.toml`
  - Usually: `C:\Users\YourName\AppData\Roaming\terma\config.toml`
  - Quick access: Type `%APPDATA%\terma` in Windows Explorer
- **macOS/Linux**: `~/.config/terma/config.toml`

### First Run Setup

When you run terma for the first time, it will automatically:
1. Create the config directory
2. Copy default `config.toml` with placeholders
3. Create default roles (`assistant.md`, `debug.md`)

### Adding Your API Key

Edit the config file and replace `YOUR_API_KEY_HERE` with your actual API key:

#### For OpenAI (GPT-5-mini - recommended for testing)

```toml
[llm]
default_provider = "openai"
default_model = "gpt-5-mini"

[llm.openai]
api_key = "sk-proj-YOUR_ACTUAL_API_KEY_HERE"
```

Get your OpenAI API key: https://platform.openai.com/api-keys

#### For Anthropic (Claude)

```toml
[llm]
default_provider = "anthropic"
default_model = "claude-3-5-sonnet-20241022"

[llm.anthropic]
api_key = "sk-ant-YOUR_ACTUAL_API_KEY_HERE"
```

Get your Anthropic API key: https://console.anthropic.com/settings/keys

#### For Local Models (Ollama - free for testing)

```toml
[llm]
default_provider = "ollama"
default_model = "llama2"

[llm.local]
base_url = "http://localhost:11434"
```

Install Ollama: https://ollama.ai

### Roles Directory

Roles are stored in:
- **Windows**: `%APPDATA%\terma\roles\`
- **macOS/Linux**: `~/.config/terma/roles/`

Default roles:
- `assistant.md` - General terminal assistant
- `debug.md` - Specialized for debugging and troubleshooting

You can create custom roles by adding new `.md` files here.

## Running the Project

### Running terma

After installing in editable mode, you can run terma directly:

```bash
# Simple question
terma "what is the current directory?"

# Without context (faster, uses fewer tokens)
terma "explain git rebase" --no-context

# Using a specific role
terma "why did my command fail?" --role debug

# Dry run (see what would be sent to LLM without making API calls)
terma "list files" --dry-run
```

### Running from Module (Alternative)

If the `terma` command doesn't work, run it as a module:

**Windows:**
```powershell
.venv\Scripts\python.exe -m terma "your question"
```

**macOS/Linux:**
```bash
python -m terma "your question"
```

### Enabling Debug Logging

Debug logging shows detailed information about configuration loading, context capture, LLM requests, and more.

**Windows (PowerShell):**
```powershell
$env:TERMA_DEBUG=1
terma "test query"
```

**Windows (CMD):**
```cmd
set TERMA_DEBUG=1
terma "test query"
```

**macOS/Linux:**
```bash
export TERMA_DEBUG=1
terma "test query"
```

Debug logs show:
- Config file loading
- Role file parsing
- Context capture (tmux vs history)
- LLM requests and responses
- Shell session details

## Testing

### Running All Tests

```bash
# Run all tests except integration tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=terma --cov-report=term-missing
```

### Running Specific Test Files

```bash
# Test a specific module
pytest tests/test_config.py

# Test a specific function
pytest tests/test_config.py::test_load_config -v

# Run tests matching a pattern
pytest -k "test_context" -v
```

### Running Integration Tests

Integration tests make real API calls and require a configured API key.

```bash
# Run only integration tests
pytest -m integration

# Skip integration tests
pytest -m "not integration"
```

**Warning**: Integration tests consume API credits/tokens.

### Test Organization

- `tests/test_config.py` - Configuration loading and role parsing
- `tests/test_context.py` - Context capture (tmux, history)
- `tests/test_interaction.py` - Shell session and command approval
- `tests/test_llm.py` - LLM setup and API key handling
- `tests/test_llm_streaming.py` - Streaming responses and tool calls
- `tests/test_llm_validation.py` - LLM response validation
- `tests/test_integration.py` - End-to-end tests with real API

### Test Markers

```bash
# List all available markers
pytest --markers

# Run tests with a specific marker
pytest -m integration
```

Current markers:
- `integration` - Tests that make real API calls

## Development Workflow

### Making Changes

1. **Activate the virtual environment**
2. **Make your code changes**
3. **Test your changes** - Changes are immediately available because the package is installed in editable mode
4. **Run tests** to ensure nothing broke

```bash
# Example workflow
source .venv/bin/activate  # or .venv\Scripts\Activate.ps1 on Windows
# Edit some files...
terma "test my changes"
pytest
```

### Do I Need to Reinstall After Changes?

**No!** Because you installed with `uv pip install -e .`, the package is in **editable mode**. All code changes are immediately reflected without reinstalling.

**Only reinstall if:**
- You modify `pyproject.toml` dependencies
- You add new entry points
- You change package structure

```bash
# Reinstall after dependency changes
uv pip install -e ".[dev]"
```

### Adding New Dependencies

1. Edit `pyproject.toml` and add the dependency
2. Reinstall the package:

```bash
uv pip install -e ".[dev]"
```

### Code Style Guidelines

- Follow the rules in `.cursor/rules/coding-style.mdc`
- Use underscore_case for variables and functions
- Add docstrings to functions
- Keep code clean and readable
- Avoid duplicate code
- Write unit tests for important functions
- Add debug logging where appropriate

### Before Committing

1. **Run all tests**: `pytest`
2. **Check for linter errors**: Review any IDE warnings
3. **Update changelog**: Add entry to `CHANGELOG.md`
4. **Update documentation**: If you changed behavior or added features

## Troubleshooting

### Virtual Environment Issues

**Problem**: `terma` command not found

**Solution 1**: Activate the virtual environment
```bash
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\Activate.ps1  # Windows PowerShell
```

**Solution 2**: Reinstall in editable mode
```bash
uv pip install -e ".[dev]"
```

**Solution 3**: Run as module
```bash
python -m terma "your question"
```

### "API key not found" Error

**Check these:**
1. Config file exists in correct location (`%APPDATA%\terma` or `~/.config/terma`)
2. API key is properly formatted (no extra quotes or spaces)
3. Using the correct provider name in `default_provider`
4. Config file has correct TOML syntax

**Quick test:**
```bash
# Enable debug logging to see config loading
export TERMA_DEBUG=1  # or $env:TERMA_DEBUG=1 on Windows
terma "test" --no-context
```

### "Module not found" Errors

**Reinstall dependencies:**
```bash
uv pip install -e ".[dev]"
```

**Check Python version:**
```bash
python --version  # Should be 3.10 or higher
```

### Reset Configuration

**Recreate config:**

**Windows:**
```powershell
# Remove
Remove-Item "$env:APPDATA\terma" -Recurse
# Run terma to recreate defaults
terma "test"
```

**macOS/Linux:**
```bash
# Remove
rm -rf ~/.config/terma
# Run terma to recreate defaults
terma "test"
```

### Clean Reinstall

```bash
# Remove virtual environment
rm -rf .venv  # or Remove-Item .venv -Recurse on Windows

# Recreate virtual environment
uv venv

# Activate it
source .venv/bin/activate  # or .venv\Scripts\Activate.ps1

# Reinstall
uv pip install -e ".[dev]"
```

### pytest Not Found

```bash
# Make sure dev dependencies are installed
uv pip install -e ".[dev]"

# Or install pytest directly
uv pip install pytest pytest-mock pytest-cov
```

### Import Errors in Tests

```bash
# Make sure the package is installed in editable mode
uv pip install -e ".[dev]"

# Run pytest from project root, not from tests/
cd /path/to/terma
pytest
```

## Additional Tips

### Testing in WSL (Windows Subsystem for Linux)

1. **Install WSL**: `wsl --install` in PowerShell (admin)
2. **Access Windows files**: Windows drives are at `/mnt/c/`, `/mnt/d/`, etc.
3. **Clone in Linux filesystem** for better performance:

```bash
# In WSL
cd ~
git clone https://github.com/your-username/terma.git
cd terma
# Follow Linux setup instructions above
```

4. **Config location in WSL**: `~/.config/terma/config.toml` (Linux path)

### Testing tmux Context Capture

terma captures richer context when running inside tmux:

**macOS/Linux:**
```bash
# Install tmux
sudo apt install tmux  # Ubuntu/Debian
brew install tmux      # macOS

# Start tmux session
tmux

# Run commands, then test context
terma "explain what I just did"
```

**Windows WSL:**
```bash
# Install tmux in WSL
sudo apt install tmux
tmux
# Test terma
```

### Useful Development Commands

```bash
# Quick test without context (fast, cheap)
terma "test query" --no-context


# Test with debug logging
TERMA_DEBUG=1 terma "test query"  # Linux/macOS
$env:TERMA_DEBUG=1; terma "test query"  # Windows PowerShell

Also `TERMA_PLAIN=1` to remove formatting

### Working with Multiple API Providers

You can configure multiple providers in `config.toml`:

```toml
[llm]
default_provider = "openai"
default_model = "gpt-5-mini"

[llm.openai]
api_key = "sk-proj-..."

[llm.anthropic]
api_key = "sk-ant-..."

[llm.local]
base_url = "http://localhost:11434"
```

Then test different providers by changing `default_provider` or implementing a `--provider` flag.
