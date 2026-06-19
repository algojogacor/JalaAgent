# Provider & Model System — Enterprise Overhaul

> Design spec for JalaAgent v2026.6.20 — Hermes-level provider/model flexibility.
> Last updated: v2026.6.20

---

## Motivation

- Qwen has two separate endpoints (`dashscope.aliyuncs.com` China / `dashscope-intl.aliyuncs.com` International) with different API keys. JalaAgent hardcodes Intl — China keys get 401.
- `/model` command is a 3-line string assignment — no validation, no provider re-resolution, no persistence.
- No interactive model picker on Telegram (the primary channel).
- No env var for custom base_url per provider.

## Target

Hermes-level `/model` command with interactive provider → model picker on Telegram + CLI, live API model discovery with disk cache, env var base_url overrides for all 16+ providers, and `--save` persistence.

---

## 1. Provider Catalog — Three-Layer Model Sourcing

### Layer 1: Static Catalog (bundled, always available)

**File:** `packages/agent-core/src/agent_core/model_catalog.py`

A `PROVIDER_MODELS: dict[str, list[str]]` dict mapping provider slugs to curated model IDs. Ships with all 16+ providers and their known models. Instant, no network — the offline fallback.

```python
PROVIDER_MODELS: dict[str, list[str]] = {
    "qwen": ["qwen-plus", "qwen-max", "qwen-turbo", "qwen3-235b-a22b", ...],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o4-mini", ...],
    ...
}
```

### Layer 2: Live API Fetch (on-demand, disk-cached)

- Probes `GET /v1/models` on the configured provider's base_url
- **1-hour TTL disk cache** at `~/.jalaagent/cache/provider_models.json` (configurable via `providers.<name>.cache_ttl_seconds` in config.yaml)
- **Cache key:** `(provider_slug, sha256(base_url + api_key[:8]))` — changing endpoint or key busts the cache
- Falls back to Layer 1 on network error
- `/model --refresh` forces cache bust + re-fetch

### Layer 3: User Config Override (config.yaml)

Users can add/override models via `providers.<name>.models`:

```yaml
providers:
  qwen:
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    models:
      - name: qwen-plus
      - name: custom-fine-tuned-model
```

Merged on top of Layer 1 + 2 results.

### Model Discovery Flow

```
User opens /model picker
  → Check disk cache (1h TTL)
    → HIT → return cached list instantly
    → MISS/EXPIRED → GET /v1/models on provider base_url
      → Success → cache result, return fresh list
      → Fail → fall back to static catalog (Layer 1)
```

---

## 2. base_url Resolution — Four-Tier Priority Chain

First match wins, top to bottom:

| Tier | Source | Example |
|------|--------|---------|
| 1 | CLI flag | `--base-url https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 2 | Env var | `DASHSCOPE_BASE_URL`, `OPENAI_BASE_URL`, etc. |
| 3 | config.yaml | `providers.<name>.base_url` |
| 4 | Static default | Hardcoded in `model_catalog.py` per provider |

### Provider Env Var Map

Every provider gets a `<PROVIDER>_BASE_URL` env var. All values are **full URLs** including path:

```python
PROVIDER_BASE_URLS: dict[str, str] = {
    "qwen":      "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "openai":    "https://api.openai.com/v1",
    "deepseek":  "https://api.deepseek.com/v1",
    "anthropic": "https://api.anthropic.com",
    "ollama":    "http://localhost:11434/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq":      "https://api.groq.com/openai/v1",
    "mistral":   "https://api.mistral.ai/v1",
    "together":  "https://api.together.xyz/v1",
    "perplexity":"https://api.perplexity.ai",
    "xai":       "https://api.x.ai/v1",
    "cohere":    "https://api.cohere.ai/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "cerebras":  "https://api.cerebras.ai/v1",
    "sambanova": "https://api.sambanova.ai/v1",
    "nvidia":    "https://integrate.api.nvidia.com/v1",
}
```

### Resolution Function

```python
def resolve_base_url(provider: str, cli_flag: str | None = None) -> str:
    # Tier 1: CLI flag
    if cli_flag:
        return cli_flag
    # Tier 2: Env var — <PROVIDER>_BASE_URL
    env_var = f"{provider.upper()}_BASE_URL"
    if os.environ.get(env_var):
        return os.environ[env_var]
    # Tier 3: config.yaml providers.<name>.base_url
    cfg = _load_config()
    cfg_url = cfg.get("providers", {}).get(provider, {}).get("base_url")
    if cfg_url:
        return cfg_url
    # Tier 4: Static default
    return PROVIDER_BASE_URLS[provider]
```

### Universal Provider Cleanup

The `PROVIDERS` hardcoded dict in `provider_universal/provider.py` will be **deleted**. The provider receives `base_url` via constructor parameter:

```python
class OpenAICompatibleProvider(BaseProvider):
    def __init__(self, base_url: str, api_key: str, model: str, ...):
        self._base_url = base_url  # Resolved by ProviderRouter, no embedded catalog
```

---

## 3. `/model` Command — Full Flow

### Without Arguments → Interactive Picker

```
User: /model
  → Show current: "⚙ Model: deepseek-chat (DeepSeek)"
  → Provider selection (inline keyboard on Telegram, rich select on CLI)
  → User selects provider → model list appears
  → User selects model → switch_model() → confirmation
```

### With Argument → Direct Switch

```
User: /model qwen/qwen-plus
  → Parse provider/model from input
  → Resolve through ProviderRouter
  → Validate against catalog
  → Switch → "✅ Switched to qwen/qwen-plus"
```

### Flags

| Flag | Effect |
|------|--------|
| `--save` | Persist to config.yaml (survives restart) |
| `--refresh` | Bust cache, force live API re-fetch |
| (no flag) | Session-only switch (in-memory, default) |

### Alias Support

```python
MODEL_ALIASES: dict[str, str] = {
    "sonnet": "claude-sonnet-4-6",
    "opus":   "claude-opus-4-8",
    "haiku":  "claude-haiku-4-5",
    "4o":     "gpt-4o",
    "ds":     "deepseek/deepseek-chat",
}
```

### Core Pipeline (`switch_model()`)

```
parse_flags()
  → resolve_provider()        # ProviderRouter with base_url chain
  → resolve_model()           # catalog lookup + live fetch if needed
  → validate_model()          # optional: probe live endpoint
  → build_result()            # ModelSwitchResult dataclass
  → apply_switch()            # update agent loop + optional persist
```

`ModelSwitchResult` dataclass:
```python
@dataclass
class ModelSwitchResult:
    success: bool
    model: str
    provider: str
    base_url: str
    provider_changed: bool
    context_length: int | None
    error_message: str | None
```

---

## 4. Channel Adaptation

### Telegram (Primary) — Inline Keyboard

Two-step interactive picker:

**Step 1 — Provider Selection:**
- `InlineKeyboardMarkup` with one button per provider group
- Buttons labeled: `Qwen (5)`, `DeepSeek (3)`, `OpenAI (12)`, `Anthropic (4)`, ...
- Callback data: `mp:<provider_slug>`
- Cancel button: `mx:`

**Step 2 — Model Selection:**
- Rendered after user taps a provider button
- One button per model: `mm:<model_index>`
- Back button: `mb:` (returns to provider selection)
- Cancel button: `mx:`

**State tracking:**
```python
self._model_picker_state[chat_id] = {
    "provider": str,
    "models": list[str],
    "page": int,
    "on_selected": callable,
}
```

**Callback handlers** in `channel_telegram/channel.py`:
- `mp:*` → show model list for that provider
- `mm:*` → call `switch_model()`, edit message to show confirmation
- `mb:*` → return to provider selection
- `mx:*` → dismiss picker, remove keyboard

### CLI — Rich Select

```python
from rich.prompt import Prompt
# or typer + rich.live for interactive selection
```

Same `switch_model()` pipeline. Channel-specific rendering only.

### Shared Pipeline

Both channels call the same `switch_model()` in `agent-core`. The channel is responsible only for:
1. Rendering the picker UI (buttons vs text)
2. Collecting the user's selection
3. Displaying the confirmation

---

## 5. Persistence

### Session-Only (Default)

```python
# AgentLoop
self._session_model_override: dict | None = None
# {"model": "qwen-plus", "provider": "qwen", "base_url": "https://..."}
```

Cleared on restart. Next `_build_agent()` reads from config.yaml.

### Permanent (`--save` flag)

Writes to `~/.jalaagent/config.yaml`:

```yaml
model:
  default: qwen-plus
  provider: qwen
  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
```

Uses the existing `model.default`, `model.provider`, and `model.base_url` fields — no new config sections needed.

### Resolution at Agent Boot

```python
def _build_agent(model: str | None = None, base_url: str | None = None):
    cfg = _load_jala_config()
    # CLI flags > config.yaml > ProviderRouter fallback
    provider = router.resolve(
        model=model or cfg.get("model", {}).get("default"),
        base_url=base_url or cfg.get("model", {}).get("base_url"),
        creds=creds,
    )
```

---

## Files to Create/Modify

### New Files

| File | Purpose |
|------|---------|
| `packages/agent-core/src/agent_core/model_catalog.py` | `PROVIDER_MODELS` static catalog, `PROVIDER_BASE_URLS` defaults, cache logic |
| `tests/packages/agent-core/test_model_catalog.py` | Unit tests for catalog + base_url resolution |
| `tests/packages/agent-core/test_provider_router.py` | Unit tests for ProviderRouter with base_url chain |

### Modified Files

| File | Changes |
|------|---------|
| `packages/agent-core/src/agent_core/providers.py` | Add `base_url` to `ProviderEntry`, `resolve_base_url()`, `KNOWN_PROVIDERS` add qwen + others, alias dict |
| `packages/agent-core/src/agent_core/commands.py` | Replace `/model` handler with `switch_model()` pipeline, parse flags, call picker or direct switch |
| `extensions/providers/universal/src/provider_universal/provider.py` | Delete `PROVIDERS` dict, accept `base_url` via constructor |
| `extensions/channels/telegram/src/channel_telegram/channel.py` | Add `send_model_picker()`, `_build_provider_keyboard()`, `_build_model_keyboard()`, callback handlers |
| `extensions/channels/cli/src/channel_cli/channel.py` | Add rich-based model selection for `/model` |
| `cli/src/jala/main.py` | Add `--base-url` CLI option, wire into `_build_agent()`, wire config persistence |
| `cli/src/jala/setup.py` | Update config template with provider base_url pattern |

---

## Verification

### Qwen Dual Endpoint
```bash
# China endpoint
export DASHSCOPE_API_KEY="sk-007..."
export DASHSCOPE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
uv run jala --model qwen/qwen-plus --prompt "hello"  # → works, no 401

# International endpoint
export DASHSCOPE_BASE_URL="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
uv run jala --model qwen/qwen-plus --prompt "hello"  # → works with intl key
```

### Interactive Picker
```bash
# CLI
uv run jala  # → type /model → see provider select → pick → model select → switch

# Telegram
# → /model → inline keyboard → tap provider → tap model → confirmation
```

### Persistence
```bash
uv run jala  # → /model --save qwen/qwen-plus
# Restart
uv run jala --prompt "what model am i using?"  # → qwen-plus
```

### Live Fetch
```bash
uv run jala  # → /model --refresh  # forces cache bust + re-fetch
```

---

## Non-Goals (for this spec)

- Remote manifest server (use bundled catalog + live API fetch instead)
- models.dev integration (add later if needed)
- OAuth provider support (API key only for v1)
- Expensive model cost guard (add later)
- SQLite session persistence (in-memory dict is sufficient)
