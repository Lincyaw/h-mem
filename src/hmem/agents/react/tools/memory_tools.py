"""Memory tools for the ReAct Agent Loop.

These tools wrap Neo4j storage operations for use in the ReAct agent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from hmem.agents.react.errors import ToolError
from hmem.agents.react.tool_base import BaseTool, ToolConfig, ToolSchema

if TYPE_CHECKING:
    from hmem.storage.neo4j_unified import Neo4jUnifiedStore


class MemoryVectorSearchTool(BaseTool[list[dict[str, Any]]]):
    """Vector similarity search for memories.

    Searches for semantically similar memories using embedding vectors.
    Supports searching across different memory types (Fact, Principle, Skill, etc.).
    """

    def __init__(
        self,
        store: Neo4jUnifiedStore,
        config: ToolConfig | None = None,
    ) -> None:
        super().__init__(
            name="memory_vector_search",
            description="Search for semantically similar memories using embedding vectors. Requires a query embedding.",
            config=config,
        )
        self.store = store

    def run(
        self,
        query_embedding: list[float],
        node_type: str = "Fact",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for similar memories by embedding.

        Args:
            query_embedding: Query embedding vector (1536 dims)
            node_type: Node type to search ("Fact", "Principle", "Skill", "Entity", "Process")
            limit: Maximum number of results

        Returns:
            List of memory dicts with id, content, score, source
        """
        valid_types = {"Fact", "Principle", "Skill", "Entity", "Process"}
        if node_type not in valid_types:
            raise ToolError(
                message=f"Invalid node_type '{node_type}'. Must be one of: {valid_types}",
                tool_name=self.name,
            )

        try:
            memories = self.store.vector_search(
                query_embedding=query_embedding,
                node_type=node_type,
                limit=limit,
            )
            return [
                {
                    "id": m.id,
                    "content": m.content,
                    "score": m.score,
                    "source": m.source,
                    "metadata": m.metadata,
                }
                for m in memories
            ]
        except Exception as e:
            raise ToolError(
                message=f"Vector search failed: {e}",
                tool_name=self.name,
            ) from e

    def classify_error(self, error: Exception) -> Literal["retriable", "fatal"]:
        """Neo4j connection errors are retriable."""
        error_str = str(error).lower()
        if any(p in error_str for p in ["connection", "timeout", "unavailable"]):
            return "retriable"
        return "fatal"

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "query_embedding": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Query embedding vector (1536 dimensions)",
                },
                "node_type": {
                    "type": "string",
                    "enum": ["Fact", "Principle", "Skill", "Entity", "Process"],
                    "description": "Type of memory to search",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default 10)",
                },
            },
            required=["query_embedding"],
        )


class MemoryFulltextSearchTool(BaseTool[list[dict[str, Any]]]):
    """Fulltext search for memories.

    Searches for memories containing specific keywords or phrases.
    Supports searching across multiple memory types simultaneously.
    """

    def __init__(
        self,
        store: Neo4jUnifiedStore,
        config: ToolConfig | None = None,
    ) -> None:
        super().__init__(
            name="memory_fulltext_search",
            description="Search for memories containing specific keywords or phrases.",
            config=config,
        )
        self.store = store

    def run(
        self,
        query: str,
        node_types: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for memories by keyword.

        Args:
            query: Search query text
            node_types: Node types to search (None = all types)
            limit: Maximum number of results

        Returns:
            List of memory dicts with id, content, score, source
        """
        if not query or not query.strip():
            return []

        try:
            memories = self.store.fulltext_search(
                query=query,
                node_types=node_types,
                limit=limit,
            )
            return [
                {
                    "id": m.id,
                    "content": m.content,
                    "score": m.score,
                    "source": m.source,
                    "metadata": m.metadata,
                }
                for m in memories
            ]
        except Exception as e:
            raise ToolError(
                message=f"Fulltext search failed: {e}",
                tool_name=self.name,
            ) from e

    def classify_error(self, error: Exception) -> Literal["retriable", "fatal"]:
        """Neo4j connection errors are retriable."""
        error_str = str(error).lower()
        if any(p in error_str for p in ["connection", "timeout", "unavailable"]):
            return "retriable"
        return "fatal"

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "query": {
                    "type": "string",
                    "description": "Search query text",
                },
                "node_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Node types to search (optional, defaults to all)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default 10)",
                },
            },
            required=["query"],
        )


class EntityLookupTool(BaseTool[dict[str, Any] | None]):
    """Look up an entity by name.

    Searches for entities by canonical name or alias.
    """

    def __init__(
        self,
        store: Neo4jUnifiedStore,
        config: ToolConfig | None = None,
    ) -> None:
        super().__init__(
            name="entity_lookup",
            description="Look up an entity by name (searches canonical names and aliases).",
            config=config,
        )
        self.store = store

    def run(self, name: str) -> dict[str, Any] | None:
        """Look up an entity by name.

        Args:
            name: Entity name to search

        Returns:
            Entity dict with id, canonical_name, aliases, entity_type, or None
        """
        if not name or not name.strip():
            return None

        try:
            result = self.store.find_entity_by_name(name)
            if result:
                # Clean up the result for agent consumption
                return {
                    "id": result.get("id"),
                    "canonical_name": result.get("canonical_name"),
                    "aliases": result.get("aliases", []),
                    "entity_type": result.get("entity_type"),
                    "needs_resolution": result.get("needs_resolution", False),
                }
            return None
        except Exception as e:
            raise ToolError(
                message=f"Entity lookup failed: {e}",
                tool_name=self.name,
            ) from e

    def classify_error(self, error: Exception) -> Literal["retriable", "fatal"]:
        """Neo4j connection errors are retriable."""
        error_str = str(error).lower()
        if any(p in error_str for p in ["connection", "timeout", "unavailable"]):
            return "retriable"
        return "fatal"

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "name": {
                    "type": "string",
                    "description": "Entity name to look up",
                },
            },
            required=["name"],
        )


class FactSearchTool(BaseTool[list[dict[str, Any]]]):
    """Search for facts about an entity.

    Finds attributes (facts) associated with a specific entity.
    """

    def __init__(
        self,
        store: Neo4jUnifiedStore,
        config: ToolConfig | None = None,
    ) -> None:
        super().__init__(
            name="fact_search",
            description="Search for facts/attributes about a specific entity.",
            config=config,
        )
        self.store = store

    def run(
        self,
        entity_name: str,
        slot: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search for facts about an entity.

        Args:
            entity_name: Entity to search facts for
            slot: Optional slot to filter by (e.g., "preference.theme")
            limit: Maximum results

        Returns:
            List of fact dicts with id, slot, value, cardinality, scope
        """
        if not entity_name:
            return []

        try:
            # First find the entity
            entity = self.store.find_entity_by_name(entity_name)
            if not entity:
                return []

            entity_id = entity["id"]

            # Query facts
            with self.store.driver.session(database=self.store.database) as session:
                if slot:
                    result = session.run(
                        """
                        MATCH (e:Entity {id: $entity_id})-[:HAS_ATTRIBUTE]->(f:Fact)
                        WHERE f.slot = $slot AND f.is_superseded = false
                        RETURN properties(f) AS props
                        LIMIT $limit
                        """,
                        entity_id=entity_id,
                        slot=slot,
                        limit=limit,
                    )
                else:
                    result = session.run(
                        """
                        MATCH (e:Entity {id: $entity_id})-[:HAS_ATTRIBUTE]->(f:Fact)
                        WHERE f.is_superseded = false
                        RETURN properties(f) AS props
                        LIMIT $limit
                        """,
                        entity_id=entity_id,
                        limit=limit,
                    )

                facts = []
                for record in result:
                    props = record["props"]
                    facts.append(
                        {
                            "id": props.get("id"),
                            "slot": props.get("slot"),
                            "value": props.get("value"),
                            "cardinality": props.get("cardinality"),
                            "scope": props.get("scope"),
                            "scope_context": props.get("scope_context"),
                        }
                    )
                return facts

        except Exception as e:
            raise ToolError(
                message=f"Fact search failed: {e}",
                tool_name=self.name,
            ) from e

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "entity_name": {
                    "type": "string",
                    "description": "Entity name to search facts for",
                },
                "slot": {
                    "type": "string",
                    "description": "Optional slot to filter by (e.g., 'preference.theme')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default 20)",
                },
            },
            required=["entity_name"],
        )
