# Target Feature - Remote Pane Control

## Overview

The **target** feature allows you to run `whai` in one tmux pane while it captures context from and executes commands in another pane. This enables a powerful workflow where you can SSH into remote VMs in separate panes and control them from a central "command" pane - **without installing whai on the remote machines**.

## Requirements

- **tmux** must be running (the feature relies on tmux's `capture-pane` and `send-keys` capabilities)
- All panes must be within the same tmux session

## Quick Start

### 1. Start tmux and create panes

```bash
# Start tmux
tmux

# Split into two panes (Ctrl+b %)
# You now have pane 0 (left) and pane 1 (right)
```

### 2. See your pane numbers

Press `Ctrl+b q` to briefly display pane numbers in each pane.

```
┌─────────────────────────┬─────────────────────────┐
│                         │                         │
│           0             │           1             │
│                         │                         │
└─────────────────────────┴─────────────────────────┘
```

### 3. SSH to remote in target pane

In pane 1 (right), SSH to your remote server:

```bash
ssh user@prod-server.com
```

### 4. Use whai from your local pane with @

In pane 0 (left), use `@` followed by the pane number:

```bash
# Target pane 1
whai @1 "check disk space"

# whai will:
# 1. Capture the terminal context from pane 1
# 2. Send your query to the LLM
# 3. Show suggested commands for approval
# 4. Execute approved commands IN pane 1
```

## Usage

### Syntax

```bash
whai @<pane_number> "your question"
```

### Examples

```bash
# Target pane 1
whai @1 "why is nginx failing"

# Target pane 2
whai @2 "check memory usage"

# Target pane 0 from pane 1
whai @0 "what files are here"
```

## How It Works

```
┌─────────────────────────────┬─────────────────────────────┐
│ Pane 0 (Local Control)      │ Pane 1 (Remote SSH)         │
│                             │                             │
│                             │ $ ssh user@prod-server      │
│                             │ [prod]$ docker ps           │
│                             │ Error: daemon not running   │
│                             │                             │
│ $ whai @1 "fix docker"      │                             │
│                             │                             │
│ [Captures pane 1 context]   │                             │
│ [LLM analyzes error]        │                             │
│                             │                             │
│ Suggested command:          │                             │
│ sudo systemctl start docker │                             │
│ [a]pprove? a                │                             │
│                             │                             │
│                             │ [prod]$ sudo systemctl      │
│                             │         start docker        │
│                             │ [docker starts]             │
│                             │                             │
└─────────────────────────────┴─────────────────────────────┘
```

### Technical Flow

1. **Pane Identification**: `Ctrl+b q` shows pane numbers; use that number with `@`

2. **Context Capture**: `whai @1` uses `tmux capture-pane -t 1` to grab pane 1's visible content and scrollback

3. **Command Execution**: Approved commands are sent using `tmux send-keys -t 1 "<command>" Enter`

## Multi-VM Workflow

Open multiple panes for different VMs:

```bash
# Terminal layout (use Ctrl+b q to see numbers):
# ┌─────────┬─────────┬─────────┐
# │    0    │    1    │    2    │
# │ Control │ prod-vm │ staging │
# └─────────┴─────────┴─────────┘

# In pane 1: ssh admin@prod.example.com
# In pane 2: ssh admin@staging.example.com

# In pane 0 (control):
whai @1 "check nginx status"
whai @2 "tail error logs"
```

## Tmux Cheat Sheet

For users new to tmux:

| Action | Shortcut |
|--------|----------|
| Start tmux | `tmux` |
| **Show pane numbers** | `Ctrl+b q` |
| Split pane vertically | `Ctrl+b %` |
| Split pane horizontally | `Ctrl+b "` |
| Switch between panes | `Ctrl+b arrow-key` |
| Close pane | `exit` or `Ctrl+d` |
| Detach from session | `Ctrl+b d` |
| Reattach to session | `tmux attach` |
| List sessions | `tmux ls` |

## Advanced: Using Pane IDs

Besides pane numbers, you can also use tmux pane IDs (shown with `echo $TMUX_PANE`):

```bash
# Using pane ID directly
whai @%5 "check logs"
```

## Limitations

- **Requires tmux**: This feature only works inside a tmux session
- **Same tmux session**: Target pane must be in the same tmux session
- **Pane must exist**: If pane number doesn't exist, whai will show an error

## Troubleshooting

### "Target feature requires tmux"
You must run whai inside a tmux session. Start one with `tmux`.

### "Pane X does not exist"
The pane number is invalid. Press `Ctrl+b q` to see available pane numbers.

### Commands not executing in target pane
Ensure the target pane is at a shell prompt (not in an editor, pager, or waiting for input).

### "Not in tmux session"
Run `tmux` first, then split panes with `Ctrl+b %` or `Ctrl+b "`.
