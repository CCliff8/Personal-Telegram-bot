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
    startup.py                # Railway startup: decode credentials + sync data from repo
    skills/
        morning_brief.py      # Weather + calendar + Gmail + Haiku
        evening_reflection.py # Multi-turn input + Haiku structuring + save to reflections/
        linkedin_draft.py     # Reads reflections/ + Haiku + saves to drafts/
        quiz.py               # Generate question + evaluate answer (two Haiku calls)
        remind.py             # Parse delay string, schedule one-shot threading.Timer
        chat.py               # Multi-turn Haiku conversation with memory.md context
        read.py               # Accumulate notes + Haiku structure + save to Notes/ (/notes)
        calendar_skill.py     # Google Calendar create/delete with NL extraction via Haiku

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

**409 Conflict:** Telegram only allows one active long-poll connection per token. During Railway rolling deploys, two instances briefly overlap and the new one gets a 409. `telegram.py` handles this by sleeping 5 seconds and returning `[]` instead of crashing, so the new instance backs off until the old one shuts down.

---

## Router

`Router` holds an ordered list of `(match_fn, handler_fn)` pairs. `dispatch()` walks the list and calls the first handler whose `match_fn` returns `True`. **Order matters** — more specific handlers must be registered before broader ones.

Handler order in `__init__.py`:
1. `/brief` — morning brief on demand (blocked if session active)
2. `/reflect` — start evening reflection (blocked if session active)
3. `/done` (reflection active) — finish and save reflection
4. Reflection accumulator — collects messages while reflection is active
5. `/notes` — start note-taking session (blocked if session active)
6. `/done` (notes active) — structure, save, and send note
7. Notes accumulator — collects messages while notes session is active
8. `/chat` — start chat session (blocked if session active)
9. Chat message handler — reply via Haiku while chat is active
10. `/linkedin` — generate LinkedIn draft (blocked if session active)
11. `/testme` — generate quiz question (blocked if session active)
12. Quiz answer handler — evaluate and reset
13. `/remind` — schedule one-shot reminder (blocked if session active)
14. `/calendar` — create or delete a Google Calendar event (blocked if session active)
15. Calendar answer handler — handle multi-turn clarification or confirmation
16. `/done` fallback — clears all state, cancels any active session

`Router.state` is a plain dict persisted to `state.json` after each handled message.

---

## Session mutual exclusion

`SESSION_KEYS` maps state keys to command names:

```python
SESSION_KEYS = {
    "awaiting_reflection": "/reflect",
    "read_title": "/notes",
    "in_chat": "/chat",
    "awaiting_quiz_answer": "/testme",
    "calendar_pending": "/calendar",
}
```

`_active_session(state)` returns the active command name or `None`. `_busy(chat_id)` calls it and sends a blocking message if a session is running. All command handlers call `_busy()` first. Only `/done` bypasses this check.

All session accumulators use `not _is_command(msg["text"])` in their match function so commands are never swallowed by an active session.

**`/done` as universal cancel:** There are specific `/done` handlers for reflection and notes (they save before clearing state). All other active sessions (chat, quiz, calendar) are caught by a final `/done` fallback that simply calls `router.state.clear()`. This means `/done` always works regardless of the active session.

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
3. `/done` → concatenate → Haiku structures → save to `reflections/YYYY-MM-DD.md` → push to GitHub repo → reset state

If the day's file already exists, the new reflection is appended with `---`.

### LinkedIn draft

1. Load last 6 files from `reflections/` sorted by filename
2. Call Haiku with learn-in-public prompt (hook → built → learned → hard → next → closing)
3. Save to `drafts/YYYY-MM-DD.md` → push to GitHub repo → send to Telegram

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

`memory.md` is loaded on every message and injected as the system prompt. The full session history (`chat_history`) is passed to Haiku each turn. `/done` clears state and ends the session.

### Notes

State keys: `read_title`, `read_messages`

1. `/notes <title>` → store title, start accumulating
2. Messages append to `read_messages`
3. `/done` → concatenate → Haiku structures into Summary + Key Concepts → save to `Notes/<title>.md` → push to GitHub repo → clear state

If the file already exists (same title), content is appended with a date separator.

### Calendar

State keys: `calendar_pending`, `calendar_awaiting`

Handles both create and delete via natural language. The flow:

1. `/calendar <text>` → `extract_intent(text)` calls Haiku, returns JSON with `intent`, `title`, `date`, `time`, `duration_min`, `description`, `location`, `search_query`
2. **Create flow:**
   - `first_missing(fields)` checks required fields in order: title → date → time → duration_min
   - If a field is missing, store `calendar_pending` and ask the question
   - Each answer is parsed by `parse_field(field, text)` (Haiku extracts ISO date / HH:MM / integer minutes)
   - Once all four required fields are present, `create_event(fields)` creates the event and sends confirmation
3. **Delete flow:**
   - `search_events(query, date, time)` queries all writable calendars (not just primary) and filters locally
   - If one match: ask to confirm, then delete on "yes"
   - If multiple matches: list up to 5, ask for a number, then confirm and delete
   - Quote stripping on query (`'calcetto'` → `calcetto`) before case-insensitive substring match

`create_event` / `delete_event` use the Google Calendar API directly. Events are created in the primary calendar; deletes target the specific calendar each event belongs to (stored as `_calendarId`).

---

## Google auth

`get_credentials()` — loads `token.json`, refreshes if expired using the stored refresh token. After every refresh, the updated `token.json` is pushed to the private GitHub repo via `github_storage.write_file()` so the latest token survives Railway restarts.

`run_auth()` — one-time browser OAuth flow. Run via `uv run personal-agent-auth`. Saves `token.json` locally.

Scopes: `gmail.readonly`, `calendar` — Gmail is read-only; Calendar is full read/write (required for event creation and deletion).

---

## GitHub storage

`github_storage.py` reads and writes files to the private repo (`CCliff8/personal-agent-data`) via the GitHub REST API using `httpx`. Auth is via a fine-grained PAT stored in `DATA_REPO_TOKEN`.

If `DATA_REPO_TOKEN` is unset or empty, all calls are silently skipped (no crash). 401/403 responses are also treated as empty (not a crash) — this allows the bot to start cleanly even if the token is misconfigured.

Used for:
- **Write after token refresh** — push updated `token.json` after every Google OAuth refresh
- **Write after every save** — reflections, LinkedIn drafts, and notes are pushed to the repo immediately after being saved locally
- **Read on startup** — `sync_data_from_repo()` pulls reflections/, drafts/, and Notes/ before the bot starts

---

## Railway startup

On Railway the disk is ephemeral — no files survive a restart. `startup.py` handles this:

1. `decode_google_credentials()`:
   - `credentials.json` — decoded from `GOOGLE_CREDENTIALS_B64` env var on every startup
   - `token.json` — pulled from private GitHub repo first (latest refreshed token); falls back to `GOOGLE_TOKEN_B64` env var if not found in the repo
2. `sync_data_from_repo()` — pulls all files from `reflections/`, `drafts/`, and `Notes/` from the private repo to local disk, so skills can read history immediately

Both steps run before anything else in `main()` and are wrapped in `try/except` so a bad GitHub token doesn't crash startup.

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
| `reflections/` | Yes — private GitHub repo after every save |
| `drafts/` | Yes — private GitHub repo after every save |
| `Notes/` | Yes — private GitHub repo after every save |
| Reminders | In-memory only — lost on restart |
