"""GraphQL query resolvers for h-mem."""

import strawberry
from strawberry.scalars import JSON

from hmem.api.dependencies import get_store
from hmem.api.graphql.types import (
    Direction,
    GraphData,
    GraphEdge,
    GraphNode,
    Node,
    NodeType,
    dict_to_node,
)


@strawberry.type
class Query:
    @strawberry.field
    def search(
        self,
        query: str,
        types: list[NodeType] | None = None,
        limit: int = 20,
    ) -> list[Node]:
        """Search for nodes by text query.

        Args:
            query: Search query text
            types: Optional filter by node types
            limit: Maximum results (default 20)
        """
        store = get_store()

        # Map enum values to Neo4j node type strings
        node_types: list[str] | None = None
        if types:
            node_types = [t.value.capitalize() for t in types]

        memories = store.fulltext_search(query, node_types=node_types, limit=limit)

        results: list[Node] = []
        for mem in memories:
            # Get full node data from store
            if mem.id:
                node_data = store.get_node_by_id(mem.id)
                if node_data:
                    results.append(dict_to_node(node_data))

        return results

    @strawberry.field
    def list_by_type(
        self,
        node_type: NodeType,
        limit: int = 50,
    ) -> list[Node]:
        """List nodes of a specific type for browsing.

        Args:
            node_type: Node type to list
            limit: Maximum results (default 50)
        """
        store = get_store()

        # Map enum to string
        type_str = node_type.value.capitalize()

        nodes = store.list_by_type(type_str, limit=limit)

        results: list[Node] = []
        for node_data in nodes:
            results.append(dict_to_node(node_data))

        return results

    @strawberry.field
    def expand(
        self,
        node_id: strawberry.ID,
        direction: Direction = Direction.BOTH,
        depth: int = 1,
    ) -> GraphData:
        """Expand a node's neighborhood for graph visualization.

        Args:
            node_id: Node ID to expand from
            direction: Direction to traverse (IN, OUT, BOTH)
            depth: Traversal depth (1-5)
        """
        store = get_store()

        result = store.get_neighbors(
            node_id=str(node_id),
            direction=direction.value,
            depth=depth,
        )

        nodes = [
            GraphNode(
                id=strawberry.ID(n["id"]),
                node_type=NodeType[n["nodeType"]],
                label=n["label"],
                q_value=n.get("qValue"),
                is_deprecated=n.get("isDeprecated", False),
            )
            for n in result["nodes"]
        ]

        edges = [
            GraphEdge(
                source=strawberry.ID(e["source"]),
                target=strawberry.ID(e["target"]),
                relationship=e["relationship"],
            )
            for e in result["edges"]
        ]

        return GraphData(
            nodes=nodes,
            edges=edges,
            has_more=result["has_more"],
        )

    @strawberry.field
    def lineage(
        self,
        node_id: strawberry.ID,
        max_depth: int = 5,
    ) -> list[Node]:
        """Get provenance lineage for a node.

        Args:
            node_id: Starting node ID
            max_depth: Maximum traversal depth
        """
        store = get_store()

        lineage_data = store.get_lineage(str(node_id), max_depth=max_depth)

        results: list[Node] = []
        seen_ids: set[str] = set()
        for item in lineage_data:
            node_id_str = item.get("id")
            if node_id_str and node_id_str not in seen_ids:
                seen_ids.add(node_id_str)
                node_data = {
                    "type": item.get("type", "Unknown"),
                    **item.get("properties", {}),
                }
                results.append(dict_to_node(node_data))

        return results

    @strawberry.field
    def node_detail(self, node_id: strawberry.ID) -> Node | None:
        """Get detailed information about a specific node.

        Args:
            node_id: Node ID to look up
        """
        store = get_store()

        node_data = store.get_node_by_id(str(node_id))
        if node_data:
            return dict_to_node(node_data)
        return None

    @strawberry.field
    def stats(self) -> JSON:
        """Get memory system statistics."""
        store = get_store()
        return store.get_stats()
