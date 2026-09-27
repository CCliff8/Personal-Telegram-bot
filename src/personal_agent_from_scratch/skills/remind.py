import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

MILAN = ZoneInfo("Europe/Rome")

TIME_PATTERN = re.compile(r"^(\d+)(m|h|d)$")


def parse(text: str) -> Optional[Tuple[str, int]]:
    """
    Parse '/remind <message> in <delay>' and return (message, seconds).
    Splits on the last ' in ' to handle 'in' appearing in the message text.
    Returns None if the format is invalid.
    """
    sep = " in "
    idx = text.lower().rfind(sep)
    if idx == -1:
        return None

    message = text[:idx].strip()
    time_str = text[idx + len(sep):].strip()

    if not message:
        return None

    match = TIME_PATTERN.match(time_str)
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)
    seconds = amount * {"m": 60, "h": 3600, "d": 86400}[unit]
    return message, seconds


def fire_time_label(seconds: int) -> str:
    due = datetime.now(MILAN) + timedelta(seconds=seconds)
    return due.strftime("%H:%M")
