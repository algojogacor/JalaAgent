"""jala serve — JalaAgent as Anthropic-Compatible API proxy."""

import json
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
_TRIVIAL = {"hello", "hi", "ping", "test", "help", "what's up", "hey"}


async def _build_proxy_provider() -> Any:
    try:
        import importlib
        return importlib.import_module("provider_universal.provider").OpenAICompatibleProvider()
    except Exception:
        from provider_ollama.provider import OllamaProvider
        return OllamaProvider()


def create_app(token: str | None = None) -> FastAPI:
    app = FastAPI(title="JalaAgent API", version="2026.6.18")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def _auth(request: Request, call_next: Any) -> Any:  # pyright: ignore[reportUnusedFunction]
        if token:
            ah = request.headers.get("x-api-key", "") or request.headers.get("authorization", "")
            if not ah or (ah != token and ah != f"Bearer {token}"):
                return StreamingResponse(
                    iter([json.dumps({"error": {"type": "authentication_error", "message": "Invalid API key"}})]),
                    media_type="text/event-stream", status_code=401,
                )
        return await call_next(request)

    @app.get("/v1/models")
    async def _models() -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        p = await _build_proxy_provider()
        models = []
        for name, info in p._config.get("providers", {}).items():
            for m in info.get("models", []):
                mn = m if isinstance(m, str) else m.get("name", "")
                if mn: models.append({"id": mn, "object": "model", "owned_by": name})
        return {"object": "list", "data": models[:50]}

    @app.post("/v1/messages/count_tokens")
    async def _count(body: dict[str, Any]) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        total = len(body.get("system", ""))
        for m in body.get("messages", []):
            if isinstance(m.get("content"), str): total += len(m["content"])
        return {"input_tokens": total // 4}

    @app.post("/v1/messages")
    async def _messages(body: dict[str, Any]) -> StreamingResponse:  # pyright: ignore[reportUnusedFunction]
        p = await _build_proxy_provider()
        user_text = ""
        for m in body.get("messages", []):
            if m.get("role") == "user" and isinstance(m.get("content"), str):
                user_text = m["content"].strip().lower()
        if user_text in _TRIVIAL:
            async def _t():
                yield f"data: {json.dumps({'type':'content_block_delta','delta':{'type':'text_delta','text':user_text.title()+'! How can I help?'}})}\n\n"
                yield "data: {\"type\":\"message_stop\"}\n\n"
            return StreamingResponse(_t(), media_type="text/event-stream")
        model = body.get("model", "claude-sonnet-4-6")
        system = body.get("system", "")
        tools = body.get("tools", [])
        from agent_core.models import AgentMessage, ProviderChunkType
        amsgs = []
        for m in body.get("messages", []):
            c = m.get("content", "")
            if isinstance(c, list): c = " ".join(b.get("text", "") for b in c if b.get("type") == "text")
            amsgs.append(AgentMessage(role=m.get("role", "user"), content=c))
        async def _s():
            try:
                async for chunk in p.stream_completion(messages=amsgs, tools=tools, system=system, model=model):
                    if chunk.type == ProviderChunkType.TEXT and chunk.content:
                        yield f"data: {json.dumps({'type':'content_block_delta','delta':{'type':'text_delta','text':chunk.content}})}\n\n"
                    elif chunk.type == ProviderChunkType.DONE:
                        yield "data: {\"type\":\"message_stop\"}\n\n"; break
            except Exception as exc:
                yield f"data: {json.dumps({'type':'error','error':{'type':'api_error','message':str(exc)}})}\n\n"
        return StreamingResponse(_s(), media_type="text/event-stream")

    return app


def run_server(host: str = "127.0.0.1", port: int = 8787, token: str | None = None) -> None:
    import uvicorn
    a = f" (auth: {token[:8]}...)" if token else " (no auth)"
    print(f"🪼 JalaAgent API v2026.6.18 — http://{host}:{port}{a}")
    print(f"   Models: http://{host}:{port}/v1/models")
    print(f"   Chat:   POST http://{host}:{port}/v1/messages")
    print(f"   Use:    ANTHROPIC_BASE_URL=http://{host}:{port} claude")
    uvicorn.run(create_app(token=token), host=host, port=port, log_level="info")
