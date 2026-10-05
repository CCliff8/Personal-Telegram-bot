import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import anthropic
from googleapiclient.discovery import build

from ..google_auth import get_credentials

MILAN = ZoneInfo("Europe/Rome")


def extract(text: str) -> dict:
    today = datetime.now(MILAN)
    prompt = (
        f"Today is {today.strftime('%Y-%m-%d')} ({today.strftime('%A')}).\n"
        "Extract scheduling info from this message and return ONLY a JSON object with no extra text.\n\n"
        "Fields:\n"
        '- "description": string — event title\n'
        '- "date": string — YYYY-MM-DD resolved from relative dates (e.g. "thursday" → next Thursday), or null\n'
        '- "time": string — HH:MM 24h, or null if vague (e.g. "morning" is null)\n'
        '- "distance_km": number or null — only for running/cycling events with a stated distance\n'
        '- "is_run": boolean — true if this is a running or cycling workout\n\n'
        f"Message: {text}"
    )
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = raw.rstrip("`").strip()
    return json.loads(raw)


def calculate_duration(fields: dict) -> int | None:
    if fields.get("is_run") and fields.get("distance_km"):
        raw_min = fields["distance_km"] * 6
        return round(raw_min / 5) * 5
    return None


def parse_time(text: str) -> str | None:
    prompt = (
        "Convert this time expression to HH:MM in 24h format. "
        "Return ONLY the HH:MM string.\n\n"
        f"Time: {text}"
    )
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )
    t = resp.content[0].text.strip()
    return t if re.match(r"^\d{2}:\d{2}$", t) else None


def parse_date(text: str) -> str | None:
    today = datetime.now(MILAN).strftime("%Y-%m-%d")
    prompt = (
        f"Today is {today}. Convert this date reference to ISO format YYYY-MM-DD. "
        "Return ONLY the date string.\n\n"
        f"Date: {text}"
    )
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=15,
        messages=[{"role": "user", "content": prompt}],
    )
    d = resp.content[0].text.strip()
    return d if re.match(r"^\d{4}-\d{2}-\d{2}$", d) else None


def parse_duration(text: str) -> int | None:
    prompt = (
        "Convert this duration to an integer number of minutes. "
        "Return ONLY the integer.\n\n"
        f"Duration: {text}"
    )
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        return int(resp.content[0].text.strip())
    except ValueError:
        return None


def first_missing(fields: dict) -> tuple[str, str] | None:
    if not fields.get("date"):
        return ("date", "What date?")
    if not fields.get("time"):
        return ("time", "What time?")
    if not fields.get("duration_min"):
        return ("duration_min", "How long? (e.g. 45min, 1h30)")
    return None


def create_event(fields: dict) -> str:
    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds)

    start_dt = datetime.strptime(
        f"{fields['date']} {fields['time']}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=MILAN)
    end_dt = start_dt + timedelta(minutes=int(fields["duration_min"]))

    service.events().insert(
        calendarId="primary",
        body={
            "summary": fields["description"],
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "Europe/Rome"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "Europe/Rome"},
        },
    ).execute()

    day = start_dt.strftime("%A %d %b")
    return f"Created: {fields['description']} — {day}, {fields['time']}–{end_dt.strftime('%H:%M')}"
