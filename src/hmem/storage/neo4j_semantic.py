"""Neo4j-based semantic memory store implementation.

Implements the SemanticStoreProtocol using Neo4j graph database for:
- Native multi-hop graph traversal via Cypher
- Full-text search indexing
- Graph algorithms (PageRank, community detection)
- Better semantic relationship queries

Graph Model:
    Nodes:
        - (:Entity {name: str, created_at: datetime})

    Relationships:
        - [:RELATION {fact_id, predicate, weight, version, access_count,
                      is_superseded, superseded_by, parent_ids, derivation_type,
                      created_at, updated_at}]

    Indexes:
        - Full-text index on Entity.name
        - Composite index on RELATION.predicate
        - Index on RELATION.fact_id
"""

from datetime import datetime, timezone
from typing import Any, LiteralString, cast
import json
import uuid

import structlog
from neo4j import GraphDatabase, Driver
from neo4j.exceptions import Neo4jError

from hmem.models import Memory, SemanticTriple
from hmem.exceptions import ConsolidationError
from hmem.storage.semantic import BaseSemanticStore

logger = structlog.get_logger()


class Neo4jSemanticStore(BaseSemanticStore):
    """Neo4j-based semantic graph store with native graph traversal.

    Advantages over SQLite:
    - Native multi-hop queries: `MATCH path = ()-[*1..3]->()` vs Python BFS
    - Full-text search: Built-in index vs SQL LIKE
    - Graph algorithms: PageRank, community detection for memory clustering
    - Better performance for relationship-heavy queries

    Features:
    - Triple storage as graph relationships
    - Weight-based importance tracking
    - Optimistic locking for conflict detection
    - Provenance tracking (parent_ids, derivation_type)
    - Multi-hop relationship traversal
    - Active forgetting (prune low-weight facts)
    - Reconsolidation (update weights on access)
    """

    MAX_QUERY_DEPTH = 3

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        username: str = "neo4j",
        password: str = "password",
        database: str = "neo4j",
    ):
        """Initialize Neo4j semantic store.

        Args:
            uri: Neo4j connection URI (bolt:// or neo4j://)
            username: Neo4j username
            password: Neo4j password
            database: Database name
        """
        self.uri = uri
        self.username = username
        self.password = password
        self.database = database
        self._driver: Driver | None = None
        self._schema_initialized = False

    @property
    def driver(self) -> Driver:
        """Lazy initialization of Neo4j driver."""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.uri, auth=(self.username, self.password)
            )
        if not self._schema_initialized:
            self._ensure_schema()
        return self._driver

    def close(self) -> None:
        """Close the Neo4j driver connection."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def _ensure_schema(self) -> None:
        """Ensure schema is initialized (called once)."""
        if self._schema_initialized:
            return
        self._schema_initialized = True
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize database schema with constraints and indexes."""
        with self.driver.session(database=self.database) as session:
            # Create unique constraint on Entity.name
            session.run(
                """
                CREATE CONSTRAINT entity_name_unique IF NOT EXISTS
                FOR (e:Entity) REQUIRE e.name IS UNIQUE
                """
            )

            # Create index on relationship fact_id
            session.run(
                """
                CREATE INDEX rel_fact_id IF NOT EXISTS
                FOR ()-[r:RELATION]-() ON (r.fact_id)
                """
            )

            # Create full-text index for entity search
            try:
                session.run(
                    """
                    CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS
                    FOR (e:Entity) ON EACH [e.name]
                    """
                )
            except Neo4jError:
                # Full-text index may already exist
                pass

            logger.info("neo4j_schema_initialized", database=self.database)

    def add_or_update(
        self,
        triple: SemanticTriple,
        parent_ids: list[str] | None = None,
    ) -> tuple[bool, int]:
        """Add a new triple or update existing one with optimistic locking.

        Uses MERGE to create or update the relationship.
        Implements optimistic locking via version field.

        Args:
            triple: Semantic triple to add/update
            parent_ids: Source memory IDs for provenance

        Returns:
            Tuple of (was_conflict, conflicts_resolved)

        Raises:
            ConsolidationError: If optimistic lock conflict after retries
        """
        parent_ids = parent_ids or triple.parent_ids
        fact_id = f"fact_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        with self.driver.session(database=self.database) as session:
            # Check for existing relationship
            result = session.run(
                """
                MATCH (s:Entity {name: $subject})-[r:RELATION {predicate: $predicate}]->(o:Entity {name: $object})
                WHERE r.is_superseded = false
                RETURN r.fact_id AS fact_id, r.version AS version, r.weight AS weight
                """,
                subject=triple.subject,
                predicate=triple.predicate,
                object=triple.object,
            )
            existing = result.single()

            if existing:
                # Update with optimistic locking
                old_version = existing["version"]
                update_result = session.run(
                    """
                    MATCH (s:Entity {name: $subject})-[r:RELATION {predicate: $predicate}]->(o:Entity {name: $object})
                    WHERE r.is_superseded = false AND r.version = $old_version
                    SET r.weight = r.weight + 0.1,
                        r.version = r.version + 1,
                        r.access_count = r.access_count + 1,
                        r.updated_at = $now
                    RETURN r.version AS new_version
                    """,
                    subject=triple.subject,
                    predicate=triple.predicate,
                    object=triple.object,
                    old_version=old_version,
                    now=now,
                )

                if update_result.single() is None:
                    raise ConsolidationError(
                        f"Optimistic lock conflict for triple: "
                        f"{triple.subject}-{triple.predicate}-{triple.object}"
                    )

                logger.debug(
                    "semantic_triple_updated",
                    subject=triple.subject,
                    predicate=triple.predicate,
                    new_version=old_version + 1,
                )
                return False, 0
            else:
                # Create new triple
                session.run(
                    """
                    MERGE (s:Entity {name: $subject})
                    ON CREATE SET s.created_at = $now
                    MERGE (o:Entity {name: $object})
                    ON CREATE SET o.created_at = $now
                    CREATE (s)-[r:RELATION {
                        fact_id: $fact_id,
                        predicate: $predicate,
                        weight: $weight,
                        version: 1,
                        access_count: 0,
                        is_superseded: false,
                        superseded_by: null,
                        parent_ids: $parent_ids,
                        derivation_type: $derivation_type,
                        created_at: $now,
                        updated_at: $now
                    }]->(o)
                    """,
                    subject=triple.subject,
                    object=triple.object,
                    fact_id=fact_id,
                    predicate=triple.predicate,
                    weight=triple.weight,
                    parent_ids=json.dumps(parent_ids),
                    derivation_type=triple.derivation_type or "extraction",
                    now=now,
                )

                logger.debug(
                    "semantic_triple_added",
                    fact_id=fact_id,
                    subject=triple.subject,
                    predicate=triple.predicate,
                )
                return False, 0

    def update_weight(self, fact_id: str, delta: float = 0.1) -> bool:
        """Update weight of a fact (reconsolidation mechanism).

        Args:
            fact_id: Unique fact identifier
            delta: Weight change (positive = strengthen, negative = weaken)

        Returns:
            True if updated, False if not found
        """
        now = datetime.now(timezone.utc).isoformat()

        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH ()-[r:RELATION {fact_id: $fact_id}]->()
                SET r.weight = r.weight + $delta,
                    r.access_count = r.access_count + 1,
                    r.updated_at = $now
                RETURN r.fact_id AS fact_id
                """,
                fact_id=fact_id,
                delta=delta,
                now=now,
            )
            return result.single() is not None

    def increment_access(self, fact_id: str) -> bool:
        """Increment access count (for reconsolidation on recall).

        Args:
            fact_id: Unique fact identifier

        Returns:
            True if updated, False if not found
        """
        return self.update_weight(fact_id, delta=0.05)

    def check_conflict(
        self, subject: str, predicate: str, new_object: str
    ) -> tuple[bool, list[SemanticTriple]]:
        """Check if a new triple conflicts with existing ones.

        A conflict exists when same (subject, predicate) has different object.

        Args:
            subject: Subject of the triple
            predicate: Predicate (relationship)
            new_object: New object value

        Returns:
            Tuple of (has_conflict, list of conflicting triples)
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (s:Entity {name: $subject})-[r:RELATION {predicate: $predicate}]->(o:Entity)
                WHERE o.name <> $new_object AND r.is_superseded = false
                RETURN r.fact_id AS fact_id,
                       s.name AS subject,
                       r.predicate AS predicate,
                       o.name AS object,
                       r.weight AS weight,
                       r.version AS version,
                       r.parent_ids AS parent_ids
                """,
                subject=subject,
                predicate=predicate,
                new_object=new_object,
            )

            conflicts = []
            for record in result:
                parent_ids = (
                    json.loads(record["parent_ids"]) if record["parent_ids"] else []
                )
                conflicts.append(
                    SemanticTriple(
                        id=record["fact_id"],
                        subject=record["subject"],
                        predicate=record["predicate"],
                        object=record["object"],
                        weight=record["weight"],
                        version=record["version"],
                        parent_ids=parent_ids,
                    )
                )

            return len(conflicts) > 0, conflicts

    def resolve_conflict(
        self,
        subject: str,
        predicate: str,
        old_object: str,
        new_object: str,
        new_parent_ids: list[str] | None = None,
    ) -> int:
        """Resolve conflict by superseding old triple and adding new one.

        Args:
            subject: Subject of the triple
            predicate: Predicate
            old_object: Old object to supersede
            new_object: New object value
            new_parent_ids: Parent IDs for the new triple

        Returns:
            Number of conflicts resolved
        """
        new_fact_id = f"fact_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        with self.driver.session(database=self.database) as session:
            # Mark old triple as superseded and create new one
            result = session.run(
                """
                MATCH (s:Entity {name: $subject})-[old:RELATION {predicate: $predicate}]->(old_o:Entity {name: $old_object})
                WHERE old.is_superseded = false
                SET old.is_superseded = true,
                    old.superseded_by = $new_fact_id,
                    old.weight = old.weight * 0.5,
                    old.updated_at = $now
                WITH s
                MERGE (new_o:Entity {name: $new_object})
                ON CREATE SET new_o.created_at = $now
                CREATE (s)-[r:RELATION {
                    fact_id: $new_fact_id,
                    predicate: $predicate,
                    weight: 1.0,
                    version: 1,
                    access_count: 0,
                    is_superseded: false,
                    superseded_by: null,
                    parent_ids: $parent_ids,
                    derivation_type: 'supersession',
                    created_at: $now,
                    updated_at: $now
                }]->(new_o)
                RETURN count(*) AS resolved
                """,
                subject=subject,
                predicate=predicate,
                old_object=old_object,
                new_object=new_object,
                new_fact_id=new_fact_id,
                parent_ids=json.dumps(new_parent_ids or []),
                now=now,
            )

            record = result.single()
            conflicts_resolved = record["resolved"] if record else 0

            logger.info(
                "semantic_conflict_resolved",
                subject=subject,
                predicate=predicate,
                old_object=old_object,
                new_object=new_object,
            )

            return conflicts_resolved

    def query_related(
        self, entity: str, max_depth: int = 2
    ) -> list[tuple[str, str, str, float]]:
        """Query related entities up to max_depth hops using native Cypher.

        Native graph traversal is much more efficient than Python BFS.

        Args:
            entity: Starting entity
            max_depth: Maximum traversal depth (1-3)

        Returns:
            List of (subject, predicate, object, weight) tuples
        """
        max_depth = min(max_depth, self.MAX_QUERY_DEPTH)

        # Build query with literal depth (Cypher doesn't support parameterized path length)
        query = f"""
            MATCH (start:Entity {{name: $entity}})-[r:RELATION*1..{max_depth}]-(end:Entity)
            WHERE ALL(rel IN r WHERE rel.is_superseded = false)
            UNWIND r AS rel
            WITH startNode(rel) AS s, rel, endNode(rel) AS o
            RETURN DISTINCT s.name AS subject,
                   rel.predicate AS predicate,
                   o.name AS object,
                   rel.weight AS weight
        """

        with self.driver.session(database=self.database) as session:
            result = session.run(cast(LiteralString, query), entity=entity)

            return [
                (
                    record["subject"],
                    record["predicate"],
                    record["object"],
                    record["weight"],
                )
                for record in result
            ]

    def expand_neighbors(
        self,
        entities: list[str],
        max_depth: int = 1,
        limit_per_entity: int = 5,
    ) -> list[SemanticTriple]:
        """Expand neighborhood around given entities for graph-based retrieval.

        Used for coordinated retrieval: after vector search finds seed entities,
        expand the graph neighborhood to find related facts.

        Args:
            entities: List of seed entities to expand from
            max_depth: How many hops to expand
            limit_per_entity: Max neighbors per entity

        Returns:
            List of neighboring triples
        """
        max_depth = min(max_depth, self.MAX_QUERY_DEPTH)

        # Build query with literal depth
        query = f"""
            UNWIND $entities AS entity_name
            MATCH (start:Entity {{name: entity_name}})-[r:RELATION*1..{max_depth}]-(end:Entity)
            WHERE ALL(rel IN r WHERE rel.is_superseded = false)
            UNWIND r AS rel
            WITH entity_name, startNode(rel) AS s, rel, endNode(rel) AS o
            ORDER BY rel.weight DESC
            WITH entity_name, collect({{s: s, rel: rel, o: o}})[0..{limit_per_entity}] AS neighbors
            UNWIND neighbors AS n
            RETURN DISTINCT n.s.name AS subject,
                   n.rel.predicate AS predicate,
                   n.o.name AS object,
                   n.rel.fact_id AS fact_id,
                   n.rel.weight AS weight,
                   n.rel.version AS version,
                   n.rel.parent_ids AS parent_ids,
                   n.rel.derivation_type AS derivation_type,
                   n.rel.created_at AS created_at,
                   n.rel.updated_at AS updated_at
        """

        with self.driver.session(database=self.database) as session:
            result = session.run(cast(LiteralString, query), entities=entities)

            triples = []
            for record in result:
                parent_ids = (
                    json.loads(record["parent_ids"]) if record["parent_ids"] else []
                )
                triples.append(
                    SemanticTriple(
                        id=record["fact_id"],
                        subject=record["subject"],
                        predicate=record["predicate"],
                        object=record["object"],
                        weight=record["weight"],
                        version=record["version"],
                        parent_ids=parent_ids,
                        derivation_type=record["derivation_type"],
                    )
                )

            return triples

    def get_by_id(self, fact_id: str) -> SemanticTriple | None:
        """Get a triple by its ID.

        Args:
            fact_id: Unique fact identifier

        Returns:
            SemanticTriple if found, None otherwise
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (s:Entity)-[r:RELATION {fact_id: $fact_id}]->(o:Entity)
                RETURN s.name AS subject,
                       r.predicate AS predicate,
                       o.name AS object,
                       r.fact_id AS fact_id,
                       r.weight AS weight,
                       r.version AS version,
                       r.parent_ids AS parent_ids,
                       r.derivation_type AS derivation_type,
                       r.created_at AS created_at,
                       r.updated_at AS updated_at
                """,
                fact_id=fact_id,
            )

            record = result.single()
            if record is None:
                return None

            parent_ids = (
                json.loads(record["parent_ids"]) if record["parent_ids"] else []
            )

            return SemanticTriple(
                id=record["fact_id"],
                subject=record["subject"],
                predicate=record["predicate"],
                object=record["object"],
                weight=record["weight"],
                version=record["version"],
                parent_ids=parent_ids,
                derivation_type=record["derivation_type"],
            )

    def search(self, query: str, limit: int = 10) -> list[Memory]:
        """Search semantic facts using full-text index.

        Uses Neo4j's native full-text search for better semantic matching
        than SQL LIKE.

        Args:
            query: Query text
            limit: Maximum results

        Returns:
            List of relevant memories with provenance
        """
        datetime.now(timezone.utc).isoformat()

        with self.driver.session(database=self.database) as session:
            # Try full-text search first, fall back to CONTAINS
            try:
                result = session.run(
                    """
                    CALL db.index.fulltext.queryNodes('entity_fulltext', $search_query)
                    YIELD node, score
                    WITH node AS e, score
                    MATCH (e)-[r:RELATION]-(other:Entity)
                    WHERE r.is_superseded = false
                    WITH startNode(r) AS s, r, endNode(r) AS o, score
                    ORDER BY score DESC, r.weight DESC
                    LIMIT $limit
                    SET r.access_count = r.access_count + 1
                    RETURN s.name AS subject,
                           r.predicate AS predicate,
                           o.name AS object,
                           r.fact_id AS fact_id,
                           r.weight AS weight,
                           r.access_count AS access_count,
                           r.parent_ids AS parent_ids,
                           r.derivation_type AS derivation_type,
                           r.updated_at AS updated_at,
                           score
                    """,
                    search_query=query,
                    limit=limit,
                )
            except Neo4jError:
                # Fall back to CONTAINS-based search
                result = session.run(
                    """
                    MATCH (s:Entity)-[r:RELATION]->(o:Entity)
                    WHERE r.is_superseded = false AND (
                        toLower(s.name) CONTAINS toLower($search_query) OR
                        toLower(o.name) CONTAINS toLower($search_query) OR
                        toLower(r.predicate) CONTAINS toLower($search_query)
                    )
                    WITH s, r, o
                    ORDER BY r.weight DESC
                    LIMIT $limit
                    SET r.access_count = r.access_count + 1
                    RETURN s.name AS subject,
                           r.predicate AS predicate,
                           o.name AS object,
                           r.fact_id AS fact_id,
                           r.weight AS weight,
                           r.access_count AS access_count,
                           r.parent_ids AS parent_ids,
                           r.derivation_type AS derivation_type,
                           r.updated_at AS updated_at,
                           r.weight AS score
                    """,
                    search_query=query,
                    limit=limit,
                )

            memories = []
            for record in result:
                parent_ids = (
                    json.loads(record["parent_ids"]) if record["parent_ids"] else []
                )
                content = (
                    f"{record['subject']} {record['predicate']} {record['object']}"
                )

                memories.append(
                    Memory(
                        id=record["fact_id"],
                        content=content,
                        score=min(record["weight"], 1.0),
                        source="semantic",
                        timestamp=datetime.fromisoformat(record["updated_at"])
                        if record["updated_at"]
                        else datetime.now(timezone.utc),
                        metadata={
                            "subject": record["subject"],
                            "predicate": record["predicate"],
                            "object": record["object"],
                            "weight": record["weight"],
                            "access_count": record["access_count"],
                        },
                        parent_ids=parent_ids,
                        derivation_type=record["derivation_type"],
                    )
                )

            return memories

    def prune_low_weight(self, threshold: float = 0.3) -> int:
        """Remove low-weight facts (active forgetting).

        Facts below threshold are soft-deleted (marked as superseded).

        Args:
            threshold: Minimum weight threshold

        Returns:
            Number of facts pruned
        """
        now = datetime.now(timezone.utc).isoformat()

        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH ()-[r:RELATION]->()
                WHERE r.weight < $threshold AND r.is_superseded = false
                SET r.is_superseded = true, r.updated_at = $now
                RETURN count(r) AS pruned
                """,
                threshold=threshold,
                now=now,
            )

            record = result.single()
            pruned = record["pruned"] if record else 0

            logger.info("semantic_facts_pruned", count=pruned, threshold=threshold)
            return pruned

    def apply_decay(self, decay_factor: float = 0.99, min_weight: float = 0.1) -> int:
        """Apply time-based decay to all weights.

        Args:
            decay_factor: Multiplier for weight decay (0-1)
            min_weight: Minimum weight floor

        Returns:
            Number of facts decayed
        """
        now = datetime.now(timezone.utc).isoformat()

        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH ()-[r:RELATION]->()
                WHERE r.weight > $min_weight AND r.is_superseded = false
                SET r.weight = r.weight * $decay_factor, r.updated_at = $now
                RETURN count(r) AS decayed
                """,
                decay_factor=decay_factor,
                min_weight=min_weight,
                now=now,
            )

            record = result.single()
            return record["decayed"] if record else 0

    def get_all_for_entity(self, entity: str) -> list[SemanticTriple]:
        """Get all facts for an entity.

        Args:
            entity: Entity to query

        Returns:
            List of semantic triples
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (s:Entity {name: $entity})-[r:RELATION]->(o:Entity)
                WHERE r.is_superseded = false
                RETURN s.name AS subject,
                       r.predicate AS predicate,
                       o.name AS object,
                       r.fact_id AS fact_id,
                       r.weight AS weight,
                       r.version AS version,
                       r.parent_ids AS parent_ids,
                       r.derivation_type AS derivation_type
                """,
                entity=entity,
            )

            triples = []
            for record in result:
                parent_ids = (
                    json.loads(record["parent_ids"]) if record["parent_ids"] else []
                )
                triples.append(
                    SemanticTriple(
                        id=record["fact_id"],
                        subject=record["subject"],
                        predicate=record["predicate"],
                        object=record["object"],
                        weight=record["weight"],
                        version=record["version"],
                        parent_ids=parent_ids,
                        derivation_type=record["derivation_type"],
                    )
                )

            return triples

    def count(self) -> dict[str, int]:
        """Get count statistics.

        Returns:
            Dictionary with node and edge counts
        """
        with self.driver.session(database=self.database) as session:
            # Count entities
            entity_result = session.run(
                "OPTIONAL MATCH (e:Entity) RETURN count(e) AS entity_count"
            )
            entity_record = entity_result.single()
            entity_count = entity_record["entity_count"] if entity_record else 0

            # Count active facts
            active_result = session.run(
                """
                OPTIONAL MATCH ()-[r:RELATION]->()
                WHERE r.is_superseded = false
                RETURN count(r) AS active_count
                """
            )
            active_record = active_result.single()
            active_count = active_record["active_count"] if active_record else 0

            # Count superseded facts
            superseded_result = session.run(
                """
                OPTIONAL MATCH ()-[r:RELATION]->()
                WHERE r.is_superseded = true
                RETURN count(r) AS superseded_count
                """
            )
            superseded_record = superseded_result.single()
            superseded_count = (
                superseded_record["superseded_count"] if superseded_record else 0
            )

            return {
                "total_facts": active_count,
                "unique_entities": entity_count,
                "superseded_facts": superseded_count,
            }

    def health_check(self) -> dict[str, Any]:
        """Get health status of the store.

        Returns:
            Health status dictionary
        """
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run("RETURN 1 AS ping")
                result.single()

            stats = self.count()
            return {"status": "healthy", "backend": "neo4j", **stats}
        except Exception as e:
            return {"status": "unhealthy", "backend": "neo4j", "error": str(e)}

    def get_stats(self) -> dict[str, Any]:
        """Get store statistics.

        Returns:
            Statistics dictionary
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH ()-[r:RELATION]->()
                WITH count(r) AS total,
                     sum(CASE WHEN r.is_superseded = false THEN 1 ELSE 0 END) AS active,
                     sum(CASE WHEN r.is_superseded = true THEN 1 ELSE 0 END) AS superseded
                RETURN total, active, superseded
                """
            )

            record = result.single()
            if record is None:
                return {"total_triples": 0, "superseded_triples": 0, "total_stored": 0}

            return {
                "total_triples": record["active"],
                "superseded_triples": record["superseded"],
                "total_stored": record["total"],
            }

    def clear(self) -> int:
        """Clear all facts (for testing).

        Returns:
            Number of facts deleted
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH ()-[r:RELATION]->()
                WITH count(r) AS deleted_count
                MATCH (n)
                DETACH DELETE n
                RETURN deleted_count
                """
            )

            record = result.single()
            return record["deleted_count"] if record else 0

    def graph_search(
        self,
        query: str,
        query_entities: list[str] | None = None,
        limit: int = 10,
    ) -> list[Memory]:
        """Graph-aware search combining full-text and relationship traversal.

        This is an enhanced search that:
        1. Finds entities matching the query text
        2. Traverses relationships from those entities
        3. Returns facts with context from the graph structure

        Args:
            query: Query text
            query_entities: Pre-extracted entities from query (optional)
            limit: Maximum results

        Returns:
            List of relevant memories
        """
        if query_entities:
            # If entities provided, do graph expansion
            triples = self.expand_neighbors(
                query_entities, max_depth=2, limit_per_entity=limit
            )
            return [
                Memory(
                    id=t.id,
                    content=f"{t.subject} {t.predicate} {t.object}",
                    score=min(t.weight, 1.0),
                    source="semantic",
                    timestamp=t.updated_at,
                    metadata={
                        "subject": t.subject,
                        "predicate": t.predicate,
                        "object": t.object,
                        "weight": t.weight,
                    },
                    parent_ids=t.parent_ids,
                    derivation_type=t.derivation_type,
                )
                for t in triples[:limit]
            ]
        else:
            # Fall back to text search
            return self.search(query, limit)

    def run_pagerank(
        self, iterations: int = 20, damping: float = 0.85
    ) -> dict[str, float]:
        """Run PageRank algorithm on the knowledge graph.

        Identifies important entities based on relationship structure.
        Requires APOC or GDS library.

        Args:
            iterations: Number of PageRank iterations
            damping: Damping factor (0-1)

        Returns:
            Dictionary mapping entity names to PageRank scores
        """
        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    CALL gds.pageRank.stream({
                        nodeProjection: 'Entity',
                        relationshipProjection: 'RELATION',
                        maxIterations: $iterations,
                        dampingFactor: $damping
                    })
                    YIELD nodeId, score
                    RETURN gds.util.asNode(nodeId).name AS entity, score
                    ORDER BY score DESC
                    """,
                    iterations=iterations,
                    damping=damping,
                )

                return {record["entity"]: record["score"] for record in result}
            except Neo4jError as e:
                logger.warning("pagerank_failed", error=str(e))
                return {}
