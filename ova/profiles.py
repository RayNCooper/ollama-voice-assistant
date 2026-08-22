from pathlib import Path

from .utils import logger

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = REPO_ROOT / "profiles"

DEFAULT_PROFILE = "default"
PROMPT_FILE = "prompt.txt"
REF_AUDIO_FILE = "ref_audio.wav"
VOICE_STATE_FILE = "voice.safetensors"


def resolve_profile_dir(profile: str) -> Path:
    """Return the profile directory, falling back to the default profile."""
    profile_dir = PROFILES_DIR / profile
    if (profile_dir / PROMPT_FILE).is_file():
        return profile_dir

    if profile != DEFAULT_PROFILE:
        logger.warning(
            (
                f"Unknown OVA profile '{profile}' or missing '{PROMPT_FILE}' in "
                f"'{profile_dir}'. Using '{DEFAULT_PROFILE}' profile."
            )
        )

    return PROFILES_DIR / DEFAULT_PROFILE


def list_profile_dirs() -> list[Path]:
    """All profile directories that contain a prompt.txt."""
    return sorted(
        d
        for d in PROFILES_DIR.iterdir()
        if d.is_dir() and (d / PROMPT_FILE).is_file()
    )
