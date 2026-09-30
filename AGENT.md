# Agent Architecture

Personal technical reference for how this project is structured and why.

---

## File map

```
src/personal_agent_from_scratch/
    __init__.py               # Entry point: main(), polling loop, all handler registrations
    telegram.py               # TelegramClient: get_updates() + send_message()
    router.py                 # Router: match-based dispatch + state.json persistence
    google_auth.py            # OAuth helpers: get_credentials() + run_auth()
    github_storage.py         # Read/write files to private GitHub repo via REST API
    startup.py                # Railway startup: decode credentials from env vars
    skills/
        morning_brief.py      # Weather + calendar + Gmail + Haiku
        evening_reflection.py # Multi-turn input + Haiku structuring + save to reflections/
        linkedin_draft.py     # Reads reflections/ + Haiku + saves to drafts/
        quiz.py               # Generate question + evaluate answer (two Haiku calls)
        remind.py             # Parse delay string, schedule one-shot threading.Timer
        chat.py               # Multi-turn Haiku conversation with memory.md context
        read.py               # Accumulate notes + Haiku structure + save to Notes/

memory.example.md             # Public template — copy to memory.md and fill in
memory.md                     # Personal context injected into /chat (gitignored)
reflections/                  # Saved reflection notes (gitignored, one .md per day)
drafts/                       # Saved LinkedIn drafts (gitignored, one .md per week)
Notes/                        # Saved reading notes (gitignored, one .md per title)
railway.json                  # Railway start command config
railpack.json                 # Railpack build config (start command)
.python-version               # Pins Python 3.11 for Railway/mise
```

---

## Polling loop

`main()` runs a `while True` loop calling `getUpdates` on the Telegram Bot API with `timeout=30` (long polling). Telegram holds the connection open for up to 30 seconds if no messages arrive, then returns an empty list. When a message arrives it returns immediately.

After each batch, `offset` is set to `last_update_id + 1`. This is sent on the next call to tell Telegram to drop all already-acknowledged updates from the queue.

Messages not in the `TELEGRAM_CHAT_ID` allowlist are silently ignored.

---

## Router

`Router` holds an ordered list of `(match_fn, handler_fn)` pairs. `dispatch()` walks the list and calls the first handler whose `match_fn` returns `True`. **Order matters** — more specific handlers must be registered before broader ones.

Handler order in `__init__.py`:
1. `/exit` — clears all state, cancels any active session
2. `/brief` — morning brief on demand
3. `/reflect` — start evening reflection (blocked if session active)
4. `/done` (reflection active) — finish and save reflection
5. Reflection accumulator — collects messages while reflection is active
6. `/read` — start reading session (blocked if session active)
7. `/done` (read active) — structure, save, and send reading note
8. Read accumulator — collects notes while read is active
9. `/chat` — start chat session (blocked if session active)
10. Chat message handler — reply via Haiku while chat is active
11. `/linkedin` — generate LinkedIn draft (blocked if session active)
12. `/testme` — generate quiz question (blocked if session active)
13. Quiz answer handler — evaluate and reset
14. `/remind` — schedule one-shot reminder (blocked if session active)

`Router.state` is a plain dict persisted to `state.json` after each handled message.

---

## Session mutual exclusion

`SESSION_KEYS` maps state keys to command names:

```python
SESSION_KEYS = {
    "awaiting_reflection": "/reflect",
    "read_title": "/read",
    "in_chat": "/chat",
    "awaiting_quiz_answer": "/testme",
}
```

`_active_session(state)` returns the active command name or `None`. `_busy(chat_id)` calls it and sends a blocking message if a session is running. All command handlers call `_busy()` first. Only `/exit` and `/done` bypass this.

All session accumulators use `not _is_command(msg["text"])` in their match function so commands are never swallowed by an active session.

**When adding a new command:** add it to `COMMANDS`, register handlers in order, and update the startup message string.

---

## Skills

Each skill is a callable (or module with a small API) that reads data, optionally calls Claude Haiku (`claude-haiku-4-5-20251001`), and returns a result. Steps are fixed — the model only writes prose.

### Morning brief

1. `_weather()` — GET `wttr.in/Milan?format=j1`, extract temp + description
2. `_calendar()` — Google Calendar API, today's events in `Europe/Rome` timezone
3. `_gmail()` — Gmail API, unread messages from last 24 hours (subject + sender only)
4. Build prompt → call Haiku → return text

Steps 2 and 3 are wrapped in `try/except` so a single API failure doesn't break the whole brief.

### Evening reflection

State keys: `awaiting_reflection`, `reflection_expires_at`, `reflection_messages`

1. `/reflect` → bot sends 4-question prompt → sets state
2. Messages accumulate in `reflection_messages`
3. `/done` → concatenate → Haiku structures → save to `reflections/YYYY-MM-DD.md` → reset state
4. Session expires after 5 minutes if `/done` is never sent

If the day's file already exists, the new reflection is appended with `---`.

### LinkedIn draft

1. Load last 6 files from `reflections/` sorted by filename
2. Call Haiku with learn-in-public prompt (hook → built → learned → hard → next → closing)
3. Save to `drafts/YYYY-MM-DD.md`, send to Telegram

### Quiz

State keys: `awaiting_quiz_answer`, `quiz_topic`, `quiz_question`

1. `/testme <topic>` → `generate_question(topic)` → store in state → send question
2. Next non-command message → `evaluate_answer()` → send evaluation → clear state

Haiku uses its training data — no internet access.

### Reminders

`remind.parse()` splits on the last ` in ` in the message (handles "in" appearing in the reminder text), extracts the delay in `m`/`h`/`d`, returns `(message, seconds)`.

A `threading.Timer(seconds, fire)` is started in a background thread. Multiple reminders can coexist. All reminders are lost on process restart.

### Chat

State keys: `in_chat`, `chat_history`

`memory.md` is loaded on every message and injected as the system prompt. The full session history (`chat_history`) is passed to Haiku each turn. `/exit` clears state and ends the session.

### Reading notes

State keys: `read_title`, `read_messages`

1. `/read <title>` → store title, start accumulating
2. Messages append to `read_messages`
3. `/done` → concatenate → Haiku structures into Summary + Key Concepts → save to `Notes/<title>.md` → clear state

If the file already exists (same title), content is appended with a date separator.

---

## Google auth

`get_credentials()` — loads `token.json`, refreshes if expired using the stored refresh token. After every refresh, the updated `token.json` is pushed to the private GitHub repo via `github_storage.write_file()` so the latest token survives Railway restarts.

`run_auth()` — one-time browser OAuth flow. Run via `uv run personal-agent-auth`. Saves `token.json` locally.

Scopes: `gmail.readonly`, `calendar.readonly` — read-only, no write access.

---

## GitHub storage

`github_storage.py` reads and writes files to the private repo (`CCliff8/personal-agent-data`) via the GitHub REST API using `httpx`. Auth is via a fine-grained PAT stored in `DATA_REPO_TOKEN`.

If `DATA_REPO_TOKEN` is unset or empty, all calls are silently skipped (no crash).

Currently used for:
- **Read on startup**: pull latest `token.json` from private repo (has the most recent refreshed token)
- **Write after token refresh**: push updated `token.json` after every Google OAuth refresh

Not yet used for: reflections, drafts, notes (saved to ephemeral Railway disk only).

---

## Railway startup

On Railway the disk is ephemeral — no files survive a restart. `startup.py` handles this:

1. `credentials.json` — decoded from `GOOGLE_CREDENTIALS_B64` env var on every startup
2. `token.json` — pulled from private GitHub repo first (latest refreshed token); falls back to `GOOGLE_TOKEN_B64` env var if not found in the repo

This runs before anything else in `main()`.

---

## Deployment

The bot runs on [Railway](https://railway.app) connected to the public GitHub repo. Every push to `main` triggers an automatic redeploy.

Build system: **Railpack** (Railway's builder). Detects Python + uv from `pyproject.toml`. Start command is defined in `railpack.json`.

Python version is pinned to `3.11` via `.python-version`.

Environment variables are set in Railway → service → Variables. They are never committed to the repo.

---

## Data persistence status

| Data | Persisted? |
|---|---|
| `token.json` | Yes — private GitHub repo after every refresh |
| `state.json` | Local disk — survives normal operation, lost on restart |
| `reflections/` | Local disk only — **not yet persisted** |
| `drafts/` | Local disk only — **not yet persisted** |
| `Notes/` | Local disk only — **not yet persisted** |
| Reminders | In-memory only — lost on restart |
