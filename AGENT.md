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
        morning_brief.py      # Morning brief: weather + calendar + gmail + Haiku
        evening_reflection.py # Evening reflection: multi-turn input + Haiku structuring

reflections/                  # Saved reflection notes (gitignored, one .md per day)
```

## How the polling loop works

`main()` runs a `while True` that calls `getUpdates` on the Telegram API with `timeout=30` (long polling). Telegram holds the connection open up to 30 s if no messages arrive, then returns an empty list. When a message arrives it returns immediately.

After each batch, `offset` is set to `last_update_id + 1`. This is sent on the next call and tells Telegram to drop all already-seen updates from the queue — it's the acknowledgement mechanism.

Messages not in the `chat_id` allowlist are silently ignored.

## Router

`Router` holds an ordered list of `(match_fn, handler_fn)` pairs. `dispatch()` walks the list and calls the first handler whose `match_fn` returns true. **Order matters** — more specific handlers must be registered before catch-all ones.

Current handler order in `__init__.py`:
1. `/brief` — morning brief on demand
2. `/reflect` — start evening reflection session
3. `/done` (only if reflection is active) — finish and save reflection
4. Reflection accumulator (only if reflection is active) — collect messages
5. Echo — catch-all

`Router.state` is a plain dict persisted to `state.json` after each handled message. Skills use it to store conversation state across messages.

## Skills

A skill is a callable that reads some data, optionally calls a model, and returns a result. Skills live in `skills/`. Each skill is:
- A **workflow**, not an agent: steps are fixed and decided by the programmer
- Registered in `__init__.py` via a command handler and/or a scheduled APScheduler job

## Morning brief

Pattern: **workflow**. Fixed steps, model only writes prose.

1. `_weather()` — GET `wttr.in/Milan?format=j1`, extract temp + description
2. `_calendar()` — Google Calendar API, today's events in `Europe/Rome` timezone
3. `_gmail()` — Gmail API, unread messages from last 24h (subject + sender only)
4. Build a prompt, call Claude Haiku (`claude-haiku-4-5-20251001`), return the text

Each of steps 2 and 3 is wrapped in a try/except so a single failure doesn't break the whole brief.

Triggers: `07:00 Europe/Rome` (scheduled) or `/brief` (on demand).

## Evening reflection

Pattern: **multi-turn stateful workflow**. First skill that uses `state.json` meaningfully.

Flow:
1. Bot sends the 4-question prompt (scheduled at 21:00 or `/reflect` on demand)
2. `reflection.start()` writes 3 keys to state: `awaiting_reflection`, `reflection_expires_at`, `reflection_messages`
3. Every message while active is appended to `reflection_messages` via `accumulate()`
4. `/done` triggers `finish()`: concatenates messages → calls Haiku to structure → saves to `reflections/YYYY-MM-DD.md` → sends structured note back to Telegram → resets state
5. If 5 minutes pass without `/done`, `is_active()` returns false and state is reset silently

Expiry is checked on every incoming message via `is_active()`, which also cleans up state if expired.

If the day's file already exists, the new reflection is appended with a `---` separator.

Triggers: `21:00 Europe/Rome` (scheduled) or `/reflect` (on demand).

## Scheduling

APScheduler's `BackgroundScheduler` runs in a background thread. The main thread runs the blocking polling loop. On shutdown (`finally` block), the scheduler is stopped cleanly before the httpx client is closed.

Scheduled jobs:
- `07:00 Europe/Rome` → morning brief
- `21:00 Europe/Rome` → evening reflection prompt

## Google auth

`get_credentials()` — loads `token.json`, refreshes if expired. Raises a clear error if `token.json` is missing (directing to run `uv run personal-agent-auth`).

`run_auth()` — one-time browser OAuth flow. Opens a browser, user logs in and clicks Allow, saves `token.json`. Never needs to be run again unless the token is revoked.

Scopes: `gmail.readonly`, `calendar.readonly` — read-only, no write access.
