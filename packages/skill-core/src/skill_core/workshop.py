"""Skill workshop: AI-assisted skill generation pipeline (propose → scan → review → apply)."""

import logging
import os
import shutil
from pathlib import Path
from uuid import UUID

from skill_core.models import Proposal, ScanResult, Verdict
from skill_core.scanner import SkillScanner

logger = logging.getLogger(__name__)

# Defaults — can be overridden at construction time.
_DEFAULT_WORKSHOP_DIR = Path.home() / ".jalaagent" / "workshop"
_DEFAULT_SKILLS_DIR = Path.home() / ".jalaagent" / "skills"


class SkillBlockedError(Exception):
    """Raised when a scan blocks a skill proposal (critical findings)."""

    def __init__(self, scan_result: ScanResult) -> None:
        self.scan_result = scan_result
        super().__init__(
            f"Skill blocked by security scanner: "
            f"{len(scan_result.findings)} finding(s)"
        )


class SkillWorkshop:
    """Propose → security_scan → review (user) → apply / reject pipeline.

    Parameters
    ----------
    scanner:
        The security scanner to use for vetting proposals.
    workshop_dir:
        Where to store pending proposals (default: ``~/.jalaagent/workshop/``).
    skills_dir:
        Where to install approved skills (default: ``~/.jalaagent/skills/``).
    """

    def __init__(
        self,
        scanner: SkillScanner | None = None,
        workshop_dir: Path | None = None,
        skills_dir: Path | None = None,
    ) -> None:
        self._scanner = scanner or SkillScanner()
        self._workshop_dir = workshop_dir or _DEFAULT_WORKSHOP_DIR
        self._skills_dir = skills_dir or _DEFAULT_SKILLS_DIR

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def propose(
        self, skill_content: str, source_session_id: str
    ) -> Proposal:
        """Stage a new skill proposal for review.

        1. Parse and validate the frontmatter.
        2. Run the security scanner.
        3. If blocked (critical finding), raise :class:`SkillBlockedError`.
        4. Otherwise, store ``PROPOSAL.md`` in the workshop directory.

        Parameters
        ----------
        skill_content:
            The full SKILL.md content (YAML frontmatter + body).
        source_session_id:
            The session that produced this proposal.

        Returns
        -------
        Proposal
            The staged proposal (with scan results attached).

        Raises
        ------
        SkillBlockedError
            If the security scanner returns a BLOCK verdict.
        """
        # Scan first — don't even stage if it's dangerous.
        scan_result = await self._scanner.scan(skill_content)

        if scan_result.verdict == Verdict.BLOCK:
            raise SkillBlockedError(scan_result)

        # Create proposal.
        proposal = Proposal(
            skill_content=skill_content,
            scan_result=scan_result,
            source_session_id=source_session_id,
        )

        # Persist to workshop directory.
        await self._write_proposal(proposal)

        logger.info(
            "Proposal %s staged — verdict=%s, findings=%d",
            proposal.id,
            scan_result.verdict.value,
            len(scan_result.findings),
        )
        return proposal

    async def review(self, proposal_id: UUID | str) -> Proposal | None:
        """Retrieve a pending proposal by ID.

        Returns ``None`` if the proposal does not exist or has already been
        applied/rejected.
        """
        proposal_dir = self._proposal_dir(proposal_id)
        proposal_file = proposal_dir / "PROPOSAL.md"

        def _read() -> Proposal | None:
            if not proposal_file.is_file():
                return None
            try:
                raw = proposal_file.read_text(encoding="utf-8")
            except OSError:
                return None
            return Proposal.model_validate_json(raw)

        import asyncio
        return await asyncio.to_thread(_read)

    async def apply(self, proposal_id: UUID | str) -> Path:
        """Write an approved proposal to the skills directory.

        The skill is written to ``<skills_dir>/<skill_name>/SKILL.md`` using
        an atomic write (temp file + rename).  If the skill already exists, a
        backup is created first and restored on failure.

        Parameters
        ----------
        proposal_id:
            The ID of the proposal to apply.

        Returns
        -------
        Path
            The path where the skill was installed.

        Raises
        ------
        ValueError
            If the proposal does not exist.
        """
        proposal = await self.review(proposal_id)
        if proposal is None:
            raise ValueError(f"Proposal {proposal_id} not found")

        # Parse the skill name from the frontmatter.
        from skill_core.loader import _parse_frontmatter

        fm_dict, _ = _parse_frontmatter(proposal.skill_content)
        skill_name = fm_dict.get("name", f"unknown-{str(proposal_id)[:8]}")

        # Sanitize the skill name for filesystem use.
        safe_name = _safe_slug(skill_name)
        target_dir = self._skills_dir / safe_name
        target_file = target_dir / "SKILL.md"

        # Atomic install with rollback.
        backup_dir: Path | None = None
        try:
            # Create backup if existing.
            if target_file.exists():
                backup_dir = self._skills_dir / f".{safe_name}.backup"
                if backup_dir.exists():
                    shutil.rmtree(backup_dir, ignore_errors=True)
                shutil.copytree(target_dir, backup_dir)

            # Write atomically.
            await self._atomic_write(target_file, proposal.skill_content)

            # Mark as applied.
            proposal.applied = True
            await self._write_proposal(proposal)

            # Cleanup backup on success.
            if backup_dir and backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)

            logger.info("Skill %s installed at %s", skill_name, target_file)
            return target_file

        except Exception:
            # Rollback: restore from backup if we have one.
            if backup_dir and backup_dir.exists():
                if target_dir.exists():
                    shutil.rmtree(target_dir, ignore_errors=True)
                shutil.move(str(backup_dir), str(target_dir))
                logger.warning("Rolled back skill %s", skill_name)
            raise

    async def reject(self, proposal_id: UUID | str) -> None:
        """Discard a pending proposal (delete its workshop directory).

        This is a no-op if the proposal does not exist.
        """
        proposal_dir = self._proposal_dir(proposal_id)

        def _rm() -> None:
            if proposal_dir.is_dir():
                shutil.rmtree(proposal_dir, ignore_errors=True)

        import asyncio
        await asyncio.to_thread(_rm)
        logger.info("Proposal %s rejected and removed", proposal_id)

    async def list_pending(self) -> list[Proposal]:
        """Return all pending (not-yet-applied) proposals."""

        def _list() -> list[Proposal]:
            if not self._workshop_dir.is_dir():
                return []
            results: list[Proposal] = []
            for child in sorted(self._workshop_dir.iterdir()):
                if not child.is_dir():
                    continue
                proposal_file = child / "PROPOSAL.md"
                if not proposal_file.is_file():
                    continue
                try:
                    raw = proposal_file.read_text(encoding="utf-8")
                    p = Proposal.model_validate_json(raw)
                    if not p.applied:
                        results.append(p)
                except Exception:
                    continue
            return results

        import asyncio
        return await asyncio.to_thread(_list)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _proposal_dir(self, proposal_id: UUID | str) -> Path:
        """Return the directory path for a proposal."""
        return self._workshop_dir / str(proposal_id)

    async def _write_proposal(self, proposal: Proposal) -> None:
        """Persist a proposal to its workshop directory."""
        proposal_dir = self._proposal_dir(proposal.id)
        proposal_file = proposal_dir / "PROPOSAL.md"

        def _sync() -> None:
            proposal_dir.mkdir(parents=True, exist_ok=True)
            proposal_file.write_text(
                proposal.model_dump_json(indent=2), encoding="utf-8"
            )

        import asyncio
        await asyncio.to_thread(_sync)

    @staticmethod
    async def _atomic_write(path: Path, content: str) -> None:
        """Write *content* to *path* via temp file + rename."""

        def _sync() -> None:
            import uuid

            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.parent / f"{path.name}.{uuid.uuid4().hex}.tmp"
            tmp.write_text(content, encoding="utf-8")
            try:
                os.replace(tmp, path)
            finally:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass

        import asyncio
        await asyncio.to_thread(_sync)


def _safe_slug(name: str) -> str:
    """Convert a skill name to a filesystem-safe directory name."""
    import re

    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "unnamed"
