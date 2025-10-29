# terma - Terminal Assistant

A lightweight, Python-based CLI tool that integrates large language models (LLMs) directly into your terminal. Get command suggestions, troubleshoot issues, and interact with your system using natural language.

## Features

- **Natural Language Command Generation**: Ask questions in plain English, get working shell commands
- **Post-Mortem Analysis**: Analyze failed commands with full context (requires tmux)
- **Collaborative Execution**: Approve, reject, or modify commands before they run
- **Context-Aware**: Captures terminal history or tmux scrollback for intelligent responses
- **Multi-LLM Support**: Works with OpenAI, Anthropic, and local models via LiteLLM
- **Customizable Roles**: Define different AI personas for different tasks
- **Stateful Sessions**: Commands like `cd` and `export` persist within a conversation

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
uv pip install -e .   # uv pip install .[dev] if you're devvin
```

### Install with pip

```bash
pip install -e .
```

## Configuration

On first run, terma creates a configuration file at `~/.config/terma/config.toml` (or `%APPDATA%\terma\config.toml` on Windows).

### Add your API key

Edit the config file and add your API key. See [TESTING.md](TESTING.md) for detailed instructions on setting up API keys for different providers.

**Quick setup for OpenAI:**

```toml
[llm]
default_provider = "openai"
default_model = "gpt-5-mini"

[llm.openai]
api_key = "sk-proj-your-actual-api-key-here"
```

Get your API key from [OpenAI Platform](https://platform.openai.com/api-keys).

**For other providers** (Anthropic, Ollama, etc.), see [TESTING.md](TESTING.md).

## Usage

### Basic Commands

```bash
# Ask a question
terma "what's the biggest folder here?"

# Get help with a task
terma "how do I find all .py files modified today?"

# Troubleshooting (works best in tmux)
terma "why did my last command fail?"
```

### Options

```bash
terma "your question" [OPTIONS]

Options:
  -r, --role TEXT        Role to use (assistant, debug, etc.) [default: assistant]
  --no-context          Skip context capture
  -m, --model TEXT      Override the LLM model
  -t, --temperature FLOAT  Override temperature
  --help                Show help message
```

### Examples

```bash
# Use the debug role for troubleshooting
terma "analyze this error" -r debug

# Use a different model
terma "list large files" -m gpt-5-mini

# Skip context capture for faster responses
terma "what is a .gitignore file?" --no-context
```

## Roles

Roles are defined in `~/.config/terma/roles/` as Markdown files with YAML frontmatter.

### Default Roles

- **assistant** (default): General-purpose terminal assistant
- **debug**: Specialized for troubleshooting and error analysis

### Creating Custom Roles

Create a new file in `~/.config/terma/roles/custom.md`:

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
terma "help me debug this pod" -r custom
```

## Context Modes

terma captures terminal context to provide better assistance:

### Deep Context (Recommended)

Run terma inside a tmux session to get full scrollback (commands + output):

```bash
tmux
terma "why did this fail?"
```

### Shallow Context (Fallback)

Without tmux, terma reads shell history (commands only):

```bash
terma "what did I just run?"
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
