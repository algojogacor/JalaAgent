"""Tests for skill-core workshop (propose → scan → review → apply pipeline)."""

import tempfile
from pathlib import Path

import pytest
from skill_core.models import Verdict
from skill_core.workshop import SkillBlockedError, SkillWorkshop

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_workshop_dir() -> Path:
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def tmp_skills_dir() -> Path:
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def workshop(tmp_workshop_dir: Path, tmp_skills_dir: Path) -> SkillWorkshop:
    return SkillWorkshop(workshop_dir=tmp_workshop_dir, skills_dir=tmp_skills_dir)


def safe_skill_md(name: str = "test-skill", description: str = "A safe skill") -> str:
    return (
        f"---\nname: {name}\ndescription: {description}\n"
        f"license: MIT\n---\n\n## {name}\n\nBody content here.\n"
    )


# ---------------------------------------------------------------------------
# Propose
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPropose:
    async def test_propose_creates_proposal(
        self, workshop: SkillWorkshop
    ) -> None:
        content = safe_skill_md()
        proposal = await workshop.propose(content, "sess-001")
        assert proposal.source_session_id == "sess-001"
        assert proposal.scan_result is not None
        assert proposal.scan_result.verdict == Verdict.ALLOW
        assert proposal.applied is False

    async def test_propose_blocked_by_scanner(
        self, workshop: SkillWorkshop
    ) -> None:
        content = "eval(user_input)\n"
        with pytest.raises(SkillBlockedError) as exc:
            await workshop.propose(content, "sess-dangerous")
        assert exc.value.scan_result.verdict == Verdict.BLOCK

    async def test_proposal_persisted(
        self, workshop: SkillWorkshop, tmp_workshop_dir: Path
    ) -> None:
        content = safe_skill_md()
        proposal = await workshop.propose(content, "sess-persist")
        # Check that the file exists on disk.
        proposal_file = tmp_workshop_dir / str(proposal.id) / "PROPOSAL.md"
        assert proposal_file.is_file()


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestReview:
    async def test_review_returns_proposal(
        self, workshop: SkillWorkshop
    ) -> None:
        content = safe_skill_md()
        proposal = await workshop.propose(content, "sess-review")
        retrieved = await workshop.review(proposal.id)
        assert retrieved is not None
        assert retrieved.id == proposal.id
        assert retrieved.skill_content == content

    async def test_review_nonexistent(self, workshop: SkillWorkshop) -> None:
        assert await workshop.review("nonexistent-id") is None


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestApply:
    async def test_apply_installs_skill(
        self, workshop: SkillWorkshop, tmp_skills_dir: Path
    ) -> None:
        content = safe_skill_md("applied-skill", "An applied skill")
        proposal = await workshop.propose(content, "sess-apply")
        skill_path = await workshop.apply(proposal.id)
        assert skill_path.exists()
        assert skill_path.name == "SKILL.md"
        assert skill_path.parent.name == "applied-skill"
        assert skill_path.read_text(encoding="utf-8") == content

    async def test_apply_marks_applied(
        self, workshop: SkillWorkshop
    ) -> None:
        content = safe_skill_md("marked-skill", "Marked as applied")
        proposal = await workshop.propose(content, "sess-mark")
        await workshop.apply(proposal.id)
        retrieved = await workshop.review(proposal.id)
        assert retrieved is not None
        assert retrieved.applied is True

    async def test_apply_nonexistent_raises(
        self, workshop: SkillWorkshop
    ) -> None:
        with pytest.raises(ValueError, match="not found"):
            await workshop.apply("nonexistent-id")

    async def test_apply_rollback_on_failure(
        self, workshop: SkillWorkshop, tmp_skills_dir: Path
    ) -> None:
        """If the atomic write fails, existing skill is preserved."""
        content = safe_skill_md("rollback-skill", "Original")
        proposal = await workshop.propose(content, "sess-rollback")
        # Install once.
        await workshop.apply(proposal.id)

        # Create a new proposal with same name (simulating update).
        content2 = safe_skill_md("rollback-skill", "Updated")
        proposal2 = await workshop.propose(content2, "sess-rollback2")
        await workshop.apply(proposal2.id)

        # Skill should have the updated content.
        skill_file = tmp_skills_dir / "rollback-skill" / "SKILL.md"
        assert skill_file.read_text(encoding="utf-8") == content2


# ---------------------------------------------------------------------------
# Reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestReject:
    async def test_reject_removes_proposal(
        self, workshop: SkillWorkshop, tmp_workshop_dir: Path
    ) -> None:
        content = safe_skill_md()
        proposal = await workshop.propose(content, "sess-reject")
        proposal_dir = tmp_workshop_dir / str(proposal.id)
        assert proposal_dir.is_dir()
        await workshop.reject(proposal.id)
        assert not proposal_dir.exists()

    async def test_reject_nonexistent_no_error(
        self, workshop: SkillWorkshop
    ) -> None:
        await workshop.reject("nonexistent")  # should not raise


# ---------------------------------------------------------------------------
# List pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestListPending:
    async def test_list_pending_includes_new(
        self, workshop: SkillWorkshop
    ) -> None:
        content = safe_skill_md("pending-skill", "Pending")
        await workshop.propose(content, "sess-pending")
        pending = await workshop.list_pending()
        assert len(pending) == 1
        assert pending[0].applied is False

    async def test_list_pending_excludes_applied(
        self, workshop: SkillWorkshop
    ) -> None:
        content = safe_skill_md("done-skill", "Done")
        proposal = await workshop.propose(content, "sess-done")
        await workshop.apply(proposal.id)
        pending = await workshop.list_pending()
        assert len(pending) == 0

    async def test_list_pending_excludes_rejected(
        self, workshop: SkillWorkshop
    ) -> None:
        content = safe_skill_md("rejected-skill", "Rejected")
        proposal = await workshop.propose(content, "sess-rej2")
        await workshop.reject(proposal.id)
        pending = await workshop.list_pending()
        assert len(pending) == 0

    async def test_list_pending_empty(self, workshop: SkillWorkshop) -> None:
        pending = await workshop.list_pending()
        assert pending == []


# ---------------------------------------------------------------------------
# Safe slug
# ---------------------------------------------------------------------------


def test_safe_slug() -> None:
    from skill_core.workshop import _safe_slug

    assert _safe_slug("My Skill!") == "my-skill"
    assert _safe_slug("  Spaces  ") == "spaces"
    assert _safe_slug("special@#$chars") == "special-chars"
    assert _safe_slug("!!") == "unnamed"
