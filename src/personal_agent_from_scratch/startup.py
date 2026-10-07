import base64
import os
from pathlib import Path


def sync_data_from_repo() -> None:
    """Pull reflections, drafts, and Notes from the private GitHub repo to local disk."""
    try:
        from .github_storage import list_files, read_file
        for folder in ("reflections", "drafts", "Notes"):
            for remote_path in list_files(folder):
                local_path = Path(remote_path)
                if not local_path.exists():
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    data = read_file(remote_path)
                    if data:
                        local_path.write_bytes(data)
    except Exception:
        pass


def decode_google_credentials() -> None:
    """
    On Railway, credentials.json and token.json are not on disk.
    - credentials.json: always decoded from GOOGLE_CREDENTIALS_B64 env var
    - token.json: pulled from private GitHub repo first (has latest refreshed token),
                  falls back to GOOGLE_TOKEN_B64 env var if not found
    """
    creds_b64 = os.environ.get("GOOGLE_CREDENTIALS_B64")
    if creds_b64 and not Path("credentials.json").exists():
        Path("credentials.json").write_bytes(base64.b64decode(creds_b64))

    if not Path("token.json").exists():
        from .github_storage import read_file
        token_data = read_file("token.json")
        if token_data:
            Path("token.json").write_bytes(token_data)
        else:
            token_b64 = os.environ.get("GOOGLE_TOKEN_B64")
            if token_b64:
                Path("token.json").write_bytes(base64.b64decode(token_b64))
