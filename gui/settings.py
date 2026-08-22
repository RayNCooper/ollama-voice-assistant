"""Persist small GUI settings (currently just the Ollama Cloud API key).

The key is stored as plain JSON at ``<REPO_ROOT>/.ova/api_key`` — the ``.ova/``
directory is already gitignored, so a saved key never lands in version control.
No keyring dependency on purpose: this is a local, single-user desktop app.
"""

import json
from pathlib import Path

# ova/profiles.py already anchors REPO_ROOT the same way (parent of the package).
REPO_ROOT = Path(__file__).resolve().parent.parent
_SETTINGS_DIR = REPO_ROOT / ".ova"
_API_KEY_FILE = _SETTINGS_DIR / "api_key"


def load_api_key() -> str:
    """Return the saved API key, or an empty string if none is stored."""
    try:
        data = json.loads(_API_KEY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    key = data.get("api_key", "") if isinstance(data, dict) else ""
    return key.strip() if isinstance(key, str) else ""


def save_api_key(key: str) -> None:
    """Persist the API key (trimmed) to the gitignored settings file."""
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    _API_KEY_FILE.write_text(
        json.dumps({"api_key": key.strip()}), encoding="utf-8"
    )
