# whai - Terminal Assistant

`whai` is a **lightweight and fast** AI terminal assistant that integrates directly into your native shell.

The philosophy of `whai` is to **never interrupt your workflow**. You use your terminal as you normally would. It is not a sub-shell or a separate REPL; it is a single, fast binary that you call on-demand.

When you get stuck, need a command, or encounter an error, you simply call `whai` for immediate help.

### Core Features

* **Analyze Previous Errors:** If a command fails, you don't need to copy-paste. Just ask:
    `> whai why did that fail?`
    It reads the failed command and its full error output from your `tmux` history to provide an immediate diagnosis and solution.
* **Persistent Roles (Memory):** `whai` uses simple, file-based "Roles" to provide persistent memory. This is the core of its customization. You define your context *once*—what machine you are on, what tools are available, your personal preferences, and how you like to work—and `whai` retains this context for all future interactions.
* **Full Session Context:** By securely reading your `tmux` scrollback, `whai` understands not just the commands you ran, but also *what those commands returned*. This provides intelligent, multi-step assistance based on the actual state of your terminal.
* **On-Demand Assistance:** Get help exactly when you need it, from command generation to complex debugging, right in your active shell:
    `> whai find all folders over G`
    `> whai how do I debug this high resource usage?`
* **Safe by Design:** No command is *ever* executed without your explicit `[a]pprove` / `[r]eject` confirmation.
* **Model-Agnostic:** Natively supports OpenAI, Gemini, Anthropic, local Ollama models, and more.

## Installation

### Prerequisites

- Python 3.10 or higher
- `uv` (recommended) or `pip`

### Install with uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/gael-vanderlee/whai.git
cd whai

# Create virtual environment and install
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv sync
```

### Install with pip

```bash
pip install -e .
```

## Configuration

### Interactive Configuration Setup

On first run, whai will launch an interactive configuration wizard to help you set up your API keys and provider settings.

You can also run the wizard manually at any time:

```bash
whai --interactive-config
```

The wizard will guide you through:
- Choosing your LLM provider (OpenAI, Anthropic, Azure OpenAI, or Ollama)
- Entering your API key
- Setting your provider's default model
- Managing multiple providers

Configuration is stored at `~/.config/whai/config.toml` (or `%APPDATA%\whai\config.toml` on Windows).

### Manual Configuration

You can also edit the config file directly:

**OpenAI:**
```toml
[llm]
default_provider = "openai"

[llm.openai]
api_key = "sk-proj-your-actual-api-key-here"
default_model = "gpt-5-mini"
```

**Anthropic:**
```toml
[llm.anthropic]
api_key = "sk-ant-your-actual-api-key-here"
default_model = "claude-3-5-sonnet-20241022"
```

**Azure OpenAI:**
```toml
[llm.azure_openai]
api_key = "your-azure-api-key"
api_base = "https://your-resource.openai.azure.com"
api_version = "2023-05-15"
default_model = "gpt-4"
```

**Ollama (Local):**
```toml
[llm.ollama]
api_base = "http://localhost:11434"
default_model = "mistral"
```

Get API keys from:
- [OpenAI Platform](https://platform.openai.com/api-keys)
- [Anthropic Console](https://console.anthropic.com/)
- [Azure Portal](https://portal.azure.com/) (for Azure OpenAI)

## Usage

### Basic Commands

> **Note:**
> If your query contains shell-sensitive characters (like spaces, apostrophes ('), or quotes (")), always wrap it in quotation marks.
> For example:
>   whai "what's the biggest file?"
>   whai "list all files named \"foo.txt\""

```bash
# Ask a question (quotes optional for multi-word queries, required for apostrophes)
whai what is the biggest folder here?
whai "what's the biggest folder here?"

# Get help with a task
whai how do I find all .py files modified today?
whai "how do I find all .py files modified today?"

# Troubleshooting (works best in tmux)
whai why did my last command fail?
whai "why did my last command fail?"
```

### Options

```bash
whai your question [OPTIONS]
whai "your question" [OPTIONS]  # quotes optional

Options:
  -r, --role TEXT           Role to use (default or a custom role)
  --no-context              Skip context capture
  -m, --model TEXT          Override the LLM model
  -t, --temperature FLOAT   Override temperature
  --timeout INTEGER         Per-command timeout in seconds [default: 60]
  --log-level, -v TEXT     Set log level: CRITICAL|ERROR|WARNING|INFO|DEBUG
  --help                    Show help message
```

### Logging Levels

```bash
# Default (ERROR)
whai "your question"

# Show timings and key steps
whai "your question" -v INFO

# Full diagnostics (payloads, prompts)
whai "your question" -v DEBUG
```

### Pretty Output

whai includes enhanced terminal output with:
- **Spinners** while waiting for AI responses
- **Code blocks** for shell commands and outputs
- **Colored text** for errors, warnings, and info messages
- **Panels** for structured display

Pretty output automatically disables in non-interactive environments (pipes, redirects, CI/CD).

To force plain text output:
```bash
export WHAI_PLAIN=1
whai your question
```

This is useful for:
- Logging output to files
- CI/CD pipelines
- Screen readers
- Terminals with limited formatting support

### Examples

```bash
# Use a custom role for troubleshooting (if you created one)
whai analyze this error -r troubleshooting

# Use a different model
whai list large files -m gpt-5-mini

# Skip context capture for faster responses
whai what is a .gitignore file? --no-context

# Quotes still work if you prefer them
whai "what is a .gitignore file?" --no-context

# Control command timeout (seconds)
whai "Do this" --timeout 30
```

## Roles

Roles are defined in `~/.config/whai/roles/` as Markdown files with YAML frontmatter.

### Default Role

- **default**: General-purpose terminal assistant

### Managing Roles

whai provides a comprehensive role management system:

```bash
# List all available roles
whai role list

# Create a new role (opens in editor)
whai role create my-role

# Edit an existing role
whai role edit my-role

# Remove a role
whai role remove my-role

# Set default role (used when --role isn't specified)
whai role set-default my-role

# Reset default role to packaged version
whai role reset-default

# Open roles folder in file explorer
whai role open-folder

# Interactive role manager (shows menu)
whai role

# Show which role whai would use right now
whai role which
```

### Creating Custom Roles

Create a new role using the CLI:

```bash
whai role create devops
```

This creates and opens `~/.config/whai/roles/devops.md` in your editor:

```markdown
---
model: gpt-5-mini
temperature: 0.5
---

You are a DevOps specialist focusing on Docker and Kubernetes.
Help users with containerization, orchestration, and deployment tasks.
```

Use it with:

```bash
whai help me debug this pod -r devops
```

### Session Roles

Set a role for your current shell session using environment variables:

```bash
# Show how to set role for your shell
whai role use devops

# Then run the command it shows, e.g. for bash/zsh:
export WHAI_ROLE="devops"

# Now all whai commands use that role
whai "help me with kubernetes"

# Clear the session role
unset WHAI_ROLE
```

### Role Precedence

When determining which role to use, whai follows this precedence (highest first):

1. CLI flag: `-r/--role`
2. Environment variable: `WHAI_ROLE`
3. Config default: `roles.default_role` in `config.toml`
4. Fallback: `default`

To quickly check the effective role based on the above rules, run:

```bash
whai role which
```

## Context Modes

whai captures terminal context to provide better assistance:

### Deep Context (Recommended)

Run whai inside a tmux session to get full scrollback (commands + output):

```bash
tmux
whai why did this fail?
```

### Shallow Context (Fallback)

Without tmux, whai reads shell history (commands only):

```bash
whai what did I just run?
```

## How It Works

1. **Context Capture**: Reads tmux scrollback or shell history
2. **LLM Query**: Sends your question with context to the configured LLM
3. **Response**: Streams the AI's response to your terminal
4. **Command Approval**: If the AI suggests a command, you approve/reject/modify it
5. **Execution**: Approved commands run in a persistent shell session
6. **Iteration**: The conversation continues until the task is complete

## Safety

- **No command runs without your explicit approval**
- You can modify any suggested command before running it
- Commands run in a subprocess (won't affect your main shell)
- Use `Ctrl+C` to interrupt at any time

## Troubleshooting

### "No module named 'whai'"

Make sure you've activated the virtual environment:

```bash
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### "API key not found"

Edit `~/.config/whai/config.toml` and add your API key.

### Commands not preserving state

This is expected. Changes like `cd` and `export` persist only within a whai session, not in your main shell.

### tmux context not working on Windows

Use WSL with tmux installed. whai will automatically detect and use WSL's tmux.

## Development

### Running Tests

```bash
# Run all unit tests
pytest tests/ -v

# Run specific test file
pytest tests/test_config.py -v

# Run integration tests (requires API key)
pytest tests/ -v -m integration
```

### Project Structure

```
whai/
├── whai/               # Main package
│   ├── __init__.py
│   ├── __main__.py     # Entry point
│   ├── main.py         # CLI logic
│   ├── config.py       # Configuration management
│   ├── context.py      # Context capture
│   ├── llm.py          # LLM provider
│   └── interaction.py  # Shell session & approval
├── tests/              # Test suite
├── pyproject.toml      # Project metadata
└── README.md
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- Built with [LiteLLM](https://github.com/BerriAI/litellm) for multi-provider support
- CLI powered by [Typer](https://typer.tiangolo.com/)
- Pretty output by [Rich](https://github.com/Textualize/rich)
- Inspired by tools like `aichat` and `shell-gpt`

## FAQ

### How is this different from ChatGPT in a browser?

whai is integrated into your terminal with full context awareness. It sees your command history, can execute commands for you, and maintains state across a session.

### Does it send my terminal history to the LLM?

Only when you run whai. It captures recent history or tmux scrollback and includes it in the request. You can use `--no-context` to disable this.

### Can I use it with local models?

Yes! Configure any LiteLLM-compatible provider, including Ollama for local models.

### Why do changes not persist after whai exits?

This is by design. whai runs commands in a subprocess to keep your main shell safe. Changes like `cd` work within a session but don't affect your parent shell.
