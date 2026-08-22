# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Ollama Voice Assistant — CUDA (Linux) backend image.
#
# ASR (NVIDIA parakeet via NeMo/torch) and TTS (Kyutai pocket-tts) run locally
# inside this container. The LLM runs on Ollama Cloud via the OpenAI-compatible
# API (OLLAMA_HOST / OLLAMA_API_KEY). The image is large by nature — torch and
# nemo-toolkit pull in a heavy dependency tree.
#
# torch installs the CUDA-enabled PyPI wheel. GPU acceleration kicks in when the
# container is run with the NVIDIA runtime (`--gpus all` / compose `gpus`); with
# no GPU the pipeline transparently falls back to CPU.
# ---------------------------------------------------------------------------

# ---- builder: resolve + install all deps into an isolated venv -------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install the project with the CUDA extra (torch, torchaudio, nemo-toolkit[asr],
# cuda-python) plus the base deps (fastapi, uvicorn, openai, numpy, soxr,
# pocket-tts). Copy the metadata + package sources needed to build the wheel.
COPY pyproject.toml README.md ./
COPY ova ./ova
RUN pip install --upgrade pip && pip install ".[cuda]"

# ---- runtime: slim image with only the venv + app sources ------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/root/.cache/huggingface

# libsndfile + ffmpeg are needed for audio I/O (pocket-tts, nemo, soxr).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsndfile1 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY ova ./ova
COPY profiles ./profiles
COPY index.html ./index.html

# Select the CUDA pipeline (ova/api.py reads backend=<x> from .config).
RUN echo "backend=cuda" > .config

# Backend (FastAPI) port. The frontend talks to it at http://localhost:5173.
EXPOSE 5173

# The API server binds the port only after models finish loading, so give it a
# generous start period (first boot also downloads the ASR/TTS weights).
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=5 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(3); s.connect(('127.0.0.1', 5173)); s.close()" || exit 1

CMD ["uvicorn", "ova.api:app", "--host", "0.0.0.0", "--port", "5173"]
