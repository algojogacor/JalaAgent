"""Tests for skill-core pydantic v2 models."""

import pytest
from pydantic import ValidationError
from skill_core.models import (
    JalaAgentSkillMeta,
    Proposal,
    ScanFinding,
    ScanResult,
    Severity,
    Skill,
    SkillFrontmatter,
    SkillRequires,
    SkillSource,
    Verdict,
)

# ---------------------------------------------------------------------------
# SkillRequires
# ---------------------------------------------------------------------------


class TestSkillRequires:
    def test_defaults(self) -> None:
        req = SkillRequires()
        assert req.bins == []
        assert req.env == []

    def test_explicit_values(self) -> None:
        req = SkillRequires(bins=["python", "git"], env=["API_KEY"])
        assert req.bins == ["python", "git"]
        assert req.env == ["API_KEY"]


# ---------------------------------------------------------------------------
# JalaAgentSkillMeta
# ---------------------------------------------------------------------------


class TestJalaAgentSkillMeta:
    def test_defaults(self) -> None:
        meta = JalaAgentSkillMeta()
        assert meta.always is False
        assert meta.emoji == "🔧"
        assert isinstance(meta.requires, SkillRequires)

    def test_always_mode(self) -> None:
        meta = JalaAgentSkillMeta(always=True)
        assert meta.always is True

    def test_custom_emoji(self) -> None:
        meta = JalaAgentSkillMeta(emoji="🐍")
        assert meta.emoji == "🐍"

    def test_requires_nested(self) -> None:
        meta = JalaAgentSkillMeta(
            requires=SkillRequires(bins=["docker"], env=["DOCKER_HOST"])
        )
        assert meta.requires.bins == ["docker"]


# ---------------------------------------------------------------------------
# SkillFrontmatter
# ---------------------------------------------------------------------------


class TestSkillFrontmatter:
    def test_minimal(self) -> None:
        fm = SkillFrontmatter(name="my-skill", description="Does stuff")
        assert fm.name == "my-skill"
        assert fm.description == "Does stuff"
        assert fm.version == "1.0.0"
        assert fm.author == "unknown"
        assert fm.license == "MIT"
        assert fm.platforms == ["windows", "linux", "macos", "termux"]

    def test_name_required(self) -> None:
        with pytest.raises(ValidationError):
            SkillFrontmatter(description="test")  # type: ignore[call-arg]

    def test_description_required(self) -> None:
        with pytest.raises(ValidationError):
            SkillFrontmatter(name="test")  # type: ignore[call-arg]

    def test_jalaagent_meta_default(self) -> None:
        fm = SkillFrontmatter(name="s", description="d")
        meta = fm.jalaagent_meta
        assert isinstance(meta, JalaAgentSkillMeta)
        assert meta.always is False

    def test_jalaagent_meta_from_metadata(self) -> None:
        fm = SkillFrontmatter(
            name="s",
            description="d",
            metadata={
                "jalaagent": {
                    "always": True,
                    "emoji": "🚀",
                    "requires": {"bins": ["python"]},
                }
            },
        )
        meta = fm.jalaagent_meta
        assert meta.always is True
        assert meta.emoji == "🚀"
        assert meta.requires.bins == ["python"]


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------


class TestSkill:
    def test_compute_hash(self) -> None:
        h = Skill.compute_hash("hello")
        assert len(h) == 12
        assert h == Skill.compute_hash("hello")
        assert h != Skill.compute_hash("world")

    def test_slug_shortcut(self) -> None:
        fm = SkillFrontmatter(name="my-skill", description="desc")
        skill = Skill(frontmatter=fm, content_hash="abc123def456")
        assert skill.slug == "my-skill"

    def test_is_always(self) -> None:
        fm_always = SkillFrontmatter(
            name="always-skill",
            description="d",
            metadata={"jalaagent": {"always": True}},
        )
        fm_normal = SkillFrontmatter(name="normal-skill", description="d")

        assert Skill(frontmatter=fm_always, content_hash="a" * 12).is_always is True
        assert Skill(frontmatter=fm_normal, content_hash="b" * 12).is_always is False

    def test_path_optional(self) -> None:
        fm = SkillFrontmatter(name="s", description="d")
        skill = Skill(frontmatter=fm, content_hash="c" * 12)
        assert skill.path is None

    def test_source_defaults_to_user(self) -> None:
        fm = SkillFrontmatter(name="s", description="d")
        skill = Skill(frontmatter=fm, content_hash="d" * 12)
        assert skill.source == SkillSource.USER

    def test_explicit_source(self) -> None:
        fm = SkillFrontmatter(name="s", description="d")
        skill = Skill(frontmatter=fm, content_hash="e" * 12, source=SkillSource.BUNDLED)
        assert skill.source == SkillSource.BUNDLED


# ---------------------------------------------------------------------------
# ScanFinding & ScanResult
# ---------------------------------------------------------------------------


class TestScanFinding:
    def test_minimal(self) -> None:
        finding = ScanFinding(rule="dangerous-exec", severity=Severity.CRITICAL)
        assert finding.rule == "dangerous-exec"
        assert finding.severity == Severity.CRITICAL
        assert finding.line == 0
        assert finding.excerpt == ""

    def test_full(self) -> None:
        finding = ScanFinding(
            rule="prompt-injection",
            severity=Severity.HIGH,
            line=42,
            excerpt="ignore previous instructions",
        )
        assert finding.line == 42
        assert "ignore" in finding.excerpt


class TestScanResult:
    def test_allow_no_findings(self) -> None:
        result = ScanResult(verdict=Verdict.ALLOW)
        assert result.verdict == Verdict.ALLOW
        assert result.findings == []
        assert result.has_critical is False
        assert result.has_high is False

    def test_block_with_critical(self) -> None:
        finding = ScanFinding(rule="dangerous-exec", severity=Severity.CRITICAL)
        result = ScanResult(verdict=Verdict.BLOCK, findings=[finding])
        assert result.has_critical is True
        assert result.has_high is False

    def test_warn_with_high(self) -> None:
        finding = ScanFinding(rule="prompt-injection", severity=Severity.HIGH)
        result = ScanResult(verdict=Verdict.WARN, findings=[finding])
        assert result.has_critical is False
        assert result.has_high is True

    def test_mixed_findings(self) -> None:
        findings = [
            ScanFinding(rule="dangerous-exec", severity=Severity.CRITICAL, line=1),
            ScanFinding(rule="obfuscation", severity=Severity.MEDIUM, line=10),
        ]
        result = ScanResult(verdict=Verdict.BLOCK, findings=findings)
        assert result.has_critical is True
        assert result.has_high is False


# ---------------------------------------------------------------------------
# Proposal
# ---------------------------------------------------------------------------


class TestProposal:
    def test_defaults(self) -> None:
        proposal = Proposal(
            skill_content="---\nname: test\ndescription: test skill\n---\n",
            source_session_id="sess-001",
        )
        assert proposal.scan_result is None
        assert proposal.applied is False
        assert proposal.source_session_id == "sess-001"

    def test_is_blocked(self) -> None:
        p1 = Proposal(
            skill_content="content",
            source_session_id="sess",
        )
        assert p1.is_blocked is False  # no scan yet

        p2 = Proposal(
            skill_content="content",
            source_session_id="sess",
            scan_result=ScanResult(verdict=Verdict.ALLOW),
        )
        assert p2.is_blocked is False

        p3 = Proposal(
            skill_content="content",
            source_session_id="sess",
            scan_result=ScanResult(
                verdict=Verdict.BLOCK,
                findings=[ScanFinding(rule="x", severity=Severity.CRITICAL)],
            ),
        )
        assert p3.is_blocked is True

    def test_requires_approval(self) -> None:
        # No scan → requires approval.
        p1 = Proposal(skill_content="c", source_session_id="s")
        assert p1.requires_approval is True

        # WARN → requires approval.
        p2 = Proposal(
            skill_content="c",
            source_session_id="s",
            scan_result=ScanResult(verdict=Verdict.WARN),
        )
        assert p2.requires_approval is True

        # ALLOW → no approval needed.
        p3 = Proposal(
            skill_content="c",
            source_session_id="s",
            scan_result=ScanResult(verdict=Verdict.ALLOW),
        )
        assert p3.requires_approval is False


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_skill_source_values(self) -> None:
        assert SkillSource.BUNDLED == "bundled"
        assert SkillSource.USER == "user"
        assert SkillSource.PLUGIN == "plugin"

    def test_severity_values(self) -> None:
        assert Severity.CRITICAL == "critical"
        assert Severity.HIGH == "high"
        assert Severity.MEDIUM == "medium"

    def test_verdict_values(self) -> None:
        assert Verdict.ALLOW == "allow"
        assert Verdict.BLOCK == "block"
        assert Verdict.WARN == "warn"
