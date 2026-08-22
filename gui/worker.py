"""Background worker that owns the OVA pipeline off the Qt UI thread.

``OVAPipeline`` loads NeMo/torch (ASR) and Pocket TTS, and each turn does
blocking ASR -> LLM -> TTS work. All of that runs here, on a dedicated
``QThread``, so the UI never freezes. The worker is a ``QObject`` moved onto the
thread; UI-thread request signals are connected to its slots (Qt delivers them
as queued calls), and it reports back with its own signals.

The pipeline is not re-entrant, so requests are naturally serialised: the single
worker thread processes one slot invocation at a time.
"""

import os
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from . import audio_io, settings, voices


class PipelineWorker(QObject):
    # Loading lifecycle
    load_started = Signal()
    loaded = Signal(list, str, bool)  # voices, current profile, has_api_key
    load_failed = Signal(str)

    # Chat lifecycle
    status = Signal(str)
    transcribed = Signal(str)
    turn_done = Signal(str, str)  # transcript, response
    turn_empty = Signal()
    turn_failed = Signal(str)

    # Voice management
    voice_created = Signal(str, list)  # new name, refreshed voices
    voice_create_failed = Signal(str)
    voice_switched = Signal(str)
    voice_switch_failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.pipeline = None

    # ------------------------------------------------------------------ load
    @Slot()
    def load(self) -> None:
        self.load_started.emit()

        # A key saved in the GUI takes precedence and is restored into the
        # environment so the pipeline picks it up; otherwise keep whatever the
        # OLLAMA_API_KEY env var already provides.
        saved_key = settings.load_api_key()
        if saved_key:
            os.environ["OLLAMA_API_KEY"] = saved_key

        try:
            # Imported lazily: pulls in torch / NeMo / Pocket TTS.
            from ova.pipeline import OVAPipeline

            self.status.emit("Loading speech models (first run downloads weights)...")
            self.pipeline = OVAPipeline(profile="default")
        except Exception as exc:  # pragma: no cover - depends on model stack
            self.load_failed.emit(
                f"Failed to load the voice pipeline:\n{exc}\n\n"
                "Make sure the CUDA extra is installed (pip install '.[cuda]') "
                "and the ASR/TTS weights are available."
            )
            return

        has_api_key = bool(os.environ.get("OLLAMA_API_KEY", "").strip())
        self.loaded.emit(voices.list_voices(), self.pipeline.profile, has_api_key)
        self.status.emit("Ready.")

    # ------------------------------------------------------------------ chat
    @Slot(object)
    def process_turn(self, wav_bytes: bytes) -> None:
        if self.pipeline is None:
            self.turn_failed.emit("The pipeline is still loading.")
            return
        try:
            self.status.emit("Transcribing...")
            transcript = self.pipeline.transcribe(wav_bytes)
            if not transcript:
                self.turn_empty.emit()
                self.status.emit("Ready.")
                return
            self.transcribed.emit(transcript)

            self.status.emit("Thinking...")
            response = self.pipeline.chat(transcript)

            self.status.emit("Speaking...")
            audio_out = self.pipeline.tts(response)
            self.turn_done.emit(transcript, response)

            try:
                audio_io.play_wav_bytes(audio_out)
            except audio_io.AudioError as exc:
                self.status.emit(f"Playback unavailable: {exc}")
            self.status.emit("Ready.")
        except Exception as exc:  # pragma: no cover - runtime/model failures
            traceback.print_exc()
            self.turn_failed.emit(str(exc))
            self.status.emit("Ready.")

    # ---------------------------------------------------------------- voices
    @Slot(str, str, str)
    def create_voice(self, name: str, wav_path: str, prompt_text: str) -> None:
        if self.pipeline is None:
            self.voice_create_failed.emit("The pipeline is still loading.")
            return
        try:
            self.status.emit(f"Encoding voice '{name}' (this can take a moment)...")
            voices.create_clone(
                name, Path(wav_path), prompt_text, self.pipeline.tts_model.model
            )
            self.voice_created.emit(name, voices.list_voices())
            self.status.emit(f"Voice '{name}' created.")
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            self.voice_create_failed.emit(str(exc))
            self.status.emit("Ready.")

    @Slot(str)
    def switch_voice(self, name: str) -> None:
        if self.pipeline is None:
            self.voice_switch_failed.emit("The pipeline is still loading.")
            return
        try:
            from ova.profiles import PROMPT_FILE, resolve_profile_dir
            from ova.tts import load_voice_state

            self.status.emit(f"Switching to voice '{name}'...")
            profile_dir = resolve_profile_dir(name)

            # Swap only the TTS voice state and system prompt on the live
            # pipeline (fast) instead of rebuilding ASR. This resets the
            # conversation, which is the expected behaviour on a voice change.
            model = self.pipeline.tts_model.model
            self.pipeline.tts_model.voice_state = load_voice_state(model, profile_dir)
            self.pipeline.system_prompt = (
                (profile_dir / PROMPT_FILE).read_text(encoding="utf-8").strip()
            )
            self.pipeline.context = [
                {"role": "system", "content": self.pipeline.system_prompt}
            ]
            self.pipeline.profile = profile_dir.name

            self.voice_switched.emit(profile_dir.name)
            self.status.emit(f"Active voice: {profile_dir.name}")
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            self.voice_switch_failed.emit(str(exc))
            self.status.emit("Ready.")
