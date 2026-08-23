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

### Web UI (`index.html`)

`index.html` is the browser frontend, served on `:8000` by `ova.sh start` and by
the Tauri desktop app. It is a single Olio-branded page:

- a **microphone button** (or the <kbd>space</kbd> key) to record, send, and
  hear the reply, with the state - listening, thinking, speaking - always
  spelled out underneath;
- a **running transcript** of both sides of the conversation, so you can read
  what was heard and what was answered;
- a **Settings** panel holding the Ollama Cloud API key, plus the active model,
  endpoint, and voice profile, closing with the Olio wordmark
  (`assets/olio-wordmark.png`) and the running version and build (e.g.
  *Version 0.1.0 - build cee594f*; a trailing `+` means the working tree was
  dirty at launch).

**Setting the API key from the UI.** Open *Settings*, paste your key, and press
*Save key*. The key is written to `.ova/api_key` (gitignored, `0600`) and takes
effect on the next turn - no restart and no `OLLAMA_API_KEY` export needed. It
is also picked up automatically the next time the backend starts. An
`OLLAMA_API_KEY` present in the environment still wins over the saved key. If no
key is set at all, the page says so and opens Settings for you; recording and
transcription keep working, only the reply needs the key.

The backend exposes this to the page over three small endpoints alongside
`POST /chat`: `GET /health`, `GET /settings`, and `POST /settings/api-key`.
`/chat` additionally returns the transcript and the reply text in the
`X-OVA-Transcript` / `X-OVA-Reply` response headers.

### Desktop app (Tauri)

A native desktop wrapper for the web UI lives in `tauri/`. It is a thin
[Tauri 2](https://v2.tauri.app/) shell: on launch it spawns the same
Python backend (`uvicorn ova.api:app` on `:5173`) and a static file server for
`index.html` (`python -m http.server` on `:8000`) as child processes, points a
900x700 webview at `http://localhost:8000`, and kills both processes on quit.
Nothing in the pipeline changes - the desktop app reuses exactly what `ova.sh`
runs. Both servers bind to loopback only.

> The webview loads the frontend from `http://localhost:8000` (not a bundled
> `tauri://` asset) on purpose: the backend's CORS policy only allows the
> `localhost:5173` / `localhost:8000` origins, so the page must be served from
> one of them for its `fetch` to `/chat` to succeed.

**Prerequisites**

- [Rust + Cargo](https://rustup.rs/) (Tauri compiles a small Rust shell)
- `uv` and the Python deps installed: `uv pip install -e ".[cuda]"`
  (on Apple Silicon, torch/NeMo run via CPU/MPS)
- The system webview: Xcode Command Line Tools on macOS (`xcode-select --install`)
- An **Ollama Cloud** API key available in the launch environment
  (`OLLAMA_API_KEY`)

**One-command macOS build**

```bash
./mac_build.sh
```

The script verifies it is running on macOS, ensures `uv` + the `.venv` and the
`.[cuda]` deps, checks the Rust toolchain (installing the Tauri CLI if needed),
regenerates the Olio-branded icons, and runs `cargo tauri build`. The bundles
land in:

```
tauri/src-tauri/target/release/bundle/macos/Ollama Voice Assistant.app
tauri/src-tauri/target/release/bundle/dmg/*.dmg
```

For a dev run without bundling: `cd tauri && cargo tauri dev`.

**First-run caveats**

- The very first launch downloads the ASR/TTS weights (a few minutes) unless
  you already ran `./ova.sh install --cuda`. The window opens immediately; the
  first voice request waits for the backend to finish warming up.
- The app runs the backend from **this repository** (it uses the repo's `.venv`
  and locates the repo relative to the build). Keep the repo in place; if you
  move the `.app` to another machine, set `OVA_REPO_DIR` to the repo path.
- Launched from Finder, GUI apps inherit a minimal environment. If your
  `OLLAMA_API_KEY` is set in a shell profile, either launch the `.app` from a
  terminal (`open -a "Ollama Voice Assistant"` inherits your shell env) or set
  the key system-wide (`launchctl setenv OLLAMA_API_KEY ...`).

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
| `OLLAMA_API_KEY` | *(required)* | Ollama Cloud API key. Optional if you saved one from the UI (Settings panel in the web UI, or the Settings tab in the desktop GUI); the env var wins when both are set. |
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
