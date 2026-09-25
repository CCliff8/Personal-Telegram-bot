import json
from pathlib import Path
from typing import Callable, List, Tuple

STATE_FILE = Path(__file__).parent / "state.json"


class Router:
    def __init__(self):
        self._handlers: List[Tuple[Callable[[dict], bool], Callable]] = []
        self.state = self._load()

    def _load(self) -> dict:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
        return {}

    def save_state(self) -> None:
        STATE_FILE.write_text(json.dumps(self.state, indent=2))

    def register(self, match: Callable[[dict], bool]) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._handlers.append((match, fn))
            return fn
        return decorator

    def dispatch(self, message: dict) -> None:
        for match, handler in self._handlers:
            if match(message):
                handler(message, self)
                return
