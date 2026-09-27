from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

MILAN = ZoneInfo("Europe/Rome")
NOTES_DIR = Path("Notes")


def structure(title: str, raw_notes: str) -> str:
    prompt = (
        f"Organise these raw reading notes into a clean structured note.\n\n"
        f"Title: {title}\n\n"
        "Use this template:\n"
        f"# {title}\n\n"
        "## Summary\n"
        "<concise summary of the main ideas>\n\n"
        "## Key Concepts\n"
        "<bullet list of key concepts, definitions, or takeaways>\n\n"
        "Rules:\n"
        "- Keep the author's own words where they are precise\n"
        "- If the notes mention something to deep dive, add a ## To Explore section\n"
        "- No filler, no padding\n\n"
        f"RAW NOTES:\n{raw_notes}"
    )
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def save(title: str, text: str) -> None:
    NOTES_DIR.mkdir(exist_ok=True)
    safe_title = title.replace(" ", "_").replace("/", "-")
    path = NOTES_DIR / f"{safe_title}.md"
    with path.open("a") as f:
        if path.exists() and path.stat().st_size > 0:
            date = datetime.now(MILAN).strftime("%Y-%m-%d")
            f.write(f"\n\n---\n\n*Updated {date}*\n\n")
        f.write(text)
