"""GraphQL mutation resolvers for h-mem."""

from datetime import datetime, timezone

import strawberry

from hmem.api.dependencies import get_store
from hmem.api.graphql.types import (
    Node,
    NodeType,
    NodeUpdateInput,
    dict_to_node,
)


@strawberry.type
class Mutation:
    @strawberry.mutation
    def update_node(
        self,
        node_id: strawberry.ID,
        node_type: NodeType,
        input: NodeUpdateInput,
    ) -> Node | None:
        """Update properties of a node.

        Args:
            node_id: Node ID to update
            node_type: Type of the node
            input: Properties to update
        """
        store = get_store()

        # Build properties dict from non-None input fields
        properties: dict = {}
        if input.q_value is not None:
            properties["q_value"] = input.q_value
        if input.is_deprecated is not None:
            properties["is_deprecated"] = input.is_deprecated
        if input.weight is not None:
            properties["weight"] = input.weight
        if input.content is not None:
            properties["content"] = input.content

        if not properties:
            # No updates, just return current node
            node_data = store.get_node_by_id(str(node_id))
            if node_data:
                return dict_to_node(node_data)
            return None

        # Add updated_at timestamp
        properties["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Map enum to Neo4j label
        neo4j_type = node_type.value.capitalize()

        store.update_node_properties(str(node_id), neo4j_type, properties)

        # Return updated node
        node_data = store.get_node_by_id(str(node_id))
        if node_data:
            return dict_to_node(node_data)
        return None

    @strawberry.mutation
    def deprecate_node(
        self,
        node_id: strawberry.ID,
        reason: str,
    ) -> bool:
        """Mark a node as deprecated.

        Args:
            node_id: Node ID to deprecate
            reason: Reason for deprecation
        """
        store = get_store()

        # Verify node exists
        node_data = store.get_node_by_id(str(node_id))
        if not node_data:
            return False

        store.deprecate(str(node_id), reason)
        return True
