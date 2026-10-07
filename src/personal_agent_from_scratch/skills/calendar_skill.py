import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import anthropic
from googleapiclient.discovery import build

from ..google_auth import get_credentials

MILAN = ZoneInfo("Europe/Rome")


def extract_intent(text: str) -> dict:
    today = datetime.now(MILAN)
    prompt = (
        f"Today is {today.strftime('%Y-%m-%d')} ({today.strftime('%A')}).\n"
        "Extract calendar action from this message. Return ONLY a JSON object.\n\n"
        "Fields:\n"
        '- "intent": "create" or "delete"\n'
        '- "title": string or null\n'
        '- "date": YYYY-MM-DD resolved from relative dates, or null\n'
        '- "time": HH:MM 24h, or null\n'
        '- "duration_min": integer minutes, or null\n'
        '- "description": string or null\n'
        '- "location": string or null\n'
        '- "search_query": string with keywords to find the event (for delete), or null\n\n'
        f"Message: {text}"
    )
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = raw.rstrip("`").strip()
    return json.loads(raw)


def parse_field(field: str, text: str) -> str | int | None:
    today = datetime.now(MILAN).strftime("%Y-%m-%d")
    prompts = {
        "title": None,
        "date": f"Today is {today}. Convert to ISO date YYYY-MM-DD. Return ONLY the date.\n\nDate: {text}",
        "time": f"Convert to HH:MM 24h format. Return ONLY HH:MM.\n\nTime: {text}",
        "duration_min": f"Convert to integer minutes. Return ONLY the integer.\n\nDuration: {text}",
    }
    if field == "title":
        return text.strip() or None
    prompt = prompts[field]
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=15,
        messages=[{"role": "user", "content": prompt}],
    )
    result = resp.content[0].text.strip()
    if field == "date":
        return result if re.match(r"^\d{4}-\d{2}-\d{2}$", result) else None
    if field == "time":
        return result if re.match(r"^\d{2}:\d{2}$", result) else None
    if field == "duration_min":
        try:
            return int(result)
        except ValueError:
            return None
    return None


def first_missing(fields: dict) -> tuple[str, str] | None:
    checks = [
        ("title", "What's the event title?"),
        ("date", "What date?"),
        ("time", "What time?"),
        ("duration_min", "How long? (e.g. 45min, 1h30)"),
    ]
    for field, question in checks:
        if not fields.get(field):
            return (field, question)
    return None


def create_event(fields: dict) -> str:
    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds)

    start_dt = datetime.strptime(
        f"{fields['date']} {fields['time']}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=MILAN)
    end_dt = start_dt + timedelta(minutes=int(fields["duration_min"]))

    body: dict = {
        "summary": fields["title"],
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Europe/Rome"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Europe/Rome"},
    }
    if fields.get("description"):
        body["description"] = fields["description"]
    if fields.get("location"):
        body["location"] = fields["location"]

    service.events().insert(calendarId="primary", body=body).execute()

    day = start_dt.strftime("%A %d %b")
    return f"Created: {fields['title']} — {day}, {fields['time']}–{end_dt.strftime('%H:%M')}"


def search_events(query: str | None, date: str | None, time: str | None = None) -> list:
    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds)

    now = datetime.now(MILAN)
    if date:
        start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=MILAN)
        end = start + timedelta(days=1)
    else:
        start = now
        end = now + timedelta(days=30)

    result = service.events().list(
        calendarId="primary",
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=50,
    ).execute()
    events = result.get("items", [])

    # Filter locally by title — case-insensitive substring match
    if query:
        query_lower = query.lower()
        events = [e for e in events if query_lower in e.get("summary", "").lower()]

    # Narrow by time if provided
    if time and events:
        try:
            target_h, target_m = map(int, time.split(":"))
            by_time = [
                e for e in events
                if (dt := datetime.fromisoformat(e["start"].get("dateTime", "")).astimezone(MILAN))
                and dt.hour == target_h and dt.minute == target_m
            ]
            if by_time:
                events = by_time
        except Exception:
            pass

    return events


def format_event(event: dict) -> str:
    start = event["start"].get("dateTime", event["start"].get("date", ""))
    try:
        dt = datetime.fromisoformat(start).astimezone(MILAN)
        return f"{event.get('summary', 'Untitled')} — {dt.strftime('%A %d %b, %H:%M')}"
    except Exception:
        return event.get("summary", "Untitled")


def delete_event(event_id: str) -> None:
    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds)
    service.events().delete(calendarId="primary", eventId=event_id).execute()
