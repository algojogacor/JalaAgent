"""jala serve — JalaAgent as Anthropic-Compatible API proxy."""

import json
import logging
from pathlib import Path
from typing import Any

from agent_core.paths import setup_import_paths
setup_import_paths()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
_TRIVIAL = {"hello", "hi", "ping", "test", "help", "what's up", "hey"}

# ---------------------------------------------------------------------------
# In-memory rate limiter (per IP, 60 requests per 60-second window)
# ---------------------------------------------------------------------------

import time as _time

_rate_limits: dict[str, list[float]] = {}


def _check_rate_limit(ip: str, max_req: int = 60, window: int = 60) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    now = _time.time()
    if ip not in _rate_limits:
        _rate_limits[ip] = []
    # Prune entries outside the window.
    _rate_limits[ip] = [t for t in _rate_limits[ip] if now - t < window]
    if len(_rate_limits[ip]) >= max_req:
        return False
    _rate_limits[ip].append(now)
    return True


async def _build_proxy_provider(model: str = "") -> Any:
    """Build the best available provider, pulling API keys from auth.json."""
    import json as _json
    import yaml as _yaml

    auth: dict[str, Any] = {}
    auth_path = Path.home() / ".jalaagent" / "auth.json"
    if auth_path.exists():
        auth = _json.loads(auth_path.read_text(encoding="utf-8"))

    def _first_key(provider: str) -> str:
        """Return the first API key for a provider from auth.json."""
        for entry in auth.get("providers", {}).get(provider, []):
            k = entry.get("key", "") or entry.get("access_token", "")
            if k:
                return k
        return ""

    # Try Anthropic if key is available (env or auth.json).
    import os as _os
    ak = _os.environ.get("ANTHROPIC_API_KEY", "") or _first_key("anthropic")
    if ak:
        try:
            from provider_anthropic.provider import AnthropicProvider
            return AnthropicProvider(api_key=ak)
        except Exception:
            pass

    # Try Groq.
    gr_key = _first_key("groq")
    if gr_key:
        try:
            from provider_groq.provider import GroqProvider
            return GroqProvider(api_key=gr_key)
        except Exception:
            pass

    # Try DeepSeek.
    ds_key = _first_key("deepseek")
    if ds_key:
        try:
            from provider_deepseek.provider import DeepSeekProvider
            return DeepSeekProvider(api_key=ds_key)
        except Exception:
            pass

    # Try Mistral.
    ms_key = _first_key("mistral")
    if ms_key:
        try:
            from provider_mistral.provider import MistralProvider
            return MistralProvider(api_key=ms_key)
        except Exception:
            pass

    # Try OpenRouter.
    or_key = _first_key("openrouter")
    if or_key:
        try:
            from provider_openrouter.provider import OpenRouterProvider
            return OpenRouterProvider(api_key=or_key)
        except Exception:
            pass

    # Last resort: Ollama (local, no key needed).
    try:
        from provider_ollama.provider import OllamaProvider
        return OllamaProvider()
    except Exception:
        from provider_openai.provider import OpenAIProvider
        return OpenAIProvider()


def create_app(token: str | None = None) -> FastAPI:
    from jala import __version__
    app = FastAPI(title="JalaAgent API", version=__version__)
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

    @app.middleware("http")
    async def _rate_limit(request: Request, call_next: Any) -> Any:  # pyright: ignore[reportUnusedFunction]
        ip = request.client.host if request.client else "unknown"
        if not _check_rate_limit(ip):
            return StreamingResponse(
                iter([json.dumps({"error": {"type": "rate_limit_error", "message": "Rate limit exceeded. Try again later.", "retry_after": 60}})]),
                media_type="text/event-stream", status_code=429,
            )
        return await call_next(request)

    @app.get("/v1/models")
    async def _models() -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        """List available models from config and auth.json."""
        from pathlib import Path
        import yaml as _yaml

        config_path = Path.home() / ".jalaagent" / "config.yaml"
        models: list[dict[str, Any]] = []
        if config_path.exists():
            cfg = _yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            prov_name = cfg.get("model", {}).get("provider", "deepseek")
            default_model = cfg.get("model", {}).get("default", "deepseek-chat")
            models.append({"id": default_model, "object": "model", "owned_by": prov_name})
            # Add fallback provider models.
            for fb in cfg.get("fallback_providers", []):
                models.append({"id": f"{fb}/default", "object": "model", "owned_by": fb})

        # Also list models from auth.json providers.
        auth_path = Path.home() / ".jalaagent" / "auth.json"
        if auth_path.exists():
            auth = json.loads(auth_path.read_text(encoding="utf-8"))
            for prov in auth.get("providers", {}):
                if prov not in {m["owned_by"] for m in models}:
                    models.append({"id": f"{prov}/default", "object": "model", "owned_by": prov})

        # Hard-coded models for Anthropic-compatible clients.
        models += [
            {"id": "claude-sonnet-4-6", "object": "model", "owned_by": "anthropic"},
            {"id": "claude-opus-4-8", "object": "model", "owned_by": "anthropic"},
            {"id": "gpt-4o", "object": "model", "owned_by": "openai"},
            {"id": "deepseek-chat", "object": "model", "owned_by": "deepseek"},
        ]
        return {"object": "list", "data": models[:50]}

    @app.post("/v1/messages/count_tokens")
    async def _count(body: dict[str, Any]) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        total = len(body.get("system", ""))
        for m in body.get("messages", []):
            if isinstance(m.get("content"), str): total += len(m["content"])
        return {"input_tokens": total // 4}

    @app.post("/v1/messages")
    async def _messages(body: dict[str, Any]) -> StreamingResponse:  # pyright: ignore[reportUnusedFunction]
        model = body.get("model", "deepseek-chat")
        p = await _build_proxy_provider(model)
        user_text = ""
        for m in body.get("messages", []):
            if m.get("role") == "user" and isinstance(m.get("content"), str):
                user_text = m["content"].strip().lower()
        if user_text in _TRIVIAL:
            async def _t():
                yield f"data: {json.dumps({'type':'content_block_delta','delta':{'type':'text_delta','text':user_text.title()+'! How can I help?'}})}\n\n"
                yield "data: {\"type\":\"message_stop\"}\n\n"
            return StreamingResponse(_t(), media_type="text/event-stream")
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
            except Exception:
                logger.exception("Streaming error for model %s", model)
                yield f"data: {json.dumps({'type':'error','error':{'type':'api_error','message':'Internal server error'}})}\n\n"
        return StreamingResponse(_s(), media_type="text/event-stream")

    return app


def run_server(host: str = "127.0.0.1", port: int = 8787, token: str | None = None) -> None:
    import uvicorn
    a = " (auth: enabled)" if token else " (no auth)"
    from jala import __version__
    logger.info("🪼 JalaAgent API v%s — http://%s:%s%s", __version__, host, port, a)
    logger.info("   Models: http://%s:%s/v1/models", host, port)
    logger.info("   Chat:   POST http://%s:%s/v1/messages", host, port)
    logger.info("   Use:    ANTHROPIC_BASE_URL=http://%s:%s claude", host, port)
    uvicorn.run(create_app(token=token), host=host, port=port, log_level="info")
