# terma - Terminal Assistant

A lightweight, Python-based CLI tool that integrates large language models (LLMs) directly into your terminal. Get command suggestions, troubleshoot issues, and interact with your system using natural language.

## Features

- **Natural Language Command Generation**: Ask questions in plain English, get working shell commands
- **Post-Mortem Analysis**: Analyze failed commands with full context (requires tmux)
- **Collaborative Execution**: Approve, reject, or modify commands before they run
- **Context-Aware**: Captures terminal history for intelligent responses
- **Multi-LLM Support**: Works with OpenAI, Anthropic, and local models via LiteLLM
- **Customizable Roles**: Define different AI personas for different tasks. Don't repeat yourself, write instructions and information once for all sessions.
- **Stateful Sessions**: Commands like `cd` and `export` persist within a conversation (does not persist into your parent shell)

## Installation

### Prerequisites

- Python 3.10 or higher
- `uv` (recommended) or `pip`

### Install with uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/terma.git
cd terma

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

On first run, terma will launch an interactive configuration wizard to help you set up your API keys and provider settings.

You can also run the wizard manually at any time:

```bash
terma --interactive-config
```

The wizard will guide you through:
- Choosing your LLM provider (OpenAI, Anthropic, Azure OpenAI, or Ollama)
- Entering your API key
- Setting your provider's default model
- Managing multiple providers

Configuration is stored at `~/.config/terma/config.toml` (or `%APPDATA%\terma\config.toml` on Windows).

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
>   terma "what's the biggest file?"
>   terma "list all files named \"foo.txt\""

```bash
# Ask a question (quotes optional for multi-word queries, required for apostrophes)
terma what is the biggest folder here?
terma "what's the biggest folder here?"

# Get help with a task
terma how do I find all .py files modified today?
terma "how do I find all .py files modified today?"

# Troubleshooting (works best in tmux)
terma why did my last command fail?
terma "why did my last command fail?"
```

### Options

```bash
terma your question [OPTIONS]
terma "your question" [OPTIONS]  # quotes optional

Options:
  -r, --role TEXT        Role to use (default or a custom role)
  --no-context          Skip context capture
  -m, --model TEXT      Override the LLM model
  -t, --temperature FLOAT  Override temperature
  --timeout INTEGER     Per-command timeout in seconds [default: 60]
  --help                Show help message
```

### Pretty Output

terma includes enhanced terminal output with:
- **Spinners** while waiting for AI responses
- **Code blocks** for shell commands and outputs
- **Colored text** for errors, warnings, and info messages
- **Panels** for structured display

Pretty output automatically disables in non-interactive environments (pipes, redirects, CI/CD).

To force plain text output:
```bash
export TERMA_PLAIN=1
terma your question
```

This is useful for:
- Logging output to files
- CI/CD pipelines
- Screen readers
- Terminals with limited formatting support

### Examples

```bash
# Use a custom role for troubleshooting (if you created one)
terma analyze this error -r troubleshooting

# Use a different model
terma list large files -m gpt-5-mini

# Skip context capture for faster responses
terma what is a .gitignore file? --no-context

# Quotes still work if you prefer them
terma "what is a .gitignore file?" --no-context

# Control command timeout (seconds)
terma "Do this" --timeout 30
```

## Roles

Roles are defined in `~/.config/terma/roles/` as Markdown files with YAML frontmatter.

### Default Role

- **default**: General-purpose terminal assistant

### Managing Roles

terma provides a comprehensive role management system:

```bash
# List all available roles
terma role list

# Create a new role (opens in editor)
terma role create my-role

# Edit an existing role
terma role edit my-role

# Remove a role
terma role remove my-role

# Set default role (used when --role isn't specified)
terma role set-default my-role

# Reset default role to packaged version
terma role reset-default

# Open roles folder in file explorer
terma role open-folder

# Interactive role manager (shows menu)
terma role

# Show which role terma would use right now
terma role which
```

### Creating Custom Roles

Create a new role using the CLI:

```bash
terma role create devops
```

This creates and opens `~/.config/terma/roles/devops.md` in your editor:

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
terma help me debug this pod -r devops
```

### Session Roles

Set a role for your current shell session using environment variables:

```bash
# Show how to set role for your shell
terma role use devops

# Then run the command it shows, e.g. for bash/zsh:
export TERMA_ROLE="devops"

# Now all terma commands use that role
terma "help me with kubernetes"

# Clear the session role
unset TERMA_ROLE
```

### Role Precedence

When determining which role to use, terma follows this precedence (highest first):

1. CLI flag: `-r/--role`
2. Environment variable: `TERMA_ROLE`
3. Config default: `roles.default_role` in `config.toml`
4. Fallback: `default`

To quickly check the effective role based on the above rules, run:

```bash
terma role which
```

## Context Modes

terma captures terminal context to provide better assistance:

### Deep Context (Recommended)

Run terma inside a tmux session to get full scrollback (commands + output):

```bash
tmux
terma why did this fail?
```

### Shallow Context (Fallback)

Without tmux, terma reads shell history (commands only):

```bash
terma what did I just run?
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

### "No module named 'terma'"

Make sure you've activated the virtual environment:

```bash
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### "API key not found"

Edit `~/.config/terma/config.toml` and add your API key.

### Commands not preserving state

This is expected. Changes like `cd` and `export` persist only within a terma session, not in your main shell.

### tmux context not working on Windows

Use WSL with tmux installed. terma will automatically detect and use WSL's tmux.

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
terma/
├── terma/              # Main package
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

terma is integrated into your terminal with full context awareness. It sees your command history, can execute commands for you, and maintains state across a session.

### Does it send my terminal history to the LLM?

Only when you run terma. It captures recent history or tmux scrollback and includes it in the request. You can use `--no-context` to disable this.

### Can I use it with local models?

Yes! Configure any LiteLLM-compatible provider, including Ollama for local models.

### Why do changes not persist after terma exits?

This is by design. terma runs commands in a subprocess to keep your main shell safe. Changes like `cd` work within a session but don't affect your parent shell.
