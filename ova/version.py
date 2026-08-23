"""App version and build identifier, resolved once at import.

The version is read from ``pyproject.toml`` (the single source of truth, shared
with the Tauri bundle) and the build is the short git commit the app is running
from — handy when someone reports a bug against a locally built ``.app``.
"""

import re
import subprocess

from .profiles import REPO_ROOT

_PYPROJECT = REPO_ROOT / "pyproject.toml"
_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def _read_version() -> str:
    try:
        text = _PYPROJECT.read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"
    match = _VERSION_RE.search(text)
    return match.group(1) if match else "0.0.0"


def _read_build() -> str:
    """Short commit hash, with ``+`` appended when the tree is dirty."""
    try:
        rev = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if rev.returncode != 0:
            return ""
        commit = rev.stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=3,
        )
        return f"{commit}+" if dirty.stdout.strip() else commit
    except (OSError, subprocess.SubprocessError):
        return ""


VERSION = _read_version()
BUILD = _read_build()
