"""Voice-profile helpers for the GUI: listing and cloning.

A "voice" is just an ``ova`` profile directory (``profiles/<name>/``) holding a
``prompt.txt`` and, for a clone, a ``ref_audio.wav`` that Pocket TTS encodes
into ``voice.safetensors``. These helpers reuse the same encoding path as
``ova.tts`` so GUI-created clones behave identically to CLI-created ones.

The consent gate lives in :mod:`gui.consent`; nothing here writes a clone
without the caller having passed that gate first.
"""

import re
import shutil
from pathlib import Path

from ova.profiles import (
    PROFILES_DIR,
    PROMPT_FILE,
    REF_AUDIO_FILE,
    VOICE_STATE_FILE,
    list_profile_dirs,
)

# A sensible starting prompt for a freshly cloned voice; mirrors the default
# profile's concise, unformatted style.
DEFAULT_CLONE_PROMPT = (
    "You are a helpful assistant.\n"
    "You respond with short, elegant, and concise answers.\n"
    "\n"
    "When responding ALWAYS follow these instructions:\n"
    "  - Be concise and to the point.\n"
    "  - NEVER respond in bullet points - use proper sentences.\n"
    "  - DO NOT include any Markdown formatting, asterisks, or emojis.\n"
)

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class VoiceError(ValueError):
    """Raised when a voice cannot be created (bad name, missing file, ...)."""


def list_voices() -> list[dict]:
    """Return metadata for every profile that has a prompt.txt.

    Each entry: ``{"name", "cloned", "encoded"}`` where ``cloned`` means a
    reference clip is present and ``encoded`` means the voice state is cached.
    """
    voices = []
    for d in list_profile_dirs():
        voices.append(
            {
                "name": d.name,
                "cloned": (d / REF_AUDIO_FILE).is_file(),
                "encoded": (d / VOICE_STATE_FILE).is_file(),
            }
        )
    return voices


def validate_new_name(name: str) -> str:
    """Normalise and validate a proposed profile name, or raise VoiceError."""
    name = (name or "").strip().lower()
    if not name:
        raise VoiceError("Please enter a name for the new voice.")
    if not _NAME_RE.match(name):
        raise VoiceError(
            "Use only lowercase letters, numbers, dashes and underscores "
            "(must start with a letter or number)."
        )
    if (PROFILES_DIR / name).exists():
        raise VoiceError(f'A voice named "{name}" already exists.')
    return name


def create_clone(name: str, source_wav: Path, prompt_text: str, tts_model) -> Path:
    """Create ``profiles/<name>/`` from a reference clip and encode its voice.

    ``tts_model`` is a loaded ``pocket_tts.TTSModel`` (reused from the running
    pipeline). Returns the new profile directory.

    The caller MUST have obtained consent (see :mod:`gui.consent`) before
    invoking this; the encoding step is otherwise identical to the CLI path.
    """
    # Import here so this module can be imported without the heavy TTS stack.
    from ova.tts import load_voice_state

    name = validate_new_name(name)
    source_wav = Path(source_wav)
    if not source_wav.is_file():
        raise VoiceError(f"Reference audio not found: {source_wav}")

    profile_dir = PROFILES_DIR / name
    profile_dir.mkdir(parents=True, exist_ok=False)
    try:
        shutil.copyfile(source_wav, profile_dir / REF_AUDIO_FILE)
        (profile_dir / PROMPT_FILE).write_text(
            (prompt_text or DEFAULT_CLONE_PROMPT).strip() + "\n", encoding="utf-8"
        )
        # Encode + cache voice.safetensors (may need gated pocket-tts weights).
        load_voice_state(tts_model, profile_dir)
    except Exception:
        # Roll back a half-built profile so the list stays clean.
        shutil.rmtree(profile_dir, ignore_errors=True)
        raise

    return profile_dir
