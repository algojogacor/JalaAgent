"""Credential pool with rotation, health checking, and automatic failover."""

import asyncio
import logging
import os
import time
from collections import defaultdict
from collections.abc import Callable
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
        # Hooks for external credential sources.
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

    def register_env_resolver(
        self, provider: str, resolver: Callable[[], list[str]]
    ) -> None:
        """Register a dynamic credential resolver (e.g., vault, secret manager)."""
        self._env_resolvers[provider] = resolver

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------

    async def acquire(self, provider: str) -> Credential | None:
        """Get the next healthy credential for *provider*.

        Uses round-robin selection, skipping credentials in cooldown.
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

        async with self._locks[provider]:
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
