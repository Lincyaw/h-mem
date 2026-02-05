"""Unified Neo4j storage supporting all memory types with complete provenance chain.

This is a major refactoring to replace the old three-store architecture (ChromaDB + Neo4j + SQLite)
with a single Neo4j store that handles all memory types with complete provenance tracking.

Graph Schema:
    Nodes:
        (:Conversation {id, session_id, created_at, metadata_json})
        (:Event {id, content, outcome, tags, embedding, created_at, metadata_json, q_value, q_update_count})
        (:Fact {id, subject, predicate, object, weight, version, embedding, is_superseded, created_at, updated_at, source_role, importance, confidence, q_value, q_update_count})
        (:Principle {id, content, evidence_count, confidence, embedding, created_at, q_value, q_update_count, is_deprecated, version})
        (:Skill {id, name, trigger_pattern, code_template_json, description, tags, embedding, created_at, updated_at, q_value, q_update_count, is_deprecated, version})

    Relationships:
        (:Conversation)-[:HAS_EVENT]->(:Event)
        (:Event)-[:GENERATES]->(:Fact)
        (:Event)-[:INDUCES]->(:Principle)
        (:Event)-[:INDUCES]->(:Skill)
        (:Fact)-[:SUPERSEDED_BY]->(:Fact)
        (:Principle)-[:SUPERSEDED_BY]->(:Principle)

Features:
    - Complete provenance chain from raw conversations to derived knowledge
    - Vector similarity search for all memory types
    - Fulltext search across content
    - Q-value based learning (MemRL integration)
    - Conflict detection and resolution for facts
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
    Event,
    Conversation,
    SemanticTriple,
    Principle,
    Skill,
    IndexProfile,
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
        password: str = "password",
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
                "CREATE CONSTRAINT evt_id_unique IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE",
                "CREATE CONSTRAINT fact_id_unique IF NOT EXISTS FOR (f:Fact) REQUIRE f.id IS UNIQUE",
                "CREATE CONSTRAINT prin_id_unique IF NOT EXISTS FOR (p:Principle) REQUIRE p.id IS UNIQUE",
                "CREATE CONSTRAINT skill_id_unique IF NOT EXISTS FOR (s:Skill) REQUIRE s.id IS UNIQUE",
            ]

            for constraint in constraints:
                try:
                    session.run(constraint)
                except Neo4jError as e:
                    logger.debug("constraint_creation_skipped", error=str(e))

            # Create vector indexes for similarity search (1536 dims, cosine)
            vector_indexes = [
                ("event_embedding_idx", "Event", "embedding"),
                ("fact_embedding_idx", "Fact", "embedding"),
                ("principle_embedding_idx", "Principle", "embedding"),
                ("skill_embedding_idx", "Skill", "embedding"),
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

            # Create fulltext index across all content
            try:
                session.run(
                    """
                    CREATE FULLTEXT INDEX unified_content_fulltext IF NOT EXISTS
                    FOR (e:Event|f:Fact|p:Principle|s:Skill)
                    ON EACH [
                        e.content,
                        f.subject, f.predicate, f.object,
                        p.content,
                        s.name, s.description
                    ]
                    """
                )
            except Neo4jError as e:
                logger.debug("fulltext_index_creation_skipped", error=str(e))

            logger.info("neo4j_unified_schema_initialized", database=self.database)

    def add_conversation(self, conv: Conversation) -> str:
        """Store a Conversation node.

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
                CREATE (c:Conversation {
                    id: $id,
                    session_id: $session_id,
                    created_at: $created_at,
                    metadata_json: $metadata_json
                })
                """,
                id=conv_id,
                session_id=conv.session_id,
                created_at=now,
                metadata_json=json.dumps(conv.metadata),
            )

        logger.debug("conversation_stored", conv_id=conv_id, session_id=conv.session_id)
        return conv_id

    def add_event(self, event: Event, parent_conv_id: str) -> str:
        """Store Event node and create HAS_EVENT relationship to parent conversation.

        Args:
            event: Event object to store
            parent_conv_id: Parent conversation ID

        Returns:
            Event ID (generated if not provided)
        """
        event_id = event.id or f"evt_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        # Note: embedding should be generated by caller and passed in event.metadata
        embedding = event.metadata.get("embedding")

        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MATCH (c:Conversation {id: $parent_conv_id})
                CREATE (e:Event {
                    id: $id,
                    content: $content,
                    outcome: $outcome,
                    tags: $tags,
                    embedding: $embedding,
                    created_at: $created_at,
                    metadata_json: $metadata_json,
                    q_value: $q_value,
                    q_update_count: $q_update_count
                })
                CREATE (c)-[:HAS_EVENT]->(e)
                """,
                parent_conv_id=parent_conv_id,
                id=event_id,
                content=event.content,
                outcome=event.outcome,
                tags=event.tags,
                embedding=embedding,
                created_at=event.timestamp.isoformat() if event.timestamp else now,
                metadata_json=json.dumps(event.metadata),
                q_value=0.5,
                q_update_count=0,
            )

        logger.debug("event_stored", event_id=event_id, parent_conv_id=parent_conv_id)
        return event_id

    def add_fact(self, fact: SemanticTriple, parent_event_ids: list[str]) -> str:
        """Store Fact node and create GENERATES relationships from parent events.

        Handles conflict detection: if same (subject, predicate) exists with different object,
        marks old fact as superseded and creates new version.

        Args:
            fact: SemanticTriple to store
            parent_event_ids: List of parent event IDs

        Returns:
            Fact ID (generated if not provided)
        """
        fact_id = fact.id or f"fact_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        # Check for conflicts
        has_conflict, conflicts = self.check_fact_conflict(
            fact.subject, fact.predicate, fact.object
        )

        with self.driver.session(database=self.database) as session:
            if has_conflict:
                # Mark old facts as superseded
                for old_fact in conflicts:
                    session.run(
                        """
                        MATCH (f:Fact {id: $old_id})
                        SET f.is_superseded = true,
                            f.updated_at = $now
                        """,
                        old_id=old_fact["id"],
                        now=now,
                    )

            # Note: embedding should be generated by caller and passed in fact.metadata
            embedding = (
                fact.index_profile.q_value if hasattr(fact, "index_profile") else None
            )
            if isinstance(embedding, float):
                embedding = None  # Placeholder until proper embedding is provided

            # Create new fact
            session.run(
                """
                MERGE (e:Event)
                WHERE e.id IN $parent_event_ids
                WITH collect(e) AS events
                CREATE (f:Fact {
                    id: $id,
                    subject: $subject,
                    predicate: $predicate,
                    object: $object,
                    weight: $weight,
                    version: $version,
                    embedding: $embedding,
                    is_superseded: false,
                    created_at: $created_at,
                    updated_at: $updated_at,
                    source_role: $source_role,
                    importance: $importance,
                    confidence: $confidence,
                    q_value: $q_value,
                    q_update_count: $q_update_count
                })
                WITH f, events
                UNWIND events AS evt
                CREATE (evt)-[:GENERATES]->(f)
                """,
                parent_event_ids=parent_event_ids,
                id=fact_id,
                subject=fact.subject,
                predicate=fact.predicate,
                object=fact.object,
                weight=fact.weight,
                version=fact.version,
                embedding=embedding,
                created_at=fact.created_at.isoformat() if fact.created_at else now,
                updated_at=fact.updated_at.isoformat() if fact.updated_at else now,
                source_role=fact.source_role,
                importance=fact.importance,
                confidence=fact.confidence,
                q_value=fact.index_profile.q_value if fact.index_profile else 0.5,
                q_update_count=fact.index_profile.q_update_count
                if fact.index_profile
                else 0,
            )

        logger.debug(
            "fact_stored",
            fact_id=fact_id,
            subject=fact.subject,
            predicate=fact.predicate,
            conflict_resolved=has_conflict,
        )
        return fact_id

    def add_principle(self, principle: Principle, evidence_event_ids: list[str]) -> str:
        """Store Principle node and create INDUCES relationships from evidence events.

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
                MERGE (e:Event)
                WHERE e.id IN $evidence_event_ids
                WITH collect(e) AS events
                CREATE (p:Principle {
                    id: $id,
                    content: $content,
                    evidence_count: $evidence_count,
                    confidence: $confidence,
                    embedding: $embedding,
                    created_at: $created_at,
                    q_value: $q_value,
                    q_update_count: $q_update_count,
                    is_deprecated: $is_deprecated,
                    version: $version
                })
                WITH p, events
                UNWIND events AS evt
                CREATE (evt)-[:INDUCES]->(p)
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

    def add_skill(self, skill: Skill, source_event_ids: list[str]) -> str:
        """Store Skill node and create INDUCES relationships from source events.

        Args:
            skill: Skill to store
            source_event_ids: List of source event IDs

        Returns:
            Skill ID (generated if not provided)
        """
        skill_id = skill.id or f"skill_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        # Note: embedding should be generated by caller and stored in metadata
        embedding = skill.metadata.get("embedding")

        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MERGE (e:Event)
                WHERE e.id IN $source_event_ids
                WITH collect(e) AS events
                CREATE (s:Skill {
                    id: $id,
                    name: $name,
                    trigger_pattern: $trigger_pattern,
                    code_template_json: $code_template_json,
                    description: $description,
                    tags: $tags,
                    embedding: $embedding,
                    created_at: $created_at,
                    updated_at: $updated_at,
                    q_value: $q_value,
                    q_update_count: $q_update_count,
                    is_deprecated: $is_deprecated,
                    version: $version
                })
                WITH s, events
                UNWIND events AS evt
                CREATE (evt)-[:INDUCES]->(s)
                """,
                source_event_ids=source_event_ids,
                id=skill_id,
                name=skill.name,
                trigger_pattern=skill.trigger_pattern,
                code_template_json=json.dumps(skill.code_template),
                description=skill.description,
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

        logger.debug(
            "skill_stored",
            skill_id=skill_id,
            name=skill.name,
        )
        return skill_id

    def vector_search(
        self,
        query_embedding: list[float],
        node_type: str,
        limit: int = 10,
    ) -> list[Memory]:
        """Vector similarity search using Neo4j vector index.

        Args:
            query_embedding: Query embedding vector (1536 dims)
            node_type: Node type to search ("Event", "Fact", "Principle", "Skill")
            limit: Maximum results

        Returns:
            List of Memory objects with similarity scores
        """
        # Map node type to index name
        index_map = {
            "Event": "event_embedding_idx",
            "Fact": "fact_embedding_idx",
            "Principle": "principle_embedding_idx",
            "Skill": "skill_embedding_idx",
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

        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    CALL db.index.fulltext.queryNodes('unified_content_fulltext', $search_query)
                    YIELD node, score
                    WITH node, score,
                         CASE
                           WHEN 'Event' IN labels(node) THEN 'Event'
                           WHEN 'Fact' IN labels(node) THEN 'Fact'
                           WHEN 'Principle' IN labels(node) THEN 'Principle'
                           WHEN 'Skill' IN labels(node) THEN 'Skill'
                           ELSE 'Unknown'
                         END AS node_type
                    WHERE $node_types IS NULL OR node_type IN $node_types
                    RETURN node, score, node_type
                    ORDER BY score DESC
                    LIMIT $limit
                    """,
                    search_query=query,
                    node_types=node_types,
                    limit=limit,
                )

                memories = []
                for record in result:
                    node = record["node"]
                    score = record["score"]
                    node_type = record["node_type"]
                    memory = self._node_to_memory(node, score, node_type)
                    if memory:
                        memories.append(memory)

                return memories

            except Neo4jError as e:
                logger.error("fulltext_search_failed", error=str(e))
                return []

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
                "Event": "episodic",
                "Fact": "semantic",
                "Principle": "principle",
                "Skill": "skill",
            }
            source: Literal["episodic", "semantic", "skill", "principle"] = (
                source_map.get(node_type, "episodic")
            )

            # Extract content based on node type
            if node_type == "Event":
                content = node_props.get("content", "")
            elif node_type == "Fact":
                content = f"{node_props.get('subject', '')} {node_props.get('predicate', '')} {node_props.get('object', '')}"
            elif node_type == "Principle":
                content = node_props.get("content", "")
            elif node_type == "Skill":
                content = (
                    f"{node_props.get('name', '')}: {node_props.get('description', '')}"
                )
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
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH path = (n)-[*1..$max_depth]->(ancestor)
                WHERE n.id = $node_id
                WITH nodes(path) AS node_list, relationships(path) AS rel_list
                UNWIND range(0, size(node_list)-1) AS i
                RETURN node_list[i] AS node,
                       CASE WHEN i < size(rel_list) THEN type(rel_list[i]) ELSE null END AS rel_type,
                       labels(node_list[i]) AS labels
                """,
                node_id=node_id,
                max_depth=max_depth,
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

    def check_fact_conflict(
        self,
        subject: str,
        predicate: str,
        new_object: str,
    ) -> tuple[bool, list[dict]]:
        """Check for conflicting facts.

        A conflict exists when same (subject, predicate) has different object.

        Args:
            subject: Subject of the triple
            predicate: Predicate (relationship)
            new_object: New object value

        Returns:
            Tuple of (has_conflict, list of conflicting fact dicts)
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (f:Fact)
                WHERE f.subject = $subject
                  AND f.predicate = $predicate
                  AND f.object <> $new_object
                  AND f.is_superseded = false
                RETURN f.id AS id, f.subject AS subject, f.predicate AS predicate,
                       f.object AS object, f.weight AS weight, f.version AS version
                """,
                subject=subject,
                predicate=predicate,
                new_object=new_object,
            )

            conflicts = []
            for record in result:
                conflicts.append(
                    {
                        "id": record["id"],
                        "subject": record["subject"],
                        "predicate": record["predicate"],
                        "object": record["object"],
                        "weight": record["weight"],
                        "version": record["version"],
                    }
                )

            return len(conflicts) > 0, conflicts

    def resolve_fact_conflict(
        self,
        subject: str,
        predicate: str,
        old_object: str,
        new_object: str,
        parent_ids: list[str] | None = None,
    ) -> int:
        """Resolve fact conflict by superseding old fact.

        Args:
            subject: Subject of the triple
            predicate: Predicate
            old_object: Old object to supersede
            new_object: New object value
            parent_ids: Parent IDs for the new fact

        Returns:
            Number of conflicts resolved
        """
        new_fact_id = f"fact_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (old:Fact)
                WHERE old.subject = $subject
                  AND old.predicate = $predicate
                  AND old.object = $old_object
                  AND old.is_superseded = false
                SET old.is_superseded = true,
                    old.weight = old.weight * 0.5,
                    old.updated_at = $now
                WITH count(old) AS resolved
                CREATE (new:Fact {
                    id: $new_fact_id,
                    subject: $subject,
                    predicate: $predicate,
                    object: $new_object,
                    weight: 1.0,
                    version: 1,
                    embedding: null,
                    is_superseded: false,
                    created_at: $now,
                    updated_at: $now,
                    source_role: null,
                    importance: 3,
                    confidence: 1.0,
                    q_value: 0.5,
                    q_update_count: 0
                })
                RETURN resolved
                """,
                subject=subject,
                predicate=predicate,
                old_object=old_object,
                new_object=new_object,
                new_fact_id=new_fact_id,
                now=now,
            )

            record = result.single()
            conflicts_resolved = record["resolved"] if record else 0

            logger.info(
                "fact_conflict_resolved",
                subject=subject,
                predicate=predicate,
                old_object=old_object,
                new_object=new_object,
            )

            return conflicts_resolved

    def get_stats(self) -> dict[str, Any]:
        """Get statistics for all node types.

        Returns:
            Dictionary with counts for each node type
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (c:Conversation)
                WITH count(c) AS conversations
                MATCH (e:Event)
                WITH conversations, count(e) AS events
                MATCH (f:Fact)
                WITH conversations, events, count(f) AS facts,
                     sum(CASE WHEN f.is_superseded = false THEN 1 ELSE 0 END) AS active_facts
                MATCH (p:Principle)
                WITH conversations, events, facts, active_facts, count(p) AS principles,
                     sum(CASE WHEN p.is_deprecated = false THEN 1 ELSE 0 END) AS active_principles
                MATCH (s:Skill)
                WITH conversations, events, facts, active_facts, principles, active_principles, count(s) AS skills,
                     sum(CASE WHEN s.is_deprecated = false THEN 1 ELSE 0 END) AS active_skills
                RETURN conversations, events, facts, active_facts, principles, active_principles, skills, active_skills
                """
            )

            record = result.single()
            if not record:
                return {
                    "conversations": 0,
                    "events": 0,
                    "facts": 0,
                    "active_facts": 0,
                    "principles": 0,
                    "active_principles": 0,
                    "skills": 0,
                    "active_skills": 0,
                }

            return {
                "conversations": record["conversations"],
                "events": record["events"],
                "facts": record["facts"],
                "active_facts": record["active_facts"],
                "principles": record["principles"],
                "active_principles": record["active_principles"],
                "skills": record["skills"],
                "active_skills": record["active_skills"],
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

    # Convenience methods for backward compatibility

    def prune_low_weight(self, threshold: float = 0.3) -> int:
        """Mark low-weight facts as superseded.

        Args:
            threshold: Minimum weight threshold

        Returns:
            Number of facts pruned
        """
        now = datetime.now(timezone.utc).isoformat()

        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (f:Fact)
                WHERE f.weight < $threshold AND f.is_superseded = false
                SET f.is_superseded = true, f.updated_at = $now
                RETURN count(f) AS pruned
                """,
                threshold=threshold,
                now=now,
            )

            record = result.single()
            pruned = record["pruned"] if record else 0

            logger.info("facts_pruned", count=pruned, threshold=threshold)
            return pruned

    def apply_decay(self, decay_factor: float = 0.99, min_weight: float = 0.1) -> int:
        """Apply weight decay to all active facts.

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
                MATCH (f:Fact)
                WHERE f.weight > $min_weight AND f.is_superseded = false
                SET f.weight = f.weight * $decay_factor, f.updated_at = $now
                RETURN count(f) AS decayed
                """,
                decay_factor=decay_factor,
                min_weight=min_weight,
                now=now,
            )

            record = result.single()
            return record["decayed"] if record else 0

    def search(self, query: str, limit: int = 10) -> list[Memory]:
        """Combined fulltext search across all node types (backward compat with SemanticStoreProtocol).

        Args:
            query: Query text
            limit: Maximum results

        Returns:
            List of Memory objects
        """
        return self.fulltext_search(query, node_types=None, limit=limit)

    def get_node_properties(self, node_id: str, node_type: str) -> dict | None:
        """Get properties of a specific node.

        Args:
            node_id: Node ID
            node_type: Type of node (Event, Fact, Principle, Skill)

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

    def count(self) -> int:
        """Get total count of all memory nodes (for backward compat).

        Returns:
            Total count of Event + Fact + Principle + Skill nodes
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (n)
                WHERE n:Event OR n:Fact OR n:Principle OR n:Skill
                RETURN count(n) AS total
                """
            )
            record = result.single()
            return record["total"] if record else 0

    def add_or_update(
        self,
        triple: SemanticTriple,
        parent_ids: list[str] | None = None,
    ) -> tuple[bool, int]:
        """Add or update fact with conflict handling (backward compat with SemanticStoreProtocol).

        Args:
            triple: Semantic triple to add/update
            parent_ids: Parent event IDs

        Returns:
            Tuple of (was_conflict, conflicts_resolved)
        """
        has_conflict, conflicts = self.check_fact_conflict(
            triple.subject, triple.predicate, triple.object
        )

        if has_conflict:
            conflicts_resolved = 0
            for conflict in conflicts:
                resolved = self.resolve_fact_conflict(
                    triple.subject,
                    triple.predicate,
                    conflict["object"],
                    triple.object,
                    parent_ids,
                )
                conflicts_resolved += resolved

            return True, conflicts_resolved
        else:
            self.add_fact(triple, parent_ids or [])
            return False, 0
