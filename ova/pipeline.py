import io
import os
import wave

import nemo.collections.asr as nemo_asr
import numpy as np
import torch
from openai import OpenAI
from omegaconf import OmegaConf

from .audio import resample
from .profiles import PROMPT_FILE, resolve_profile_dir
from .tts import PocketTTS
from .utils import get_device, logger

DEFAULT_SR = 24000  # default sample rate
DEFAULT_CHAT_MODEL = "deepseek-v4-flash:0731"
DEFAULT_ASR_MODEL = "nvidia/parakeet-tdt-0.6b-v3"

# Ollama Cloud backend (OpenAI-compatible). Falls back to local Ollama if unset.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "https://ollama.com/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")


class OVAPipeline:
    def __init__(self, profile: str = "default"):
        profile_dir = resolve_profile_dir(profile)
        self.profile = profile_dir.name

        self.device = get_device()

        self.system_prompt = (
            (profile_dir / PROMPT_FILE).read_text(encoding="utf-8").strip()
        )
        self.context = [{"role": "system", "content": self.system_prompt}]

        # initialize TTS
        self.tts_model = PocketTTS(profile_dir)

        # initialize ASR
        self.asr_model = nemo_asr.models.ASRModel.from_pretrained(
            model_name=DEFAULT_ASR_MODEL
        )
        self._configure_asr_decoding()

        # initialize chat model
        self.chat_model = DEFAULT_CHAT_MODEL

    def _disable_asr_cuda_graphs(self) -> bool:
        decoding = getattr(getattr(self.asr_model, "decoding", None), "decoding", None)
        if decoding is None or not hasattr(decoding, "disable_cuda_graphs"):
            return False

        changed = bool(decoding.disable_cuda_graphs())
        if changed:
            logger.info("Disabled NeMo CUDA graph decoder for ASR.")
        return changed

    def _configure_asr_decoding(self) -> None:
        if not str(self.device).startswith("cuda"):
            return

        decoding_cfg = getattr(getattr(self.asr_model, "cfg", None), "decoding", None)
        if decoding_cfg is None:
            self._disable_asr_cuda_graphs()
            return

        try:
            decoding_cfg = OmegaConf.to_container(decoding_cfg, resolve=True)
            if not isinstance(decoding_cfg, dict):
                raise TypeError(f"Unexpected decoding config type: {type(decoding_cfg)}")

            greedy_cfg = decoding_cfg.setdefault("greedy", {})
            if greedy_cfg.get("use_cuda_graph_decoder") is False:
                self._disable_asr_cuda_graphs()
                return

            greedy_cfg["use_cuda_graph_decoder"] = False
            self.asr_model.change_decoding_strategy(
                OmegaConf.create(decoding_cfg), verbose=False
            )
            logger.info(
                "Configured ASR decoding with NeMo CUDA graph decoder disabled."
            )
        except Exception as exc:
            logger.warning(
                "Failed to reconfigure ASR decoding strategy (%s). Disabling CUDA graphs directly.",
                exc,
            )
            self._disable_asr_cuda_graphs()

    def _decode_asr(
        self, audio_tensor: torch.Tensor, length_tensor: torch.Tensor
    ) -> str:
        self.asr_model.eval()
        with torch.inference_mode():
            out = self.asr_model(
                input_signal=audio_tensor, input_signal_length=length_tensor
            )

            if isinstance(out, (tuple, list)) and len(out) >= 2:
                logits, logit_lengths = out[0], out[1]
            elif isinstance(out, dict):
                logits = out.get("logits", out.get("encoded"))
                logit_lengths = out.get("logit_lengths", out.get("encoded_len"))
                if logits is None or logit_lengths is None:
                    raise RuntimeError(
                        f"Unexpected model output keys: {list(out.keys())}"
                    )
            else:
                raise RuntimeError(f"Unexpected model output type: {type(out)}")

            decoding = getattr(self.asr_model, "decoding", None)
            if decoding is None:
                raise RuntimeError("Model has no `decoding`; cannot decode.")

            if hasattr(decoding, "ctc_decoder_predictions_tensor"):
                texts = decoding.ctc_decoder_predictions_tensor(logits, logit_lengths)
            elif hasattr(decoding, "rnnt_decoder_predictions_tensor"):
                texts = decoding.rnnt_decoder_predictions_tensor(logits, logit_lengths)
            else:
                raise RuntimeError(
                    "No supported decoder method found on `asr_model.decoding`."
                )

        # Extract text from Hypothesis object if needed
        if texts and len(texts) > 0:
            text = texts[0]
            if hasattr(text, "text"):
                return text.text.strip()
            elif isinstance(text, str):
                return text.strip()
            else:
                return str(text).strip()

        return ""

    def tts(self, text: str) -> bytes:
        return self.tts_model.synthesize(text)

    def transcribe(self, wav_bytes: bytes) -> str:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            num_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            src_sr = wf.getframerate()
            num_frames = wf.getnframes()
            pcm = wf.readframes(num_frames)

        # PCM -> float32 in [-1, 1]
        if sampwidth == 1:
            audio = np.frombuffer(pcm, dtype=np.uint8).astype(np.int16) - 128
            audio = audio.astype(np.float32) / 128.0
        elif sampwidth == 2:
            audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 4:
            a_f32 = np.frombuffer(pcm, dtype=np.float32)
            if (
                np.isfinite(a_f32).all()
                and (np.abs(a_f32).max() <= 10.0)
                and (np.abs(a_f32).mean() < 0.5)
            ):
                audio = a_f32.astype(np.float32)
            else:
                audio = (
                    np.frombuffer(pcm, dtype=np.int32).astype(np.float32) / 2147483648.0
                )
        else:
            raise ValueError(f"Unsupported WAV sample width: {sampwidth} bytes")

        # Downmix to mono if needed
        if num_channels > 1:
            audio = audio.reshape(-1, num_channels).mean(axis=1).astype(np.float32)

        # Resample to model SR
        model_sr = int(
            getattr(getattr(self.asr_model, "cfg", None), "sample_rate", DEFAULT_SR)
        )
        audio = resample(audio, src_sr, model_sr)

        # Torch tensors on model device
        device = next(self.asr_model.parameters()).device
        audio_tensor = (
            torch.from_numpy(audio).unsqueeze(0).to(device=device, dtype=torch.float32)
        )  # [1, T]
        length_tensor = torch.tensor([audio.shape[0]], device=device, dtype=torch.long)

        try:
            return self._decode_asr(audio_tensor, length_tensor)
        except Exception as exc:
            exc_msg = str(exc).lower()
            is_cuda_graph_failure = device.type == "cuda" and (
                "not enough values to unpack" in exc_msg
                or "too many values to unpack" in exc_msg
            )
            if is_cuda_graph_failure and self._disable_asr_cuda_graphs():
                logger.warning(
                    "ASR CUDA graph decoding failed (%s). Retrying with CUDA graphs disabled.",
                    exc,
                )
                return self._decode_asr(audio_tensor, length_tensor)

            is_cuda_failure = device.type == "cuda" and (
                "cufft" in exc_msg
                or "cuda out of memory" in exc_msg
                or "cublas" in exc_msg
                or "cuda error" in exc_msg
            )
            if not is_cuda_failure:
                raise

            logger.warning(
                "ASR failed on CUDA (%s). Falling back to CPU transcription.", exc
            )
            self.asr_model = self.asr_model.to("cpu")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            audio_tensor = (
                torch.from_numpy(audio)
                .unsqueeze(0)
                .to(device="cpu", dtype=torch.float32)
            )
            length_tensor = torch.tensor(
                [audio.shape[0]], device="cpu", dtype=torch.long
            )
            return self._decode_asr(audio_tensor, length_tensor)

    def chat(self, text: str) -> str:
        self.context.append({"role": "user", "content": text})

        client = OpenAI(base_url=OLLAMA_HOST, api_key=OLLAMA_API_KEY or "ollama")

        response = client.chat.completions.create(
            model=self.chat_model,
            messages=self.context,
            stream=False,
        )

        response = (
            response.choices[0].message.content.replace("**", "")
            .replace("_", "")
            .replace("#", "")
            .strip()
        )

        self.context.append({"role": "assistant", "content": response})

        return response
