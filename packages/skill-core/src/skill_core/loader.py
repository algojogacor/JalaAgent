"""Skill discovery and loading from multiple sources."""

import logging
import sys
from pathlib import Path

import yaml

from skill_core.models import Skill, SkillFrontmatter, SkillSource

logger = logging.getLogger(__name__)

# YAML frontmatter delimiter.
_FRONTMATTER_DELIM = "---"

# Limits per CLAUDE.md and PRD F-04.4.
_MAX_SKILLS = 150
_MAX_CHARS_PER_SKILL = 40_000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    """Split *raw* into (frontmatter_dict, body).

    Returns (empty_dict, raw) if no YAML frontmatter is found.
    """
    if not raw.startswith(_FRONTMATTER_DELIM):
        return {}, raw

    parts = raw.split(_FRONTMATTER_DELIM, 2)
    if len(parts) < 3:
        return {}, raw

    try:
        # Use CSafeLoader for speed, fall back to SafeLoader.
        loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
        fm = yaml.load(parts[1], Loader=loader) or {}
    except yaml.YAMLError as exc:
        logger.warning("YAML parse error in skill frontmatter: %s", exc)
        return {}, raw

    body = parts[2].strip()
    return fm, body


def _current_platform() -> str:
    """Return a short platform name matching the frontmatter ``platforms`` list."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        # Check for Termux (Android) — heuristic via environment.
        if "ANDROID_ROOT" in sys.__dict__.get("path", []):
            return "termux"
        return "linux"
    return sys.platform


# ---------------------------------------------------------------------------
# SkillLoader
# ---------------------------------------------------------------------------


class SkillLoader:
    """Loads SKILL.md files from multiple sources respecting priority order.

    Sources (highest priority first):

    1. Bundled — shipped with JalaAgent.
    2. User-installed — ``~/.jalaagent/skills/``.
    3. Plugin-provided — via extensions.
    4. Extra dirs — user-configured paths.

    Parameters
    ----------
    bundled_dir:
        Path to the directory containing bundled skills, or ``None``.
    user_dir:
        Path to ``~/.jalaagent/skills/``, or ``None``.
    plugin_dirs:
        List of paths to plugin-provided skill directories.
    extra_dirs:
        Additional user-configured skill directories.
    """

    def __init__(
        self,
        bundled_dir: Path | None = None,
        user_dir: Path | None = None,
        plugin_dirs: list[Path] | None = None,
        extra_dirs: list[Path] | None = None,
    ) -> None:
        self._bundled_dir = bundled_dir
        self._user_dir = user_dir
        self._plugin_dirs = plugin_dirs or []
        self._extra_dirs = extra_dirs or []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def load_all(self) -> list[Skill]:
        """Load skills from all configured sources in priority order.

        Returns
        -------
        list[Skill]
            Loaded skills, with bundled first, then user, then plugins.
        """
        skills: list[Skill] = []

        # 1. Bundled (highest priority).
        if self._bundled_dir:
            bundled = await self.load_from_dir(self._bundled_dir, SkillSource.BUNDLED)
            skills.extend(bundled)

        # 2. User-installed.
        if self._user_dir:
            user = await self.load_from_dir(self._user_dir, SkillSource.USER)
            # User skills override bundled skills of the same slug.
            user_slugs = {s.slug for s in user}
            skills = [s for s in skills if s.slug not in user_slugs]
            skills.extend(user)

        # 3. Plugin-provided.
        for plugin_dir in self._plugin_dirs:
            plugin = await self.load_from_dir(plugin_dir, SkillSource.PLUGIN)
            existing_slugs = {s.slug for s in skills}
            skills.extend(s for s in plugin if s.slug not in existing_slugs)

        # 4. Extra dirs.
        for extra_dir in self._extra_dirs:
            extra = await self.load_from_dir(extra_dir, SkillSource.USER)
            existing_slugs = {s.slug for s in skills}
            skills.extend(s for s in extra if s.slug not in existing_slugs)

        return skills

    async def load_from_dir(self, directory: Path, source: SkillSource) -> list[Skill]:
        """Load all SKILL.md files found recursively under *directory*.

        Parameters
        ----------
        directory:
            Root directory to search.
        source:
            The source label to assign to loaded skills.

        Returns
        -------
        list[Skill]
            Skills loaded from this directory (may be empty).
        """
        if not directory.is_dir():
            return []

        skills: list[Skill] = []
        for skill_file in sorted(directory.rglob("SKILL.md")):
            try:
                raw = skill_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("Cannot read %s: %s", skill_file, exc)
                continue

            skill = self._parse_skill(raw, skill_file, source)
            if skill is not None:
                skills.append(skill)

        return skills

    def format_for_prompt(self, skills: list[Skill]) -> str:
        """Format *skills* as an ``<available_skills>`` XML block.

        The result is injected as a **user message** (not system prompt) to
        preserve the Anthropic prompt cache.

        Parameters
        ----------
        skills:
            Skills to include (will be capped at :data:`_MAX_SKILLS`).

        Returns
        -------
        str
            An ``<available_skills>`` XML block, or empty string if no skills.
        """
        if not skills:
            return ""

        # Cap to max skills.
        selected = skills[:_MAX_SKILLS]
        platform = _current_platform()

        # Filter by platform and always-load flag, then sort: always first.
        applicable = [s for s in selected if _is_applicable(s, platform)]
        applicable.sort(key=lambda s: (not s.is_always, s.slug))

        if not applicable:
            return ""

        parts = ["<available_skills>"]
        for skill in applicable:
            body = skill.body
            if len(body) > _MAX_CHARS_PER_SKILL:
                body = body[:_MAX_CHARS_PER_SKILL - 3] + "..."
            emoji = skill.frontmatter.jalaagent_meta.emoji
            parts.append(
                f"<skill name=\"{skill.slug}\">\n"
                f"{emoji} **{skill.frontmatter.description}**\n"
                f"{body}\n"
                f"</skill>"
            )
        parts.append("</available_skills>")

        return "\n".join(parts) + "\n"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_skill(
        raw: str, path: Path, source: SkillSource
    ) -> Skill | None:
        """Parse a single SKILL.md file into a :class:`Skill`, or ``None``."""
        fm_dict, body = _parse_frontmatter(raw)

        # Required fields.
        if "name" not in fm_dict:
            logger.warning("Skill at %s is missing required 'name' field", path)
            return None
        if "description" not in fm_dict:
            logger.warning("Skill at %s is missing required 'description' field", path)
            return None

        try:
            frontmatter = SkillFrontmatter(**fm_dict)
        except Exception as exc:
            logger.warning("Invalid frontmatter in %s: %s", path, exc)
            return None

        content_hash = Skill.compute_hash(raw)

        return Skill(
            frontmatter=frontmatter,
            body=body,
            path=path,
            content_hash=content_hash,
            source=source,
        )


def _is_applicable(skill: Skill, platform: str) -> bool:
    """Return ``True`` if *skill* supports *platform*."""
    return platform in skill.frontmatter.platforms
