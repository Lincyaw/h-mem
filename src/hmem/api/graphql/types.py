"""Strawberry GraphQL type definitions for h-mem."""

from enum import Enum
from typing import Any

import strawberry


@strawberry.enum
class NodeType(Enum):
    CONVERSATION = "CONVERSATION"
    FACT = "FACT"
    PRINCIPLE = "PRINCIPLE"
    SKILL = "SKILL"
    ENTITY = "ENTITY"
    PROCESS = "PROCESS"


@strawberry.enum
class Direction(Enum):
    IN = "IN"
    OUT = "OUT"
    BOTH = "BOTH"


@strawberry.type
class GraphNode:
    id: strawberry.ID
    node_type: NodeType
    label: str
    q_value: float | None = None
    is_deprecated: bool = False


@strawberry.type
class GraphEdge:
    source: strawberry.ID
    target: strawberry.ID
    relationship: str


@strawberry.type
class GraphData:
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    has_more: bool


# === Concrete node types for the union ===


@strawberry.type
class ConversationNode:
    id: strawberry.ID
    node_type: NodeType
    session_id: str
    created_at: str
    metadata_json: str | None = None


@strawberry.type
class FactNode:
    id: strawberry.ID
    node_type: NodeType
    entity_id: str | None = None
    slot: str | None = None
    value: str | None = None
    cardinality: str | None = None
    version: int
    is_superseded: bool
    created_at: str
    updated_at: str | None = None
    source_role: str | None = None
    importance: int | None = None
    confidence: float | None = None
    q_value: float
    q_update_count: int


@strawberry.type
class PrincipleNode:
    id: strawberry.ID
    node_type: NodeType
    content: str
    evidence_count: int
    confidence: float | None = None
    created_at: str
    is_deprecated: bool = False
    version: int = 1
    q_value: float = 0.5
    q_update_count: int = 0


@strawberry.type
class SkillNode:
    id: strawberry.ID
    node_type: NodeType
    name: str
    trigger_pattern: str | None = None
    description: str | None = None
    action_template: str | None = None
    tags: list[str] | None = None
    created_at: str
    updated_at: str | None = None
    is_deprecated: bool
    version: int
    q_value: float
    q_update_count: int


@strawberry.type
class EntityNode:
    id: strawberry.ID
    node_type: NodeType
    canonical_name: str
    aliases: list[str] | None = None
    entity_type: str
    needs_resolution: bool
    created_at: str
    updated_at: str | None = None


@strawberry.type
class ProcessNode:
    id: strawberry.ID
    node_type: NodeType
    trigger: str
    action: str
    outcome: str | None = None
    confidence: float | None = None
    is_deprecated: bool = False
    created_at: str = ""
    updated_at: str | None = None
    q_value: float = 0.5
    q_update_count: int = 0


Node = strawberry.union(
    "Node",
    types=[
        ConversationNode,
        FactNode,
        PrincipleNode,
        SkillNode,
        EntityNode,
        ProcessNode,
    ],
)


@strawberry.input
class NodeUpdateInput:
    q_value: float | None = None
    is_deprecated: bool | None = None
    weight: float | None = None
    content: str | None = None


def dict_to_node(data: dict[str, Any]) -> Node:
    """Convert a raw dict from the store into the appropriate Strawberry union type.

    Args:
        data: Dict with at least a 'type' key and node properties.

    Returns:
        A concrete Node union member.
    """
    node_type_str = data.get("type", "Unknown")
    node_type_enum = (
        NodeType[node_type_str.upper()] if node_type_str != "Unknown" else NodeType.FACT
    )

    if node_type_str == "Conversation":
        return ConversationNode(
            id=strawberry.ID(data.get("id", "")),
            node_type=node_type_enum,
            session_id=data.get("session_id", ""),
            created_at=data.get("created_at", ""),
            metadata_json=data.get("metadata_json"),
        )
    elif node_type_str == "Fact":
        return FactNode(
            id=strawberry.ID(data.get("id", "")),
            node_type=node_type_enum,
            entity_id=data.get("entity_id"),
            slot=data.get("slot"),
            value=data.get("value"),
            cardinality=data.get("cardinality"),
            version=data.get("version", 1),
            is_superseded=data.get("is_superseded", False),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at"),
            source_role=data.get("source_role"),
            importance=data.get("importance"),
            confidence=data.get("confidence"),
            q_value=data.get("q_value", 0.5),
            q_update_count=data.get("q_update_count", 0),
        )
    elif node_type_str == "Principle":
        return PrincipleNode(
            id=strawberry.ID(data.get("id", "")),
            node_type=node_type_enum,
            content=data.get("content", ""),
            evidence_count=data.get("evidence_count", 0),
            confidence=data.get("confidence", 0.0),
            created_at=data.get("created_at", ""),
            is_deprecated=data.get("is_deprecated", False),
            version=data.get("version", 1),
            q_value=data.get("q_value", 0.5),
            q_update_count=data.get("q_update_count", 0),
        )
    elif node_type_str == "Skill":
        return SkillNode(
            id=strawberry.ID(data.get("id", "")),
            node_type=node_type_enum,
            name=data.get("name", ""),
            trigger_pattern=data.get("trigger_pattern"),
            description=data.get("description"),
            action_template=data.get("action_template"),
            tags=data.get("tags"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at"),
            is_deprecated=data.get("is_deprecated", False),
            version=data.get("version", 1),
            q_value=data.get("q_value", 0.5),
            q_update_count=data.get("q_update_count", 0),
        )
    elif node_type_str == "Entity":
        return EntityNode(
            id=strawberry.ID(data.get("id", "")),
            node_type=node_type_enum,
            canonical_name=data.get("canonical_name", ""),
            aliases=data.get("aliases"),
            entity_type=data.get("entity_type", "CONCEPT"),
            needs_resolution=data.get("needs_resolution", False),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at"),
        )
    elif node_type_str == "Process":
        return ProcessNode(
            id=strawberry.ID(data.get("id", "")),
            node_type=node_type_enum,
            trigger=data.get("trigger", ""),
            action=data.get("action", ""),
            outcome=data.get("outcome"),
            confidence=data.get("confidence", 1.0),
            is_deprecated=data.get("is_deprecated", False),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at"),
            q_value=data.get("q_value", 0.5),
            q_update_count=data.get("q_update_count", 0),
        )
    else:
        # Fallback to FactNode with available data
        return FactNode(
            id=strawberry.ID(data.get("id", "")),
            node_type=NodeType.FACT,
            version=data.get("version", 1),
            is_superseded=data.get("is_superseded", False),
            created_at=data.get("created_at", ""),
            q_value=data.get("q_value", 0.5),
            q_update_count=data.get("q_update_count", 0),
        )
