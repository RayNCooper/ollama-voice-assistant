# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-09-01

### Added
- WebGL orb frontend: a shader-displaced icosahedron that breathes with the
  conversation and reacts to live audio amplitude (listening / thinking /
  speaking states), built on a vendored three.js copy in `assets/vendor/`
  (`assets/orb.js`, `assets/orb.noise.js`, `assets/app.js`, `assets/audio.js`).
- `POST /transcribe` endpoint in `ova/api.py`: partial ASR-only transcription
  for the live "what I'm hearing" display while you talk. Same ASR model as
  `/chat` with no LLM or TTS cost; failures never break the turn.
- CSS fallback orb for browsers without WebGL.
- Regenerated Tauri platform icons (macOS + Windows) from the Olio brand mark.

### Changed
- Full dark-theme UI redesign of `index.html`: ambient lighting, dissolving
  transcript stream, and the orb as the app's centerpiece.
- Updated `.gitignore` for local debug artifacts.

## [0.1.0] - 2026-08-23

### Added
- Initial fork of [acatovic/ova](https://github.com/acatovic/ova): local ASR
  (NVIDIA Parakeet) + local TTS (Kyutai Pocket TTS) with the LLM on Ollama
  Cloud via the OpenAI-compatible `/v1` endpoint.
- Docker + packaging for one-liner runs; `ova.sh` orchestrator.
- Cross-platform desktop GUI with consent-gated voice cloning.
- In-app setting for the Ollama Cloud API key.
- Tauri desktop-app scaffold with macOS build via `./mac_build.sh`
  (signing, mic entitlement).
- Web UI with transcript, states, and in-app API key settings.