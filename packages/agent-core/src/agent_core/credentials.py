"""Credential pool with rotation, health checking, and automatic failover."""

import asyncio
import logging
import os
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Credential:
    """A single credential entry with health status."""

    def __init__(self, key: str, metadata: dict[str, Any] | None = None) -> None:
        self.key = key
        self.metadata = metadata or {}
        self.failures: int = 0
        self.last_used: float = 0.0
        self.last_error: str | None = None
        self.cooldown_until: float = 0.0

    @property
    def is_healthy(self) -> bool:
        return time.monotonic() >= self.cooldown_until

    @property
    def masked_key(self) -> str:
        if len(self.key) <= 8:
            return "***"
        return self.key[:4] + "..." + self.key[-4:]


class CredentialPool:
    """Rotating credential pool with health tracking and automatic failover.

    Per CLAUDE.md: on auth/rate-limit/billing errors, rotates credentials
    from a pool before activating provider fallback.

    Usage::

        pool = CredentialPool()
        pool.add("anthropic", "sk-ant-xxx", metadata={"tier": "pro"})
        pool.add("anthropic", "sk-ant-yyy", metadata={"tier": "backup"})

        # Get a healthy credential.
        cred = await pool.acquire("anthropic")
        if cred:
            api_key = cred.key

        # Mark on failure.
        await pool.report_failure("anthropic", cred, "rate_limited")
    """

    def __init__(self) -> None:
        self._pools: dict[str, list[Credential]] = defaultdict(list)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._index: dict[str, int] = defaultdict(int)  # Round-robin index.
        self._strategies: dict[str, str] = defaultdict(lambda: "round_robin")
        self._env_resolvers: dict[str, Callable[[], list[str]]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def add(
        self,
        provider: str,
        key: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a credential to the pool for *provider*."""
        cred = Credential(key, metadata)
        self._pools[provider].append(cred)
        logger.info(
            "Credential added for %s: %s", provider, cred.masked_key
        )

    def add_from_env(self, provider: str, env_var: str) -> None:
        """Add credentials from an environment variable (comma-separated)."""
        raw = os.environ.get(env_var, "")
        if raw:
            for key in raw.split(","):
                key = key.strip()
                if key:
                    self.add(provider, key)

    def add_from_auth_json(self, path: str | None = None) -> int:
        """Bulk-load credentials from a JalaAgent/Hermes auth.json file.

        Handles both key field names: ``key`` (JalaAgent) and ``access_token``
        (Hermes).  The top-level ``providers`` key is expected; if absent the
        flat provider→[entries] format is used as a fallback.

        Returns the number of credentials loaded.
        """
        import json as _json

        auth_path = Path(path) if path else (
            Path.home() / ".jalaagent" / "auth.json"
        )
        if not auth_path.exists():
            return 0

        try:
            data = _json.loads(auth_path.read_text(encoding="utf-8"))
        except Exception:
            return 0

        # Support Hermes-style credential_pool (highest priority).
        cred_pool = data.get("credential_pool", {})
        if cred_pool:
            providers = dict(cred_pool)
        else:
            providers = data.get("providers", {})
            if not providers:
                # Backward-compat: flat {provider: [entries]} format.
                providers = {k: v for k, v in data.items() if isinstance(v, list)}

        count = 0
        for provider, entries in providers.items():
            for entry in entries:
                # Normalize key field: accept "key", "access_token", and "api_key".
                key = (
                    entry.get("key", "") or
                    entry.get("access_token", "") or
                    entry.get("api_key", "")
                )
                if not key:
                    # Skip entries without keys (e.g., token-based auth).
                    continue

                # Hermes-style rich metadata.
                metadata = {
                    "label": entry.get("label", ""),
                    "priority": entry.get("priority", 1),
                    "source": entry.get("source", "auth_json"),
                    "auth_type": entry.get("auth_type", "api_key"),
                    "base_url": entry.get("base_url", ""),
                    "last_status": entry.get("last_status", ""),
                    "last_error_code": entry.get("last_error_code"),
                    "last_error_message": entry.get("last_error_message", ""),
                }
                self.add(provider, key, metadata)
                count += 1

        # Apply per-provider strategies from credential_pool config.
        strategies = data.get("credential_pool_strategies", {})
        for provider, strategy in strategies.items():
            self.set_strategy(provider, strategy)

        return count

    def register_env_resolver(
        self, provider: str, resolver: Callable[[], list[str]]
    ) -> None:
        """Register a dynamic credential resolver (e.g., vault, secret manager)."""
        self._env_resolvers[provider] = resolver

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------

    def set_strategy(self, provider: str, strategy: str) -> None:
        """Set selection strategy: random, priority, or round_robin (default)."""
        self._strategies[provider] = strategy

    async def acquire(self, provider: str) -> Credential | None:
        """Get the next healthy credential for *provider*.

        Supports strategies: round_robin (default), random, priority.
        Returns ``None`` if no healthy credential is available.
        """
        pool = self._pools.get(provider, [])
        if not pool:
            # Try env resolver.
            resolver = self._env_resolvers.get(provider)
            if resolver:
                for key in resolver():
                    self.add(provider, key)
                pool = self._pools[provider]
            if not pool:
                return None

        strategy = self._strategies.get(provider, "round_robin")
        async with self._locks[provider]:
            if strategy == "random":
                import random
                healthy = [c for c in pool if c.is_healthy]
                if healthy:
                    cred = random.choice(healthy)
                    cred.last_used = time.monotonic()
                    return cred
                return None
            if strategy == "priority":
                healthy = sorted([c for c in pool if c.is_healthy], key=lambda c: c.metadata.get("priority", 99))
                if healthy:
                    cred = healthy[0]
                    cred.last_used = time.monotonic()
                    return cred
                return None
            # Default: round_robin.
            start = self._index[provider] % len(pool)
            for offset in range(len(pool)):
                idx = (start + offset) % len(pool)
                cred = pool[idx]
                if cred.is_healthy:
                    cred.last_used = time.monotonic()
                    self._index[provider] = (idx + 1) % len(pool)
                    return cred

        return None  # All in cooldown.

    # ------------------------------------------------------------------
    # Health reporting
    # ------------------------------------------------------------------

    async def report_failure(
        self,
        provider: str,
        credential: Credential,
        reason: str = "unknown",
    ) -> None:
        """Report a credential failure, triggering cooldown or removal.

        Cooldown is exponential: 30s * 2^failures, capped at 30 minutes.
        After 5 consecutive failures, the credential is removed.
        """
        credential.failures += 1
        credential.last_error = reason

        if credential.failures >= 5:
            pool = self._pools.get(provider, [])
            if credential in pool:
                pool.remove(credential)
                logger.warning(
                    "Credential %s removed after %d failures",
                    credential.masked_key,
                    credential.failures,
                )
        else:
            cooldown = min(30 * (2 ** credential.failures), 1800)
            credential.cooldown_until = time.monotonic() + cooldown
            logger.warning(
                "Credential %s in cooldown for %.0fs (failures=%d, reason=%s)",
                credential.masked_key,
                cooldown,
                credential.failures,
                reason,
            )

    async def report_success(self, provider: str, credential: Credential) -> None:
        """Reset failure count on successful use."""
        credential.failures = 0
        credential.last_error = None
        credential.cooldown_until = 0.0

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def status(self) -> dict[str, Any]:
        """Return pool health status."""
        result: dict[str, Any] = {}
        for provider, pool in self._pools.items():
            result[provider] = {
                "total": len(pool),
                "healthy": sum(1 for c in pool if c.is_healthy),
                "credentials": [
                    {
                        "key": c.masked_key,
                        "healthy": c.is_healthy,
                        "failures": c.failures,
                        "last_error": c.last_error,
                    }
                    for c in pool
                ],
            }
        return result
