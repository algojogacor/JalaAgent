"""Verify all bundled skills load without errors."""

import os
import pytest
from pathlib import Path
from skill_core.loader import SkillLoader


import asyncio
from skill_core.models import SkillSource


def test_all_bundled_skills_load() -> None:
    """Every bundled SKILL.md must parse without errors."""
    bundled = Path(__file__).parent.parent.parent / "packages" / "skill-core" / "src" / "skill_core" / "bundled"
    if not bundled.is_dir():
        pytest.skip("Bundled skills dir not found")

    async def _load():
        loader = SkillLoader(bundled_dir=bundled)
        return await loader.load_from_dir(bundled, SkillSource.BUNDLED)

    skills = asyncio.run(_load())
    skill_files = list(bundled.rglob("SKILL.md"))
    assert len(skill_files) > 0, f"No SKILL.md files found in {bundled}"

    loaded_names = {s.slug for s in skills}
    expected_names = {p.parent.name for p in skill_files}
    missing = expected_names - loaded_names
    assert not missing, f"Failed to load {len(missing)} skills: {missing}"


def test_every_skill_has_required_fields() -> None:
    bundled = Path(__file__).parent.parent.parent / "packages" / "skill-core" / "src" / "skill_core" / "bundled"
    if not bundled.is_dir():
        pytest.skip("Bundled skills dir not found")

    async def _load():
        loader = SkillLoader(bundled_dir=bundled)
        return await loader.load_from_dir(bundled, SkillSource.BUNDLED)

    skills = asyncio.run(_load())
    assert len(skills) >= 40, f"Expected 40+ skills, got {len(skills)}"
    for skill in skills:
        assert skill.slug, f"Skill {skill.path} has no name"
        assert skill.frontmatter.description, f"Skill {skill.slug} has no description"
        assert skill.content_hash, f"Skill {skill.slug} has no content hash"
