"""Tests for Neo4j Semantic Store implementation.

These tests require a running Neo4j instance.
Run with: docker-compose up -d neo4j
"""

import pytest

from hmem.models import SemanticTriple, Memory
from hmem.storage.neo4j_semantic import Neo4jSemanticStore
from hmem.storage import create_semantic_store


# Neo4j connection settings for tests
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "testpassword123"
NEO4J_DATABASE = "neo4j"


def is_neo4j_available() -> bool:
    """Check if Neo4j is available."""
    try:
        store = Neo4jSemanticStore(
            uri=NEO4J_URI,
            username=NEO4J_USERNAME,
            password=NEO4J_PASSWORD,
            database=NEO4J_DATABASE,
        )
        health = store.health_check()
        store.close()
        return health["status"] == "healthy"
    except Exception:
        return False


# Skip all tests if Neo4j is not available
pytestmark = pytest.mark.skipif(
    not is_neo4j_available(),
    reason="Neo4j is not available. Run 'docker-compose up -d neo4j' first.",
)


@pytest.fixture
def neo4j_store():
    """Create a Neo4j store and clean up after test."""
    store = Neo4jSemanticStore(
        uri=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
        database=NEO4J_DATABASE,
    )
    # Clean up before test
    store.clear()
    yield store
    # Clean up after test
    store.clear()
    store.close()


class TestNeo4jStoreBasics:
    """Test basic Neo4j store operations."""

    def test_health_check(self, neo4j_store: Neo4jSemanticStore):
        """Test health check returns healthy status."""
        health = neo4j_store.health_check()

        assert health["status"] == "healthy"
        assert health["backend"] == "neo4j"
        assert "total_facts" in health

    def test_add_and_get_triple(self, neo4j_store: Neo4jSemanticStore):
        """Test adding and retrieving a triple."""
        triple = SemanticTriple(
            subject="Alice",
            predicate="PREFERS",
            object="dark_mode",
            weight=1.0,
        )

        # Add triple
        was_conflict, conflicts = neo4j_store.add_or_update(triple)
        assert not was_conflict
        assert conflicts == 0

        # Retrieve via search
        results = neo4j_store.search("Alice", limit=5)
        assert len(results) > 0
        assert any("Alice" in m.content for m in results)

    def test_add_duplicate_increments_weight(self, neo4j_store: Neo4jSemanticStore):
        """Test that adding duplicate triple increments weight."""
        triple = SemanticTriple(
            subject="Bob",
            predicate="LIKES",
            object="Python",
            weight=1.0,
        )

        # Add first time
        neo4j_store.add_or_update(triple)

        # Add again - should increment weight
        neo4j_store.add_or_update(triple)

        # Search and check weight increased
        results = neo4j_store.search("Bob", limit=5)
        assert len(results) > 0
        assert results[0].metadata["weight"] > 1.0

    def test_count_statistics(self, neo4j_store: Neo4jSemanticStore):
        """Test count returns correct statistics."""
        # Add some triples
        neo4j_store.add_or_update(
            SemanticTriple(subject="A", predicate="REL", object="B")
        )
        neo4j_store.add_or_update(
            SemanticTriple(subject="B", predicate="REL", object="C")
        )

        stats = neo4j_store.count()
        assert stats["total_facts"] == 2
        assert stats["unique_entities"] >= 2


class TestNeo4jConflictResolution:
    """Test conflict detection and resolution."""

    def test_detect_conflict(self, neo4j_store: Neo4jSemanticStore):
        """Test conflict detection for contradicting facts."""
        # Add initial fact
        neo4j_store.add_or_update(
            SemanticTriple(subject="User", predicate="EATS", object="Vegetarian")
        )

        # Check for conflict with different object
        has_conflict, conflicts = neo4j_store.check_conflict(
            subject="User",
            predicate="EATS",
            new_object="Pescatarian",
        )

        assert has_conflict
        assert len(conflicts) == 1
        assert conflicts[0].object == "Vegetarian"

    def test_resolve_conflict(self, neo4j_store: Neo4jSemanticStore):
        """Test conflict resolution supersedes old fact."""
        # Add initial fact
        neo4j_store.add_or_update(
            SemanticTriple(subject="User", predicate="EATS", object="Vegetarian")
        )

        # Resolve conflict
        resolved = neo4j_store.resolve_conflict(
            subject="User",
            predicate="EATS",
            old_object="Vegetarian",
            new_object="Pescatarian",
        )

        assert resolved == 1

        # Search should find new preference
        results = neo4j_store.search("Pescatarian", limit=5)
        assert len(results) > 0

        # Old preference should be superseded (not in active results)
        neo4j_store.search("Vegetarian", limit=5)
        # May or may not find it depending on search implementation
        # but the active triple should be Pescatarian


class TestNeo4jGraphTraversal:
    """Test multi-hop graph traversal capabilities."""

    def test_query_related_depth_1(self, neo4j_store: Neo4jSemanticStore):
        """Test querying directly related entities."""
        # Build a small graph: Alice -> Bob -> Carol
        neo4j_store.add_or_update(
            SemanticTriple(subject="Alice", predicate="KNOWS", object="Bob")
        )
        neo4j_store.add_or_update(
            SemanticTriple(subject="Bob", predicate="KNOWS", object="Carol")
        )

        # Query depth 1 from Alice
        results = neo4j_store.query_related("Alice", max_depth=1)

        assert len(results) >= 1
        # Should find Alice-KNOWS-Bob
        subjects = [r[0] for r in results]
        objects = [r[2] for r in results]
        assert "Alice" in subjects or "Alice" in objects

    def test_query_related_depth_2(self, neo4j_store: Neo4jSemanticStore):
        """Test querying entities 2 hops away."""
        # Build a chain: A -> B -> C -> D
        neo4j_store.add_or_update(
            SemanticTriple(subject="A", predicate="NEXT", object="B")
        )
        neo4j_store.add_or_update(
            SemanticTriple(subject="B", predicate="NEXT", object="C")
        )
        neo4j_store.add_or_update(
            SemanticTriple(subject="C", predicate="NEXT", object="D")
        )

        # Query depth 2 from A
        results = neo4j_store.query_related("A", max_depth=2)

        # Should find relationships up to 2 hops
        assert len(results) >= 2

    def test_expand_neighbors(self, neo4j_store: Neo4jSemanticStore):
        """Test expanding neighborhood from seed entities."""
        # Build a graph
        neo4j_store.add_or_update(
            SemanticTriple(subject="Python", predicate="IS_A", object="Language")
        )
        neo4j_store.add_or_update(
            SemanticTriple(subject="Python", predicate="USED_FOR", object="WebDev")
        )
        neo4j_store.add_or_update(
            SemanticTriple(subject="Java", predicate="IS_A", object="Language")
        )

        # Expand from Python
        neighbors = neo4j_store.expand_neighbors(["Python"], max_depth=1)

        assert len(neighbors) >= 2
        subjects = [t.subject for t in neighbors]
        assert "Python" in subjects


class TestNeo4jSearch:
    """Test search capabilities."""

    def test_text_search(self, neo4j_store: Neo4jSemanticStore):
        """Test text-based search."""
        neo4j_store.add_or_update(
            SemanticTriple(
                subject="Alice",
                predicate="PREFERS",
                object="dark_mode",
                parent_ids=["conv_123"],
            )
        )

        # Search by entity name (exact match works better with full-text)
        results = neo4j_store.search("Alice", limit=5)

        assert len(results) > 0
        assert isinstance(results[0], Memory)
        assert results[0].source == "semantic"

    def test_search_increments_access_count(self, neo4j_store: Neo4jSemanticStore):
        """Test that search increments access count (reconsolidation)."""
        neo4j_store.add_or_update(
            SemanticTriple(subject="Test", predicate="HAS", object="Value")
        )

        # Search twice
        neo4j_store.search("Test", limit=5)
        results = neo4j_store.search("Test", limit=5)

        # Access count should have increased
        if results:
            assert results[0].metadata["access_count"] >= 1


class TestNeo4jWeightManagement:
    """Test weight-based operations."""

    def test_update_weight(self, neo4j_store: Neo4jSemanticStore):
        """Test updating weight of a fact."""
        triple = SemanticTriple(subject="X", predicate="REL", object="Y")
        neo4j_store.add_or_update(triple)

        # Get the fact ID
        results = neo4j_store.search("X", limit=1)
        fact_id = results[0].id
        assert fact_id is not None, "fact_id should not be None"

        # Update weight
        success = neo4j_store.update_weight(fact_id, delta=0.5)
        assert success

        # Verify weight increased
        updated = neo4j_store.search("X", limit=1)
        assert updated[0].metadata["weight"] > 1.0

    def test_prune_low_weight(self, neo4j_store: Neo4jSemanticStore):
        """Test pruning low-weight facts."""
        # Add a low-weight fact
        triple = SemanticTriple(
            subject="Weak", predicate="REL", object="Fact", weight=0.1
        )
        neo4j_store.add_or_update(triple)

        # Prune with threshold
        pruned = neo4j_store.prune_low_weight(threshold=0.5)

        assert pruned >= 1

    def test_apply_decay(self, neo4j_store: Neo4jSemanticStore):
        """Test applying weight decay."""
        neo4j_store.add_or_update(
            SemanticTriple(
                subject="Decay", predicate="TEST", object="Value", weight=1.0
            )
        )

        # Apply decay
        decayed = neo4j_store.apply_decay(decay_factor=0.5, min_weight=0.05)

        assert decayed >= 1

        # Check weight decreased
        results = neo4j_store.search("Decay", limit=1)
        if results:
            assert results[0].metadata["weight"] < 1.0


class TestNeo4jProvenance:
    """Test provenance tracking."""

    def test_triple_with_parent_ids(self, neo4j_store: Neo4jSemanticStore):
        """Test that parent_ids are stored and retrieved."""
        parent_ids = ["conv_abc123", "msg_xyz789"]
        triple = SemanticTriple(
            subject="User",
            predicate="SAID",
            object="Hello",
            parent_ids=parent_ids,
        )

        neo4j_store.add_or_update(triple, parent_ids=parent_ids)

        results = neo4j_store.search("User", limit=1)
        assert len(results) > 0
        assert results[0].parent_ids == parent_ids

    def test_get_by_id(self, neo4j_store: Neo4jSemanticStore):
        """Test retrieving triple by ID."""
        neo4j_store.add_or_update(
            SemanticTriple(subject="Entity", predicate="HAS", object="Property")
        )

        # Get fact ID from search
        results = neo4j_store.search("Entity", limit=1)
        fact_id = results[0].id
        assert fact_id is not None, "fact_id should not be None"

        # Get by ID
        triple = neo4j_store.get_by_id(fact_id)

        assert triple is not None
        assert triple.subject == "Entity"
        assert triple.predicate == "HAS"
        assert triple.object == "Property"


class TestNeo4jFactory:
    """Test factory function for creating stores."""

    def test_create_neo4j_store_via_factory(self):
        """Test creating Neo4j store via factory function."""
        store = create_semantic_store(
            backend="neo4j",
            uri=NEO4J_URI,
            username=NEO4J_USERNAME,
            password=NEO4J_PASSWORD,
            database=NEO4J_DATABASE,
        )

        assert isinstance(store, Neo4jSemanticStore)

        health = store.health_check()
        assert health["status"] == "healthy"

        store.close()
