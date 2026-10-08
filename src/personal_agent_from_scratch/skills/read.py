from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

MILAN = ZoneInfo("Europe/Rome")
NOTES_DIR = Path("Notes")


def structure(title: str, raw_notes: str) -> str:
    prompt = (
        f"Organise these raw notes into a clean structured note.\n\n"
        f"Title: {title}\n\n"
        "Rules:\n"
        "- NEVER write a summary — preserve and reorganise the original content, do not paraphrase\n"
        "- If the notes contain links or URLs: format as a bullet list, one item per link, with any context the user wrote next to it\n"
        "- If the notes are prose or concepts: reorganise into ## sections with bullet points, keep the author's own words\n"
        "- If something to explore is mentioned, add a ## To Explore section\n"
        "- Start with # {title}, then the content — nothing else before it\n"
        "- No filler, no padding, no summaries\n\n"
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
    try:
        from ..github_storage import write_file
        write_file(f"Notes/{safe_title}.md", path.read_bytes(), f"note: {title}")
    except Exception:
        pass
