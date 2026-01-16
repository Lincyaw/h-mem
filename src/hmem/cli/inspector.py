"""Diagnostic tools for debugging memory system.

Provides interactive tools for visualizing and tracing memory operations:
- show_graph(): Display entity relationship graph as ASCII tree
- trace_consolidation(): Show consolidation history for a session
"""

from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger()


class MemoryInspector:
    """Interactive debugger for memory system.

    Example:
        >>> from hmem.core.memory_system import MemorySystem
        >>> memory = MemorySystem()
        >>> inspector = MemoryInspector(memory)
        >>> inspector.show_graph("Alice")
        Alice
        ├── PREFERS → DarkMode (weight: 0.9)
        ├── LIVES_IN → Beijing (weight: 1.0)
        └── WORKS_AT → TechCorp (weight: 0.8)
    """

    def __init__(self, memory_system: Any = None) -> None:
        """Initialize inspector.

        Args:
            memory_system: MemorySystem instance to inspect
        """
        self._memory_system = memory_system

    def set_memory_system(self, memory_system: Any) -> None:
        """Set the memory system to inspect.

        Args:
            memory_system: MemorySystem instance
        """
        self._memory_system = memory_system

    def _get_semantic_store(self) -> Any:
        """Get semantic store from memory system."""
        if self._memory_system is None:
            raise ValueError(
                "No memory system configured. Call set_memory_system() first."
            )
        return self._memory_system._semantic_store

    def _get_episodic_store(self) -> Any:
        """Get episodic store from memory system."""
        if self._memory_system is None:
            raise ValueError(
                "No memory system configured. Call set_memory_system() first."
            )
        return self._memory_system._episodic_store

    def _get_event_log(self) -> Any:
        """Get event log from memory system."""
        if self._memory_system is None:
            raise ValueError(
                "No memory system configured. Call set_memory_system() first."
            )
        return self._memory_system._event_log

    def show_graph(self, entity: str, depth: int = 2) -> str:
        """Show entity's relationship graph as ASCII tree.

        Traverses the semantic graph starting from the given entity
        and renders relationships as a tree structure.

        Args:
            entity: Root entity name to start traversal
            depth: Maximum traversal depth (default: 2)

        Returns:
            ASCII tree representation of the entity graph

        Example output:
            Alice
            ├── PREFERS → DarkMode (weight: 0.9, v1)
            │   └── CATEGORY → UIPreference (weight: 1.0, v1)
            ├── LIVES_IN → Beijing (weight: 1.0, v1)
            └── WORKS_AT → TechCorp (weight: 0.8, v2)
                └── LOCATED_IN → Shanghai (weight: 1.0, v1)
        """
        semantic_store = self._get_semantic_store()

        # Build graph from Neo4j
        relationships = self._fetch_entity_relationships(semantic_store, entity, depth)

        if not relationships:
            return f"{entity}\n└── (no relationships found)"

        # Render as ASCII tree
        lines = [entity]
        lines.extend(self._render_tree(relationships, depth=0, max_depth=depth))

        result = "\n".join(lines)
        logger.debug(
            "show_graph_complete", entity=entity, depth=depth, lines=len(lines)
        )
        return result

    def _fetch_entity_relationships(
        self, store: Any, entity: str, max_depth: int
    ) -> list[dict[str, Any]]:
        """Fetch relationships for an entity from Neo4j.

        Args:
            store: Neo4j semantic store
            entity: Entity name
            max_depth: Maximum depth to traverse

        Returns:
            List of relationship dictionaries
        """
        relationships: list[dict[str, Any]] = []

        try:
            with store.driver.session(database=store.database) as session:
                # Query outgoing relationships
                result = session.run(
                    """
                    MATCH (s:Entity {name: $entity})-[r:RELATION]->(o:Entity)
                    WHERE r.is_superseded = false
                    RETURN r.predicate AS predicate,
                           o.name AS target,
                           r.weight AS weight,
                           r.version AS version,
                           r.fact_id AS fact_id,
                           r.access_count AS access_count
                    ORDER BY r.weight DESC
                    """,
                    entity=entity,
                )

                for record in result:
                    rel = {
                        "predicate": record["predicate"],
                        "target": record["target"],
                        "weight": record["weight"],
                        "version": record["version"],
                        "fact_id": record["fact_id"],
                        "access_count": record["access_count"] or 0,
                        "children": [],
                    }

                    # Recursively fetch children if depth allows
                    if max_depth > 1:
                        rel["children"] = self._fetch_entity_relationships(
                            store, record["target"], max_depth - 1
                        )

                    relationships.append(rel)

        except Exception as e:
            logger.warning("fetch_relationships_failed", entity=entity, error=str(e))

        return relationships

    def _render_tree(
        self,
        relationships: list[dict[str, Any]],
        depth: int = 0,
        max_depth: int = 2,
        prefix: str = "",
    ) -> list[str]:
        """Render relationships as ASCII tree lines.

        Args:
            relationships: List of relationship dicts
            depth: Current depth
            max_depth: Maximum depth
            prefix: Prefix for indentation

        Returns:
            List of formatted lines
        """
        lines: list[str] = []

        for i, rel in enumerate(relationships):
            is_last = i == len(relationships) - 1
            connector = "└── " if is_last else "├── "
            child_prefix = prefix + ("    " if is_last else "│   ")

            # Format: PREDICATE → Target (weight: X.XX, vN)
            weight_str = f"{rel['weight']:.2f}" if rel["weight"] else "?"
            version_str = f"v{rel['version']}" if rel["version"] else "v?"
            access_str = (
                f", accessed: {rel['access_count']}" if rel["access_count"] > 0 else ""
            )

            line = (
                f"{prefix}{connector}{rel['predicate']} → {rel['target']} "
                f"(weight: {weight_str}, {version_str}{access_str})"
            )
            lines.append(line)

            # Render children
            if rel.get("children") and depth < max_depth:
                child_lines = self._render_tree(
                    rel["children"],
                    depth=depth + 1,
                    max_depth=max_depth,
                    prefix=child_prefix,
                )
                lines.extend(child_lines)

        return lines

    def trace_consolidation(self, session_id: str) -> str:
        """Show consolidation trace for a session.

        Displays the complete processing history of a session including:
        - Raw events stored in event log
        - Extracted episodic memories
        - Derived semantic triples
        - Induced principles (if any)

        Args:
            session_id: Session ID to trace

        Returns:
            Formatted trace output

        Example output:
            === Consolidation Trace: session_001 ===

            [1] Event Log Entries (2)
                • [conversation] conv_abc123: "My name is Alice..."
                • [conversation] conv_def456: "I prefer dark mode..."

            [2] Episodic Memories (3)
                • evt_001: "User mentioned name Alice" (score: 0.95)
                • evt_002: "User preference for dark mode" (score: 0.88)

            [3] Semantic Triples (2)
                • User NAMED Alice (weight: 1.0, v1)
                • User PREFERS DarkMode (weight: 0.9, v1)

            [4] Principles (0)
                (none induced yet)
        """
        lines: list[str] = []
        lines.append(f"=== Consolidation Trace: {session_id} ===")
        lines.append("")

        # 1. Event Log entries
        event_log = self._get_event_log()
        log_entries = event_log.get_session_events(session_id)

        lines.append(f"[1] Event Log Entries ({len(log_entries)})")
        if log_entries:
            for entry in log_entries[:10]:  # Limit to first 10
                content_preview = (
                    str(entry)[:60] + "..." if len(str(entry)) > 60 else str(entry)
                )
                lines.append(f"    • {content_preview}")
        else:
            lines.append("    (no entries)")
        lines.append("")

        # 2. Episodic Memories
        episodic_store = self._get_episodic_store()
        episodic_memories = self._search_episodic_by_session(episodic_store, session_id)

        lines.append(f"[2] Episodic Memories ({len(episodic_memories)})")
        if episodic_memories:
            for mem in episodic_memories[:10]:
                content_preview = (
                    mem["content"][:50] + "..."
                    if len(mem["content"]) > 50
                    else mem["content"]
                )
                lines.append(f'    • {mem["id"]}: "{content_preview}"')
        else:
            lines.append("    (no memories)")
        lines.append("")

        # 3. Semantic Triples
        semantic_store = self._get_semantic_store()
        triples = self._search_semantic_by_session(semantic_store, session_id)

        lines.append(f"[3] Semantic Triples ({len(triples)})")
        if triples:
            for triple in triples[:10]:
                lines.append(
                    f"    • {triple['subject']} {triple['predicate']} {triple['object']} "
                    f"(weight: {triple['weight']:.1f}, v{triple['version']})"
                )
        else:
            lines.append("    (no triples)")
        lines.append("")

        # 4. Principles
        principles = self._get_principles_by_session(session_id)

        lines.append(f"[4] Principles ({len(principles)})")
        if principles:
            for p in principles[:5]:
                content_preview = (
                    p["content"][:50] + "..."
                    if len(p["content"]) > 50
                    else p["content"]
                )
                lines.append(
                    f'    • {p["id"]}: "{content_preview}" (confidence: {p["confidence"]:.2f})'
                )
        else:
            lines.append("    (none induced yet)")

        result = "\n".join(lines)
        logger.debug(
            "trace_consolidation_complete",
            session_id=session_id,
            events=len(log_entries),
            episodic=len(episodic_memories),
            semantic=len(triples),
        )
        return result

    def _search_episodic_by_session(
        self, store: Any, session_id: str
    ) -> list[dict[str, Any]]:
        """Search episodic memories by session ID.

        Args:
            store: ChromaDB episodic store
            session_id: Session to search

        Returns:
            List of memory dictionaries
        """
        memories: list[dict[str, Any]] = []

        try:
            # Query ChromaDB with metadata filter
            result = store.collection.get(
                where={"session_id": session_id},
                include=["documents", "metadatas"],
            )

            ids = result.get("ids", [])
            documents = result.get("documents", [])
            metadatas = result.get("metadatas", [])

            for i, doc_id in enumerate(ids):
                memories.append(
                    {
                        "id": doc_id,
                        "content": documents[i] if documents else "",
                        "metadata": metadatas[i] if metadatas else {},
                    }
                )

        except Exception as e:
            logger.warning(
                "search_episodic_failed", session_id=session_id, error=str(e)
            )

        return memories

    def _search_semantic_by_session(
        self, store: Any, session_id: str
    ) -> list[dict[str, Any]]:
        """Search semantic triples by session ID.

        Args:
            store: Neo4j semantic store
            session_id: Session to search

        Returns:
            List of triple dictionaries
        """
        triples: list[dict[str, Any]] = []

        try:
            with store.driver.session(database=store.database) as session:
                # Query triples that reference this session in parent_ids
                result = session.run(
                    """
                    MATCH (s:Entity)-[r:RELATION]->(o:Entity)
                    WHERE r.is_superseded = false
                          AND r.parent_ids CONTAINS $session_id
                    RETURN s.name AS subject,
                           r.predicate AS predicate,
                           o.name AS object,
                           r.weight AS weight,
                           r.version AS version,
                           r.fact_id AS fact_id
                    ORDER BY r.created_at DESC
                    LIMIT 20
                    """,
                    session_id=session_id,
                )

                for record in result:
                    triples.append(
                        {
                            "subject": record["subject"],
                            "predicate": record["predicate"],
                            "object": record["object"],
                            "weight": record["weight"],
                            "version": record["version"],
                            "fact_id": record["fact_id"],
                        }
                    )

        except Exception as e:
            logger.warning(
                "search_semantic_failed", session_id=session_id, error=str(e)
            )

        return triples

    def _get_principles_by_session(self, session_id: str) -> list[dict[str, Any]]:
        """Get principles derived from a session.

        Args:
            session_id: Session to search

        Returns:
            List of principle dictionaries
        """
        principles: list[dict[str, Any]] = []

        try:
            semantic_store = self._get_semantic_store()

            with semantic_store.driver.session(
                database=semantic_store.database
            ) as session:
                # Query principle nodes that reference this session
                result = session.run(
                    """
                    MATCH (p:Principle)
                    WHERE p.parent_ids CONTAINS $session_id
                    RETURN p.id AS id,
                           p.content AS content,
                           p.confidence AS confidence,
                           p.evidence_count AS evidence_count
                    ORDER BY p.created_at DESC
                    LIMIT 10
                    """,
                    session_id=session_id,
                )

                for record in result:
                    principles.append(
                        {
                            "id": record["id"],
                            "content": record["content"],
                            "confidence": record["confidence"] or 0.0,
                            "evidence_count": record["evidence_count"] or 0,
                        }
                    )

        except Exception as e:
            # Principles may not exist yet - this is not an error
            logger.debug("get_principles_failed", session_id=session_id, error=str(e))

        return principles

    def get_memory_stats(self) -> dict[str, Any]:
        """Get comprehensive memory system statistics.

        Returns:
            Dictionary with statistics from all stores
        """
        if self._memory_system is None:
            return {"error": "No memory system configured"}

        stats: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
        }

        # Episodic store stats
        try:
            episodic = self._get_episodic_store()
            stats["episodic"] = {
                "total_count": episodic.count(),
                "health": episodic.health_check(),
            }
        except Exception as e:
            stats["episodic"] = {"error": str(e)}

        # Semantic store stats
        try:
            semantic = self._get_semantic_store()
            stats["semantic"] = semantic.get_stats()
        except Exception as e:
            stats["semantic"] = {"error": str(e)}

        # Skill store stats
        try:
            skill = self._memory_system._skill_store
            stats["skill"] = skill.get_stats()
        except Exception as e:
            stats["skill"] = {"error": str(e)}

        # Event log stats
        try:
            event_log = self._get_event_log()
            stats["event_log"] = event_log.count()
        except Exception as e:
            stats["event_log"] = {"error": str(e)}

        return stats

    def explain_memory(self, memory_id: str) -> str:
        """Explain a memory's provenance and usage history.

        Args:
            memory_id: Memory ID to explain

        Returns:
            Formatted explanation of the memory
        """
        lines: list[str] = []
        lines.append(f"=== Memory Explanation: {memory_id} ===")
        lines.append("")

        # Get lineage
        if self._memory_system:
            try:
                lineage = self._memory_system.get_lineage(memory_id, max_depth=5)
                lines.append("[Provenance Chain]")
                if lineage:
                    for i, ancestor_id in enumerate(lineage):
                        indent = "  " * (i + 1)
                        lines.append(f"{indent}↑ {ancestor_id}")
                else:
                    lines.append("  (no ancestors - this is a root memory)")
                lines.append("")

                # Get derived memories
                derived = self._memory_system.get_derived(memory_id)
                lines.append("[Derived Memories]")
                if derived:
                    for mem in derived[:5]:
                        lines.append(f"  ↓ {mem.id}: {mem.content[:40]}...")
                else:
                    lines.append("  (no derived memories)")

            except Exception as e:
                lines.append(f"[Error] Could not trace memory: {e}")

        return "\n".join(lines)
