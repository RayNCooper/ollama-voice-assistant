# ollama-voice-assistant

An open-source voice assistant from [Olio Solutions](https://olio.solutions). ASR and TTS run fully local with open-weight models; the LLM ("the brain") runs on Ollama Cloud via its OpenAI-compatible API.

It uses a simple FastAPI backend and a plain HTML front-end. You get a smarter, faster model without needing a GPU big enough to hold it, because the heavy LLM lives in the cloud while speech recognition and speech synthesis stay on your machine.

## About this project

- **A fork.** This is a fork of [acatovic/ova](https://github.com/acatovic/ova). The original design and much of the pipeline are its work; full credit to the upstream author. This fork swaps the local Ollama LLM for Ollama Cloud.
- **Mostly written by AI.** The code and docs in this fork are mostly written by AI (Claude Code / Hermes), reviewed and shipped by a human. We disclose this openly.
- **An Olio Solutions open-source project.** Published under the [Olio Solutions](https://olio.solutions) identity, based in Mönchengladbach, Germany. Contact: dennis@olio.solutions.

Models used:

* ASR: [NVIDIA parakeet-tdt-0.6b-v3 600M](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) (local)
* LLM: [deepseek-v4-flash:0731](https://ollama.com/library/deepseek-v4-flash) via Ollama Cloud (fast + intelligent; swap in `ova/pipeline.py` for any other cloud model)
* TTS: [Kyutai Pocket TTS](https://huggingface.co/kyutai/pocket-tts) - a lightweight CPU-friendly TTS with built-in voice cloning (local)

How it works:

1. Frontend captures user's audio and sends a blob of bytes to the backend `/chat` endpoint
2. Backend parses the bytes, extracts sample rate (SR) and channels, then:
   1. Transcribes the audio to text using an automatic speech recognition (ASR) model
   2. Sends the transcribed text to the LLM on **Ollama Cloud**, i.e. "the brain"
   3. Sends the LLM response to a text-to-speech (TTS) model
   4. Performs normalization of TTS output, converts it to bytes, and sends the bytes back to frontend
3. The frontend plays the response audio back to the user

All voices - the default one and the cloned ones - are handled by a single TTS model: Kyutai's Pocket TTS. It runs faster than real-time on a plain CPU.

Voice cloning requires no finetuning and no transcript: a profile is just a 3-30 second `ref_audio.wav` clip plus a `prompt.txt` with instructions for the LLM. During install (`./ova.sh install`), a one-off setup step encodes each profile's reference clip into a voice state (`profiles/<profile>/voice.safetensors`) and runs a short warmup dialogue (saved under `.ova/` so you can audition each voice). Subsequent starts simply load the cached `.safetensors`, which is much faster than re-encoding the audio. The default profile has no reference clip and uses Pocket TTS's built-in "alba" voice - a nice female voice.

> **Note on voice cloning:** encoding your own `ref_audio.wav` requires access to the gated [kyutai/pocket-tts](https://huggingface.co/kyutai/pocket-tts) weights - accept the terms on the model page and log in locally with `uvx hf auth login`. Without it, the built-in voices (e.g. the default profile) still work, and the install step will simply skip the cloned profiles with a warning.


## Quick start

### Docker (one-liner)

The fastest way to run the whole thing. You only need Docker and an Ollama Cloud
API key. ASR + TTS run locally inside the container; the LLM runs on Ollama Cloud.

```bash
export OLLAMA_API_KEY=your_key   # or put it in a .env file (see .env.example)
docker compose up --build
```

Then open **http://localhost:8000**. The backend API is on `:5173`.

- The image bundles the CUDA (Linux) pipeline; the container works on CPU out of
  the box. For GPU acceleration, install the NVIDIA Container Toolkit and
  uncomment `gpus: all` in `docker-compose.yml`.
- First boot downloads the ASR/TTS weights (cached in a named volume for next
  time), so the initial start takes a few minutes.

### pip / uv

Prefer a native install (you already have `uv` and an NVIDIA/CUDA machine)?
Install the deps and use `ova.sh` to orchestrate everything:

```bash
# NVIDIA / CUDA
pip install ".[cuda]"

# then install models + run (uses uv under the hood)
OLLAMA_API_KEY=your_key ./ova.sh install --cuda
OLLAMA_API_KEY=your_key ./ova.sh start
```

See [Install](#install) and [Start](#start) below for details.

### Desktop GUI

A cross-platform desktop app (PySide6/Qt) is the primary experience: voice chat
and voice cloning in one native window, Olio-branded. It imports the pipeline
directly and runs everything in a single process (local ASR + TTS, LLM on Ollama
Cloud).

Install the optional `gui` extra (PySide6 + sounddevice), then launch `gui.py`:

```bash
# GUI extra (add [cuda] too for the local ASR/TTS backend)
pip install ".[gui,cuda]"

OLLAMA_API_KEY=your_key python gui.py
```

The app has three tabs:

- **Chat** - click *Record*, speak, click again to send; the assistant
  transcribes, replies via Ollama Cloud, and speaks the answer back. A banner
  warns you if no Ollama Cloud API key is set.
- **Voices** - list your voices, set the active one, and create a new clone from
  a short reference `.wav`.
- **Settings** - paste your Ollama Cloud API key here instead of setting
  `OLLAMA_API_KEY`; it is saved locally and takes effect immediately (no
  restart).

**Consent gate.** Creating a cloned voice always opens a mandatory consent
dialog asking whether *"the person in this recording has been informed and
personally consented to their voice being cloned and used by this app."* The
*Create Voice* button stays disabled until you tick **both** boxes ("the person
has been informed" and "the person has personally consented"); there is no way
to skip it. Each confirmed clone is recorded - with a UTC timestamp and profile
name - to an append-only audit log at `consent_log.jsonl` in the repo root.

## Pre-requisites

- Python >=3.12
- `uv` installed and available in PATH
- An **Ollama Cloud** API key (set `OLLAMA_API_KEY`; get one at https://ollama.com)

## Install

Fetch Python deps and HF models (the LLM is not downloaded; it lives on Ollama Cloud):

```bash
OLLAMA_API_KEY=your_key ./ova.sh install --cuda
```

The last install step downloads the Pocket TTS weights, builds the voice state (`voice.safetensors`) for every profile, and generates a short warmup dialogue per voice under `.ova/` - have a listen! Cloning your own voice (adding a profile with a `ref_audio.wav`) needs access to the gated [kyutai/pocket-tts](https://huggingface.co/kyutai/pocket-tts) weights (see the note above); the default voice works without it.

## Start

Start the front-end and back-end services (non-blocking) with a fast default voice assistant:

```bash
OLLAMA_API_KEY=your_key ./ova.sh start
```

To start the voice assistant with one of your own cloned voices (see [Adding new voices](#adding-new-voices-clones--profiles) or use the [Desktop GUI](#desktop-gui)):

```bash
OVA_PROFILE=my-voice OLLAMA_API_KEY=your_key ./ova.sh start
```

- Front-end: http://localhost:8000
- Back-end: http://localhost:5173

Logs and PIDs are stored under `.ova/`. If you want to follow the logs in another terminal window:

```bash
tail -f .ova/backend.log
```

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `OLLAMA_API_KEY` | *(required)* | Ollama Cloud API key |
| `OLLAMA_HOST` | `https://ollama.com/v1` | OpenAI-compatible base URL for Ollama Cloud. |
| `OVA_PROFILE` | `default` | Voice profile to use |

To change the LLM, edit `DEFAULT_CHAT_MODEL` in `ova/pipeline.py` (any model available on Ollama Cloud works, e.g. `glm-5.2`, `kimi-k3`, `nemotron-3-nano:30b`).

## Stop

Stop all services:

```bash
./ova.sh stop
```

## Adding new voices (clones / profiles)

In order to add a new voice, no code changes are required. You simply need to do the following:

1. Create a new directory `profiles/<voice>/`
2. Add a 3-30 second voice clip `ref_audio.wav` and any instructions in the `prompt.txt` - both under the sub-directory created in the previous step. No transcript needed!
3. To start the service with the new voice, simply run `OVA_PROFILE=<voice> ./ova.sh start`

On first start the reference clip is encoded and cached as `profiles/<voice>/voice.safetensors`; subsequent starts load the cached voice state directly. You can also pre-build the voice state (and get a warmup clip to audition under `.ova/`) with:

```bash
uv run --no-sync python3 -m ova.tts <voice>
```

---

**Disclaimer & Ethical Considerations:** This project is a proof-of-concept demonstration and is provided **as is** without any warranties or guarantees. It is intended for educational and experimental purposes only. The voice cloning is also purely for educational purposes - for real-life/commercial use, one should always seek the relevant permissions. This demo also highlights the ethical and security aspects - the ease with which one can clone a voice with no finetuning, using only a 3-5 second audio clip - which is both eerie, and potentially dangerous in the wrong hands. The ASR and TTS run locally; the LLM runs on Ollama Cloud.
