# Providers — 16+ APIs

JalaAgent uses a universal provider that speaks OpenAI-compatible format. One adapter covers all 16 backends.

## Supported Providers

| Provider | Base URL | Free Tier |
|----------|----------|:---:|
| DeepSeek | api.deepseek.com/v1 | ✅ |
| OpenRouter | openrouter.ai/api/v1 | ✅ Free collection |
| Groq | api.groq.com/openai/v1 | ✅ |
| Mistral | api.mistral.ai/v1 | ✅ |
| Together | api.together.xyz/v1 | ✅ |
| Perplexity | api.perplexity.ai | ✅ |
| xAI | api.x.ai/v1 | — |
| Alibaba/Qwen | dashscope-intl.aliyuncs.com | — |
| Cohere | api.cohere.ai/v1 | ✅ |
| Fireworks | api.fireworks.ai/inference/v1 | — |
| Cerebras | api.cerebras.ai/v1 | ✅ |
| SambaNova | api.sambanova.ai/v1 | ✅ |
| NVIDIA NIM | integrate.api.nvidia.com/v1 | ✅ |
| OpenAI | api.openai.com/v1 | — |
| Gemini | generativelanguage.googleapis.com | ✅ |
| Ollama | localhost:11434/v1 | ✅ Local |

## Credential Setup

Add keys to `~/.jalaagent/auth.json`:

```json
{
  "deepseek": [{"key": "sk-xxx", "priority": 1}],
  "openrouter": [{"key": "sk-or-xxx", "priority": 1}]
}
```

## Model Routing

Use `provider/model` syntax:
```bash
jala --model deepseek/deepseek-chat
jala --model openrouter/anthropic/claude-sonnet-4
```

## Fallback Chain

If primary provider fails, JalaAgent auto-rotates through the fallback list:
```yaml
fallback_providers: [deepseek, openrouter, groq, mistral, ollama]
```
