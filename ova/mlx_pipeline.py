import os
import tempfile

# mlx-audio 0.4.x has a circular import (stt.generate -> stt.models.glmasr ->
# stt.generate); importing stt.models first breaks the cycle.
import mlx_audio.stt.models  # noqa: F401
from mlx_audio.stt.generate import generate_transcription
from mlx_audio.stt.utils import load_model as load_asr_model
from ollama import chat

from .profiles import PROMPT_FILE, resolve_profile_dir
from .tts import PocketTTS

DEFAULT_CHAT_MODEL = "ministral-3:3b-instruct-2512-q4_K_M"
DEFAULT_ASR_MODEL = "mlx-community/parakeet-tdt-0.6b-v3"


class OVAPipeline:
    def __init__(self, profile: str = "default"):
        profile_dir = resolve_profile_dir(profile)
        self.profile = profile_dir.name

        self.system_prompt = (
            (profile_dir / PROMPT_FILE).read_text(encoding="utf-8").strip()
        )
        self.context = [{"role": "system", "content": self.system_prompt}]

        # initialize TTS
        self.tts_model = PocketTTS(profile_dir)

        # initialize ASR
        self.asr_model = load_asr_model(DEFAULT_ASR_MODEL)

        # initialize chat model
        self.chat_model = DEFAULT_CHAT_MODEL

    def tts(self, text: str) -> bytes:
        return self.tts_model.synthesize(text)

    def transcribe(self, wav_bytes: bytes) -> str:
        if not wav_bytes:
            return ""

        with tempfile.TemporaryDirectory(prefix="ova_transcribe_") as tmp_dir:
            audio_path = os.path.join(tmp_dir, "audio.wav")
            with open(audio_path, "wb") as audio_file:
                audio_file.write(wav_bytes)

            transcript_path = os.path.join(tmp_dir, "transcript")
            result = generate_transcription(
                model=self.asr_model,
                audio=audio_path,
                output_path=transcript_path,
                format="txt",
            )

        if hasattr(result, "text"):
            return result.text.strip()
        if isinstance(result, str):
            return result.strip()
        return str(result).strip()

    def chat(self, text: str) -> str:
        self.context.append({"role": "user", "content": text})

        response = chat(
            model=self.chat_model,
            messages=self.context,
            think=False,
            stream=False,
        )

        response = (
            response.message.content.replace("**", "")
            .replace("_", "")
            .replace("#", "")
            .strip()
        )

        self.context.append({"role": "assistant", "content": response})

        return response
