# whai - Terminal Assistant

<!-- TODO: Add demo video showcasing the tool in action -->

## Table of Contents

- [What is it](#what-is-it)
- [Core Features](#core-features)
- [Quick Examples](#quick-examples)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Key Features](#key-features)
- [FAQ](#faq)
- [Acknowledgments](#acknowledgments)

## What is it

`whai` is a lightweight and fast AI terminal assistant that integrates directly into your native shell.
The philosophy of `whai` is to never interrupt your workflow. You use your terminal as you normally would. 
It is not a sub-shell or a separate REPL; it is a single, fast binary that you call on-demand.
When you get stuck, need a command, or encounter an error, you simply call `whai` for immediate help.

### Core Features

* **Analyze Previous Errors:** If a command fails, you don't need to copy-paste. Just call `whai` (no arguments needed!) or ask `whai why did that fail?`.
    It reads the failed command and its full error output from your terminal history to provide an immediate diagnosis and solution. *Note: Command output is available when running inside tmux or a `whai shell` session. Otherwise, the model will only see your commands but not their outputs.*
* **Persistent Roles (Memory):** `whai` uses simple, file-based "Roles" to provide persistent memory. This is the core of its customization. You define your context *once*, what machine you are on, what tools are available, your personal preferences, and how you like to work, and `whai` retains this context for all future interactions.
* **Full Session Context:** When running inside `tmux` or a `whai shell` session, `whai` securely reads your command history and outputs to understand both what you ran and what happened. This provides intelligent, multi-step assistance based on the actual state of your terminal.
* **On-Demand Assistance:** Get help exactly when you need it, from command generation to complex debugging, right in your active shell:

    `> whai check my docker containers logs for errors`

    `> whai "how do I debug this high resource usage?"`

* **Safe by Design:** No command is *ever* executed without your explicit `[a]pprove` / `[r]eject` confirmation.
* **Model-Agnostic:** Natively supports OpenAI, Gemini, Anthropic, local Ollama models, and more.

## Quick Examples

See `whai` in action:

### Example 1: Running a command

```zsh
$ whai give me the biggest folder here
Info: Model: gpt-5-mini | Role: default
I'll list all top-level directories (including hidden ones), 
compute their disk usage, sort them, and show the largest 
few with human-readable sizes.

I'll run this command:
find . -maxdepth 1 -mindepth 1 -type d -print0 | \
  xargs -0 du -sk 2>/dev/null | \
  sort -n | tail -n 5 | \
  awk '{print $1 "\t" $2}' | \
  numfmt --to=iec-i --suffix=B --field=1,1

Breakdown of what each part does:
- find . -maxdepth 1 -mindepth 1 -type d: Find directories at 
  current level only (excludes . and ..)
- -print0: Use null separator to safely handle spaces in 
  directory names
- xargs -0 du -sk: Pass each directory to du to get disk usage 
  in kilobytes, 2>/dev/null suppresses errors
- sort -n: Sort numerically by size
- tail -n 5: Show the 5 largest entries
- awk '{print $1 "\t" $2}': Format output as size (tab) path
- numfmt --to=iec-i --suffix=B --field=1,1: Convert sizes to 
  human-readable format (KiB, MiB, etc.)

╭─────────────────────── Proposed command ────────────────────────╮
│ find . -maxdepth 1 -mindepth 1 -type d -print0 |                │
│   xargs -0 du -sk 2>/dev/null |                                 │
│   sort -n | tail -n 5 |                                         │
│   awk '{print $1 "\t" $2}' |                                    │
│   numfmt --to=iec-i --suffix=B --field=1,1                      │
╰─────────────────────────────────────────────────────────────────╯
[a]pprove / [r]eject / [m]odify: a

╭─────────────────── Output ────────────────────╮
│ 440B ./tests                                  │
│ 1.4KiB ./.git                                 │
│ 87KiB ./.venv_tmp                             │
│ 108KiB ./.venv                                │
│ 123KiB ./.venv-linux                          │
╰───────────────────────────────────────────────╯

Result (interpretation)
- The largest top-level directory here is ./.venv-linux 
  with ~123KiB.

Next steps (options)
- Show the top N largest items anywhere under the current 
  tree (files+dirs):
  - du -ah . 2>/dev/null | sort -rh | head -n 30
- Show only directories, recursively, largest first:
  - du -h --max-depth=3 2>/dev/null | sort -hr | head -n 30
```

### Example 2: Troubleshooting terminal output

```zsh
$ uv pip install requirements.txt
Using Python 3.11.9 environment at: .venv-linux
  × No solution found when resolving dependencies:
  ╰─▶ Because requirements-txt was not found in the package registry...

$ whai what is the problem
Info: Model: gpt-5-mini | Role: default
What's happening
- You ran: uv pip install requirements.txt
- pip treated "requirements.txt" as the name of a package to 
  download from the package index, not as a file of requirements.
- The resolver tried to find a package called (normalized) 
  "requirements-txt" on PyPI and failed, so it reports the 
  dependencies are unsatisfiable.

How to fix it
- Use the -r (or --requirement) flag so pip reads the file 
  instead of treating it as a package name.

Commands you can run
1) Check the requirements file exists:
ls -l requirements.txt

2) Install from the file (match how you invoked pip):
uv pip install -r requirements.txt

Do you want me to:
- run the ls to confirm the file exists, or
- run the install command for you now?
```

### Example 3: Calling whai without arguments

```zsh
$ git push origin main
To https://github.com/user/repo.git
 ! [rejected]        main -> main (non-fast-forward)
error: failed to push some refs to 'https://github.com/user/repo.git'
hint: Updates were rejected because the tip of your current branch is behind
hint: its remote counterpart. Integrate the remote changes (e.g.
hint: 'git pull ...') before pushing again.

$ whai
Info: Model: gpt-5-mini | Role: default
What's happening
- You tried to push your local branch "main" to the remote, 
  but git rejected it.
- Your local branch is behind the remote branch—someone else 
  pushed changes to the remote that you don't have locally.
- Git won't let you push because it would overwrite those 
  remote changes.

How to fix it
- Pull the remote changes first, then push. This integrates 
  the remote commits with your local ones.

Commands you can run
1) See what commits are on the remote but not locally:
git fetch
git log HEAD..origin/main

2) Pull and merge the remote changes:
git pull origin main

3) After resolving any merge conflicts (if they occur), push again:
git push origin main

Do you want me to run git pull for you now?
```

### Example 4: Asking questions

```zsh
$ whai "Quick how do I exit Vim??"
Info: Model: gpt-5-mini | Role: default
I'll show the quick ways to exit Vim and what each one does.

1) Get to Normal mode
- Press Esc (or Ctrl-[) until you stop inserting text. If Esc doesn't respond, try Ctrl-C.

2) Common exit commands (type them in Normal mode, then press Enter)
- :q
  - Quit (works only if no changes since last save).
- :q!
  - Quit and discard any unsaved changes.
- :wq
  - Write (save) and quit.
- :x
  - Write (only if changed) and quit (similar to :wq).

3) Shortcuts
- ZZ (Shift+Z twice) — save and quit (same as :wq if there are changes).
- ZQ — quit without saving (same as :q!).
```

## Installation

### Option 1: uv (Recommended)

```zsh
uv tool install whai
```
*Or even without installing it!*
```zsh
uvx whai "your command"
```

### Option 2: pipx

```zsh
pipx install whai
```

### Option 3: pip

```zsh
pip install whai
```

### Option 4: From source

```zsh
git clone https://github.com/gael-vanderlee/whai.git
cd whai
pip install -e .
```

## Quick Start

### 1. Configure your API key

On first run, `whai` launches an interactive configuration wizard:

```zsh
whai --interactive-config
```

Or edit `~/.config/whai/config.toml` directly:

```zsh
[llm]
default_provider = "openai"

[llm.openai]
api_key = "sk-proj-your-key-here"
default_model = "gpt-5-mini"
```

Get API keys from:
- [OpenAI Platform](https://platform.openai.com/api-keys)
- [Anthropic Console](https://console.anthropic.com/)
- [Azure Portal](https://portal.azure.com/) (for Azure OpenAI)
- [Google AI Studio](https://aistudio.google.com/app/api-keys) (for Gemini) 

#### Using Local Models (LM Studio)

To use a local model with LM Studio:

1. **Enable the server in LM Studio:**
   - Open LM Studio
   - Go to the Developer menu
   - Enable the server toggle

2. **Configure whai:**
   ```zsh
   whai --interactive-config
   ```
   - Select `lm_studio` as the provider
   - Enter the API base URL: `http://localhost:1234/v1`
   - Enter the model name without prefix (e.g., `llama-3-8b-instruct`)
   
   Note: Model names are stored without provider prefixes in the config file. Prefixes are automatically added at runtime when needed.

3. **Check available models:**
   ```zsh
   curl http://localhost:1234/v1/models
   ```

### 2. Start using whai

```zsh
whai "your question"
```

That's it! `whai` will:
- Read your terminal context (commands + output if in tmux or `whai shell`, commands only otherwise)
- Send your question to the configured LLM
- Suggest commands with `[a]pprove` / `[r]eject` / `[m]odify` prompts
- Execute approved commands and continue the conversation

> **Tip:** Quotes are not necessary, but do use them if you use special characters like `'` or `?`
> ```bash
> whai show me the biggest file here
> whai "what's the biggest file?"
> ```

> **Getting Help:** For a complete list of command-line options and flags, run `whai --help`.

## Key Features

### Roles

Roles allow you to customize `whai`'s behavior and responses. More importantly, they let you save information you don't have to repeat yourself in every conversation.

lets create a role that tells `whai` to respond only in emoji:

```zsh
$ whai role create emoji # "Answer using only emojis"
$ whai can you tell me the plot of the first Shrek movie --role emoji
Info: Model: gpt-5-mini | Role: emoji
👑👸💤🐉🏰
👹🏞️🕳️➡️🏰🐴😂
⚔️🐉🔥💨👸
👹❤️👸💚
🌅💋✨💚💚
🎉🎶🧅
```

But more practically, roles let you store:
- Your system information (OS, available tools, paths)
- Your preferences (shell style, preferred commands, workflows)
- Environment constraints (what you can/can't do, security policies)
- Project-specific context (tools in use, conventions, setup)

```zsh
# Create a new role
whai role create my-workflow

# Use it
whai "help me with this task" -r my-workflow

# List all roles
whai role list
```

For a complete list of role management commands, run `whai role --help`.

Define it once, use it everywhere. Roles are stored in `~/.config/whai/roles/` as Markdown files with YAML frontmatter, like so:
```yaml
---
model: gpt-5-mini
# Optional parameters you can add:
# provider: openai                # Override default provider for this role
# temperature: 0.3                # Only used when supported by the selected model
---
You are a helpful terminal assistant.
Describe context, behaviors, tone, and constraints here.

```

**Available Providers:**

You can specify any of the following providers in the `provider` field:

- `openai` - OpenAI models (e.g., `gpt-5-mini`, `gpt-4`)
- `anthropic` - Anthropic Claude models (e.g., `claude-3-5-sonnet-20241022`)
- `gemini` - Google Gemini models (e.g., `gemini-2.5-flash`)
- `azure_openai` - Azure OpenAI service
- `ollama` - Local Ollama models (requires local Ollama instance)
- `lm_studio` - LM Studio local models (requires LM Studio server running)

The provider must be configured in your `~/.config/whai/config.toml` file before it can be used. If no `provider` is specified in the role, `whai` uses the default provider from your configuration.

The default role is defined in the config.

### Context Awareness

`whai` automatically captures context from:
- **tmux scrollback** (recommended): Full commands + output for intelligent debugging *(only available when running in tmux)*
- **Recorded shell sessions**: Full commands + output when using `whai shell` *(deep context without tmux)*
- **Shell history** (fallback): Recent commands only when not in tmux *(command output is not available in this mode)*

#### Recorded Shell Sessions

For deep context without tmux, use `whai shell` to launch an interactive shell with session recording:

```zsh
whai shell
```

This command:
- Opens your normal shell (bash, zsh, fish, or PowerShell) with identical behavior
- Records all commands and outputs to a session log
- Provides deep context (commands + outputs) to whai without requiring tmux
- Preloads the LLM library, making future `whai` calls significantly faster (1-4 seconds faster)

The recorded session behaves exactly like your normal shell - same prompt, keybindings, history, and environment. The only difference is that `whai` can now access full command outputs for better assistance.

**To exit:** Type `exit` in the shell to return to your previous terminal.

**Options:**
```zsh
# Launch with a specific shell
whai shell --shell zsh

# Specify a custom log path
whai shell --log ~/my-session.log
```

Session logs are stored temporarily during the session and are deleted when you exit the shell.
When you run `whai` from within a recorded shell session, it automatically uses the in-session log for deep context.

### Safety First

- Every command requires explicit approval
- Modify commands before execution
- Commands run in isolated subprocess (won't affect your main shell)
- Press `Ctrl+C` to interrupt anytime

## FAQ

### How is this different from [insert app here] ?

`whai` is integrated into your terminal with full context awareness. It sees your command history and can execute commands.
Most terminal assistants either require you to explicitely start a REPL loop which takes you out of your usual workflow, don't allow for roles, or don't allow to mix natural language conversation and shell execution. 
I wanted something that's flexible, understands you, and is always ready to help while leaving you in control.

### Does it send my terminal history to the LLM?

Only when you run `whai`.
It captures recent history (50 last commands), tmux scrollback (commands + output), or recorded shell session content (commands + output while the session is active) and includes it in the request.
If you use a remote API model, it will see your recent terminal history.
You can disable this with the `--no-context` flag.

### Can I use it with local models?

Yes! Configure any LiteLLM-compatible provider, including Ollama and LMStudio for local models. See the configuration section above.

## Acknowledgments

Built with [LiteLLM](https://github.com/BerriAI/litellm) for multi-provider support, [Typer](https://typer.tiangolo.com/) for the CLI, and [Rich](https://github.com/Textualize/rich) for pretty terminal output.
