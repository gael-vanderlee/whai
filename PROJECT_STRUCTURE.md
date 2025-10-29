# terma Project Structure

This document provides a detailed overview of the terma project architecture, file organization, and key functions.

## Table of Contents

- [Project Overview](#project-overview)
- [Directory Structure](#directory-structure)
- [Core Architecture](#core-architecture)
- [Module Details](#module-details)
- [Data Flow](#data-flow)
- [Testing Structure](#testing-structure)

## Project Overview

**terma** is a Python-based CLI tool that integrates large language models directly into your terminal. It functions as a context-aware assistant that can:
- Answer questions about terminal commands
- Generate and execute shell commands with user approval
- Analyze command failures using terminal context
- Maintain persistent shell state across multiple commands

### Key Design Principles

1. **User Control**: All command execution requires explicit user approval
2. **Context Awareness**: Captures terminal history (tmux scrollback or shell history) for context
3. **LLM Agnostic**: Uses LiteLLM to support multiple LLM providers (OpenAI, Anthropic, etc.)
4. **Stateful Sessions**: Maintains a persistent shell subprocess so `cd` and `export` commands persist
5. **Fail-Fast**: No silent fallbacks; the tool crashes on configuration errors to surface issues

## Directory Structure

```
terma/
├── .venv/                      # Virtual environment (managed by uv)
├── defaults/                   # Default configuration files (shipped with package)
│   ├── config.toml            # Default configuration template
│   ├── system_prompt.txt      # Base system prompt for all LLM interactions
│   └── roles/                 # Default role definitions
│       ├── assistant.md       # General purpose assistant role
│       └── debug.md           # Debugging-focused role
│
├── terma/                      # Main package source code
│   ├── __init__.py            # Package initialization
│   ├── __main__.py            # Entry point for `python -m terma`
│   ├── main.py                # CLI interface and main conversation loop
│   ├── config.py              # Configuration loading and role management
│   ├── context.py             # Terminal context capture (tmux/history)
│   ├── llm.py                 # LLM provider wrapper using LiteLLM
│   ├── interaction.py         # Shell session and command approval
│   └── logging_setup.py       # Centralized logging configuration
│
├── tests/                      # Test suite
│   ├── __init__.py
│   ├── test_config.py         # Tests for configuration management
│   ├── test_context.py        # Tests for context capture
│   ├── test_llm.py            # Tests for LLM integration
│   ├── test_interaction.py    # Tests for shell session and approval
│   └── test_integration.py    # End-to-end integration tests
│
├── pyproject.toml             # Project metadata and dependencies
├── README.md                  # User-facing documentation
├── TESTING.md                 # Guide for setting up API keys and testing
├── CHANGELOG.md               # Version history and changes
└── PROJECT_STRUCTURE.md       # This file
```

## Core Architecture

### Request-Response Loop

The tool operates on a persistent request-response loop:

1. **User invokes terma** with a query
2. **Context capture** extracts terminal history/scrollback
3. **Configuration loading** reads user settings and role definitions
4. **LLM interaction** sends context + query to the LLM
5. **Response streaming** displays LLM's text response in real-time
6. **Tool call handling** intercepts command execution requests
7. **Approval loop** prompts user to approve/reject/modify commands
8. **Command execution** runs approved commands in persistent shell
9. **Loop continuation** sends results back to LLM for follow-up

### Persistent Shell Session

Unlike traditional CLI tools, terma maintains a single subprocess throughout the session:
- Created with `subprocess.Popen` at startup
- State persists (`cd`, `export`, environment variables)
- Uses unique markers to detect command completion
- Closed automatically when terma exits

## Module Details

### `terma/__init__.py`

**Purpose**: Package initialization and version definition.

**Key Elements**:
- `__version__`: Current version string
- Sets up a `NullHandler` for library logging to prevent noise

---

### `terma/__main__.py`

**Purpose**: Entry point for running terma as a module (`python -m terma`).

**Key Elements**:
- Configures logging via `configure_logging()`
- Launches the Typer CLI app

---

### `terma/main.py`

**Purpose**: Main CLI interface and conversation orchestration.

**Key Functions**:

#### `print_error(message: str)` / `print_warning()` / `print_info()`
Helper functions for styled console output using Typer's color system.

#### `main(query, role, no_context, model, temperature)`
The main CLI command, invoked when user runs `terma "query"`.

**Flow**:
1. Load configuration from `~/.config/terma/config.toml`
2. Load specified role (default: "assistant")
3. Capture terminal context (tmux scrollback or shell history)
4. Initialize LLM provider with configured API keys
5. Create persistent shell session
6. Build initial message with system prompt + role + context + query
7. Enter conversation loop:
   - Send messages to LLM (streaming)
   - Display text responses
   - Parse tool calls (command execution requests)
   - Run approval loop for each command
   - Execute approved commands in shell session
   - Add results to message history
   - Continue until no more tool calls or user rejects
8. Clean up shell session on exit

**Error Handling**:
- Crashes on configuration load failures (no silent fallbacks)
- Displays detailed tracebacks for unexpected errors
- Handles keyboard interrupts gracefully

---

### `terma/config.py`

**Purpose**: Configuration file and role management.

**Key Functions**:

#### `get_config_dir() -> Path`
Returns the platform-appropriate config directory:
- Windows: `%APPDATA%/terma`
- Unix: `~/.config/terma`

#### `get_default_config() -> str`
Reads the default configuration template from `defaults/config.toml`.
- **Crashes** if file is missing (indicates broken installation)

#### `load_config() -> Dict[str, Any]`
Loads configuration from user's config directory.
- Creates default config file if it doesn't exist
- Parses TOML format using `tomllib`
- Returns configuration dictionary

#### `get_default_role(role_name: str) -> str`
Reads default role content from `defaults/roles/{role_name}.md`.
- **Crashes** if file is missing (indicates broken installation)

#### `ensure_default_roles() -> None`
Copies default role files to user's config directory if they don't exist.

#### `parse_role_file(content: str) -> Tuple[Dict, str]`
Parses role markdown files with YAML frontmatter.
- Frontmatter format: `---\nkey: value\n---\n`
- Extracts metadata (model, temperature, etc.)
- Returns tuple of (metadata dict, markdown body)

#### `load_role(role_name: str) -> Tuple[Dict, str]`
Loads a role from user's config directory.
- Ensures default roles exist first
- Reads role file
- Parses frontmatter and body
- Returns (metadata, system prompt)

---

### `terma/context.py`

**Purpose**: Capture terminal context for LLM understanding.

**Key Functions**:

#### `_is_wsl() -> bool`
Detects if running on Windows with WSL available.
- Checks if `wsl --status` command succeeds
- Used to determine how to invoke tmux on Windows

#### `_get_tmux_context() -> Optional[str]`
Captures tmux scrollback buffer (deep context).
- Checks `TMUX` environment variable
- Runs `tmux capture-pane -p` to get full scrollback
- On Windows, runs command through WSL if available
- Returns scrollback text or None if not in tmux

#### `_get_shell_from_env() -> str`
Detects current shell from `SHELL` environment variable.
- Returns "bash", "zsh", or "unknown"

#### `_parse_zsh_history(history_file: Path, max_commands: int) -> list`
Parses zsh history file format.
- Format: `: <timestamp>:<duration>;<command>`
- Handles multiline commands
- Returns list of most recent commands

#### `_parse_bash_history(history_file: Path, max_commands: int) -> list`
Parses bash history file (simpler format).
- One command per line
- Returns list of most recent commands

#### `_get_history_context(max_commands: int) -> Optional[str]`
Fallback context capture using shell history files (shallow context).
- Detects shell type
- Reads appropriate history file (`~/.zsh_history` or `~/.bash_history`)
- Formats as numbered list
- Returns formatted history or None

#### `get_context(max_commands: int) -> Tuple[str, bool]`
Main context capture function.
- **Tries tmux first** (deep context with command output)
- **Falls back to history** (shallow context with commands only)
- Returns tuple: (context_string, is_deep_context)
- The `is_deep_context` flag affects system prompt generation

**Context Types**:
- **Deep Context**: tmux scrollback including commands AND their output (ideal for post-mortem)
- **Shallow Context**: shell history with commands only (limited troubleshooting ability)

---

### `terma/llm.py`

**Purpose**: LLM integration using LiteLLM for provider agnosticism.

**Key Constants**:

#### `EXECUTE_SHELL_TOOL`
Tool definition in OpenAI function calling format:
- Function name: "execute_shell"
- Parameter: "command" (string)
- Enables LLM to request command execution

**Key Functions**:

#### `get_base_system_prompt(is_deep_context: bool) -> str`
Loads and formats the base system prompt.
- Reads template from `defaults/system_prompt.txt`
- Injects context note (deep vs shallow)
- **Crashes** if template file is missing
- This prompt is prepended to all conversations

#### `LLMProvider` Class

**`__init__(config, model, temperature)`**
Initializes the LLM provider.
- Extracts LLM settings from config
- Sets model and temperature
- Configures API keys via `_configure_api_keys()`

**`_configure_api_keys()`**
Sets environment variables for LiteLLM.
- Reads API keys from config
- Sets `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.
- LiteLLM uses these env vars automatically

**`send_message(messages, tools, stream) -> Generator or Dict`**
Sends messages to LLM and returns responses.

**Parameters**:
- `messages`: List of message dicts (OpenAI chat format)
- `tools`: List of tool definitions (defaults to `[EXECUTE_SHELL_TOOL]`)
- `stream`: Whether to stream response (default True)

**Returns**:
- If streaming: Generator yielding chunks
- If not streaming: Complete response dict

**Chunk Types**:
- `{"type": "text", "content": "..."}` - Text content
- `{"type": "tool_call", "id": "...", "name": "...", "arguments": {...}}` - Tool call

**`_handle_streaming_response(response) -> Generator`**
Processes streaming response from LiteLLM.
- Accumulates partial tool call arguments across chunks
- Handles incomplete JSON gracefully (waits for complete JSON)
- Yields text chunks and tool calls as they arrive
- Prevents duplicate emissions for same tool call ID

**`_handle_complete_response(response) -> Dict`**
Processes non-streaming response from LiteLLM.
- Extracts content and tool calls
- Parses tool call arguments (JSON)
- Returns formatted response dict

---

### `terma/interaction.py`

**Purpose**: Shell session management and command approval.

**Key Classes**:

#### `ShellSession` Class

Manages a persistent shell subprocess for stateful command execution.

**`__init__(shell: str = None)`**
Creates a new shell session.
- Defaults to `bash` on Unix, `cmd.exe` on Windows
- Starts subprocess via `_start_shell()`

**`_start_shell()`**
Launches the shell subprocess.
- Uses `subprocess.Popen` with stdin/stdout/stderr pipes
- Unix shells: launched with `-i` (interactive mode)
- Sets `PS1=""` to disable prompt (prevents confusion)
- Unbuffered I/O for immediate output

**`execute_command(command: str, timeout: int) -> Tuple[str, str, int]`**
Executes a command in the shell session.

**How It Works**:
1. Generates unique marker (e.g., `___TERMA_CMD_DONE_123456___`)
2. Writes command + `echo marker` to shell's stdin
3. Reads stdout/stderr line by line until marker appears
4. Returns everything before the marker as command output
5. Times out if marker not seen within timeout period

**Returns**: `(stdout, stderr, returncode)`

**Special Handling**:
- Windows: Normalizes `cd` to `cd /d` for drive changes
- Both platforms: Uses marker-based end-of-command detection

**`_read_line_with_timeout(stream, timeout: float) -> Optional[str]`**
Platform-specific non-blocking line reading.
- Unix: Uses `select.select()` for timeout
- Windows: Uses threading + queue (select doesn't work on file objects)

**`close()`**
Terminates the shell subprocess.
- Closes stdin
- Sends SIGTERM (graceful)
- Falls back to SIGKILL if needed

**Context Manager Support**:
- `__enter__` and `__exit__` allow use with `with` statement
- Automatically closes on context exit

---

**Key Functions**:

#### `approval_loop(command: str) -> Optional[str]`
Presents a command to the user for approval.

**Display**:
```
============================================================
Proposed command:
  > ls -la
============================================================
[a]pprove / [r]eject / [m]odify:
```

**Options**:
- `a` or `approve`: Return command as-is
- `r` or `reject`: Return None
- `m` or `modify`: Prompt for modified command
- Ctrl+C or EOF: Return None (rejected)

**Returns**: Approved command string or None if rejected

#### `parse_tool_calls(response_chunks: list) -> list`
Extracts tool calls from LLM response chunks.
- Filters chunks with `type == "tool_call"`
- Returns list of tool call dicts with id, name, and arguments

---

### `terma/logging_setup.py`

**Purpose**: Centralized logging configuration.

**Key Functions**:

#### `configure_logging(mode: Optional[str] = None) -> None`
Configures root logger based on environment.

**Modes**:
- **Development** (`TERMA_DEBUG=1` or `TERMA_ENV=dev`):
  - Root logger level: DEBUG
  - Console handler with formatted output
  - Silences noisy third-party loggers (litellm, httpx, etc.)
- **Production** (default):
  - Root logger level: WARNING
  - NullHandler (silent)
  - No console output during normal operation

**Environment Variables**:
- `TERMA_DEBUG=1`: Enable debug logging
- `TERMA_ENV=dev`: Enable development mode
- `TERMA_VERBOSE_DEPS=1`: Show third-party library logs in dev mode

#### `get_logger(name: str) -> logging.Logger`
Convenience function to create module loggers with consistent naming.

---

## Data Flow

### Complete Execution Flow

```
1. User runs: terma "why did this fail?"
   ↓
2. main.py: parse CLI arguments
   ↓
3. config.py: load_config() → read ~/.config/terma/config.toml
   ↓
4. config.py: load_role("assistant") → read role file with frontmatter
   ↓
5. context.py: get_context()
   ├─ Try: _get_tmux_context() [deep context]
   └─ Fallback: _get_history_context() [shallow context]
   ↓
6. llm.py: get_base_system_prompt(is_deep_context)
   ↓
7. interaction.py: ShellSession() → create persistent shell subprocess
   ↓
8. main.py: assemble message:
   {
     "role": "system",
     "content": base_prompt + role_prompt
   }
   {
     "role": "user",
     "content": "CONTEXT: ...\nQUERY: why did this fail?"
   }
   ↓
9. llm.py: send_message(messages, stream=True)
   ↓
10. LiteLLM: calls OpenAI/Anthropic/etc API
    ↓
11. llm.py: _handle_streaming_response()
    ├─ Text chunks → printed to stdout
    └─ Tool calls → buffered
    ↓
12. main.py: parse_tool_calls() → extract execute_shell calls
    ↓
13. interaction.py: approval_loop(command)
    ├─ Display command
    ├─ Wait for user input
    └─ Return approved/modified/None
    ↓
14. interaction.py: shell_session.execute_command(command)
    ├─ Write command + marker to shell stdin
    ├─ Read stdout/stderr until marker
    └─ Return output
    ↓
15. main.py: add tool result to messages
    {
      "role": "tool",
      "tool_call_id": "...",
      "content": "Command: ...\nOutput: ..."
    }
    ↓
16. Loop back to step 9 (send updated messages to LLM)
    ↓
17. LLM responds with analysis/next steps
    ↓
18. If no more tool calls: exit loop
    ↓
19. interaction.py: shell_session.close()
    ↓
20. Exit
```

### Message Flow Example

**Initial Query**:
```python
[
  {
    "role": "system",
    "content": "You are a terminal assistant...\n\nYou are a helpful assistant..."
  },
  {
    "role": "user",
    "content": "CONTEXT: [...tmux scrollback...]\nQUERY: why did pip install fail?"
  }
]
```

**LLM Response** (streamed):
```python
# Text chunks:
{"type": "text", "content": "Looking at the error, you're missing python3-dev. "}
{"type": "text", "content": "Let me install it:"}

# Tool call:
{
  "type": "tool_call",
  "id": "call_123",
  "name": "execute_shell",
  "arguments": {"command": "sudo apt install python3-dev"}
}
```

**After User Approval & Execution**:
```python
[
  ...previous messages...,
  {
    "role": "assistant",
    "content": "",
    "tool_calls": [{
      "id": "call_123",
      "type": "function",
      "function": {
        "name": "execute_shell",
        "arguments": '{"command": "sudo apt install python3-dev"}'
      }
    }]
  },
  {
    "role": "tool",
    "tool_call_id": "call_123",
    "content": "Command: sudo apt install python3-dev\n\nOutput: [...installation output...]"
  }
]
```

**Next LLM Response**:
```python
{"type": "text", "content": "Great! Now try running your pip install again."}
```

---

## Testing Structure

### Test Files

#### `tests/test_config.py`
Tests for configuration management:
- Config directory detection (platform-specific)
- Default config loading
- Role file parsing (with/without frontmatter)
- Role loading and creation

#### `tests/test_context.py`
Tests for context capture:
- WSL detection on Windows
- tmux context capture (Unix and Windows+WSL)
- Shell history parsing (zsh and bash formats)
- Fallback behavior

#### `tests/test_llm.py`
Tests for LLM integration:
- System prompt generation
- LLMProvider initialization
- API key configuration
- Message sending (mocked responses)
- Streaming response handling
- Tool call parsing
- Integration test with real API (marked with `@pytest.mark.integration`)

#### `tests/test_interaction.py`
Tests for shell session and approval:
- Shell session creation (platform-specific)
- Command execution with marker detection
- Timeout handling
- Approval loop (approve/reject/modify)
- Tool call parsing
- Context manager behavior

#### `tests/test_integration.py`
End-to-end integration tests:
- Full conversation flow (Q&A without commands)
- Command generation and approval
- Command rejection handling
- CLI option testing (role, model, no-context)
- Error handling (missing config, keyboard interrupt)

### Running Tests

**All tests except integration**:
```bash
pytest tests/ -v -m "not integration"
```

**Integration tests only** (requires API key):
```bash
pytest tests/ -v -m integration
```

**All tests**:
```bash
pytest tests/ -v
```

### Test Markers

- `@pytest.mark.integration`: Tests that make real API calls (excluded by default)

---

## Configuration Files

### `defaults/config.toml`

Default configuration template:
```toml
[llm]
default_provider = "openai"
default_model = "gpt-5-mini"

[llm.openai]
api_key = "YOUR_OPENAI_API_KEY_HERE"

[llm.anthropic]
api_key = "YOUR_ANTHROPIC_API_KEY_HERE"
```

### `defaults/system_prompt.txt`

Base system prompt template with `{context_note}` placeholder:
- Defines terma's role as a terminal assistant
- Explains the execute_shell tool
- Sets expectations for command execution and state persistence
- Instructs on streaming behavior and tool usage

### `defaults/roles/*.md`

Role definition files with YAML frontmatter:

**Structure**:
```markdown
---
model: gpt-5-mini
temperature: 0.7
---

You are a helpful terminal assistant...
```

**Built-in Roles**:
- `assistant.md`: General-purpose assistance
- `debug.md`: Debugging and troubleshooting focus

---

## Key Design Patterns

### 1. Fail-Fast Configuration
- No silent fallbacks for missing config files
- Raises `FileNotFoundError` if defaults are missing
- Crashes immediately to surface installation issues

### 2. Platform Abstraction
- Platform-specific code isolated in functions
- Graceful handling of Windows vs Unix differences
- WSL detection for tmux on Windows

### 3. Stateful Shell Sessions
- Single persistent subprocess per terma invocation
- State (`cd`, `export`) preserved across commands
- Marker-based command completion detection

### 4. Streaming-First
- LLM responses streamed in real-time
- Tool calls parsed from streaming chunks
- Handles incomplete JSON gracefully

### 5. Explicit Approval
- All commands require user approval
- No autonomous execution
- User can modify commands before execution

### 6. Context-Aware Prompting
- System prompt adapts based on context availability
- Deep context (tmux) enables post-mortem analysis
- Shallow context (history) acknowledged in prompt

---

## Development Guidelines

### Adding a New Module

1. Create module in `terma/` directory
2. Add imports to `terma/__init__.py` if needed
3. Import logging: `from terma.logging_setup import get_logger`
4. Create logger: `logger = get_logger(__name__)`
5. Add corresponding test file in `tests/`

### Adding a New Role

1. Create `defaults/roles/{role_name}.md`
2. Add YAML frontmatter with model/temperature
3. Write system prompt in markdown body
4. Update `ensure_default_roles()` in `config.py` if it should be auto-created

### Adding a New LLM Provider

1. Add API key section to `defaults/config.toml`
2. Update `_configure_api_keys()` in `llm.py`
3. LiteLLM handles the rest automatically

### Debugging

Enable debug logging:
```bash
export TERMA_DEBUG=1
terma "test query"
```

See third-party library logs:
```bash
export TERMA_DEBUG=1
export TERMA_VERBOSE_DEPS=1
terma "test query"
```

---

## Future Extension Points

### Potential Enhancements

1. **Conversation History**: Save/resume conversations
2. **Custom Tools**: Allow users to define additional tools beyond execute_shell
3. **Multi-Pane tmux**: Capture context from specific panes
4. **Shell Integrations**: Keybindings for zsh/bash (Ctrl+T translation, etc.)
5. **Alternative Context**: Git status, working directory metadata
6. **Cost Tracking**: Log token usage per conversation
7. **Model Fallbacks**: Retry with different model on failure
8. **Command History**: Track successful commands for learning

### Extension Hooks

- `context.py`: Add new context capture methods
- `llm.py`: Add tools to `EXECUTE_SHELL_TOOL` list
- `interaction.py`: Add approval loop plugins
- `defaults/roles/`: Create specialized role definitions

---

## Troubleshooting

### Common Issues

**"Failed to load config"**
- Ensure `defaults/config.toml` exists in package
- Check file permissions
- Reinstall terma if file is missing

**"Role 'xyz' not found"**
- Ensure role file exists in `~/.config/terma/roles/`
- Check filename matches (case-sensitive)
- Run `terma --help` to see available roles

**"No context available"**
- Not in tmux and no shell history found
- Use `--no-context` flag to run without context
- Install tmux for deep context support

**Commands hang or timeout**
- Long-running commands may exceed 30s timeout
- Adjust timeout in `execute_command()` if needed
- Consider running long commands manually

**API errors**
- Check API key in `~/.config/terma/config.toml`
- Verify network connectivity
- Check LiteLLM logs with `TERMA_DEBUG=1`

---

## Summary

terma is architecturally designed around these core concepts:

1. **Persistent Shell State**: Single subprocess preserves state across commands
2. **Context Awareness**: Deep (tmux) or shallow (history) context for LLM understanding
3. **Explicit Control**: User approval required for all command execution
4. **LLM Agnostic**: LiteLLM enables multiple provider support
5. **Streaming First**: Real-time response display with tool call parsing
6. **Fail-Fast**: Crashes on configuration errors rather than silent fallbacks

The modular architecture separates concerns cleanly:
- `main.py`: Orchestration and CLI
- `config.py`: Configuration management
- `context.py`: Terminal context capture
- `llm.py`: LLM interaction
- `interaction.py`: Shell management and approval

This separation enables easy testing, extension, and maintenance.

