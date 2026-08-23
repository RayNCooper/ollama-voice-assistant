import os
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from . import settings
from .pipeline import DEFAULT_CHAT_MODEL, OLLAMA_HOST, OVAPipeline
from .version import BUILD, VERSION

OVA_PROFILE = os.getenv("OVA_PROFILE", "default")


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # The browser UI reads the transcript/reply text off the response headers.
    expose_headers=["X-OVA-Transcript", "X-OVA-Reply"],
)

# A key saved from the UI lives in .ova/api_key; make it the process default so
# the pipeline picks it up without the user exporting anything.
settings.apply_saved_api_key()

pipeline = OVAPipeline(profile=OVA_PROFILE)


def _header_safe(text: str) -> str:
    """Percent-encode text so it survives a latin-1 HTTP header round-trip."""
    return quote(text or "", safe="")


@app.get("/health")
async def health() -> dict:
    """Reachable only once the pipeline finished loading, which is the point."""
    return {"ready": True, "version": VERSION, "build": BUILD}


@app.get("/settings")
async def read_settings() -> dict:
    key = settings.active_api_key()
    return {
        "has_api_key": bool(key),
        "api_key_hint": settings.mask_api_key(key),
        "api_key_from_env": bool(os.environ.get("OLLAMA_API_KEY", "").strip())
        and not settings.load_api_key(),
        "model": pipeline.chat_model,
        "host": OLLAMA_HOST,
        "profile": pipeline.profile,
        "default_model": DEFAULT_CHAT_MODEL,
        "version": VERSION,
        "build": BUILD,
    }


class ApiKeyUpdate(BaseModel):
    api_key: str = ""


@app.post("/settings/api-key")
async def write_api_key(update: ApiKeyUpdate) -> dict:
    key = (update.api_key or "").strip()
    settings.save_api_key(key)
    # chat() reads os.environ at call time, so this takes effect immediately.
    os.environ["OLLAMA_API_KEY"] = key
    return {
        "has_api_key": bool(key),
        "api_key_hint": settings.mask_api_key(key),
    }


@app.post("/chat", response_class=Response)
async def chat_request_handler(request: Request):
    audio_in = await request.body()

    transcribed_text = pipeline.transcribe(audio_in)

    if not transcribed_text:
        # return "empty" bytes if no transcription
        return Response(content=bytes(), media_type="audio/wav")

    if not settings.active_api_key():
        return JSONResponse(
            status_code=503,
            content={
                "error": "no_api_key",
                "transcript": transcribed_text,
                "detail": (
                    "No Ollama Cloud API key set. Add one in Settings to get "
                    "spoken replies."
                ),
            },
        )

    try:
        chat_response = pipeline.chat(transcribed_text)
    except Exception as exc:  # surface the reason instead of a bare 500
        return JSONResponse(
            status_code=502,
            content={
                "error": "chat_failed",
                "transcript": transcribed_text,
                "detail": str(exc),
            },
        )

    audio_out = pipeline.tts(chat_response)

    return Response(
        content=audio_out,
        media_type="audio/wav",
        headers={
            "X-OVA-Transcript": _header_safe(transcribed_text),
            "X-OVA-Reply": _header_safe(chat_response),
        },
    )
