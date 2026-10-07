import time
from typing import List, Optional
import httpx


class TelegramClient:
    def __init__(self, token: str):
        self._base = f"https://api.telegram.org/bot{token}"
        self._http = httpx.Client()

    def get_updates(self, offset: Optional[int] = None, timeout: int = 30) -> List[dict]:
        params: dict = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        resp = self._http.get(
            f"{self._base}/getUpdates",
            params=params,
            timeout=timeout + 5,
        )
        if resp.status_code == 409:
            # Another instance is already polling — wait for it to shut down
            time.sleep(5)
            return []
        resp.raise_for_status()
        return resp.json()["result"]

    def send_message(self, chat_id: int, text: str) -> None:
        resp = self._http.post(
            f"{self._base}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        resp.raise_for_status()

    def close(self) -> None:
        self._http.close()
