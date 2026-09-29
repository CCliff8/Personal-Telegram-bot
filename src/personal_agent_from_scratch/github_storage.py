import base64
import os
from typing import Optional

import httpx

REPO = "CCliff8/personal-agent-data"
API_BASE = f"https://api.github.com/repos/{REPO}/contents"


def _headers() -> dict:
    token = os.environ.get("DATA_REPO_TOKEN", "")
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def _token_available() -> bool:
    return bool(os.environ.get("DATA_REPO_TOKEN", "").strip())


def read_file(path: str) -> Optional[bytes]:
    if not _token_available():
        return None
    resp = httpx.get(f"{API_BASE}/{path}", headers=_headers(), timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return base64.b64decode(resp.json()["content"])


def write_file(path: str, content: bytes, message: str = "update") -> None:
    if not _token_available():
        return
    sha = None
    existing = httpx.get(f"{API_BASE}/{path}", headers=_headers(), timeout=10)
    if existing.status_code == 200:
        sha = existing.json()["sha"]

    body: dict = {
        "message": message,
        "content": base64.b64encode(content).decode(),
    }
    if sha:
        body["sha"] = sha

    resp = httpx.put(f"{API_BASE}/{path}", headers=_headers(), json=body, timeout=10)
    resp.raise_for_status()
