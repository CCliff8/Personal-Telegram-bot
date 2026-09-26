# Personal Agent

A single-process Telegram bot with long polling, a chat ID allowlist, and a skill-based router. Built from scratch using the Telegram Bot API directly (no bot framework).

## Features

- **Echo handler** — replies with whatever text you send
- **Morning brief** (`/brief`) — daily summary of Milan weather, Google Calendar events, and unread Gmail, written by Claude Haiku. Fires automatically at 07:00 Milan time.
- **Evening reflection** (`/reflect`) — bot prompts you with four questions; reply across one or more messages, send `/done` when finished. Claude Haiku structures your dump into a dated note saved to `reflections/YYYY-MM-DD.md`. Fires automatically at 21:00 Milan time. If you don't send `/done` within 5 minutes the session expires.

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

### 4. Run

```bash
uv run personal-agent-from-scratch
```

Send `/brief` to trigger the morning brief on demand, `/reflect` to start an evening reflection session.
