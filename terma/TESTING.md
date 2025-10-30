# Testing terma with Real LLM API

This guide explains how to set up your API keys to test terma with a real LLM.

## Setup Steps

### 1. Find Your Config File

terma stores its configuration in:
- **Windows**: `%APPDATA%\terma\config.toml`
  - Usually: `C:\Users\YourName\AppData\Roaming\terma\config.toml`
  - Quick access: Type `%APPDATA%\terma` in Windows Explorer
  - `$env:TERMA_DEBUG=1` for logging
- **macOS/Linux**: `~/.config/terma/config.toml`
  - `export TERMA_DEBUG=1 ` for logging
  

### 2. Add Your API Key

Edit the `config.toml` file and add your API key.

#### For OpenAI (GPT-5-mini)

```toml
[llm]
default_provider = "openai"
default_model = "gpt-5-mini"

[llm.openai]
api_key = "sk-proj-YOUR_ACTUAL_API_KEY_HERE"
```

Get your OpenAI API key from: https://platform.openai.com/api-keys

#### For Anthropic (Claude)

```toml
[llm]
default_provider = "anthropic"
default_model = "claude-3-5-sonnet-20241022"

[llm.anthropic]
api_key = "sk-ant-YOUR_ACTUAL_API_KEY_HERE"
```

Get your Anthropic API key from: https://console.anthropic.com/settings/keys

#### For Local Models (Ollama)

```toml
[llm]
default_provider = "ollama"
default_model = "llama2"

[llm.local]
base_url = "http://localhost:11434"
```

Install Ollama from: https://ollama.ai

### 3. Test Your Setup

Run terma with a simple query:

```bash
# Activate your virtual environment first
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # macOS/Linux

# Test with a simple question
terma "what is the current directory?" --no-context
```

If configured correctly, you should see:
1. The LLM's response
2. If it suggests a command, you'll be prompted to approve it
3. The command will execute and show results

## Running Integration Tests

To run integration tests that use real API calls:

```bash
# Make sure your API key is configured first
pytest tests/ -v -m integration
```

**Note**: Integration tests will make real API calls and consume credits/tokens.

## Troubleshooting

### "API key not found" error

Make sure you've:
1. Created the config file in the correct location
2. Added your API key without quotes around it
3. Saved the file

### "Rate limit exceeded" error

You've hit your API provider's rate limit. Wait a few minutes and try again.

### "Invalid API key" error

Double-check:
1. You copied the full API key (they're usually quite long)
2. You're using the correct provider setting
3. Your API key hasn't been revoked

## Cost Considerations

- **GPT-5-mini**: Significantly cheaper and works well for most tasks
- **Claude**: Pricing varies by tier
- **Local (Ollama)**: Free but requires local resources

For development/testing, consider using:
- `gpt-5-mini` for quick tests
- `--no-context` flag to reduce token usage
- Local models for unlimited free testing

## Example Session

```bash
# Start terma with a question
terma "show me the 5 largest files in this directory"

# You'll see:
# 1. LLM explains what it will do
# 2. Proposes a command (e.g., "du -ah . | sort -rh | head -5")
# 3. Asks for approval: [a]pprove [r]eject [m]odify:
# 4. Type 'a' to run the command
# 5. See the results and any follow-up from the LLM
```

## Security Notes

- **Never commit your API keys** to version control
- The `config.toml` file is in `.gitignore` by default
- API keys are stored in plain text, so protect your config directory
- Use environment-specific API keys (separate dev/prod keys)

