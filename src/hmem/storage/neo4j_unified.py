"""Unified Neo4j storage supporting all memory types with complete provenance chain.

Graph Schema:
    Nodes:
        (:Conversation {id, session_id, created_at, metadata_json})
        (:Entity {id, canonical_name, aliases, entity_type, embedding, needs_resolution, created_at, updated_at})
        (:Fact {id, entity_id, slot, value, cardinality, confidence, embedding, is_superseded, created_at, updated_at, source_role, q_value, q_update_count})
        (:Process {id, trigger, action, outcome, confidence, embedding, is_deprecated, created_at, updated_at, q_value, q_update_count})
        (:Principle {id, content, evidence_count, confidence, embedding, created_at, q_value, q_update_count, is_deprecated, version})
        (:Skill {id, name, description, trigger_pattern, action_template, tags, embedding, created_at, updated_at, q_value, q_update_count, is_deprecated, version})

    Relationships:
        (:Conversation)-[:GENERATES]->(:Fact)
        (:Conversation)-[:GENERATES]->(:Process)
        (:Entity)-[:HAS_ATTRIBUTE]->(:Fact)
        (:Process)-[:INVOLVES]->(:Fact)
        (:Process)-[:INSTANCE_OF]->(:Skill)
        (:Fact)-[:SUPPORTS]->(:Principle)
        (:Skill)-[:GUIDED_BY]->(:Principle)
        (:Fact)-[:SUPERSEDED_BY]->(:Fact)
        (:Principle)-[:SUPERSEDED_BY]->(:Principle)

Features:
    - Complete provenance chain from raw conversations to derived knowledge
    - Entity-centric fact storage with alias-based resolution
    - Process extraction with trigger-action-outcome structure
    - Skill induction from similar processes
    - Vector similarity search for all memory types
    - Fulltext search across content
    - Q-value based learning (MemRL integration)
    - Conflict detection and resolution for single-cardinality attributes
    - Versioning and supersession tracking
    - Lineage traversal (upstream and downstream)
"""

from datetime import datetime, timezone
from typing import Any, Literal
import json
import uuid

import structlog
from neo4j import GraphDatabase, Driver
from neo4j.exceptions import Neo4jError

from hmem.models import (
    Memory,
    Conversation,
    Principle,
    Skill,
    IndexProfile,
    Entity,
    Attribute,
    Process,
)

logger = structlog.get_logger()


class Neo4jUnifiedStore:
    """Unified Neo4j storage supporting all memory types with complete provenance chain.

    This replaces the three-store architecture with a single graph database
    that maintains complete provenance relationships between all memory types.
    """

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        username: str = "neo4j",
        password: str = "testpassword123",
        database: str = "neo4j",
    ):
        """Initialize unified Neo4j store.

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
            self._schema_initialized = False

    def _ensure_schema(self) -> None:
        """Ensure schema is initialized (called once on first access)."""
        if self._schema_initialized:
            return
        self._schema_initialized = True
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize database schema with constraints, vector indexes, and fulltext indexes."""
        with self.driver.session(database=self.database) as session:
            # Create unique constraints on all node type IDs
            constraints = [
                "CREATE CONSTRAINT conv_id_unique IF NOT EXISTS FOR (c:Conversation) REQUIRE c.id IS UNIQUE",
                "CREATE CONSTRAINT fact_id_unique IF NOT EXISTS FOR (f:Fact) REQUIRE f.id IS UNIQUE",
                "CREATE CONSTRAINT prin_id_unique IF NOT EXISTS FOR (p:Principle) REQUIRE p.id IS UNIQUE",
                "CREATE CONSTRAINT skill_id_unique IF NOT EXISTS FOR (s:Skill) REQUIRE s.id IS UNIQUE",
                "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
                "CREATE CONSTRAINT proc_id_unique IF NOT EXISTS FOR (p:Process) REQUIRE p.id IS UNIQUE",
            ]

            for constraint in constraints:
                try:
                    session.run(constraint)
                except Neo4jError as e:
                    logger.debug("constraint_creation_skipped", error=str(e))

            # Create vector indexes for similarity search (1536 dims, cosine)
            vector_indexes = [
                ("fact_embedding_idx", "Fact", "embedding"),
                ("principle_embedding_idx", "Principle", "embedding"),
                ("skill_embedding_idx", "Skill", "embedding"),
                ("entity_embedding_idx", "Entity", "embedding"),
                ("process_embedding_idx", "Process", "embedding"),
            ]

            for idx_name, node_label, property_name in vector_indexes:
                try:
                    session.run(
                        f"""
                        CREATE VECTOR INDEX {idx_name} IF NOT EXISTS
                        FOR (n:{node_label}) ON (n.{property_name})
                        OPTIONS {{indexConfig: {{
                            `vector.dimensions`: 1536,
                            `vector.similarity_function`: 'cosine'
                        }}}}
                        """
                    )
                except Neo4jError as e:
                    logger.debug(
                        "vector_index_creation_skipped", index=idx_name, error=str(e)
                    )

            # Create fulltext indexes for each node type (separate indexes)
            fulltext_indexes = [
                (
                    "fact_content_fulltext",
                    "Fact",
                    "n.slot, n.value",
                ),
                (
                    "principle_content_fulltext",
                    "Principle",
                    "n.content",
                ),
                (
                    "skill_content_fulltext",
                    "Skill",
                    "n.name, n.description",
                ),
                (
                    "entity_content_fulltext",
                    "Entity",
                    "n.canonical_name",
                ),
                (
                    "process_content_fulltext",
                    "Process",
                    "n.trigger, n.action",
                ),
            ]

            for idx_name, label, properties in fulltext_indexes:
                try:
                    session.run(
                        f"""
                        CREATE FULLTEXT INDEX {idx_name} IF NOT EXISTS
                        FOR (n:{label})
                        ON EACH [{properties}]
                        """
                    )
                except Neo4jError as e:
                    logger.debug(
                        "fulltext_index_creation_skipped", index=idx_name, error=str(e)
                    )

            logger.info("neo4j_unified_schema_initialized", database=self.database)

    def add_conversation(self, conv: Conversation) -> str:
        """Store a Conversation node (upsert - skip if exists).

        Args:
            conv: Conversation object to store

        Returns:
            Conversation ID (generated if not provided)
        """
        conv_id = conv.id or f"conv_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MERGE (c:Conversation {id: $id})
                ON CREATE SET
                    c.session_id = $session_id,
                    c.created_at = $created_at,
                    c.metadata_json = $metadata_json
                """,
                id=conv_id,
                session_id=conv.session_id,
                created_at=now,
                metadata_json=json.dumps(conv.metadata),
            )

        logger.debug("conversation_stored", conv_id=conv_id, session_id=conv.session_id)
        return conv_id

    def add_principle(self, principle: Principle, evidence_event_ids: list[str]) -> str:
        """Store Principle node.

        Args:
            principle: Principle to store
            evidence_event_ids: List of evidence event IDs

        Returns:
            Principle ID (generated if not provided)
        """
        prin_id = principle.id or f"prin_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        # Note: embedding should be generated by caller and stored in metadata
        embedding = principle.metadata.get("embedding")

        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MERGE (p:Principle {id: $id})
                ON CREATE SET
                    p.content = $content,
                    p.evidence_count = $evidence_count,
                    p.confidence = $confidence,
                    p.embedding = $embedding,
                    p.created_at = $created_at,
                    p.q_value = $q_value,
                    p.q_update_count = $q_update_count,
                    p.is_deprecated = $is_deprecated,
                    p.version = $version
                """,
                evidence_event_ids=evidence_event_ids,
                id=prin_id,
                content=principle.content,
                evidence_count=principle.evidence_count,
                confidence=principle.confidence,
                embedding=embedding,
                created_at=principle.created_at.isoformat()
                if principle.created_at
                else now,
                q_value=principle.index_profile.q_value
                if principle.index_profile
                else 0.5,
                q_update_count=principle.index_profile.q_update_count
                if principle.index_profile
                else 0,
                is_deprecated=principle.is_deprecated,
                version=principle.version,
            )

        logger.debug(
            "principle_stored",
            prin_id=prin_id,
            evidence_count=len(evidence_event_ids),
        )
        return prin_id

    def add_skill(
        self,
        skill: Skill,
        source_process_ids: list[str] | None = None,
    ) -> str:
        """Store Skill node and create relationships.

        Args:
            skill: Skill to store
            source_process_ids: Process IDs this skill was induced from

        Returns:
            Skill ID (generated if not provided)
        """
        skill_id = skill.id or f"skill_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        # Note: embedding should be generated by caller and stored in metadata
        embedding = skill.metadata.get("embedding") if skill.metadata else None

        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MERGE (s:Skill {id: $id})
                ON CREATE SET
                    s.name = $name,
                    s.description = $description,
                    s.trigger_pattern = $trigger_pattern,
                    s.action_template = $action_template,
                    s.tags = $tags,
                    s.embedding = $embedding,
                    s.created_at = $created_at,
                    s.updated_at = $updated_at,
                    s.q_value = $q_value,
                    s.q_update_count = $q_update_count,
                    s.is_deprecated = $is_deprecated,
                    s.version = $version
                """,
                id=skill_id,
                name=skill.name,
                description=skill.description,
                trigger_pattern=skill.trigger_pattern,
                action_template=skill.action_template,
                tags=skill.tags,
                embedding=embedding,
                created_at=skill.created_at.isoformat() if skill.created_at else now,
                updated_at=skill.updated_at.isoformat() if skill.updated_at else now,
                q_value=skill.index_profile.q_value if skill.index_profile else 0.5,
                q_update_count=skill.index_profile.q_update_count
                if skill.index_profile
                else 0,
                is_deprecated=skill.is_deprecated,
                version=skill.version,
            )

            # Link to source processes via INSTANCE_OF (new model)
            if source_process_ids:
                for pid in source_process_ids:
                    session.run(
                        """
                        MATCH (p:Process {id: $proc_id})
                        MATCH (s:Skill {id: $skill_id})
                        MERGE (p)-[:INSTANCE_OF]->(s)
                        """,
                        proc_id=pid,
                        skill_id=skill_id,
                    )

        logger.debug(
            "skill_stored",
            skill_id=skill_id,
            name=skill.name,
        )
        return skill_id

    # === Entity-Centric Storage ===

    def add_entity(self, entity: Entity) -> str:
        """Store an Entity node (upsert).

        Args:
            entity: Entity to store

        Returns:
            Entity ID
        """
        entity_id = entity.id or f"entity_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MERGE (e:Entity {id: $id})
                ON CREATE SET
                    e.canonical_name = $canonical_name,
                    e.aliases = $aliases,
                    e.entity_type = $entity_type,
                    e.embedding = $embedding,
                    e.needs_resolution = $needs_resolution,
                    e.created_at = $created_at,
                    e.updated_at = $updated_at
                ON MATCH SET
                    e.updated_at = $updated_at
                """,
                id=entity_id,
                canonical_name=entity.canonical_name,
                aliases=entity.aliases,
                entity_type=entity.entity_type,
                embedding=entity.embedding,
                needs_resolution=entity.needs_resolution,
                created_at=entity.created_at.isoformat() if entity.created_at else now,
                updated_at=now,
            )

        logger.debug("entity_stored", entity_id=entity_id, name=entity.canonical_name)
        return entity_id

    def find_entity_by_name(self, name: str) -> dict | None:
        """Find entity by canonical name or alias.

        Args:
            name: Name to search (matches canonical_name or aliases)

        Returns:
            Entity dict or None
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (e:Entity)
                WHERE e.canonical_name = $name
                   OR $name IN e.aliases
                RETURN properties(e) AS props
                LIMIT 1
                """,
                name=name,
            )
            record = result.single()
            if record:
                return dict(record["props"])
            return None

    def merge_entities(self, source_id: str, target_id: str) -> None:
        """Merge source entity into target entity.

        Moves all relationships and aliases from source to target,
        then deletes source.

        Args:
            source_id: Entity to merge from (will be deleted)
            target_id: Entity to merge into (will receive all relationships)
        """
        now = datetime.now(timezone.utc).isoformat()

        with self.driver.session(database=self.database) as session:
            # Move aliases
            session.run(
                """
                MATCH (src:Entity {id: $source_id})
                MATCH (tgt:Entity {id: $target_id})
                SET tgt.aliases = tgt.aliases + src.aliases + [src.canonical_name],
                    tgt.updated_at = $now
                """,
                source_id=source_id,
                target_id=target_id,
                now=now,
            )

            # Move HAS_ATTRIBUTE relationships
            session.run(
                """
                MATCH (src:Entity {id: $source_id})-[r:HAS_ATTRIBUTE]->(f:Fact)
                MATCH (tgt:Entity {id: $target_id})
                SET f.entity_id = $target_id
                MERGE (tgt)-[:HAS_ATTRIBUTE]->(f)
                DELETE r
                """,
                source_id=source_id,
                target_id=target_id,
            )

            # Delete source entity
            session.run(
                "MATCH (src:Entity {id: $source_id}) DETACH DELETE src",
                source_id=source_id,
            )

        logger.info("entities_merged", source_id=source_id, target_id=target_id)

    def add_attribute(
        self, attr: Attribute, entity_id: str, source_conv_id: str
    ) -> str:
        """Store an Attribute as a Fact node linked to an Entity via HAS_ATTRIBUTE.

        Handles conflict detection for single-cardinality attributes:
        - single: if (entity_id, slot) already has a different value, supersede old
        - multi: just add, skip if duplicate value exists

        Provenance: Fact links to source Conversation via GENERATES relationship.

        Args:
            attr: Attribute to store
            entity_id: Entity this attribute belongs to
            source_conv_id: Source conversation ID for provenance

        Returns:
            Fact ID
        """
        fact_id = attr.id or f"fact_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        with self.driver.session(database=self.database) as session:
            if attr.cardinality == "single":
                # Check for conflict: same (entity_id, slot) with different value
                conflict_result = session.run(
                    """
                    MATCH (e:Entity {id: $entity_id})-[:HAS_ATTRIBUTE]->(f:Fact)
                    WHERE f.slot = $slot
                      AND f.value <> $value
                      AND f.is_superseded = false
                    RETURN f.id AS id, f.value AS value
                    """,
                    entity_id=entity_id,
                    slot=attr.slot,
                    value=attr.value,
                )

                for conflict in conflict_result:
                    # Supersede old attribute
                    session.run(
                        """
                        MATCH (f:Fact {id: $old_id})
                        SET f.is_superseded = true, f.updated_at = $now
                        """,
                        old_id=conflict["id"],
                        now=now,
                    )
                    logger.info(
                        "attribute_conflict_resolved",
                        entity_id=entity_id,
                        slot=attr.slot,
                        old_value=conflict["value"],
                        new_value=attr.value,
                    )
            else:
                # Multi-cardinality: skip if same (entity_id, slot, value) exists
                existing = session.run(
                    """
                    MATCH (e:Entity {id: $entity_id})-[:HAS_ATTRIBUTE]->(f:Fact)
                    WHERE f.slot = $slot AND f.value = $value AND f.is_superseded = false
                    RETURN f.id AS id
                    LIMIT 1
                    """,
                    entity_id=entity_id,
                    slot=attr.slot,
                    value=attr.value,
                )
                if existing.single():
                    logger.debug(
                        "attribute_duplicate_skipped",
                        entity_id=entity_id,
                        slot=attr.slot,
                        value=attr.value,
                    )
                    return existing.single()["id"] if existing.single() else fact_id

            # Create the Fact node and link to Entity + Conversation
            session.run(
                """
                MATCH (e:Entity {id: $entity_id})
                MERGE (f:Fact {id: $id})
                ON CREATE SET
                    f.entity_id = $entity_id,
                    f.slot = $slot,
                    f.value = $value,
                    f.cardinality = $cardinality,
                    f.confidence = $confidence,
                    f.scope = $scope,
                    f.scope_context = $scope_context,
                    f.embedding = $embedding,
                    f.is_superseded = false,
                    f.created_at = $created_at,
                    f.updated_at = $updated_at,
                    f.source_role = $source_role,
                    f.version = $version,
                    f.q_value = $q_value,
                    f.q_update_count = $q_update_count
                MERGE (e)-[:HAS_ATTRIBUTE]->(f)
                WITH f
                OPTIONAL MATCH (c:Conversation {id: $source_conv_id})
                FOREACH (_ IN CASE WHEN c IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (c)-[:GENERATES]->(f)
                )
                """,
                entity_id=entity_id,
                id=fact_id,
                slot=attr.slot,
                value=attr.value,
                cardinality=attr.cardinality,
                confidence=attr.confidence,
                scope=attr.scope,
                scope_context=attr.scope_context,
                embedding=attr.embedding,
                is_superseded=False,
                created_at=attr.created_at.isoformat() if attr.created_at else now,
                updated_at=now,
                source_role=attr.source_role,
                version=attr.version,
                q_value=attr.index_profile.q_value if attr.index_profile else 0.5,
                q_update_count=attr.index_profile.q_update_count
                if attr.index_profile
                else 0,
                source_conv_id=source_conv_id,
            )

        logger.debug(
            "attribute_stored",
            fact_id=fact_id,
            entity_id=entity_id,
            slot=attr.slot,
            value=attr.value,
        )
        return fact_id

    def add_process(self, process: Process, source_conv_id: str) -> str:
        """Store a Process node with relationship to source conversation.

        Provenance: Process links to source Conversation via GENERATES relationship.

        Args:
            process: Process to store
            source_conv_id: Source conversation ID for provenance

        Returns:
            Process ID
        """
        proc_id = process.id or f"proc_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MERGE (p:Process {id: $id})
                ON CREATE SET
                    p.trigger = $trigger,
                    p.action = $action,
                    p.outcome = $outcome,
                    p.confidence = $confidence,
                    p.is_generalizable = $is_generalizable,
                    p.embedding = $embedding,
                    p.is_deprecated = false,
                    p.created_at = $created_at,
                    p.updated_at = $updated_at,
                    p.q_value = $q_value,
                    p.q_update_count = $q_update_count,
                    p.version = $version
                WITH p
                OPTIONAL MATCH (c:Conversation {id: $source_conv_id})
                FOREACH (_ IN CASE WHEN c IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (c)-[:GENERATES]->(p)
                )
                """,
                id=proc_id,
                trigger=process.trigger,
                action=process.action,
                outcome=process.outcome,
                confidence=process.confidence,
                is_generalizable=process.is_generalizable,
                embedding=process.embedding,
                created_at=process.created_at.isoformat()
                if process.created_at
                else now,
                updated_at=now,
                q_value=process.index_profile.q_value if process.index_profile else 0.5,
                q_update_count=process.index_profile.q_update_count
                if process.index_profile
                else 0,
                version=process.version,
                source_conv_id=source_conv_id,
            )

            # Create INVOLVES relationships to facts
            if process.involved_fact_ids:
                session.run(
                    """
                    MATCH (p:Process {id: $proc_id})
                    UNWIND $fact_ids AS fid
                    MATCH (f:Fact {id: fid})
                    MERGE (p)-[:INVOLVES]->(f)
                    """,
                    proc_id=proc_id,
                    fact_ids=process.involved_fact_ids,
                )

            # Link to existing skill if specified
            if process.skill_id:
                session.run(
                    """
                    MATCH (p:Process {id: $proc_id})
                    MATCH (s:Skill {id: $skill_id})
                    MERGE (p)-[:INSTANCE_OF]->(s)
                    """,
                    proc_id=proc_id,
                    skill_id=process.skill_id,
                )

        logger.debug(
            "process_stored",
            proc_id=proc_id,
            trigger=process.trigger,
            action=process.action,
            outcome=process.outcome,
        )
        return proc_id

    def find_similar_processes(
        self,
        trigger_embedding: list[float],
        limit: int = 10,
        min_score: float = 0.7,
    ) -> list[dict]:
        """Find processes with similar triggers using vector search.

        Args:
            trigger_embedding: Embedding vector of the trigger text
            limit: Maximum results
            min_score: Minimum similarity score

        Returns:
            List of process dicts with similarity scores
        """
        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    CALL db.index.vector.queryNodes('process_embedding_idx', $limit, $embedding)
                    YIELD node, score
                    WHERE score >= $min_score AND node.is_deprecated = false
                    RETURN properties(node) AS props, score
                    ORDER BY score DESC
                    """,
                    limit=limit,
                    embedding=trigger_embedding,
                    min_score=min_score,
                )

                return [
                    {**dict(record["props"]), "similarity": record["score"]}
                    for record in result
                ]
            except Neo4jError as e:
                logger.debug("find_similar_processes_failed", error=str(e))
                return []

    def link_process_to_skill(self, process_id: str, skill_id: str) -> None:
        """Create INSTANCE_OF relationship from Process to Skill.

        Args:
            process_id: Process ID
            skill_id: Skill ID
        """
        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MATCH (p:Process {id: $process_id})
                MATCH (s:Skill {id: $skill_id})
                MERGE (p)-[:INSTANCE_OF]->(s)
                """,
                process_id=process_id,
                skill_id=skill_id,
            )

    def link_fact_to_principle(self, fact_id: str, principle_id: str) -> None:
        """Create SUPPORTS relationship from Fact to Principle (sparse).

        Args:
            fact_id: Fact ID
            principle_id: Principle ID
        """
        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MATCH (f:Fact {id: $fact_id})
                MATCH (p:Principle {id: $principle_id})
                MERGE (f)-[:SUPPORTS]->(p)
                """,
                fact_id=fact_id,
                principle_id=principle_id,
            )

    def link_skill_to_principle(self, skill_id: str, principle_id: str) -> None:
        """Create GUIDED_BY relationship from Skill to Principle (very sparse).

        Args:
            skill_id: Skill ID
            principle_id: Principle ID
        """
        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MATCH (s:Skill {id: $skill_id})
                MATCH (p:Principle {id: $principle_id})
                MERGE (s)-[:GUIDED_BY]->(p)
                """,
                skill_id=skill_id,
                principle_id=principle_id,
            )

    def get_processes_without_skill(self, limit: int = 100) -> list[dict]:
        """Get generalizable processes not yet linked to any skill (candidates for induction).

        Only returns processes where is_generalizable=true to ensure skill induction
        is based on reusable patterns, not one-time debugging steps.

        Args:
            limit: Maximum results

        Returns:
            List of process property dicts
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (p:Process)
                WHERE NOT (p)-[:INSTANCE_OF]->(:Skill)
                  AND p.is_deprecated = false
                  AND COALESCE(p.is_generalizable, true) = true
                  AND p.embedding IS NOT NULL
                RETURN properties(p) AS props
                ORDER BY p.created_at DESC
                LIMIT $limit
                """,
                limit=limit,
            )
            return [dict(record["props"]) for record in result]

    def vector_search(
        self,
        query_embedding: list[float],
        node_type: str,
        limit: int = 10,
    ) -> list[Memory]:
        """Vector similarity search using Neo4j vector index.

        Args:
            query_embedding: Query embedding vector (1536 dims)
            node_type: Node type to search ("Fact", "Principle", "Skill")
            limit: Maximum results

        Returns:
            List of Memory objects with similarity scores
        """
        index_map = {
            "Fact": "fact_embedding_idx",
            "Principle": "principle_embedding_idx",
            "Skill": "skill_embedding_idx",
            "Entity": "entity_embedding_idx",
            "Process": "process_embedding_idx",
        }

        index_name = index_map.get(node_type)
        if not index_name:
            logger.warning("invalid_node_type", node_type=node_type)
            return []

        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    CALL db.index.vector.queryNodes($index_name, $limit, $embedding)
                    YIELD node, score
                    RETURN node, score
                    """,
                    index_name=index_name,
                    limit=limit,
                    embedding=query_embedding,
                )

                memories = []
                for record in result:
                    node = record["node"]
                    score = record["score"]
                    memory = self._node_to_memory(node, score, node_type)
                    if memory:
                        memories.append(memory)

                return memories

            except Neo4jError as e:
                logger.error("vector_search_failed", error=str(e), node_type=node_type)
                return []

    def fulltext_search(
        self,
        query: str,
        node_types: list[str] | None = None,
        limit: int = 10,
    ) -> list[Memory]:
        """Fulltext search across node types.

        Args:
            query: Query text
            node_types: Node types to search (None = all types)
            limit: Maximum results

        Returns:
            List of Memory objects
        """
        if not query or not query.strip():
            logger.debug("fulltext_search_empty_query")
            return []

        # Build list of indexes to query based on node_types
        index_map = {
            "Fact": "fact_content_fulltext",
            "Principle": "principle_content_fulltext",
            "Skill": "skill_content_fulltext",
            "Entity": "entity_content_fulltext",
            "Process": "process_content_fulltext",
        }

        if node_types:
            indexes_to_query = [
                (idx_name, label)
                for label, idx_name in index_map.items()
                if label in node_types
            ]
        else:
            indexes_to_query = list(index_map.items())
            # Swap to (idx_name, label) format
            indexes_to_query = [(idx, label) for label, idx in index_map.items()]

        with self.driver.session(database=self.database) as session:
            all_results: list[tuple[Any, float, str]] = []

            for idx_name, label in indexes_to_query:
                try:
                    result = session.run(
                        f"""
                        CALL db.index.fulltext.queryNodes('{idx_name}', $search_query)
                        YIELD node, score
                        RETURN node, score, '{label}' AS node_type
                        ORDER BY score DESC
                        LIMIT $limit
                        """,
                        search_query=query,
                        limit=limit,
                    )
                    for record in result:
                        all_results.append(
                            (record["node"], record["score"], record["node_type"])
                        )
                except Neo4jError as e:
                    logger.debug(
                        "fulltext_search_index_query_failed",
                        index=idx_name,
                        error=str(e),
                    )

            # Sort all results by score and limit
            all_results.sort(key=lambda x: x[1], reverse=True)
            all_results = all_results[:limit]

            memories = []
            for node, score, node_type in all_results:
                memory = self._node_to_memory(node, score, node_type)
                if memory:
                    memories.append(memory)

            return memories

    def _node_to_memory(self, node: Any, score: float, node_type: str) -> Memory | None:
        """Convert Neo4j node to Memory object.

        Args:
            node: Neo4j node
            score: Similarity/relevance score
            node_type: Type of node

        Returns:
            Memory object or None
        """
        try:
            node_props = dict(node.items())

            # Map node type to source field
            source_map: dict[
                str, Literal["episodic", "semantic", "skill", "principle"]
            ] = {
                "Fact": "semantic",
                "Principle": "principle",
                "Skill": "skill",
                "Process": "episodic",
                "Entity": "semantic",
            }
            source: Literal["episodic", "semantic", "skill", "principle"] = (
                source_map.get(node_type, "episodic")
            )

            # Extract content based on node type
            if node_type == "Fact":
                slot = node_props.get("slot", "")
                value = node_props.get("value", "")
                content = f"{slot}: {value}" if slot and value else ""
            elif node_type == "Principle":
                content = node_props.get("content", "")
            elif node_type == "Skill":
                content = (
                    f"{node_props.get('name', '')}: {node_props.get('description', '')}"
                )
            elif node_type == "Process":
                trigger = node_props.get("trigger", "")
                action = node_props.get("action", "")
                content = f"When {trigger} → {action}"
            elif node_type == "Entity":
                content = f"Entity: {node_props.get('canonical_name', '')}"
            else:
                content = ""

            # Parse timestamp
            created_at_str = node_props.get("created_at")
            timestamp = (
                datetime.fromisoformat(created_at_str)
                if created_at_str
                else datetime.now(timezone.utc)
            )

            # Build index profile
            index_profile = IndexProfile(
                q_value=node_props.get("q_value", 0.5),
                q_update_count=node_props.get("q_update_count", 0),
                created_at=timestamp,
            )

            # Get parent IDs from relationships (would require separate query)
            # For now, return empty list
            parent_ids: list[str] = []

            return Memory(
                id=node_props.get("id"),
                content=content,
                score=min(score, 1.0),
                source=source,
                timestamp=timestamp,
                metadata=node_props,
                parent_ids=parent_ids,
                index_profile=index_profile,
            )

        except Exception as e:
            logger.error("node_to_memory_failed", error=str(e), node_type=node_type)
            return None

    def get_lineage(self, node_id: str, max_depth: int = 5) -> list[dict]:
        """Traverse up the provenance chain to find all ancestors.

        Args:
            node_id: Starting node ID
            max_depth: Maximum traversal depth

        Returns:
            List of ancestor nodes with relationships
        """
        # Sanitize max_depth to prevent injection (must be positive int, max 10)
        safe_depth = max(1, min(int(max_depth), 10))

        with self.driver.session(database=self.database) as session:
            # Neo4j doesn't allow parameters in variable-length path bounds,
            # so we interpolate the sanitized depth directly
            result = session.run(
                f"""
                MATCH path = (n)-[*1..{safe_depth}]->(ancestor)
                WHERE n.id = $node_id
                WITH nodes(path) AS node_list, relationships(path) AS rel_list
                UNWIND range(0, size(node_list)-1) AS i
                RETURN node_list[i] AS node,
                       CASE WHEN i < size(rel_list) THEN type(rel_list[i]) ELSE null END AS rel_type,
                       labels(node_list[i]) AS labels
                """,
                node_id=node_id,
            )

            lineage = []
            for record in result:
                node = record["node"]
                rel_type = record["rel_type"]
                labels = record["labels"]

                lineage.append(
                    {
                        "id": node.get("id"),
                        "type": labels[0] if labels else "Unknown",
                        "relationship": rel_type,
                        "properties": dict(node.items()),
                    }
                )

            return lineage

    def get_descendants(self, node_id: str) -> list[dict]:
        """Get all nodes derived from a given node.

        Args:
            node_id: Source node ID

        Returns:
            List of descendant nodes
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (source)-[r*1..]->(descendant)
                WHERE source.id = $node_id
                RETURN descendant, labels(descendant) AS labels, type(r[0]) AS first_rel
                """,
                node_id=node_id,
            )

            descendants = []
            for record in result:
                node = record["descendant"]
                labels = record["labels"]

                descendants.append(
                    {
                        "id": node.get("id"),
                        "type": labels[0] if labels else "Unknown",
                        "properties": dict(node.items()),
                    }
                )

            return descendants

    def supersede(self, old_id: str, new_node: dict, node_type: str) -> str:
        """Mark old node as superseded and create new version.

        Args:
            old_id: Old node ID to supersede
            new_node: New node properties
            node_type: Type of node ("Fact", "Principle")

        Returns:
            New node ID
        """
        new_id = f"{node_type.lower()}_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        with self.driver.session(database=self.database) as session:
            if node_type == "Fact":
                session.run(
                    """
                    MATCH (old:Fact {id: $old_id})
                    SET old.is_superseded = true, old.updated_at = $now
                    CREATE (new:Fact {
                        id: $new_id,
                        subject: $subject,
                        predicate: $predicate,
                        object: $object,
                        weight: $weight,
                        version: old.version + 1,
                        embedding: $embedding,
                        is_superseded: false,
                        created_at: $now,
                        updated_at: $now,
                        source_role: $source_role,
                        importance: $importance,
                        confidence: $confidence,
                        q_value: $q_value,
                        q_update_count: $q_update_count
                    })
                    CREATE (old)-[:SUPERSEDED_BY]->(new)
                    """,
                    old_id=old_id,
                    new_id=new_id,
                    now=now,
                    **new_node,
                )
            elif node_type == "Principle":
                session.run(
                    """
                    MATCH (old:Principle {id: $old_id})
                    SET old.is_deprecated = true
                    CREATE (new:Principle {
                        id: $new_id,
                        content: $content,
                        evidence_count: $evidence_count,
                        confidence: $confidence,
                        embedding: $embedding,
                        created_at: $now,
                        q_value: $q_value,
                        q_update_count: $q_update_count,
                        is_deprecated: false,
                        version: old.version + 1
                    })
                    CREATE (old)-[:SUPERSEDED_BY]->(new)
                    """,
                    old_id=old_id,
                    new_id=new_id,
                    now=now,
                    **new_node,
                )

        logger.debug(
            "node_superseded", old_id=old_id, new_id=new_id, node_type=node_type
        )
        return new_id

    def deprecate(self, node_id: str, reason: str) -> None:
        """Mark a node as deprecated.

        Args:
            node_id: Node ID to deprecate
            reason: Deprecation reason
        """
        now = datetime.now(timezone.utc).isoformat()

        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MATCH (n)
                WHERE n.id = $node_id
                SET n.is_deprecated = true,
                    n.deprecation_reason = $reason,
                    n.deprecated_at = $now
                """,
                node_id=node_id,
                reason=reason,
                now=now,
            )

        logger.debug("node_deprecated", node_id=node_id, reason=reason)

    def update_q_value(
        self,
        node_id: str,
        node_type: str,
        delta_q: float,
        alpha: float = 0.1,
    ) -> None:
        """Update Q-value using Monte Carlo update rule.

        Update rule: Q_new = Q_old + α(reward - Q_old)
        where delta_q represents the reward signal.

        Args:
            node_id: Node ID
            node_type: Type of node
            delta_q: Q-value change (reward signal)
            alpha: Learning rate
        """
        with self.driver.session(database=self.database) as session:
            session.run(
                f"""
                MATCH (n:{node_type} {{id: $node_id}})
                SET n.q_value = n.q_value + $alpha * ($delta_q - n.q_value),
                    n.q_update_count = n.q_update_count + 1
                """,
                node_id=node_id,
                delta_q=delta_q,
                alpha=alpha,
            )

        logger.debug("q_value_updated", node_id=node_id, delta_q=delta_q)

    def get_stats(self) -> dict[str, Any]:
        """Get statistics for all node types.

        Returns:
            Dictionary with counts for each node type
        """
        empty = {
            "conversations": 0,
            "facts": 0,
            "active_facts": 0,
            "principles": 0,
            "active_principles": 0,
            "skills": 0,
            "active_skills": 0,
            "entities": 0,
            "processes": 0,
            "active_processes": 0,
        }

        with self.driver.session(database=self.database) as session:
            # Use separate CALL subqueries to avoid property-not-exist warnings
            # when node types have no instances yet
            result = session.run(
                """
                CALL () { MATCH (c:Conversation) RETURN count(c) AS conversations }
                CALL () { MATCH (f:Fact) RETURN count(f) AS facts }
                CALL () { MATCH (f:Fact) WHERE COALESCE(f.is_superseded, false) = false RETURN count(f) AS active_facts }
                CALL () { MATCH (p:Principle) RETURN count(p) AS principles }
                CALL () { MATCH (p:Principle) WHERE COALESCE(p.is_deprecated, false) = false RETURN count(p) AS active_principles }
                CALL () { MATCH (s:Skill) RETURN count(s) AS skills }
                CALL () { MATCH (s:Skill) WHERE COALESCE(s.is_deprecated, false) = false RETURN count(s) AS active_skills }
                CALL () { MATCH (ent:Entity) RETURN count(ent) AS entities }
                CALL () { MATCH (proc:Process) RETURN count(proc) AS processes }
                CALL () { MATCH (proc:Process) WHERE COALESCE(proc.is_deprecated, false) = false RETURN count(proc) AS active_processes }
                RETURN conversations, facts, active_facts, principles,
                       active_principles, skills, active_skills, entities, processes, active_processes
                """
            )

            record = result.single()
            if not record:
                return empty

            return {
                "conversations": record["conversations"],
                "facts": record["facts"],
                "active_facts": record["active_facts"],
                "principles": record["principles"],
                "active_principles": record["active_principles"],
                "skills": record["skills"],
                "active_skills": record["active_skills"],
                "entities": record["entities"],
                "processes": record["processes"],
                "active_processes": record["active_processes"],
            }

    def clear(self) -> int:
        """Clear all data (for testing).

        Returns:
            Number of nodes deleted
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (n)
                WITH count(n) AS deleted_count
                MATCH (node)
                DETACH DELETE node
                RETURN deleted_count
                """
            )

            record = result.single()
            deleted = record["deleted_count"] if record else 0

            logger.info("neo4j_unified_cleared", deleted_count=deleted)
            return deleted

    def get_node_properties(self, node_id: str, node_type: str) -> dict | None:
        """Get properties of a specific node.

        Args:
            node_id: Node ID
            node_type: Type of node (Fact, Principle, Skill)

        Returns:
            Dict of node properties or None if not found
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(
                f"""
                MATCH (n:{node_type} {{id: $node_id}})
                RETURN properties(n) AS props
                """,
                node_id=node_id,
            )
            record = result.single()
            if record:
                return dict(record["props"])
            return None

    def update_node_properties(
        self, node_id: str, node_type: str, properties: dict
    ) -> None:
        """Update properties of a specific node.

        Args:
            node_id: Node ID
            node_type: Type of node
            properties: Properties to update
        """
        with self.driver.session(database=self.database) as session:
            # Build SET clause dynamically
            set_clauses = ", ".join([f"n.{k} = ${k}" for k in properties.keys()])
            params = {"node_id": node_id, **properties}
            session.run(
                f"""
                MATCH (n:{node_type} {{id: $node_id}})
                SET {set_clauses}
                """,
                **params,
            )

    def query_nodes_by_q_value(
        self,
        node_type: str,
        max_q_value: float,
        min_usage: int,
        limit: int = 100,
    ) -> list[dict]:
        """Query nodes with low Q-value and high usage (evolution candidates).

        Args:
            node_type: Type of node to query
            max_q_value: Maximum Q-value threshold
            min_usage: Minimum usage count
            limit: Maximum results

        Returns:
            List of node property dicts
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(
                f"""
                MATCH (n:{node_type})
                WHERE n.q_value <= $max_q_value
                  AND n.q_update_count >= $min_usage
                  AND (n.is_deprecated IS NULL OR n.is_deprecated = false)
                RETURN properties(n) AS props
                ORDER BY n.q_value ASC
                LIMIT $limit
                """,
                max_q_value=max_q_value,
                min_usage=min_usage,
                limit=limit,
            )
            return [dict(record["props"]) for record in result]

    def create_node(self, node_type: str, properties: dict) -> str:
        """Create a new node with given properties.

        Args:
            node_type: Type of node to create
            properties: Node properties

        Returns:
            Node ID
        """
        node_id = properties.get("id", f"{node_type.lower()}_{uuid.uuid4().hex[:12]}")
        properties["id"] = node_id

        with self.driver.session(database=self.database) as session:
            # Build property list dynamically
            prop_list = ", ".join([f"{k}: ${k}" for k in properties.keys()])
            session.run(
                f"CREATE (n:{node_type} {{{prop_list}}})",
                **properties,
            )
        return node_id

    def create_relationship(
        self,
        from_id: str,
        from_type: str,
        to_id: str,
        to_type: str,
        rel_type: str,
        properties: dict | None = None,
    ) -> None:
        """Create a relationship between two nodes.

        Args:
            from_id: Source node ID
            from_type: Source node type
            to_id: Target node ID
            to_type: Target node type
            rel_type: Relationship type
            properties: Relationship properties
        """
        with self.driver.session(database=self.database) as session:
            if properties:
                prop_list = ", ".join([f"{k}: ${k}" for k in properties.keys()])
                session.run(
                    f"""
                    MATCH (a:{from_type} {{id: $from_id}})
                    MATCH (b:{to_type} {{id: $to_id}})
                    CREATE (a)-[:{rel_type} {{{prop_list}}}]->(b)
                    """,
                    from_id=from_id,
                    to_id=to_id,
                    **properties,
                )
            else:
                session.run(
                    f"""
                    MATCH (a:{from_type} {{id: $from_id}})
                    MATCH (b:{to_type} {{id: $to_id}})
                    CREATE (a)-[:{rel_type}]->(b)
                    """,
                    from_id=from_id,
                    to_id=to_id,
                )

    # === Web UI API Methods ===

    def get_node_by_id(self, node_id: str) -> dict | None:
        """Get any node by ID, auto-detecting type from prefix.

        Args:
            node_id: Node ID (e.g., "conv_xxx", "evt_xxx", "fact_xxx", "prin_xxx", "skill_xxx")

        Returns:
            Dict with node properties and type, or None if not found
        """
        # Detect node type from ID prefix
        type_map = {
            "conv_": "Conversation",
            "fact_": "Fact",
            "prin_": "Principle",
            "skill_": "Skill",
            "entity_": "Entity",
            "proc_": "Process",
        }

        node_type = None
        for prefix, ntype in type_map.items():
            if node_id.startswith(prefix):
                node_type = ntype
                break

        if not node_type:
            # Try to find in any node type
            for ntype in [
                "Conversation",
                "Fact",
                "Principle",
                "Skill",
                "Entity",
                "Process",
            ]:
                result = self.get_node_properties(node_id, ntype)
                if result:
                    return {"type": ntype, **result}
            return None

        props = self.get_node_properties(node_id, node_type)
        if props:
            return {"type": node_type, **props}
        return None

    def list_by_type(
        self,
        node_type: str,
        limit: int = 50,
        order_by: str = "created_at",
        descending: bool = True,
    ) -> list[dict]:
        """List nodes of a specific type for browsing.

        Args:
            node_type: Node type (Conversation, Fact, Principle, Skill, Entity, Process)
            limit: Maximum nodes to return
            order_by: Property to sort by (created_at, q_value, etc.)
            descending: Sort descending (True) or ascending (False)

        Returns:
            List of node dicts with type and properties
        """
        valid_types = ["Conversation", "Fact", "Principle", "Skill", "Entity", "Process"]
        if node_type not in valid_types:
            return []

        order_dir = "DESC" if descending else "ASC"

        with self.driver.session(database=self.database) as session:
            # Use COALESCE for optional properties
            result = session.run(
                f"""
                MATCH (n:{node_type})
                RETURN n, labels(n) AS labels
                ORDER BY COALESCE(n.{order_by}, n.created_at) {order_dir}
                LIMIT $limit
                """,
                limit=limit,
            )

            nodes = []
            for record in result:
                node = record["n"]
                props = dict(node.items())
                nodes.append({"type": node_type, **props})

            return nodes

    def get_neighbors(
        self,
        node_id: str,
        direction: str = "BOTH",
        depth: int = 1,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Get neighboring nodes and edges for lazy loading in graph visualization.

        Args:
            node_id: Starting node ID
            direction: "IN", "OUT", or "BOTH"
            depth: Traversal depth (1-5)
            limit: Maximum nodes to return

        Returns:
            Dict with nodes, edges, and has_more flag
        """
        depth = max(1, min(depth, 5))

        # Build relationship pattern based on direction
        if direction == "IN":
            rel_pattern = "<-[r*1..{depth}]-"
        elif direction == "OUT":
            rel_pattern = "-[r*1..{depth}]->"
        else:
            rel_pattern = "-[r*1..{depth}]-"

        rel_pattern = rel_pattern.format(depth=depth)

        with self.driver.session(database=self.database) as session:
            # First, get the starting node
            start_node = self.get_node_by_id(node_id)
            if not start_node:
                return {"nodes": [], "edges": [], "has_more": False}

            # Query for neighbors
            result = session.run(
                f"""
                MATCH (start {{id: $node_id}}){rel_pattern}(neighbor)
                WITH DISTINCT neighbor, start
                LIMIT $limit + 1
                WITH collect(neighbor) AS neighbors, start
                UNWIND neighbors[0..$limit] AS n
                OPTIONAL MATCH (start)-[r]-(n)
                WITH start, n, collect(DISTINCT r) AS rels,
                     size(neighbors) > $limit AS has_more
                RETURN
                    n.id AS neighbor_id,
                    labels(n) AS neighbor_labels,
                    properties(n) AS neighbor_props,
                    [rel IN rels | {{
                        type: type(rel),
                        source: startNode(rel).id,
                        target: endNode(rel).id
                    }}] AS relationships,
                    has_more
                """,
                node_id=node_id,
                limit=limit,
            )

            nodes: list[dict] = []
            edges: list[dict] = []
            seen_nodes: set[str] = {node_id}
            seen_edges: set[str] = set()
            has_more = False

            # Add starting node
            nodes.append(self._format_graph_node(start_node))

            for record in result:
                neighbor_id = record["neighbor_id"]
                neighbor_labels = record["neighbor_labels"]
                neighbor_props = dict(record["neighbor_props"])
                relationships = record["relationships"]
                has_more = record["has_more"]

                if neighbor_id and neighbor_id not in seen_nodes:
                    seen_nodes.add(neighbor_id)
                    node_type = neighbor_labels[0] if neighbor_labels else "Unknown"
                    nodes.append(
                        self._format_graph_node({"type": node_type, **neighbor_props})
                    )

                for rel in relationships:
                    if rel:
                        edge_key = f"{rel['source']}-{rel['type']}-{rel['target']}"
                        if edge_key not in seen_edges:
                            seen_edges.add(edge_key)
                            edges.append(
                                {
                                    "source": rel["source"],
                                    "target": rel["target"],
                                    "relationship": rel["type"],
                                }
                            )

            return {"nodes": nodes, "edges": edges, "has_more": has_more}

    def _format_graph_node(self, node_data: dict) -> dict:
        """Format node data for graph visualization.

        Args:
            node_data: Raw node data with 'type' key

        Returns:
            Formatted node dict for GraphQL
        """
        node_type = node_data.get("type", "Unknown")
        node_id = node_data.get("id", "")

        # Generate label based on node type
        if node_type == "Conversation":
            label = f"Conv: {node_data.get('session_id', node_id)[:20]}"
        elif node_type == "Fact":
            slot = node_data.get("slot", "")
            value = node_data.get("value", "")
            label = f"{slot}: {value}" if slot and value else node_id
            if len(label) > 50:
                label = label[:50] + "..."
        elif node_type == "Entity":
            label = node_data.get("canonical_name", node_id)
        elif node_type == "Process":
            trigger = node_data.get("trigger", "")
            label = f"⚡ {trigger[:40]}..." if len(trigger) > 40 else f"⚡ {trigger}"
        elif node_type == "Principle":
            content = node_data.get("content", "")
            label = content[:50] + "..." if len(content) > 50 else content
        elif node_type == "Skill":
            label = node_data.get("name", node_id)
        else:
            label = node_id

        # Determine if deprecated
        is_deprecated = node_data.get("is_deprecated", False) or node_data.get(
            "is_superseded", False
        )

        return {
            "id": node_id,
            "nodeType": node_type.upper(),
            "label": label,
            "qValue": node_data.get("q_value"),
            "isDeprecated": is_deprecated,
        }

    # === Skill Sync Methods ===

    def sync_skill_metadata(
        self,
        skill_name: str,
        q_value: float,
        q_update_count: int,
        embedding: list[float] | None = None,
    ) -> bool:
        """Sync skill metadata from file system to Neo4j.

        Used to update Neo4j when skill metadata changes in SKILL.md files.

        Args:
            skill_name: Skill name (matches Neo4j 'name' property)
            q_value: Updated Q-value
            q_update_count: Updated Q-update count
            embedding: Optional embedding vector to update

        Returns:
            True if skill found and updated
        """
        now = datetime.now(timezone.utc).isoformat()

        with self.driver.session(database=self.database) as session:
            # Build update query
            if embedding:
                result = session.run(
                    """
                    MATCH (s:Skill {name: $name})
                    SET s.q_value = $q_value,
                        s.q_update_count = $q_update_count,
                        s.embedding = $embedding,
                        s.updated_at = $now
                    RETURN s.id AS id
                    """,
                    name=skill_name,
                    q_value=q_value,
                    q_update_count=q_update_count,
                    embedding=embedding,
                    now=now,
                )
            else:
                result = session.run(
                    """
                    MATCH (s:Skill {name: $name})
                    SET s.q_value = $q_value,
                        s.q_update_count = $q_update_count,
                        s.updated_at = $now
                    RETURN s.id AS id
                    """,
                    name=skill_name,
                    q_value=q_value,
                    q_update_count=q_update_count,
                    now=now,
                )

            record = result.single()
            if record:
                logger.debug("skill_metadata_synced", skill_name=skill_name)
                return True

            logger.debug("skill_not_found_for_sync", skill_name=skill_name)
            return False

    def get_skill_by_name(self, skill_name: str) -> dict | None:
        """Get skill properties by name.

        Args:
            skill_name: Skill name

        Returns:
            Dict of skill properties or None
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (s:Skill {name: $name})
                WHERE COALESCE(s.is_deprecated, false) = false
                RETURN properties(s) AS props
                """,
                name=skill_name,
            )
            record = result.single()
            if record:
                return dict(record["props"])
            return None

    def list_skills(
        self,
        include_deprecated: bool = False,
        limit: int = 100,
    ) -> list[dict]:
        """List all skills.

        Args:
            include_deprecated: Include deprecated skills
            limit: Maximum results

        Returns:
            List of skill property dicts
        """
        with self.driver.session(database=self.database) as session:
            if include_deprecated:
                result = session.run(
                    """
                    MATCH (s:Skill)
                    RETURN properties(s) AS props
                    ORDER BY s.q_value DESC
                    LIMIT $limit
                    """,
                    limit=limit,
                )
            else:
                result = session.run(
                    """
                    MATCH (s:Skill)
                    WHERE COALESCE(s.is_deprecated, false) = false
                    RETURN properties(s) AS props
                    ORDER BY s.q_value DESC
                    LIMIT $limit
                    """,
                    limit=limit,
                )

            return [dict(record["props"]) for record in result]

    def update_skill(
        self,
        skill_id: str,
        updates: dict,
    ) -> bool:
        """Update skill properties.

        Args:
            skill_id: Skill ID
            updates: Dict of properties to update

        Returns:
            True if updated
        """
        if not updates:
            return False

        now = datetime.now(timezone.utc).isoformat()
        updates["updated_at"] = now

        with self.driver.session(database=self.database) as session:
            set_clauses = ", ".join([f"s.{k} = ${k}" for k in updates.keys()])
            params = {"skill_id": skill_id, **updates}

            result = session.run(
                f"""
                MATCH (s:Skill {{id: $skill_id}})
                SET {set_clauses}
                RETURN s.id AS id
                """,
                **params,
            )

            return result.single() is not None
