"""Pydantic v2 models for the JalaAgent skill system."""

import hashlib
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SkillSource(str, Enum):
    """Where a skill was loaded from."""

    BUNDLED = "bundled"
    USER = "user"
    PLUGIN = "plugin"


class Severity(str, Enum):
    """Finding severity for security scan results."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"


class Verdict(str, Enum):
    """Overall security verdict for a scanned skill."""

    ALLOW = "allow"
    BLOCK = "block"
    WARN = "warn"


# ---------------------------------------------------------------------------
# Skill frontmatter (YAML header)
# ---------------------------------------------------------------------------


class SkillRequires(BaseModel):
    """External dependencies declared by a skill."""

    bins: list[str] = Field(
        default_factory=list,
        description="Executable binaries required by the skill",
    )
    env: list[str] = Field(
        default_factory=list,
        description="Environment variables required by the skill",
    )


class JalaAgentSkillMeta(BaseModel):
    """JalaAgent-specific metadata embedded in the SKILL.md frontmatter."""

    always: bool = Field(
        default=False,
        description="If True, this skill is always loaded into the prompt",
    )
    emoji: str = Field(
        default="🔧",
        min_length=1,
        max_length=8,
        description="Emoji icon for the skill",
    )
    requires: SkillRequires = Field(
        default_factory=SkillRequires,
        description="External dependencies",
    )


class SkillFrontmatter(BaseModel):
    """Parsed YAML frontmatter from a SKILL.md file.

    Compatible with the agentskills.io frontmatter format.
    """

    name: str = Field(..., min_length=1, description="Unique skill slug")
    description: str = Field(
        ..., min_length=1, description="One-line description of the skill"
    )
    version: str = Field(
        default="1.0.0", min_length=1, description="SemVer version string"
    )
    author: str = Field(default="unknown", description="Skill author")
    license: str = Field(default="MIT", description="SPDX license identifier")
    platforms: list[str] = Field(
        default_factory=lambda: ["windows", "linux", "macos", "termux"],
        description="Supported platforms",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Arbitrary metadata (including jalaagent key)",
    )

    @property
    def jalaagent_meta(self) -> JalaAgentSkillMeta:
        """Extract the JalaAgent-specific metadata, or return defaults."""
        raw = self.metadata.get("jalaagent", {})
        if isinstance(raw, dict):
            return JalaAgentSkillMeta(**raw)
        return JalaAgentSkillMeta()


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------


class Skill(BaseModel):
    """A fully loaded skill from a SKILL.md file.

    Contains both the parsed YAML frontmatter and the Markdown body.
    The ``content_hash`` is the first 12 characters of the SHA-256 hex digest
    of the full SKILL.md content, used for cache-aware re-reading.
    """

    frontmatter: SkillFrontmatter = Field(..., description="Parsed YAML header")
    body: str = Field(
        default="", description="Markdown body after the YAML frontmatter"
    )
    path: Path | None = Field(
        default=None, description="Filesystem path where the skill was loaded from"
    )
    content_hash: str = Field(
        ..., min_length=1, description="SHA-256:12 prefix of the full SKILL.md content"
    )
    source: SkillSource = Field(
        default=SkillSource.USER, description="Where the skill came from"
    )

    @staticmethod
    def compute_hash(content: str) -> str:
        """Return the 12-char SHA-256 prefix for *content*."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]

    @property
    def slug(self) -> str:
        """Shortcut to ``frontmatter.name``."""
        return self.frontmatter.name

    @property
    def is_always(self) -> bool:
        """Whether this skill should always be loaded."""
        return self.frontmatter.jalaagent_meta.always


# ---------------------------------------------------------------------------
# Security scanner models
# ---------------------------------------------------------------------------


class ScanFinding(BaseModel):
    """A single issue found by the security scanner."""

    rule: str = Field(..., min_length=1, description="Rule identifier")
    severity: Severity = Field(..., description="How severe the finding is")
    line: int = Field(default=0, ge=0, description="Line number where the issue was found")
    excerpt: str = Field(
        default="", description="Brief excerpt of the matched content"
    )


class ScanResult(BaseModel):
    """The result of scanning a skill for security issues."""

    verdict: Verdict = Field(..., description="Overall security decision")
    findings: list[ScanFinding] = Field(
        default_factory=list, description="Individual findings"
    )

    @property
    def has_critical(self) -> bool:
        """True if any finding is critical severity."""
        return any(f.severity == Severity.CRITICAL for f in self.findings)

    @property
    def has_high(self) -> bool:
        """True if any finding is high severity."""
        return any(f.severity == Severity.HIGH for f in self.findings)


# ---------------------------------------------------------------------------
# Workshop models
# ---------------------------------------------------------------------------


class Proposal(BaseModel):
    """A pending skill proposal in the workshop pipeline."""

    id: UUID = Field(default_factory=uuid4, description="Unique proposal ID")
    skill_content: str = Field(..., min_length=1, description="Full SKILL.md content")
    scan_result: ScanResult | None = Field(
        default=None, description="Security scan result (None if not yet scanned)"
    )
    source_session_id: str = Field(
        ..., min_length=1, description="Session that produced this proposal"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the proposal was created",
    )
    applied: bool = Field(default=False, description="Whether the proposal was applied")

    @property
    def is_blocked(self) -> bool:
        """True if the scan result is a hard block."""
        return self.scan_result is not None and self.scan_result.verdict == Verdict.BLOCK

    @property
    def requires_approval(self) -> bool:
        """True if this proposal needs user review before applying."""
        if self.scan_result is None:
            return True
        return self.scan_result.verdict != Verdict.ALLOW


__all__ = [
    "SkillSource",
    "Severity",
    "Verdict",
    "SkillRequires",
    "JalaAgentSkillMeta",
    "SkillFrontmatter",
    "Skill",
    "ScanFinding",
    "ScanResult",
    "Proposal",
]
