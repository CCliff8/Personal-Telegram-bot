from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

MILAN = ZoneInfo("Europe/Rome")
REFLECTIONS_DIR = Path("reflections")

PROMPT_MESSAGE = (
    "Evening check-in. Reply to all four, then send /done:\n\n"
    "1. What did you build today?\n"
    "2. What did you learn?\n"
    "3. What confused you?\n"
    "4. What's next?"
)


def start(state: dict) -> None:
    now = datetime.now(MILAN)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    state["awaiting_reflection"] = True
    state["reflection_expires_at"] = expires
    state["reflection_messages"] = []


def is_active(state: dict) -> bool:
    if not state.get("awaiting_reflection"):
        return False
    expires_at = datetime.fromisoformat(state["reflection_expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        reset(state)
        return False
    return True


def accumulate(state: dict, text: str) -> None:
    state["reflection_messages"].append(text)


def finish(state: dict) -> str:
    messages = state.get("reflection_messages", [])
    raw = "\n".join(messages)
    reset(state)

    structured = _structure(raw)
    _save(structured)
    return structured


def reset(state: dict) -> None:
    state.pop("awaiting_reflection", None)
    state.pop("reflection_expires_at", None)
    state.pop("reflection_messages", None)


def _structure(raw: str) -> str:
    today = datetime.now(MILAN).strftime("%Y-%m-%d")
    prompt = (
        f"Structure this messy reflection into a clean dated note. Date: {today}.\n\n"
        "Use exactly these markdown sections:\n"
        f"# Reflection — {today}\n\n"
        "## What I built\n"
        "## What I learned\n"
        "## What confused me\n"
        "## What's next\n\n"
        "Rules: no filler, no encouragement, keep the user's own words where possible, "
        "infer section content from context if the user didn't answer a question explicitly.\n\n"
        f"RAW INPUT:\n{raw}"
    )
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def _save(text: str) -> None:
    REFLECTIONS_DIR.mkdir(exist_ok=True)
    today = datetime.now(MILAN).strftime("%Y-%m-%d")
    path = REFLECTIONS_DIR / f"{today}.md"
    with path.open("a") as f:
        if path.stat().st_size > 0:
            f.write("\n\n---\n\n")
        f.write(text)
