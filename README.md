# Personal Agent

A single-process Telegram bot with long polling, a chat ID allowlist, and a skill-based router. Built from scratch using the Telegram Bot API directly (no bot framework).

## Features

- **Morning brief** (`/brief`) — daily summary of Milan weather, Google Calendar events, and unread Gmail, written by Claude Haiku. Fires automatically at 07:00 Milan time.
- **Evening reflection** (`/reflect`) — bot prompts you with four questions; reply across one or more messages, send `/done` when finished. Claude Haiku structures your dump into a dated note saved to `reflections/YYYY-MM-DD.md`. Fires automatically at 21:00 Milan time. Session expires after 5 minutes without `/done`.
- **LinkedIn draft** (`/linkedin`) — reads last 6 reflection files and generates a learn-in-public LinkedIn post saved to `drafts/YYYY-MM-DD.md`. Fires automatically every Sunday at 18:00 Milan time.
- **Quiz** (`/testme <topic>`) — Haiku generates one question on the topic you specify, you answer, Haiku evaluates with brief feedback and suggests what to deep dive. One question per command.
- **Reminders** (`/remind <message> in <time>`) — set one-shot reminders. Supports `m`, `h`, `d`. Lost on restart.
- **Chat** (`/chat`) — multi-turn conversation with Claude Haiku. Loads `memory.md` as personal context. Send `/exit` to end.
- **Reading notes** (`/read <title>`) — dump notes freely across messages, send `/done` to have Haiku structure them into Summary + Key Concepts and save to `Notes/<title>.md`.
- **Mutual exclusion** — only one session-based command can be active at a time. `/exit` always cancels.

## Requirements

- Python 3.9+
- [uv](https://docs.astral.sh/uv/)
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- A Google Cloud project with Gmail API and Google Calendar API enabled
- An Anthropic API key

## Setup

### 1. Clone and install

```bash
git clone <repo-url>
cd personal-agent-from-scratch
uv sync
```

### 2. Environment variables

Create a `.env` file in the project root:

```
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
ANTHROPIC_API_KEY=your_key_here
```

`TELEGRAM_CHAT_ID` is the allowlist — only messages from this chat ID are processed. Multiple IDs can be comma-separated.

### 3. Google credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project and enable **Gmail API** and **Google Calendar API**
3. Create an OAuth 2.0 credential (Desktop app type) and download `credentials.json` to the project root
4. Run the one-time auth flow:

```bash
uv run personal-agent-auth
```

A browser window opens — log in and click Allow. This saves `token.json` locally (auto-refreshes, never needed again).

### 4. Fill in memory.md

Edit `memory.md` at the project root with personal context (projects, goals, preferences). This is injected into every `/chat` session.

### 5. Run

```bash
uv run personal-agent-from-scratch
```

On startup the bot sends a command list to Telegram. Unrecognised messages are silently ignored.

## Commands

| Command | Description |
|---|---|
| `/brief` | Trigger morning brief on demand |
| `/reflect` | Start evening reflection session |
| `/done` | Save and finish reflection or reading session |
| `/linkedin` | Generate LinkedIn draft from last 6 reflections |
| `/testme <topic>` | Get quizzed on any topic |
| `/remind <message> in <time>` | Set a reminder (10m, 2h, 1d) |
| `/chat` | Start a conversation with Haiku |
| `/read <title>` | Start a reading note session |
| `/exit` | Cancel any active session |
