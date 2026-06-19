"""Tests for GBrain-inspired knowledge graph."""

import tempfile
from pathlib import Path

import pytest
from memory_core.knowledge_graph import KnowledgeGraph, sync_brain_repo


@pytest.fixture
def kg_path() -> Path:
    with tempfile.TemporaryDirectory() as td:
        yield Path(td) / "graph.db"


@pytest.mark.asyncio
class TestKnowledgeGraph:
    async def test_initialize(self, kg_path: Path) -> None:
        kg = KnowledgeGraph(kg_path)
        await kg.initialize()
        stats = await kg.get_stats()
        assert stats["entities"] == 0
        await kg.close()

    async def test_ingest_person_page(self, kg_path: Path) -> None:
        kg = KnowledgeGraph(kg_path)
        await kg.initialize()
        page_id = await kg.ingest_page(
            Path("garry-tan.md"),
            '"Garry Tan" works at Y Combinator as CEO. He invested in OpenAI and founded Posterous.',
            "person",
        )
        assert len(page_id) == 16
        stats = await kg.get_stats()
        assert stats["pages"] >= 1
        assert stats["entities"] >= 1
        await kg.close()

    async def test_search_entities(self, kg_path: Path) -> None:
        kg = KnowledgeGraph(kg_path)
        await kg.initialize()
        await kg.ingest_page(Path("test.md"), '"Jane Smith" uses Python and works at Google.', "person")
        results = await kg.search_entities("Jane")
        assert len(results) >= 1
        await kg.close()

    async def test_graph_query(self, kg_path: Path) -> None:
        kg = KnowledgeGraph(kg_path)
        await kg.initialize()
        await kg.ingest_page(Path("test.md"), '"Alice" invested in "Google Inc". "Bob" works at "Google Inc" too.', "person")
        results = await kg.search_entities("Google")
        assert len(results) >= 1
        graph = await kg.graph_query("Google", max_hops=1)
        assert isinstance(graph, list)
        await kg.close()


@pytest.mark.asyncio
class TestSyncBrainRepo:
    async def test_sync_directory(self, kg_path: Path) -> None:
        kg = KnowledgeGraph(kg_path)
        await kg.initialize()
        with tempfile.TemporaryDirectory() as repo:
            repo_dir = Path(repo)
            (repo_dir / "page1.md").write_text("# Page 1\nContent about AI.", encoding="utf-8")
            (repo_dir / "page2.md").write_text("# Page 2\nMore content.", encoding="utf-8")
            stats = await sync_brain_repo(repo_dir, kg)
            assert stats["synced"] == 2
            kg_stats = await kg.get_stats()
            assert kg_stats["pages"] == 2
        await kg.close()


def test_entity_extraction() -> None:
    content = '"John Doe" works at Google Inc. "Jane Smith" invested in OpenAI.'
    entities = KnowledgeGraph._extract_entities(content)
    assert len(entities) >= 2
    names = {e["name"] for e in entities}
    assert "John Doe" in names
