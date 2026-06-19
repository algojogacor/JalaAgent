"""WhatsApp channel for JalaAgent.

Communicates with Baileys (Node.js WhatsApp Web library) via subprocess
stdin/stdout JSON lines protocol.

Mirrors the TelegramChannel pattern:
- ``start()`` launches the Baileys subprocess
- ``run()`` is the main polling loop (reads from subprocess stdout)
- ``send_message()`` and ``send_approval_request()`` satisfy the BaseChannel Protocol
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON-line protocol helpers
# ---------------------------------------------------------------------------

_CMD = {"action": "send", "to": "", "text": ""}


def _make_send_cmd(to: str, text: str) -> dict[str, Any]:
    return {"action": "send", "to": to, "text": text}


# ---------------------------------------------------------------------------
# WhatsAppChannel
# ---------------------------------------------------------------------------


class WhatsAppChannel:
    """Channel that bridges JalaAgent with WhatsApp via a Baileys subprocess.

    The Baileys process is expected to:
    - Accept JSON-lines commands on stdin (``{"action": "send", "to": "...", "text": "..."}``)
    - Emit JSON-lines events on stdout (``{"type": "message", "from": "...", "body": "..."}``)
    """

    def __init__(
        self,
        agent_loop: Any = None,
        command_registry: Any = None,
    ) -> None:
        self._agent_loop = agent_loop
        self._registry = command_registry
        self._process: asyncio.subprocess.Process | None = None
        self._running = False
        self._pending_approvals: dict[str, asyncio.Future[bool]] = {}

        # Credentials
        self._bridge_url = os.environ.get("WHATSAPP_BRIDGE_URL", "")
        self._auth_dir = Path(os.environ.get("WHATSAPP_AUTH_DIR", Path.home() / ".jalaagent" / "whatsapp"))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch the Baileys bridge subprocess and start reading output."""
        if self._bridge_url:
            logger.info("WhatsApp bridge URL configured: %s", self._bridge_url)
            # HTTP-based bridge — no subprocess needed.
            return

        # Ensure auth directory exists.
        self._auth_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._process = await asyncio.create_subprocess_exec(
                "node",
                str(self._auth_dir / "baileys_bridge.js"),
                "--auth-dir", str(self._auth_dir),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            logger.info("WhatsApp Baileys subprocess started (pid=%d)", self._process.pid)
        except FileNotFoundError:
            logger.warning(
                "Baileys bridge not found at %s — WhatsApp channel disabled. "
                "Install baileys_bridge.js to enable WhatsApp.",
                self._auth_dir / "baileys_bridge.js",
            )
            self._process = None
        except Exception:
            logger.exception("Failed to start Baileys subprocess")
            self._process = None

    async def stop(self) -> None:
        """Kill the Baileys subprocess gracefully."""
        self._running = False
        if self._process:
            try:
                self._process.stdin.close()
            except Exception:
                pass
            try:
                self._process.kill()
            except Exception:
                pass
            await self._process.wait()
            logger.info("WhatsApp Baileys subprocess stopped")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Poll for incoming messages (blocking loop)."""
        self._running = True

        if self._bridge_url:
            await self._poll_http()
        elif self._process and self._process.stdout:
            await self._poll_subprocess()
        else:
            logger.info("WhatsApp channel: no bridge configured — idle")

    async def _poll_subprocess(self) -> None:
        """Read JSON-line events from the Baileys subprocess stdout."""
        assert self._process and self._process.stdout
        from channel_whatsapp.handlers import WhatsAppHandlers

        handlers = WhatsAppHandlers(channel=self, command_registry=self._registry)

        while self._running:
            try:
                line = await asyncio.wait_for(
                    self._process.stdout.readline(), timeout=30.0
                )
            except asyncio.TimeoutError:
                continue

            if not line:
                logger.warning("WhatsApp subprocess stdout closed")
                break

            try:
                event = json.loads(line.decode("utf-8").strip())
            except json.JSONDecodeError:
                continue

            if event.get("type") == "message":
                sender = event.get("from", "")
                body = event.get("body", "")
                asyncio.create_task(self._handle_incoming(sender, body, handlers))

    async def _poll_http(self) -> None:
        """Poll an HTTP-based WhatsApp bridge (alternative to subprocess)."""
        import aiohttp

        from channel_whatsapp.handlers import WhatsAppHandlers

        handlers = WhatsAppHandlers(channel=self, command_registry=self._registry)

        async with aiohttp.ClientSession() as session:
            while self._running:
                try:
                    async with session.get(
                        f"{self._bridge_url}/messages", timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for msg in data.get("messages", []):
                                sender = msg.get("from", "")
                                body = msg.get("body", "")
                                asyncio.create_task(
                                    self._handle_incoming(sender, body, handlers)
                                )
                except Exception:
                    logger.debug("WhatsApp HTTP poll error", exc_info=True)
                await asyncio.sleep(2)

    async def _handle_incoming(
        self, sender: str, body: str, handlers: Any
    ) -> None:
        """Dispatch an incoming message through handlers."""
        try:
            response = await handlers.handle_message(sender, body)
            if response:
                await self.send_message(sender, response)
        except Exception:
            logger.exception("Error handling WhatsApp message from %s", sender)

    # ------------------------------------------------------------------
    # Messaging (BaseChannel Protocol)
    # ------------------------------------------------------------------

    async def send_message(self, to: str, text: str) -> None:
        """Send a text message to a WhatsApp number or JID."""
        if self._bridge_url:
            await self._send_http(to, text)
        elif self._process and self._process.stdin:
            cmd = _make_send_cmd(to, text)
            try:
                self._process.stdin.write(
                    (json.dumps(cmd) + "\n").encode("utf-8")
                )
                await self._process.stdin.drain()
            except Exception:
                logger.exception("Failed to send WhatsApp message to %s", to)
        else:
            logger.warning("WhatsApp channel not connected — cannot send message")

    async def _send_http(self, to: str, text: str) -> None:
        """Send via HTTP bridge."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            try:
                await session.post(
                    f"{self._bridge_url}/send",
                    json={"to": to, "text": text},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
            except Exception:
                logger.exception("WhatsApp HTTP send failed")

    async def send_approval_request(self, action: Any, phone: str = "") -> bool:
        """Send an approval request to the user via WhatsApp.

        WhatsApp lacks inline keyboards, so we send a text prompt
        and wait for a reply with a 60-second timeout (fail-closed).
        """
        if not phone:
            logger.warning("No phone number for WhatsApp approval request")
            return False

        text = (
            f"⚠️ *Approval Required*\n\n"
            f"Tool: `{getattr(action, 'tool_name', 'unknown')}`\n"
            f"Args: `{getattr(action, 'arguments', {})}`\n\n"
            f"Reply *approve {getattr(action, 'id', '')}* "
            f"or *reject {getattr(action, 'id', '')}*"
        )
        await self.send_message(phone, text)

        future: asyncio.Future[bool] = asyncio.Future()
        self._pending_approvals[getattr(action, "id", "")] = future
        try:
            return await asyncio.wait_for(future, timeout=60.0)
        except asyncio.TimeoutError:
            logger.warning("WhatsApp approval timed out for %s", getattr(action, "id", ""))
            return False

    # ------------------------------------------------------------------
    # Agent integration
    # ------------------------------------------------------------------

    async def process_message(self, sender: str, text: str) -> str | None:
        """Route a plain-text message through the agent loop.

        Called by WhatsAppHandlers when the message is not a slash command.
        """
        if self._agent_loop:
            try:
                result = await self._agent_loop.run(text)
                return result
            except Exception:
                logger.exception("Agent loop error for WhatsApp message")
                return "Sorry, I encountered an error processing your message."
        return None

    def is_allowed(self, sender: str) -> bool:
        """Check if a sender is allowed (placeholder — extend as needed)."""
        allowed = os.environ.get("WHATSAPP_ALLOWED_NUMBERS", "")
        if not allowed:
            return True  # No restriction by default
        return sender.strip() in allowed.split(",")
