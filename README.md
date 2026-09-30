# Personal Agent

A personal Telegram bot powered by Claude Haiku. It runs 24/7 on Railway, connects to your Google account, and acts as a daily productivity assistant — morning briefs, evening reflections, LinkedIn drafts, reminders, quizzes, and a context-aware chat.

Everything is manual and on-demand. No scheduled messages.

---

## What it does

| Command | Description |
|---|---|
| `/brief` | Morning brief: Milan weather, today's calendar events, unread Gmail — summarised by Haiku |
| `/reflect` | Start an evening reflection. Answer 4 questions across multiple messages, send `/done` to save |
| `/done` | Finish and save the current reflection or reading session |
| `/linkedin` | Generate a learn-in-public LinkedIn post from your last 6 reflections |
| `/testme <topic>` | Get quizzed on any topic. Haiku asks a question, you answer, Haiku evaluates |
| `/remind <message> in <time>` | Set a one-shot reminder. Supports `10m`, `2h`, `1d` |
| `/chat` | Multi-turn conversation with Haiku, loaded with your personal context from `memory.md` |
| `/read <title>` | Dump notes across multiple messages, send `/done` to have Haiku structure and save them |
| `/exit` | Cancel any active session |

Only one session-based command can run at a time. All others are blocked until you `/exit` or `/done`.

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- A Telegram bot token — create one via [@BotFather](https://t.me/BotFather)
- An [Anthropic API key](https://console.anthropic.com)
- A Google Cloud project with **Gmail API** and **Google Calendar API** enabled
- A [Railway](https://railway.app) account (for cloud deployment)
- A private GitHub repository (for persisting data across Railway restarts)

---

## Local setup

### 1. Clone and install

```bash
git clone https://github.com/CCliff8/personal-agent-from-scratch
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

`TELEGRAM_CHAT_ID` is the allowlist — only messages from this ID are processed. To find yours, message [@userinfobot](https://t.me/userinfobot) on Telegram.

### 3. Google credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project, enable **Gmail API** and **Google Calendar API**
3. Create an **OAuth 2.0 credential** (Desktop app type) and download `credentials.json` to the project root
4. Run the one-time auth flow:

```bash
uv run personal-agent-auth
```

A browser window opens — log in and click Allow. This saves `token.json` locally. It auto-refreshes and never needs to be run again.

### 4. Personal context

Copy the template and fill it in:

```bash
cp memory.example.md memory.md
```

Edit `memory.md` with your name, role, current projects, and preferences. This is injected as context into every `/chat` session.

### 5. Run locally

```bash
uv run personal-agent-from-scratch
```

The bot sends a startup message to Telegram listing all commands.

---

## Deploy to Railway

Railway runs the bot 24/7. Because Railway's disk is ephemeral (wiped on restart), secrets and data are stored externally.

### What goes where

| Data | Where it lives |
|---|---|
| Secrets (API keys, tokens) | Railway environment variables |
| Google OAuth token (refreshed periodically) | Private GitHub repo |
| Reflections, drafts, notes | Railway disk (ephemeral — **not yet persisted**, see Known limitations) |

### Steps

**1. Create a private GitHub repo** for your personal data (e.g. `personal-agent-data`).

**2. Create a fine-grained GitHub PAT** with access to that repo only:
- GitHub → Settings → Developer settings → Fine-grained tokens
- Repository access: only `personal-agent-data`
- Permissions: Contents → Read and write

**3. Base64-encode your Google files** (run locally):

```bash
base64 -i credentials.json | tr -d '\n'
base64 -i token.json | tr -d '\n'
```

**4. Sign up on [Railway](https://railway.app)**, create a new project from your GitHub repo.

**5. Set environment variables** in Railway → your service → Variables:

| Variable | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather token |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GOOGLE_CREDENTIALS_B64` | Base64 output of `credentials.json` |
| `GOOGLE_TOKEN_B64` | Base64 output of `token.json` |
| `DATA_REPO_TOKEN` | GitHub PAT from step 2 |

**6.** Railway auto-deploys. The bot comes online and sends you the startup message.

---

## Known limitations

- **Reflections, drafts, and notes are not yet persisted** to the private GitHub repo. They survive normal operation but are lost if Railway restarts the container. This will be fixed in a future update.
- **Reminders are lost on restart.** They run in-memory and are not persisted.
- The bot is single-user by design. To use it with others, they need to deploy their own instance.
