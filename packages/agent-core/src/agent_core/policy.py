"""4-layer tool policy pipeline from CLAUDE.md: global → agent → category → sender."""

from enum import Enum

from agent_core.models import ActionCategory, ApprovalMode


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


# Default CUSTOM rules from CLAUDE.md.
_DEFAULT_RULES: dict[str, str] = {
    "file_read": "auto",
    "file_write": "auto",
    "file_delete": "ask",
    "shell_exec": "ask",
    "network_get": "auto",
    "network_post": "ask",
    "messaging_send": "ask",
    "memory_write": "auto",
}

# Categories that are considered destructive (used in NORMAL mode).
_DESTRUCTIVE = {
    ActionCategory.FILE_WRITE,
    ActionCategory.FILE_DELETE,
    ActionCategory.SHELL_EXEC,
    ActionCategory.NETWORK_POST,
    ActionCategory.MESSAGING_SEND,
    ActionCategory.MEMORY_WRITE,
}


class PolicyPipeline:
    """4-layer policy pipeline.

    global → agent → category → sender
    deny always wins over allow.
    """

    def __init__(
        self,
        mode: ApprovalMode = ApprovalMode.NORMAL,
        custom_rules: dict[str, str] | None = None,
    ) -> None:
        self._mode = mode
        self._rules = custom_rules or dict(_DEFAULT_RULES)

    @property
    def mode(self) -> ApprovalMode:
        return self._mode

    @mode.setter
    def mode(self, value: ApprovalMode) -> None:
        self._mode = value

    def check(self, category: ActionCategory, sender: str = "") -> PolicyDecision:
        """Check whether an action in *category* requires approval.

        Deny always wins over allow.
        """
        # PARANOID: everything requires approval.
        if self._mode == ApprovalMode.PARANOID:
            return PolicyDecision.ASK

        # YOLO: nothing requires approval.
        if self._mode == ApprovalMode.YOLO:
            return PolicyDecision.ALLOW

        # NORMAL: destructive categories require approval.
        if self._mode == ApprovalMode.NORMAL:
            return PolicyDecision.ASK if category in _DESTRUCTIVE else PolicyDecision.ALLOW

        # CUSTOM: per-category rules.
        if self._mode == ApprovalMode.CUSTOM:
            rule = self._rules.get(category.value, "ask")
            if rule == "auto":
                return PolicyDecision.ALLOW
            if rule == "deny":
                return PolicyDecision.DENY
            return PolicyDecision.ASK

        return PolicyDecision.ASK

    def requires_approval(self, category: ActionCategory, sender: str = "") -> bool:
        return self.check(category, sender) == PolicyDecision.ASK

    def update_rules(self, rules: dict[str, str]) -> None:
        self._rules.update(rules)
