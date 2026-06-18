"""Tests for skill-core loader (SKILL.md loading and formatting)."""

import tempfile
from pathlib import Path

import pytest
from skill_core.loader import (
    SkillLoader,
    _current_platform,
    _is_applicable,
    _parse_frontmatter,
)
from skill_core.models import Skill, SkillFrontmatter, SkillSource

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_skill_md(
    directory: Path,
    name: str = "test-skill",
    description: str = "A test skill",
    body: str = "Skill body content.",
    extra_frontmatter: dict | None = None,
) -> Path:
    """Create a minimal SKILL.md file and return its path."""
    fm = f"---\nname: {name}\ndescription: {description}\n"
    if extra_frontmatter:
        import yaml
        for key, value in extra_frontmatter.items():
            fm += f"{key}: {yaml.dump(value).strip()}\n"
    fm += "---\n"
    content = fm + body
    skill_file = directory / name / "SKILL.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(content, encoding="utf-8")
    return skill_file


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_parses_valid_yaml(self) -> None:
        raw = "---\nname: my-skill\ndescription: does something\n---\nBody here."
        fm, body = _parse_frontmatter(raw)
        assert fm["name"] == "my-skill"
        assert fm["description"] == "does something"
        assert body == "Body here."

    def test_no_frontmatter(self) -> None:
        raw = "Just a plain markdown file."
        fm, body = _parse_frontmatter(raw)
        assert fm == {}
        assert body == raw

    def test_empty_frontmatter(self) -> None:
        raw = "---\n---\nBody"
        fm, body = _parse_frontmatter(raw)
        assert body == "Body"

    def test_invalid_yaml(self) -> None:
        raw = "---\n: invalid yaml :::\n---\nBody"
        fm, body = _parse_frontmatter(raw)
        assert fm == {}
        assert body == raw

    def test_only_one_delimiter(self) -> None:
        raw = "---\nname: test\n"
        fm, body = _parse_frontmatter(raw)
        assert fm == {}


# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------


class TestCurrentPlatform:
    def test_returns_string(self) -> None:
        plat = _current_platform()
        assert plat in ("windows", "linux", "macos", "termux")


class TestIsApplicable:
    def test_platform_match(self) -> None:
        fm = SkillFrontmatter(name="s", description="d", platforms=["windows", "linux"])
        skill = Skill(frontmatter=fm, content_hash="a" * 12)
        assert _is_applicable(skill, "windows") is True
        assert _is_applicable(skill, "linux") is True
        assert _is_applicable(skill, "macos") is False

    def test_all_platforms_default(self) -> None:
        fm = SkillFrontmatter(name="s", description="d")
        skill = Skill(frontmatter=fm, content_hash="b" * 12)
        for plat in ("windows", "linux", "macos", "termux"):
            assert _is_applicable(skill, plat) is True


# ---------------------------------------------------------------------------
# SkillLoader
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_bundled_dir() -> Path:
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def tmp_user_dir() -> Path:
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def loader(tmp_bundled_dir: Path, tmp_user_dir: Path) -> SkillLoader:
    return SkillLoader(bundled_dir=tmp_bundled_dir, user_dir=tmp_user_dir)


@pytest.mark.asyncio
class TestLoadFromDir:
    async def test_loads_single_skill(
        self, loader: SkillLoader, tmp_bundled_dir: Path
    ) -> None:
        make_skill_md(tmp_bundled_dir, "git-help", "Git helper skill")

        skills = await loader.load_from_dir(tmp_bundled_dir, SkillSource.BUNDLED)
        assert len(skills) == 1
        assert skills[0].slug == "git-help"
        assert skills[0].source == SkillSource.BUNDLED

    async def test_empty_directory(self, loader: SkillLoader) -> None:
        with tempfile.TemporaryDirectory() as td:
            skills = await loader.load_from_dir(Path(td), SkillSource.USER)
            assert skills == []

    async def test_nonexistent_directory(self, loader: SkillLoader) -> None:
        skills = await loader.load_from_dir(Path("/nonexistent/path"), SkillSource.USER)
        assert skills == []

    async def test_skips_invalid_frontmatter(
        self, loader: SkillLoader, tmp_bundled_dir: Path
    ) -> None:
        d = tmp_bundled_dir / "bad-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("No frontmatter at all.", encoding="utf-8")
        skills = await loader.load_from_dir(tmp_bundled_dir, SkillSource.BUNDLED)
        assert len(skills) == 0

    async def test_content_hash_computed(
        self, loader: SkillLoader, tmp_bundled_dir: Path
    ) -> None:
        make_skill_md(tmp_bundled_dir, "hash-test", "Hash testing")
        skills = await loader.load_from_dir(tmp_bundled_dir, SkillSource.BUNDLED)
        assert len(skills[0].content_hash) == 12


@pytest.mark.asyncio
class TestLoadAll:
    async def test_loads_from_all_sources(
        self, tmp_bundled_dir: Path, tmp_user_dir: Path
    ) -> None:
        make_skill_md(tmp_bundled_dir, "bundled-skill", "Bundled")
        make_skill_md(tmp_user_dir, "user-skill", "User installed")

        loader = SkillLoader(bundled_dir=tmp_bundled_dir, user_dir=tmp_user_dir)
        skills = await loader.load_all()
        assert len(skills) == 2
        sources = {s.source for s in skills}
        assert SkillSource.BUNDLED in sources
        assert SkillSource.USER in sources

    async def test_user_overrides_bundled(
        self, tmp_bundled_dir: Path, tmp_user_dir: Path
    ) -> None:
        make_skill_md(tmp_bundled_dir, "same-slug", "Bundled version")
        make_skill_md(tmp_user_dir, "same-slug", "User version")

        loader = SkillLoader(bundled_dir=tmp_bundled_dir, user_dir=tmp_user_dir)
        skills = await loader.load_all()
        assert len(skills) == 1
        assert skills[0].source == SkillSource.USER
        assert skills[0].frontmatter.description == "User version"

    async def test_plugin_skills_added(
        self, tmp_bundled_dir: Path
    ) -> None:
        with tempfile.TemporaryDirectory() as plugin_td:
            plugin_dir = Path(plugin_td)
            make_skill_md(plugin_dir, "plugin-skill", "Plugin provided")

            loader = SkillLoader(
                bundled_dir=tmp_bundled_dir, plugin_dirs=[plugin_dir]
            )
            skills = await loader.load_all()
            assert len(skills) == 1
            assert skills[0].source == SkillSource.PLUGIN


class TestFormatForPrompt:
    def test_empty_skills(self) -> None:
        loader = SkillLoader()
        assert loader.format_for_prompt([]) == ""

    def test_formats_xml_block(self) -> None:
        fm = SkillFrontmatter(
            name="my-skill", description="Does things", platforms=["windows", "linux"]
        )
        skill = Skill(frontmatter=fm, content_hash="a" * 12, body="The body.")

        loader = SkillLoader()
        result = loader.format_for_prompt([skill])
        assert "<available_skills>" in result
        assert "</available_skills>" in result
        assert 'name="my-skill"' in result
        assert "The body." in result

    def test_truncates_long_body(self) -> None:
        fm = SkillFrontmatter(name="s", description="d")
        long_body = "x" * 50000
        skill = Skill(frontmatter=fm, content_hash="b" * 12, body=long_body)

        loader = SkillLoader()
        result = loader.format_for_prompt([skill])
        assert len(result) < 50000  # body should be truncated

    def test_sorts_always_first(self) -> None:
        fm_normal = SkillFrontmatter(name="normal", description="Normal skill")
        fm_always = SkillFrontmatter(
            name="always",
            description="Always skill",
            metadata={"jalaagent": {"always": True}},
        )

        normal = Skill(frontmatter=fm_normal, content_hash="n" * 12)
        always = Skill(frontmatter=fm_always, content_hash="a" * 12)

        loader = SkillLoader()
        result = loader.format_for_prompt([normal, always])
        assert result.index("always") < result.index("normal")
