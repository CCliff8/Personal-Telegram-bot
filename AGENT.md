# Agent Architecture

Personal reference for how this project is structured and why.

## File map

```
src/personal_agent_from_scratch/
    __init__.py               # Entry point: main(), polling loop, APScheduler, all handlers
    telegram.py               # TelegramClient: get_updates() + send_message()
    router.py                 # Router: match-based dispatch + state.json
    google_auth.py            # OAuth helpers: get_credentials() + run_auth()
    skills/
        morning_brief.py      # Morning brief: weather + calendar + gmail + Haiku
        evening_reflection.py # Evening reflection: multi-turn input + Haiku structuring
        linkedin_draft.py     # LinkedIn draft: reads reflections + Haiku + saves to drafts/
        quiz.py               # Quiz: generate question + evaluate answer (two-step stateful)
        remind.py             # Reminder: parse delay string, schedule one-shot job
        chat.py               # Chat: multi-turn Haiku conversation with memory.md context
        read.py               # Reading notes: accumulate + Haiku structure + save to Notes/

memory.md                     # Personal context injected into /chat (manual, not gitignored)
reflections/                  # Saved reflection notes (gitignored, one .md per day)
drafts/                       # Saved LinkedIn drafts (gitignored, one .md per week)
Notes/                        # Saved reading notes (gitignored, one .md per title)
```

## How the polling loop works

`main()` runs a `while True` that calls `getUpdates` on the Telegram API with `timeout=30` (long polling). Telegram holds the connection open up to 30 s if no messages arrive, then returns an empty list. When a message arrives it returns immediately.

After each batch, `offset` is set to `last_update_id + 1`. This is sent on the next call and tells Telegram to drop all already-seen updates from the queue — it's the acknowledgement mechanism.

Messages not in the `chat_id` allowlist are silently ignored.

## Router

`Router` holds an ordered list of `(match_fn, handler_fn)` pairs. `dispatch()` walks the list and calls the first handler whose `match_fn` returns true. **Order matters** — more specific handlers must be registered before catch-all ones.

Current handler order in `__init__.py`:
1. `/exit` — clears all state, cancels any active session
2. `/brief` — morning brief on demand
3. `/reflect` — start evening reflection (blocked if session active)
4. `/done` (reflection active) — finish and save reflection
5. Reflection accumulator (if reflection active) — collect messages
6. `/read` — start reading session (blocked if session active)
7. `/done` (read active) — structure, save, and send reading note
8. Read accumulator (if read active) — collect notes
9. `/chat` — start chat session (blocked if session active)
10. Chat message handler (if chat active) — reply via Haiku
11. `/linkedin` — generate LinkedIn draft (blocked if session active)
12. `/testme` — generate quiz question (blocked if session active)
13. Quiz answer handler (if quiz active) — evaluate and reset
14. `/remind` — schedule one-shot reminder (blocked if session active)

Unrecognised messages that match no handler are silently ignored.

`Router.state` is a plain dict persisted to `state.json` after each handled message.

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

`_active_session(state)` returns the active command name or `None`. `_busy(chat_id)` calls it and sends a blocking message if a session is running. All command handlers call `_busy()` before doing anything. Only `/exit` and `/done` are exempt — `/exit` always clears state, `/done` is the valid way to finish a session.

## Command registry

`COMMANDS` is a set of all known command strings:
```python
COMMANDS = {
    "/exit", "/brief", "/reflect", "/done", "/linkedin",
    "/testme", "/remind", "/chat", "/read",
}
```

`_is_command(text)` checks if the first word of a message is in `COMMANDS`. All session accumulators (reflection input, read input, chat messages, quiz answers) use `not _is_command(msg["text"])` in their match function — this ensures commands are never swallowed by an active session and always reach their handler.

**When adding a new command:** add it to `COMMANDS` and update the startup message string.

## Skills

A skill is a callable that reads some data, optionally calls a model, and returns a result. Each skill is a **workflow**: steps are fixed and decided by the programmer, not the model.

## Morning brief

Pattern: **workflow**. Fixed steps, model only writes prose.

1. `_weather()` — GET `wttr.in/Milan?format=j1`, extract temp + description
2. `_calendar()` — Google Calendar API, today's events in `Europe/Rome` timezone
3. `_gmail()` — Gmail API, unread messages from last 24h (subject + sender only)
4. Build a prompt, call Claude Haiku (`claude-haiku-4-5-20251001`), return the text

Each of steps 2 and 3 is wrapped in a try/except so a single failure doesn't break the whole brief.

Triggers: `07:00 Europe/Rome` (scheduled) or `/brief` (on demand).

## Evening reflection

Pattern: **multi-turn stateful workflow**.

State keys: `awaiting_reflection`, `reflection_expires_at`, `reflection_messages`.

Flow:
1. Bot sends the 4-question prompt (scheduled or `/reflect`)
2. Messages accumulate in `reflection_messages`
3. `/done` → concatenate → Haiku structures → save to `reflections/YYYY-MM-DD.md` → send back → reset state
4. Expires after 5 minutes if `/done` not sent

If the day's file already exists, new reflection is appended with `---`.

Triggers: `21:00 Europe/Rome` (scheduled) or `/reflect` (on demand).

## LinkedIn draft

Pattern: **workflow**. Reads local files, calls Haiku, writes a file.

1. Load last 6 files from `reflections/` sorted by filename
2. Call Haiku with learn-in-public prompt (hook → built → learned → hard → next → closing)
3. Save to `drafts/YYYY-MM-DD.md`, send to Telegram

Triggers: `Sunday 18:00 Europe/Rome` (scheduled) or `/linkedin` (on demand).

## Quiz

Pattern: **two-step stateful workflow**.

State keys: `awaiting_quiz_answer`, `quiz_topic`, `quiz_question`.

1. `/testme <topic>` → `generate_question(topic)` → store in state → send question
2. Next message → `evaluate_answer()` → send evaluation → clear state

Haiku uses training data only — no internet. Works well for established concepts.

Triggers: `/testme <topic>` only.

## Reminders

Pattern: **stateless dynamic scheduling**. No session state.

`remind.parse()` splits on the last ` in ` (handles "in" appearing in message text), extracts delay in m/h/d, returns `(message, seconds)`. A one-shot APScheduler `"date"` job is created at runtime. Multiple reminders can coexist. Lost on restart.

Triggers: `/remind <message> in <time>` only.

## Chat

Pattern: **multi-turn stateful conversation**.

State keys: `in_chat`, `chat_history` (list of `{role, content}` dicts).

`memory.md` is loaded on every message and injected as the system prompt. The entire session history is passed to Haiku each turn. `/exit` clears state and ends the session.

Triggers: `/chat` only.

## Reading notes

Pattern: **multi-turn stateful workflow**.

State keys: `read_title`, `read_messages`.

1. `/read <title>` → store title, start accumulating
2. Messages append to `read_messages`
3. `/done` → concatenate → Haiku structures into Summary + Key Concepts (+ To Explore if mentioned) → save to `Notes/<title>.md` → send back → clear state

If the file already exists (same title), new content is appended with a date separator.

Triggers: `/read <title>` only.

## Startup message

On launch, after the scheduler starts, the bot sends a full command list to `brief_chat_id` as confirmation it's online.

## Scheduling

APScheduler's `BackgroundScheduler` runs in a background thread. The main thread runs the blocking polling loop. On shutdown (`finally` block), the scheduler is stopped cleanly before the httpx client is closed.

Scheduled jobs:
- `07:00 Europe/Rome` → morning brief
- `21:00 Europe/Rome` → evening reflection prompt
- `Sunday 18:00 Europe/Rome` → LinkedIn draft

## Google auth

`get_credentials()` — loads `token.json`, refreshes if expired. Raises a clear error if `token.json` is missing.

`run_auth()` — one-time browser OAuth flow. Saves `token.json`. Run via `uv run personal-agent-auth`.

Scopes: `gmail.readonly`, `calendar.readonly` — read-only, no write access.
