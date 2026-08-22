"""Microphone capture and audio playback for the desktop GUI.

Kept deliberately small. Recording captures mono 16-bit PCM into an in-memory
buffer and hands back a WAV byte blob that ``ova.pipeline.OVAPipeline`` can
transcribe directly (it resamples internally). Playback decodes a WAV blob and
plays it through the default output device.

``sounddevice`` is an optional dependency (the ``gui`` extra). It is imported
lazily so the rest of the GUI can still start and show a clear message if the
audio stack or a device is unavailable.
"""

import io
import wave

import numpy as np

RECORD_SR = 16000  # capture rate; ASR resamples to its own rate anyway


class AudioError(RuntimeError):
    """Raised for any recording/playback failure with a user-facing message."""


def _sd():
    """Import sounddevice lazily, turning import errors into AudioError."""
    try:
        import sounddevice as sd
    except Exception as exc:  # pragma: no cover - depends on host audio stack
        raise AudioError(
            "Audio support is unavailable: could not import 'sounddevice'. "
            "Install the GUI extra (pip install '.[gui]') and ensure PortAudio "
            "is present on this machine."
        ) from exc
    return sd


class MicRecorder:
    """Toggle-style microphone recorder backed by a sounddevice input stream."""

    def __init__(self, samplerate: int = RECORD_SR):
        self.samplerate = samplerate
        self._stream = None
        self._frames: list[np.ndarray] = []

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        if self._stream is not None:
            return
        sd = _sd()
        self._frames = []

        def _callback(indata, _frames, _time, status):  # noqa: ANN001
            # status carries xruns etc.; copy because indata is reused by PA.
            self._frames.append(indata.copy())

        try:
            self._stream = sd.InputStream(
                samplerate=self.samplerate,
                channels=1,
                dtype="int16",
                callback=_callback,
            )
            self._stream.start()
        except Exception as exc:  # pragma: no cover - depends on host devices
            self._stream = None
            raise AudioError(
                f"Could not open the microphone: {exc}. Check that an input "
                "device is connected and permitted."
            ) from exc

    def stop(self) -> bytes:
        """Stop recording and return the captured audio as WAV bytes."""
        if self._stream is None:
            return b""
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None

        if not self._frames:
            return b""

        audio = np.concatenate(self._frames, axis=0).reshape(-1).astype(np.int16)
        return _int16_to_wav_bytes(audio, self.samplerate)


def _int16_to_wav_bytes(audio: np.ndarray, samplerate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


def play_wav_bytes(data: bytes) -> None:
    """Play a WAV byte blob through the default output device (blocking).

    Intended to run on a worker thread, not the Qt UI thread.
    """
    if not data:
        return
    sd = _sd()

    with wave.open(io.BytesIO(data), "rb") as wf:
        sr = wf.getframerate()
        sampwidth = wf.getsampwidth()
        channels = wf.getnchannels()
        pcm = wf.readframes(wf.getnframes())

    if sampwidth != 2:
        raise AudioError(f"Unsupported playback sample width: {sampwidth} bytes")

    audio = np.frombuffer(pcm, dtype=np.int16)
    if channels > 1:
        audio = audio.reshape(-1, channels)

    try:
        sd.play(audio, sr)
        sd.wait()
    except Exception as exc:  # pragma: no cover - depends on host devices
        raise AudioError(f"Could not play audio: {exc}") from exc
