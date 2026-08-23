"""Persist small local settings (currently just the Ollama Cloud API key).

Stored as plain JSON at ``<REPO_ROOT>/.ova/api_key``. The ``.ova/`` directory is
gitignored, so a saved key never lands in version control. No keyring
dependency on purpose: this is a local, single-user desktop app.

Both entry points share this module: the FastAPI backend (``ova.api``) and the
PySide6 GUI (``gui.settings`` re-exports it).
"""

import json
import os
from pathlib import Path

from .profiles import REPO_ROOT

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
    try:
        _API_KEY_FILE.chmod(0o600)
    except OSError:
        # Best effort; a permissions failure must not block saving the key.
        pass


def active_api_key() -> str:
    """The key the pipeline will actually use: environment first, then saved."""
    return os.environ.get("OLLAMA_API_KEY", "").strip() or load_api_key()


def apply_saved_api_key() -> str:
    """Copy the saved key into ``os.environ`` unless the env already sets one.

    ``ova.pipeline.chat`` reads ``OLLAMA_API_KEY`` at call time, so this is all
    that is needed for a key saved from the UI to take effect immediately.
    Returns the key now in effect (possibly empty).
    """
    env_key = os.environ.get("OLLAMA_API_KEY", "").strip()
    if env_key:
        return env_key
    saved = load_api_key()
    if saved:
        os.environ["OLLAMA_API_KEY"] = saved
    return saved


def mask_api_key(key: str) -> str:
    """A safe-to-display hint for a key, e.g. ``abcd...wxyz``. Never the key."""
    key = (key or "").strip()
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"
