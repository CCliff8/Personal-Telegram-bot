from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
]

CREDS_FILE = Path("credentials.json")
TOKEN_FILE = Path("token.json")


def get_credentials() -> Credentials:
    """Return valid credentials, refreshing if expired. Raises if token.json is missing."""
    if not TOKEN_FILE.exists():
        raise RuntimeError("No token.json found. Run `uv run personal-agent-auth` first.")
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())
            try:
                from .github_storage import write_file
                write_file("token.json", TOKEN_FILE.read_bytes(), "refresh token")
            except Exception:
                pass
        else:
            raise RuntimeError("Token is invalid. Run `uv run personal-agent-auth` again.")
    return creds


def run_auth() -> None:
    """One-time OAuth browser flow. Saves token.json."""
    if not CREDS_FILE.exists():
        raise FileNotFoundError(f"{CREDS_FILE} not found. Download it from Google Cloud Console.")
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_FILE.write_text(creds.to_json())
    print("Authentication successful. token.json saved.")
