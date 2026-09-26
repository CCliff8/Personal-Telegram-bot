from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic
import httpx
from googleapiclient.discovery import build

from ..google_auth import get_credentials

BERLIN = ZoneInfo("Europe/Berlin")


def _weather() -> str:
    resp = httpx.get("https://wttr.in/Berlin?format=j1", timeout=10)
    c = resp.json()["current_condition"][0]
    desc = c["weatherDesc"][0]["value"]
    temp = c["temp_C"]
    feels = c["FeelsLikeC"]
    return f"{desc}, {temp}°C (feels like {feels}°C)"


def _calendar() -> str:
    creds = get_credentials()
    svc = build("calendar", "v3", credentials=creds)
    now = datetime.now(BERLIN)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = now.replace(hour=23, minute=59, second=59, microsecond=0)

    result = svc.events().list(
        calendarId="primary",
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])
    if not events:
        return "No events today."

    lines = []
    for e in events:
        start_raw = e["start"].get("dateTime", e["start"].get("date", ""))
        if "T" in start_raw:
            t = datetime.fromisoformat(start_raw).astimezone(BERLIN).strftime("%H:%M")
            lines.append(f"{t} {e['summary']}")
        else:
            lines.append(f"All day: {e['summary']}")
    return "\n".join(lines)


def _gmail() -> str:
    creds = get_credentials()
    svc = build("gmail", "v1", credentials=creds)
    result = svc.users().messages().list(
        userId="me",
        q="is:unread newer_than:1d",
        maxResults=10,
    ).execute()

    messages = result.get("messages", [])
    if not messages:
        return "No unread emails."

    lines = []
    for m in messages:
        msg = svc.users().messages().get(
            userId="me",
            id=m["id"],
            format="metadata",
            metadataHeaders=["Subject", "From"],
        ).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        subject = headers.get("Subject", "(no subject)")
        sender = headers.get("From", "unknown")
        lines.append(f"{sender}: {subject}")
    return "\n".join(lines)


def run() -> str:
    weather = _weather()

    try:
        calendar = _calendar()
    except Exception as e:
        calendar = f"(unavailable: {e})"

    try:
        emails = _gmail()
    except Exception as e:
        emails = f"(unavailable: {e})"

    prompt = (
        "Write a brief morning summary. Be concise, max 200 words.\n\n"
        f"WEATHER IN BERLIN: {weather}\n\n"
        f"TODAY'S CALENDAR:\n{calendar}\n\n"
        f"UNREAD EMAILS (last 24h):\n{emails}\n\n"
        "Format: 3 short sections with emoji headers (☀️ Weather, 📅 Calendar, 📧 Email). "
        "Conversational tone."
    )

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text
