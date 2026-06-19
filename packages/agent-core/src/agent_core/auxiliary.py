"""AuxiliaryRouter — task-specific sub-provider routing.

Hermes-parity: routes specific tasks (compression, dreaming,
title_generation, vision) to cheaper or multimodal models configured
in config.yaml ``auxiliary.<task>`` sections.

If a task's auxiliary config is empty, the main provider is used as
the default (no degradation).
"""

from typing import Any


class AuxiliaryRouter:
    """Routes background tasks to task-specific providers."""

    def __init__(self, config: dict[str, Any], main_provider: Any) -> None:
        self._config = config
        self._main = main_provider

    def resolve(self, task: str) -> Any:
        """Return a provider for *task*, falling back to the main provider.

        Tasks: ``compression``, ``dreaming``, ``title_generation``, ``vision``.
        """
        aux_cfg = self._config.get("auxiliary", {}).get(task, {})
        provider_name = aux_cfg.get("provider", "")
        model_name = aux_cfg.get("model", "")

        if not provider_name or not model_name:
            return self._main  # Use main provider by default.

        return self._build_provider(provider_name, model_name, aux_cfg)

    def _build_provider(
        self, provider: str, model: str, cfg: dict[str, Any]
    ) -> Any:
        """Build a provider instance from config."""
        try:
            if provider == "deepseek":
                from provider_deepseek.provider import DeepSeekProvider
                return DeepSeekProvider(model=model)
            elif provider == "groq":
                from provider_groq.provider import GroqProvider
                return GroqProvider(model=model)
            elif provider == "mistral":
                from provider_mistral.provider import MistralProvider
                return MistralProvider(model=model)
            elif provider == "openai":
                from provider_openai.provider import OpenAIProvider
                return OpenAIProvider(model=model)
            elif provider == "anthropic":
                from provider_anthropic.provider import AnthropicProvider
                return AnthropicProvider(model=model)
            elif provider == "ollama":
                from provider_ollama.provider import OllamaProvider
                return OllamaProvider(model=model)
            elif provider == "openrouter":
                from provider_openrouter.provider import OpenRouterProvider
                return OpenRouterProvider(model=model)
            elif provider == "custom":
                # Custom provider with explicit base_url.
                from provider_universal.provider import OpenAICompatibleProvider
                return OpenAICompatibleProvider(
                    default_provider=provider, default_model=model,
                )
        except Exception:
            pass

        return self._main  # Fall back to main provider.
