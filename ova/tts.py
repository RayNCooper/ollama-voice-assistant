"""Pocket TTS integration - the single TTS engine for all OVA backends.

Voice resolution for a profile:

1. profiles/<p>/voice.safetensors -> precomputed voice state (fast path)
2. profiles/<p>/ref_audio.wav     -> encode the reference clip (voice cloning)
                                     and cache the state as voice.safetensors
3. neither                        -> Pocket TTS built-in DEFAULT_VOICE, also
                                     cached as voice.safetensors

Encoding a reference clip (2) requires access to the gated
https://huggingface.co/kyutai/pocket-tts weights; the built-in voices (3)
work without it.

Run `python -m ova.tts` (done automatically by `./ova.sh install`) to
pre-build the voice states and generate a short warmup dialogue per profile.
"""

import argparse
from pathlib import Path

import numpy as np
from pocket_tts import TTSModel, export_model_state

from .audio import numpy_to_wav_bytes
from .profiles import (
    PROFILES_DIR,
    PROMPT_FILE,
    REF_AUDIO_FILE,
    REPO_ROOT,
    VOICE_STATE_FILE,
    list_profile_dirs,
)
from .utils import logger

DEFAULT_VOICE = "alba"  # Pocket TTS built-in female English voice
LSD_DECODE_STEPS = 4  # decode steps: higher = better quality, slower (lib default: 1)
FRAMES_AFTER_EOS = 8  # extra frames after end-of-speech to avoid clipped tail phonemes
WARMUP_DIALOGUE = (
    "Hi! I am your outrageous voice assistant. My voice is now ready, so let's chat!"
)


def load_model() -> TTSModel:
    return TTSModel.load_model(lsd_decode_steps=LSD_DECODE_STEPS)


def load_voice_state(model: TTSModel, profile_dir: Path) -> dict:
    """Load the profile's voice state, encoding and caching it if necessary."""
    voice_state_path = profile_dir / VOICE_STATE_FILE
    if voice_state_path.is_file():
        logger.info(f"Loading cached voice state: {voice_state_path}")
        return model.get_state_for_audio_prompt(voice_state_path)

    ref_audio = profile_dir / REF_AUDIO_FILE
    if ref_audio.is_file():
        logger.info(f"Encoding reference audio: {ref_audio}")
        # truncate=True caps the reference at 30s to bound encode time/state size
        state = model.get_state_for_audio_prompt(ref_audio, truncate=True)
    else:
        logger.info(
            f"No {REF_AUDIO_FILE} in {profile_dir}; using built-in '{DEFAULT_VOICE}' voice"
        )
        state = model.get_state_for_audio_prompt(DEFAULT_VOICE)

    export_model_state(state, voice_state_path)
    logger.info(f"Cached voice state: {voice_state_path}")

    return state


class PocketTTS:
    """Loads Pocket TTS once and reuses the profile's voice state across generations."""

    def __init__(self, profile_dir: Path):
        self.model = load_model()
        self.voice_state = load_voice_state(self.model, profile_dir)

    def synthesize(self, text: str) -> bytes:
        if not text.strip():
            return b""

        audio = self.model.generate_audio(
            self.voice_state, text, frames_after_eos=FRAMES_AFTER_EOS
        )

        arr = audio.detach().cpu().numpy().astype(np.float32)

        return numpy_to_wav_bytes(arr, sr=self.model.sample_rate)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare Pocket TTS voice states for OVA profiles."
    )
    parser.add_argument(
        "profiles",
        nargs="*",
        help="Profile names to set up (default: every directory under profiles/)",
    )
    args = parser.parse_args()

    if args.profiles:
        profile_dirs = []
        for name in args.profiles:
            profile_dir = PROFILES_DIR / name
            if (profile_dir / PROMPT_FILE).is_file():
                profile_dirs.append(profile_dir)
            else:
                logger.warning(
                    f"Skipping unknown profile '{name}' (no {PROMPT_FILE} in {profile_dir})"
                )
    else:
        profile_dirs = list_profile_dirs()

    model = load_model()

    warmup_dir = REPO_ROOT / ".ova"
    warmup_dir.mkdir(exist_ok=True)

    for profile_dir in profile_dirs:
        profile = profile_dir.name
        logger.info(f"Setting up voice for profile '{profile}'")

        try:
            state = load_voice_state(model, profile_dir)
        except ValueError as exc:
            logger.warning(f"Skipping profile '{profile}': {exc}")
            continue

        audio = model.generate_audio(
            state, WARMUP_DIALOGUE, frames_after_eos=FRAMES_AFTER_EOS
        )
        arr = audio.detach().cpu().numpy().astype(np.float32)

        warmup_wav = warmup_dir / f"warmup_{profile}.wav"
        warmup_wav.write_bytes(numpy_to_wav_bytes(arr, sr=model.sample_rate))
        logger.info(
            f"Voice check for '{profile}': {arr.size / model.sample_rate:.2f}s -> {warmup_wav}"
        )


if __name__ == "__main__":
    main()
