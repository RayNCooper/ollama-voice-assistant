# Ollama Voice Assistant

Open-source voice assistant: local ASR (NVIDIA parakeet) + local TTS (Kyutai Pocket TTS), LLM on Ollama Cloud via OpenAI-compatible `/v1`.

## Project identity (MANDATORY)
- This is a **fork of [acatovic/ova](https://github.com/acatovic/ova)**. Always credit the original.
- **Mostly written by AI** (Claude Code / Hermes). Disclose this honestly in the README and any public-facing copy.
- **Olio-branded**: it's published under the Olio Solutions identity. Use the real Olio brand assets, not invented shapes.

## Olio brand (from olio-letter-design skill)
- Accent: indigo `#6366f1`. Ink: `#1e293b` (slate-800). Muted: `#475569` (slate-600). Border: `#e2e8f0` (slate-200).
- Logo: `/home/hermeswebui/.hermes/skills/productivity/olio-letter-design/assets/olio-logo.png` (indigo wordmark).
- OG mark: `/workspace/scripts/og_mark.png` (transparent RGBA brand mark from olio.solutions/og.png).
- Fonts: Merriweather (body serif), Inter (sans), Caveat (signature).
- NO decorative chrome: no pill badges, no concentric circles, no invented geometry. Use real brand assets only.
- Olio is based in Mönchengladbach. Contact: dennis@olio.solutions, +49 172 7593488.

## Tech
- Python >=3.12, `uv` for env. Backend FastAPI + uvicorn, frontend plain HTML.
- LLM: `deepseek-v4-flash:0731` via Ollama Cloud (`OLLAMA_HOST` default `https://ollama.com/v1`, `OLLAMA_API_KEY` env).
- ASR/TTS run local. `ova.sh` orchestrates install/start/stop.

## Conventions
- Keep the `ova/` package name (it's the upstream layout).
- `gh_app_token.py` mints the GitHub App install token (walled-garden helper).
- Commit messages: concise, imperative.
