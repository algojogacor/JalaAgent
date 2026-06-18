"""Security scanner for skills: prompt injection, dangerous exec, env exfiltration detection.

Scans SKILL.md content for known attack patterns before a skill is installed
or loaded into the prompt.  Returns a :class:`ScanResult` with an overall
verdict and per-finding details.
"""

import re

from skill_core.models import ScanFinding, ScanResult, Severity, Verdict

# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------
# Each rule is a dict with:
#   rule    — short identifier
#   severity — Severity enum value
#   patterns — list of compiled regexes
# ---------------------------------------------------------------------------

_RULES: list[dict] = [
    # ---- dangerous-exec ------------------------------------------------
    {
        "rule": "dangerous-exec",
        "severity": Severity.CRITICAL,
        "patterns": [
            re.compile(r"\beval\s*\(", re.IGNORECASE),
            re.compile(r"\bexec\s*\(", re.IGNORECASE),
            re.compile(r"__import__\s*\("),
            re.compile(r"subprocess\.Popen\s*\(.*shell\s*=\s*True", re.IGNORECASE),
        ],
    },
    # ---- crypto-mining -------------------------------------------------
    {
        "rule": "crypto-mining",
        "severity": Severity.CRITICAL,
        "patterns": [
            re.compile(r"stratum\+tcp", re.IGNORECASE),
            re.compile(r"\bhashrate\b", re.IGNORECASE),
            re.compile(r"\bmonero\b", re.IGNORECASE),
            re.compile(r"\bcoinhive\b", re.IGNORECASE),
        ],
    },
    # ---- prompt-injection ----------------------------------------------
    {
        "rule": "prompt-injection",
        "severity": Severity.HIGH,
        "patterns": [
            re.compile(r"ignore\s+(all\s+)?previous\s+(instructions?|prompts?)", re.IGNORECASE),
            re.compile(r"\bdisregard\s+(all\s+)?(previous\s+)?instructions?\b", re.IGNORECASE),
            re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
            re.compile(r"you\s+are\s+now\s+(a\s+|the\s+)?new", re.IGNORECASE),
            re.compile(r"system\s+prompt\s*(override|hijack|leak)", re.IGNORECASE),
        ],
    },
    # ---- shell-pipe ----------------------------------------------------
    {
        "rule": "shell-pipe",
        "severity": Severity.HIGH,
        "patterns": [
            re.compile(r"\|\s*curl\b", re.IGNORECASE),
            re.compile(r"\|\s*wget\b", re.IGNORECASE),
            re.compile(r"\|\s*bash\b", re.IGNORECASE),
            re.compile(r"\|\s*sh\b", re.IGNORECASE),
        ],
    },
    # ---- env-exfiltration ----------------------------------------------
    {
        "rule": "env-exfiltration",
        "severity": Severity.HIGH,
        "patterns": [
            # os.environ sent to external URL on same or nearby line.
            re.compile(r"os\.environ.*https?://", re.IGNORECASE),
            re.compile(r"process\.env.*https?://", re.IGNORECASE),
            # URLs containing env var names as query params (heuristic).
            re.compile(r"https?://[^\s]*\$\(.*\)", re.IGNORECASE),
        ],
    },
    # ---- obfuscation ---------------------------------------------------
    {
        "rule": "obfuscation",
        "severity": Severity.MEDIUM,
        "patterns": [
            re.compile(r"base64\.b64decode\(.*\)\s*.*\bexec\b", re.IGNORECASE),
            re.compile(r"chr\s*\(\s*\d+\s*\)\s*\+\s*chr\s*\(", re.IGNORECASE),
            re.compile(r"__builtins__\s*\[", re.IGNORECASE),
        ],
    },
]


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class SkillScanner:
    """Scans SKILL.md content for security issues before install and at propose time.

    Usage::

        scanner = SkillScanner()
        result = await scanner.scan(skill_content)
        if result.verdict == Verdict.BLOCK:
            raise SkillBlockedError(result)
    """

    def __init__(self) -> None:
        self._rules = _RULES

    async def scan(self, skill_content: str) -> ScanResult:
        """Scan *skill_content* against all security rules.

        Parameters
        ----------
        skill_content:
            The full SKILL.md content (frontmatter + body).

        Returns
        -------
        ScanResult
            Overall verdict and per-finding details.
        """
        findings: list[ScanFinding] = []

        lines = skill_content.split("\n")

        for rule_def in self._rules:
            for pattern in rule_def["patterns"]:
                for i, line in enumerate(lines, start=1):
                    match = pattern.search(line)
                    if match:
                        findings.append(
                            ScanFinding(
                                rule=rule_def["rule"],
                                severity=rule_def["severity"],
                                line=i,
                                excerpt=line.strip()[:120],
                            )
                        )

        # Determine verdict.
        verdict = self._compute_verdict(findings)

        return ScanResult(verdict=verdict, findings=findings)

    @staticmethod
    def _compute_verdict(findings: list[ScanFinding]) -> Verdict:
        """Compute the overall verdict from a list of findings.

        * Any critical finding → BLOCK.
        * Any high finding → WARN.
        * Medium only (or no findings) → ALLOW.
        """
        has_critical = any(f.severity == Severity.CRITICAL for f in findings)
        has_high = any(f.severity == Severity.HIGH for f in findings)

        if has_critical:
            return Verdict.BLOCK
        if has_high:
            return Verdict.WARN
        return Verdict.ALLOW
