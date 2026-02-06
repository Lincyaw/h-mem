"""Extraction helper tools for the ReAct Agent Loop.

These tools help with deduplication and similarity checking during
knowledge extraction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hmem.agents.react.errors import ToolError
from hmem.agents.react.tool_base import BaseTool, ToolConfig, ToolSchema

if TYPE_CHECKING:
    from hmem.storage.neo4j_unified import Neo4jUnifiedStore


class FactDeduplicationTool(BaseTool[bool]):
    """Check if a fact already exists.

    Used during extraction to avoid creating duplicate facts.
    """

    def __init__(
        self,
        store: Neo4jUnifiedStore,
        config: ToolConfig | None = None,
    ) -> None:
        super().__init__(
            name="fact_exists",
            description="Check if a fact (entity + slot + value) already exists. Returns true if duplicate.",
            config=config,
        )
        self.store = store

    def run(
        self,
        entity_name: str,
        slot: str,
        value: str,
    ) -> bool:
        """Check if a fact already exists.

        Args:
            entity_name: Entity name to check
            slot: Attribute slot
            value: Attribute value

        Returns:
            True if the fact exists (duplicate), False otherwise
        """
        if not entity_name or not slot:
            return False

        try:
            # First find the entity
            entity = self.store.find_entity_by_name(entity_name)
            if not entity:
                return False

            entity_id = entity["id"]

            # Check for existing fact
            with self.store.driver.session(database=self.store.database) as session:
                result = session.run(
                    """
                    MATCH (e:Entity {id: $entity_id})-[:HAS_ATTRIBUTE]->(f:Fact)
                    WHERE f.slot = $slot AND f.value = $value AND f.is_superseded = false
                    RETURN count(f) > 0 AS exists
                    """,
                    entity_id=entity_id,
                    slot=slot,
                    value=value,
                )
                record = result.single()
                return bool(record["exists"]) if record else False

        except Exception as e:
            raise ToolError(
                message=f"Fact existence check failed: {e}",
                tool_name=self.name,
            ) from e

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "entity_name": {
                    "type": "string",
                    "description": "Entity name",
                },
                "slot": {
                    "type": "string",
                    "description": "Attribute slot (e.g., 'preference.theme')",
                },
                "value": {
                    "type": "string",
                    "description": "Attribute value",
                },
            },
            required=["entity_name", "slot", "value"],
        )


class ProcessSimilarityTool(BaseTool[list[dict[str, Any]]]):
    """Find similar processes by trigger.

    Used during extraction to check for similar existing processes
    and during skill induction to find process clusters.
    """

    def __init__(
        self,
        store: Neo4jUnifiedStore,
        config: ToolConfig | None = None,
    ) -> None:
        super().__init__(
            name="find_similar_processes",
            description="Find processes with similar triggers. Used to identify patterns for skill induction.",
            config=config,
        )
        self.store = store

    def run(
        self,
        trigger: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Find similar processes.

        Args:
            trigger: Trigger text to search by
            limit: Maximum results

        Returns:
            List of process dicts with id, trigger, action, outcome
        """
        if not trigger:
            return []

        try:
            # Use fulltext search on process triggers
            with self.store.driver.session(database=self.store.database) as session:
                result = session.run(
                    """
                    CALL db.index.fulltext.queryNodes('process_content_fulltext', $search_term)
                    YIELD node, score
                    WHERE node.is_deprecated = false OR node.is_deprecated IS NULL
                    RETURN properties(node) AS props, score
                    ORDER BY score DESC
                    LIMIT $limit
                    """,
                    search_term=trigger,
                    limit=limit,
                )

                processes = []
                for record in result:
                    props = record["props"]
                    processes.append(
                        {
                            "id": props.get("id"),
                            "trigger": props.get("trigger"),
                            "action": props.get("action"),
                            "outcome": props.get("outcome"),
                            "similarity_score": record["score"],
                            "q_value": props.get("q_value", 0.5),
                            "is_generalizable": props.get("is_generalizable", True),
                        }
                    )
                return processes

        except Exception as e:
            raise ToolError(
                message=f"Process similarity search failed: {e}",
                tool_name=self.name,
            ) from e

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "trigger": {
                    "type": "string",
                    "description": "Trigger text to search by",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default 10)",
                },
            },
            required=["trigger"],
        )
