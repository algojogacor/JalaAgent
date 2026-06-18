"""Message sanitization — provider-aware pre-flight cleanup."""

import re
from typing import Any


class MessageSanitizer:
    """Provider-aware message sanitization pipeline."""

    @staticmethod
    async def sanitize(messages: list[Any], provider: str) -> list[Any]:
        msgs = list(messages)
        for sanitizer in [
            MessageSanitizer._strip_surrogates,
            MessageSanitizer._strip_empty,
        ]:
            msgs = [sanitizer(m) for m in msgs if m is not None]
        return [m for m in msgs if m is not None]

    @staticmethod
    def _strip_surrogates(msg: Any) -> Any:
        if hasattr(msg, "content") and isinstance(msg.content, str):
            msg.content = re.sub(r"[\uD800-\uDFFF]", "", msg.content)
        return msg

    @staticmethod
    def _strip_empty(msg: Any) -> Any | None:
        if hasattr(msg, "content") and isinstance(msg.content, str) and not msg.content.strip():
            return None
        return msg
