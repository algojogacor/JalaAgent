"""Layer 3 — Dreaming pipeline: Light Sleep → REM → Deep Sleep consolidation.

Runs daily (default: 3 AM) as a cron-driven background task.  Reads recent
session transcripts, extracts patterns via an LLM, deduplicates, and promotes
high-confidence facts to ``MEMORY.md``.

Phases
------
1. **Light Sleep** — scan recent ``.jsonl`` session files for new episodes
   since the last dreaming run.
2. **REM Sleep** — send episode batches to an LLM for pattern extraction.
   Deduplicate candidate facts via SHA1 content hash.
3. **Deep Sleep** — filter facts by confidence ≥ 0.7; submit to the approval
   callback (unless YOLO mode); promote approved facts to ``MEMORY.md``.
4. **Diary** — write a human-readable ``dream-diary.md`` entry summarising
   the run.

Architecture
------------
The pipeline takes two injected dependencies so it can remain pure and not
depend on ``agent-core``:

* ``DreamingLLMAdapter`` — protocol for calling an LLM.
* ``ApprovalCallback`` — protocol for requesting user approval.

Both are simple async callables / protocols, easily mocked in tests.
"""

import asyncio
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from typing import Protocol

from memory_core.file_layer import FileLayer
from memory_core.models import DreamReport, Episode, Fact, MemoryConfig
from memory_core.vector_layer import VectorLayer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols (injected dependencies)
# ---------------------------------------------------------------------------


class DreamingLLMAdapter(Protocol):
    """Protocol for an LLM that the dreaming pipeline can call.

    Kept minimal so the memory-core package does not depend on agent-core.
    """

    async def generate(self, prompt: str) -> str:
        """Send *prompt* to the LLM and return the generated text."""
        ...


class ApprovalCallback(Protocol):
    """Protocol for requesting user approval of fact promotions.

    In YOLO mode the implementation auto-approves everything.
    In NORMAL/PARANOID mode it presents facts to the user and returns the
    IDs that were accepted.
    """

    async def request_approval(self, facts: list[Fact]) -> list[str]:
        """Ask the user to approve *facts* for promotion.

        Returns
        -------
        list[str]
            The ``id`` values of the facts that were approved (as strings).
        """
        ...


# ---------------------------------------------------------------------------
# Dreaming Pipeline
# ---------------------------------------------------------------------------

# JSON schema we ask the LLM to conform to when extracting facts.
_EXTRACTION_SYSTEM_PROMPT = """\
You are a memory consolidation agent.  Your job is to read session transcripts
and extract **atomic, high-confidence facts** about the user.

Rules:
1. One fact per line.  Each fact must be a single, self-contained sentence.
2. Facts must be about the **user** — their preferences, projects, tools,
   habits, and knowledge.  Do NOT extract facts about the assistant.
3. Assign a `confidence` between 0.0 (guess) and 1.0 (certain).
4. Output ONLY valid JSON — an array of objects with keys:
   "content" (string), "confidence" (float)

Example output:
[
  {"content": "The user develops on Windows 11 with WSL2.", "confidence": 0.95},
  {"content": "The user prefers Python 3.12+ with type hints.", "confidence": 0.88}
]

Do not include any text outside the JSON array."""


def _make_extraction_prompt(episodes: list[Episode]) -> str:
    """Build the LLM prompt for extracting facts from a batch of episodes."""
    transcript = "\n".join(
        f"[{ep.role}] {ep.content}" for ep in episodes
    )
    return (
        f"Extract facts from this session transcript:\n\n"
        f"---TRANSCRIPT---\n{transcript}\n---END---\n\n"
        f"Return ONLY a JSON array of fact objects."
    )


def _sha1(text: str) -> str:
    """SHA-1 hex digest (used for dedup as specified in PRD)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _format_fact_markdown(fact: Fact) -> str:
    """Render a fact as a Markdown list item for MEMORY.md."""
    ts = fact.promoted_at
    ts_str = ts.strftime("%Y-%m-%d %H:%M UTC") if ts else "unknown"
    return (
        f"- [{ts_str}] [{fact.confidence:.2f}] "
        f"{fact.content}  "
        f"<!-- id:{fact.id} count:{fact.promotion_count} -->"
    )


class DreamingPipeline:
    """Cron-based multi-phase memory consolidation from session transcripts.

    Parameters
    ----------
    config:
        Memory subsystem configuration.
    file_layer:
        File-layer instance for reading sessions and writing memory.
    vector_layer:
        Vector-layer instance for upserting extracted facts.
    llm:
        An :class:`DreamingLLMAdapter` for calling an LLM during REM sleep.
    approval_callback:
        An :class:`ApprovalCallback` for requesting user approval of
        promoted facts.  In YOLO mode this should auto-approve everything.
    """

    def __init__(
        self,
        config: MemoryConfig,
        file_layer: FileLayer,
        vector_layer: VectorLayer,
        llm: DreamingLLMAdapter,
        approval_callback: ApprovalCallback,
    ) -> None:
        self._config = config
        self._file_layer = file_layer
        self._vector_layer = vector_layer
        self._llm = llm
        self._approval = approval_callback

        # Track the last dreaming run to know what's new.
        self._last_run: datetime | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> DreamReport:
        """Execute the full dreaming pipeline and return a report.

        Phases are run sequentially: light → rem → deep → promote → diary.
        """
        started = time.monotonic()

        # Light Sleep — find what's new since last run.
        since = self._last_run or datetime.now(UTC).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        episodes = await self._light_sleep(since)
        signals_count = len(episodes)
        logger.info("Light sleep: %d new episodes found", signals_count)

        # REM Sleep — extract patterns via LLM.
        rem_started = time.monotonic()
        facts = await self._rem_sleep(episodes)
        rem_duration = time.monotonic() - rem_started
        patterns_count = len(facts)
        logger.info(
            "REM sleep: %d patterns extracted in %.1fs",
            patterns_count,
            rem_duration,
        )

        # Deep Sleep — filter by confidence.
        candidates = await self._deep_sleep(facts)
        logger.info("Deep sleep: %d candidates for promotion", len(candidates))

        # Promote (with approval).
        promoted_count = await self._promote_facts(candidates)

        # Build report.
        duration = time.monotonic() - started
        diary = self._build_diary_entry(
            signals_count, patterns_count, candidates, promoted_count
        )
        report = DreamReport(
            light_sleep_signals=signals_count,
            rem_patterns=patterns_count,
            deep_sleep_promotions=promoted_count,
            diary_entry=diary,
            duration_seconds=duration,
        )

        # Write diary.
        await self._write_diary(report)

        # Update last run timestamp.
        self._last_run = datetime.now(UTC)

        logger.info(
            "Dreaming complete: %d signals, %d patterns, %d promoted in %.1fs",
            signals_count,
            patterns_count,
            promoted_count,
            duration,
        )
        return report

    # ------------------------------------------------------------------
    # Phase 1 — Light Sleep
    # ------------------------------------------------------------------

    async def _light_sleep(self, since: datetime) -> list[Episode]:
        """Scan session JSONL files for episodes created since *since*.

        Parameters
        ----------
        since:
            Only return episodes whose ``timestamp`` is >= this datetime.

        Returns
        -------
        list[Episode]
            Episodes found across all session files (chronological order).
        """
        session_ids = await self._file_layer.list_sessions()
        if not session_ids:
            return []

        all_episodes: list[Episode] = []
        for sid in session_ids:
            episodes = await self._file_layer.read_session(sid)
            for ep in episodes:
                if ep.timestamp >= since:
                    all_episodes.append(ep)

        # Sort chronologically.
        all_episodes.sort(key=lambda e: e.timestamp)
        return all_episodes

    # ------------------------------------------------------------------
    # Phase 2 — REM Sleep
    # ------------------------------------------------------------------

    async def _rem_sleep(self, episodes: list[Episode]) -> list[Fact]:
        """Extract facts from episodes via LLM, deduplicate via SHA1.

        Parameters
        ----------
        episodes:
            Episodes gathered during Light Sleep.

        Returns
        -------
        list[Fact]
            Extracted facts with ``source_episode_ids`` populated.
        """
        if not episodes:
            return []

        # Build extraction prompt and call LLM.
        prompt = _make_extraction_prompt(episodes)
        try:
            raw = await self._llm.generate(prompt)
        except Exception as exc:
            logger.error("LLM call failed during REM sleep: %s", exc)
            return []

        # Parse LLM output.
        facts = self._parse_facts(raw)
        if not facts:
            return []

        # Attach source episode IDs to each fact.
        episode_ids = [str(ep.id) for ep in episodes]
        for fact in facts:
            fact.source_episode_ids = episode_ids

        # Deduplicate by SHA1 content hash.
        return self._deduplicate(facts)

    @staticmethod
    def _parse_facts(raw: str) -> list[Fact]:
        """Parse the LLM's JSON output into :class:`Fact` objects.

        Tolerates common LLM formatting mistakes (markdown fences, trailing
        commas, leading/trailing text).
        """
        # Strip markdown fences if present.
        text = raw.strip()
        if text.startswith("```"):
            # Remove opening fence line.
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            # Remove closing fence line.
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)

        # Find the JSON array bounds.
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1:
            logger.warning("REM sleep: no JSON array found in LLM output")
            return []

        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            logger.warning("REM sleep: JSON parse error: %s", exc)
            return []

        if not isinstance(data, list):
            return []

        facts: list[Fact] = []
        for item in data:
            try:
                content = item.get("content", "").strip()
                confidence = float(item.get("confidence", 0.5))
                if content:
                    # Clamp confidence to [0, 1].
                    confidence = max(0.0, min(1.0, confidence))
                    facts.append(Fact(content=content, confidence=confidence))
            except (TypeError, ValueError):
                continue

        return facts

    @staticmethod
    def _deduplicate(facts: list[Fact]) -> list[Fact]:
        """Remove duplicate facts by SHA1 content hash.

        When two facts have the same hash, keep the one with higher confidence.
        """
        seen: dict[str, Fact] = {}
        for fact in facts:
            key = _sha1(fact.content)
            if key in seen:
                # Merge source episode IDs.
                existing = seen[key]
                existing.source_episode_ids = list(
                    set(existing.source_episode_ids + fact.source_episode_ids)
                )
                # Keep the higher confidence.
                if fact.confidence > existing.confidence:
                    existing.confidence = fact.confidence
            else:
                seen[key] = fact
        return list(seen.values())

    # ------------------------------------------------------------------
    # Phase 3 — Deep Sleep
    # ------------------------------------------------------------------

    async def _deep_sleep(self, facts: list[Fact]) -> list[Fact]:
        """Filter facts by confidence threshold (0.7) for promotion.

        Parameters
        ----------
        facts:
            Facts extracted during REM sleep.

        Returns
        -------
        list[Fact]
            Facts with confidence >= 0.7, sorted by confidence descending.
        """
        threshold = 0.7
        candidates = [f for f in facts if f.confidence >= threshold]
        candidates.sort(key=lambda f: f.confidence, reverse=True)
        return candidates

    # ------------------------------------------------------------------
    # Promotion
    # ------------------------------------------------------------------

    async def _promote_facts(self, facts: list[Fact]) -> int:
        """Request approval and promote approved facts to ``MEMORY.md``.

        Parameters
        ----------
        facts:
            Candidate facts from Deep Sleep (already filtered by confidence).

        Returns
        -------
        int
            Number of facts actually promoted.
        """
        if not facts:
            return 0

        # Request approval.
        try:
            approved_ids = await self._approval.request_approval(facts)
        except Exception as exc:
            logger.error("Approval callback failed: %s", exc)
            return 0

        approved_set = set(approved_ids)

        # Promote each approved fact.
        now = datetime.now(UTC)
        promoted_count = 0

        for fact in facts:
            if str(fact.id) not in approved_set:
                continue

            # Update promotion metadata.
            fact.promoted_at = now
            fact.promotion_count += 1

            # Append to MEMORY.md.
            current = await self._file_layer.read_memory()
            new_line = _format_fact_markdown(fact)
            if current and not current.endswith("\n"):
                current += "\n"
            updated = current + new_line + "\n"
            await self._file_layer.write_memory(updated)

            # Upsert into vector layer.
            await self._vector_layer.upsert_fact(fact)

            promoted_count += 1

        return promoted_count

    # ------------------------------------------------------------------
    # Diary
    # ------------------------------------------------------------------

    @staticmethod
    def _build_diary_entry(
        signals: int,
        patterns: int,
        candidates: list[Fact],
        promoted: int,
    ) -> str:
        """Build a human-readable diary narrative."""
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"## Dream Report — {now}",
            "",
            f"- **Light Sleep:** {signals} new episodes scanned",
            f"- **REM Sleep:** {patterns} patterns identified",
            f"- **Deep Sleep:** {len(candidates)} candidates above threshold",
            f"- **Promoted:** {promoted} facts written to MEMORY.md",
        ]

        if promoted and candidates:
            promoted_facts = [f for f in candidates if f.promotion_count > 0]
            if promoted_facts:
                lines.append("")
                lines.append("### Promoted Facts")
                for fact in promoted_facts:
                    lines.append(f"- [{fact.confidence:.2f}] {fact.content}")

        lines.append("")
        return "\n".join(lines)

    async def _write_diary(self, report: DreamReport) -> None:
        """Append the dream report to ``dream-diary.md``."""
        diary_path = self._config.memory_dir / "dream-diary.md"
        # Read existing content.
        try:
            existing = await self._file_layer._read_file(diary_path)
        except AttributeError:
            # Fallback: direct read.
            def _read() -> str:
                try:
                    return diary_path.read_text(encoding="utf-8")
                except FileNotFoundError:
                    return ""

            existing = await asyncio.to_thread(_read)

        # Prepend new entry (most recent first).
        new_entry = report.diary_entry
        content = new_entry + "\n" + existing if existing else new_entry

        # Write atomically.
        await self._file_layer._write_atomic(diary_path, content)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def last_run(self) -> datetime | None:
        """The timestamp of the last completed :meth:`run` call."""
        return self._last_run
