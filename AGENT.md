# Agent Architecture

Personal reference for how this project is structured and why.

## File map

```
src/personal_agent_from_scratch/
    __init__.py               # Entry point: main(), polling loop, APScheduler
    telegram.py               # TelegramClient: get_updates() + send_message()
    router.py                 # Router: match-based dispatch + state.json
    handlers.py               # Echo handler
    google_auth.py            # OAuth helpers: get_credentials() + run_auth()
    skills/
        morning_brief.py      # Morning brief skill: weather + calendar + gmail + Haiku
```

## How the polling loop works

`main()` runs a `while True` that calls `getUpdates` on the Telegram API with `timeout=30` (long polling). Telegram holds the connection open up to 30 s if no messages arrive, then returns an empty list. When a message arrives it returns immediately.

After each batch, `offset` is set to `last_update_id + 1`. This is sent on the next call and tells Telegram to drop all already-seen updates from the queue — it's the acknowledgement mechanism.

Messages not in the `chat_id` allowlist are silently ignored.

## Router

`Router` holds an ordered list of `(match_fn, handler_fn)` pairs. `dispatch()` walks the list and calls the first handler whose `match_fn` returns true. **Order matters** — more specific handlers must be registered before catch-all ones.

`Router.state` is a plain dict persisted to `state.json` after each handled message. Right now it's empty — future skills will use it to store conversation state (e.g. current step in a multi-turn flow).

## Skills

A skill is a callable that reads some data, optionally calls a model, and returns a result. Skills live in `skills/`. Each skill is:
- A **workflow**, not an agent: steps are fixed and decided by the programmer
- Registered in `__init__.py` via a command handler (e.g. `/brief`)
- Also triggerable on a schedule via APScheduler

## Morning brief

Pattern: **workflow**. Fixed steps, model only writes prose.

1. `_weather()` — GET `wttr.in/Milan?format=j1`, extract temp + description
2. `_calendar()` — Google Calendar API, today's events in `Europe/Rome` timezone
3. `_gmail()` — Gmail API, unread messages from last 24h (subject + sender only)
4. Build a prompt with all three, call Claude Haiku (`claude-haiku-4-5-20251001`), return the text

Each of steps 2 and 3 is wrapped in a try/except so a single failure doesn't break the whole brief.

Triggers:
- `07:00 Europe/Rome` via APScheduler `BackgroundScheduler` (runs in a thread alongside the polling loop)
- `/brief` command on demand

## Scheduling

APScheduler's `BackgroundScheduler` runs in a background thread. The main thread runs the blocking polling loop. On shutdown (`finally` block), the scheduler is stopped cleanly before the httpx client is closed.

## Google auth

`get_credentials()` — loads `token.json`, refreshes if expired. Raises a clear error if `token.json` is missing (directing the user to run `uv run personal-agent-auth`).

`run_auth()` — one-time browser OAuth flow. Opens a browser, user logs in and clicks Allow, saves `token.json`. Never needs to be run again unless the token is revoked.

Scopes: `gmail.readonly`, `calendar.readonly` — read-only, no write access.
