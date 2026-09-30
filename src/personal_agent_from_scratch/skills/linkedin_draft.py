from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

MILAN = ZoneInfo("Europe/Rome")
REFLECTIONS_DIR = Path("reflections")
DRAFTS_DIR = Path("drafts")


def _load_last_reflections(n: int = 6) -> str:
    files = sorted(REFLECTIONS_DIR.glob("*.md"))[-n:]
    if not files:
        return ""
    parts = []
    for f in files:
        parts.append(f"### {f.stem}\n{f.read_text().strip()}")
    return "\n\n".join(parts)


def run() -> str:
    raw = _load_last_reflections()
    if not raw:
        return "No reflections found — nothing to draft."

    prompt = (
        "You are writing a LinkedIn post for a developer learning AI and building in public.\n\n"
        "Tone: honest, direct, learn-in-public style. No corporate jargon, no fake positivity.\n\n"
        "Structure (use line breaks generously for LinkedIn readability):\n"
        "1. Hook — 1-2 lines that stop the scroll (no 'I'm excited to share')\n"
        "2. What I built this week\n"
        "3. What I learned\n"
        "4. What's still hard / confused me\n"
        "5. What's next\n"
        "6. Closing line — one honest sentence, no generic CTA\n\n"
        "Keep it under 1300 characters. Write in first person.\n\n"
        f"SOURCE MATERIAL (last 6 daily reflections):\n\n{raw}"
    )

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    draft = resp.content[0].text
    _save(draft)
    return draft


def _save(text: str) -> None:
    DRAFTS_DIR.mkdir(exist_ok=True)
    today = datetime.now(MILAN).strftime("%Y-%m-%d")
    path = DRAFTS_DIR / f"{today}.md"
    path.write_text(text)
    try:
        from ..github_storage import write_file
        write_file(f"drafts/{today}.md", path.read_bytes(), f"linkedin draft {today}")
    except Exception:
        pass
