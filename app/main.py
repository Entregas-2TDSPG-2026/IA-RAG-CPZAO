"""API e interface do chat RAG da disciplina."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.rag import RagService

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app = FastAPI(title="Disruptive Architectures RAG", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
service: RagService | None = None
requests_by_ip: dict[str, deque[float]] = defaultdict(deque)


@app.on_event("startup")
def load_service() -> None:
    global service
    try:
        service = RagService()
    except (OSError, ValueError, KeyError) as exc:
        logger.error("Índice ou configuração indisponível: %s", exc)
        service = None


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1600)


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=1200)
    conversation_id: UUID | None = None
    history: list[Turn] = Field(default_factory=list, max_length=12)


@app.get("/")
def homepage() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/widget.js")
def widget() -> FileResponse:
    return FileResponse(STATIC_DIR / "widget.js", media_type="application/javascript")


@app.get("/api/health")
def health() -> JSONResponse:
    if service is None:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok", **service.metadata})


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request) -> dict:
    if service is None:
        raise HTTPException(status_code=503, detail="O chat ainda não está pronto. Tente novamente.")
    ip = request.client.host if request.client else "unknown"
    window = requests_by_ip[ip]
    now = time.monotonic()
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= 30:
        raise HTTPException(status_code=429, detail="Muitas perguntas em sequência. Aguarde um minuto.")
    window.append(now)
    try:
        result = await asyncio.to_thread(
            service.answer,
            payload.message.strip(),
            [turn.model_dump() for turn in payload.history],
        )
    except Exception:
        logger.exception("Falha ao consultar a API Gemini")
        raise HTTPException(
            status_code=503,
            detail="Não consegui consultar a IA agora. Tente novamente em instantes.",
        ) from None
    return {"conversation_id": str(payload.conversation_id or uuid4()), **result}
