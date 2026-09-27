from pathlib import Path
from typing import List, Dict

import anthropic

MEMORY_FILE = Path("memory.md")


def _load_memory() -> str:
    if MEMORY_FILE.exists():
        return MEMORY_FILE.read_text().strip()
    return ""


def reply(history: List[Dict[str, str]], user_message: str) -> str:
    history.append({"role": "user", "content": user_message})

    memory = _load_memory()
    system = (
        "You are a personal assistant for a developer learning AI and building in public. "
        "Be direct, concise, and helpful.\n\n"
        f"PERSONAL CONTEXT:\n{memory}" if memory else
        "You are a personal assistant for a developer learning AI and building in public. "
        "Be direct, concise, and helpful."
    )

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system=system,
        messages=history,
    )
    assistant_message = resp.content[0].text
    history.append({"role": "assistant", "content": assistant_message})
    return assistant_message
