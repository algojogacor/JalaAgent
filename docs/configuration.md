# Configuration — Full config.yaml Reference

JalaAgent's `~/.jalaagent/config.yaml` has 8 blocks matching Hermes' structure.

## Block 1: Provider System
```yaml
model: {default: deepseek-chat, provider: deepseek, context_length: 200000}
providers:
  deepseek: {base_url: https://api.deepseek.com/v1, models: [{name: deepseek-chat, default: true}]}
  openrouter: {base_url: https://openrouter.ai/api/v1, models: [{name: anthropic/claude-sonnet-4, default: true}]}
  # ... 14 more providers
fallback_providers: [deepseek, openrouter, groq, mistral, ollama]
credential_pool: {strategy: random, health_check_interval: 3600, max_retries: 3, jitter: true}
auxiliary: {provider: deepseek, model: deepseek-chat}
```

## Block 2: Agent Runtime
```yaml
agent: {name: JalaAgent, max_iterations: 100, api_max_retries: 3, tool_use_enforcement: auto}
delegation: {max_sub_agent_depth: 1, max_concurrent_sub_agents: 5, sub_agent_iteration_budget: 50}
compression: {enabled: true, threshold: 0.8, keep_recent_tokens: 20000}
prompt_caching: {enabled: true, provider: anthropic}
```

## Block 3: Tools & Execution
```yaml
tool_loop_guardrails: {loop_detection_window: 10, loop_warning_threshold: 3, loop_hard_stop_threshold: 5}
approval: {mode: normal, rules: {file_read: auto, file_write: auto, file_delete: ask, shell_exec: ask, ...}}
```

## Block 4: Channels
```yaml
channels:
  cli: {enabled: true, footer: true, spinner: true}
  telegram: {token: "${TELEGRAM_BOT_TOKEN}", allowed_users: []}
```

## Block 5: Memory & Skills
```yaml
memory: {embedding_model: qwen3:0.6b, embedding_dim: 1024, dreaming: {enabled: true, schedule: "0 3 * * *"}}
skills: {user_dir: ~/.jalaagent/skills, max_skills_in_prompt: 150, max_chars_per_skill: 40000}
```

## Block 6-8
See full documentation in `~/.jalaagent/config.yaml` after running `jala setup`.
