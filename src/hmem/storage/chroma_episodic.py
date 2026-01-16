"""ChromaDB-based episodic memory store implementation (Phase 2)."""

import json
import uuid
from datetime import datetime
from typing import Any, Literal

import chromadb  # type: ignore
import structlog
from chromadb.config import Settings  # type: ignore

from hmem.models import Event, Memory
from hmem.utils.embeddings import get_embedding

logger = structlog.get_logger()


class ChromaEpisodicStore:
    """ChromaDB-based episodic memory store with vector search.

    Features:
    - Automatic embedding generation
    - Vector similarity search
    - Metadata filtering
    - Index lifecycle management
    """

    def __init__(
        self,
        persist_directory: str = "./.hmem/chroma_data",
        collection_name: str = "episodic_memories",
    ):
        """Initialize ChromaDB store.

        Args:
            persist_directory: Directory for persistent storage
            collection_name: Name of the collection
        """
        self.client = chromadb.PersistentClient(
            path=persist_directory, settings=Settings(anonymized_telemetry=False)
        )

        self.collection = self.client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"}
        )

        self.insertion_count = 0
        self.last_rebuild_count = 0

    def add(self, event: Event) -> str:
        """Add an event to the episodic store.

        Args:
            event: Event to store

        Returns:
            Unique ID of the stored event
        """
        event_id = event.id if event.id else str(uuid.uuid4())
        embedding = get_embedding(event.content)

        metadata = {
            "outcome": event.outcome,
            "tags": ",".join(event.tags),
            "timestamp": event.timestamp.isoformat(),
            "parent_ids": json.dumps(event.parent_ids),
            "derivation_type": event.derivation_type,
            **event.metadata,
        }

        self.collection.add(
            ids=[event_id],
            embeddings=[embedding],  # type: ignore[arg-type]
            documents=[event.content],
            metadatas=[metadata],
        )

        self.insertion_count += 1
        self._check_rebuild()

        return event_id

    def add_event(self, event: Event, initial_weight: float = 1.0) -> str:
        """Add event to store with initial weight.

        Args:
            event: Event to store
            initial_weight: Initial importance weight (stored in metadata)

        Returns:
            Event ID
        """
        # Add weight to event metadata
        event_with_weight = Event(
            id=event.id,
            content=event.content,
            outcome=event.outcome,
            tags=event.tags,
            timestamp=event.timestamp,
            metadata={**event.metadata, "weight": initial_weight},
            parent_ids=event.parent_ids,
            derivation_type=event.derivation_type,
        )
        return self.add(event_with_weight)

    def search(
        self, query: str, limit: int = 10, filters: dict | None = None
    ) -> list[Memory]:
        """Search for similar events using vector similarity.

        Args:
            query: Query text
            limit: Maximum number of results
            filters: Optional metadata filters

        Returns:
            List of relevant memories sorted by similarity
        """
        query_embedding = get_embedding(query)

        where_filter = self._build_filter(filters) if filters else None

        results = self.collection.query(
            query_embeddings=[query_embedding],  # type: ignore[arg-type]
            n_results=limit,
            where=where_filter,
        )

        memories = []
        ids_list = results.get("ids")
        metadatas_list = results.get("metadatas")
        documents_list = results.get("documents")
        distances_list = results.get("distances")

        if ids_list and len(ids_list) > 0 and len(ids_list[0]) > 0:
            for i, doc_id in enumerate(ids_list[0]):
                metadata = metadatas_list[0][i] if metadatas_list else {}
                distance = (
                    distances_list[0][i]
                    if distances_list and distances_list[0]
                    else 0.0
                )

                # Clamp similarity to [0, 1] to avoid floating point precision issues
                similarity = max(0.0, min(1.0, 1.0 - float(distance)))

                timestamp_str = str(
                    metadata.get("timestamp", datetime.now().isoformat())
                )

                # Extract provenance fields from metadata
                parent_ids_str = (
                    str(metadata.get("parent_ids", "[]")) if metadata else "[]"
                )
                parent_ids = json.loads(parent_ids_str) if parent_ids_str else []
                deriv_val = (
                    str(metadata.get("derivation_type", "extraction"))
                    if metadata
                    else "extraction"
                )
                derivation: Literal["extraction", "derivation"] = (
                    deriv_val
                    if deriv_val in ("extraction", "derivation")
                    else "extraction"  # type: ignore[assignment]
                )

                memories.append(
                    Memory(
                        id=doc_id,
                        content=str(documents_list[0][i]) if documents_list else "",
                        score=similarity,
                        source="episodic",
                        timestamp=datetime.fromisoformat(timestamp_str),
                        metadata=dict(metadata) if metadata else {},
                        parent_ids=parent_ids,
                        derivation_type=derivation,
                    )
                )

        return memories

    def _build_filter(self, filters: dict) -> dict[str, Any] | None:
        """Build ChromaDB where filter from user filters.

        Args:
            filters: User-provided filters

        Returns:
            ChromaDB where clause
        """
        where: dict[str, Any] = {}

        if "session_id" in filters:
            where["session_id"] = filters["session_id"]

        if "outcome" in filters:
            where["outcome"] = filters["outcome"]

        if "tags" in filters:
            where["tags"] = {"$contains": filters["tags"]}

        return where if where else None

    def _check_rebuild(self):
        """Check if index rebuild is needed and trigger if necessary."""
        current_count = self.collection.count()

        if current_count == 0:
            return

        growth_rate = (self.insertion_count - self.last_rebuild_count) / current_count

        if growth_rate > 0.1:
            self._trigger_rebuild()

    def _trigger_rebuild(self) -> None:
        """Trigger index optimization and log statistics.

        ChromaDB manages HNSW index internally, so this primarily
        logs index health metrics and resets insertion counter.
        """
        current_count = self.collection.count()
        insertions_since_last = self.insertion_count - self.last_rebuild_count

        logger.info(
            "index_optimization_triggered",
            memory_count=current_count,
            insertions_since_last=insertions_since_last,
            growth_rate=insertions_since_last / max(current_count, 1),
        )

        # Reset counter
        self.last_rebuild_count = self.insertion_count

        # ChromaDB handles HNSW index optimization automatically
        # No explicit rebuild needed

    def count(self) -> int:
        """Get total number of stored memories.

        Returns:
            Total count of memories
        """
        return self.collection.count()

    def get_all_tags(self) -> list[str]:
        """Extract all unique tags from stored memories.

        Scans all metadata to collect unique topic tags for reflection.

        Returns:
            List of unique tag strings
        """
        all_tags: set[str] = set()

        # Get all documents with metadata
        result = self.collection.get(include=["metadatas"])
        metadatas = result.get("metadatas")

        if metadatas is None:
            return []

        for metadata in metadatas:
            if metadata is None or "tags" not in metadata:
                continue
            tags_value = metadata.get("tags")
            if not isinstance(tags_value, str):
                continue
            # Tags are stored as comma-separated string
            for tag in tags_value.split(","):
                tag = tag.strip()
                if tag:
                    all_tags.add(tag)

        return list(all_tags)

    def health_check(self) -> dict[str, Any]:
        """Get health status of the store.

        Returns:
            Health status dictionary
        """
        return {
            "status": "healthy",
            "total_memories": self.count(),
            "insertions_since_rebuild": self.insertion_count - self.last_rebuild_count,
        }

    def get_by_id(self, event_id: str) -> Event | None:
        """Get event by ID.

        Args:
            event_id: Event identifier

        Returns:
            Event if found, None otherwise
        """
        result = self.collection.get(
            ids=[event_id],
            include=["documents", "metadatas"],
        )

        if not result["ids"]:
            return None

        metadata = result["metadatas"][0] if result["metadatas"] else {}
        content = result["documents"][0] if result["documents"] else ""

        # Parse parent_ids from JSON string
        parent_ids_str = str(metadata.get("parent_ids", "[]")) if metadata else "[]"
        parent_ids = json.loads(parent_ids_str) if parent_ids_str else []

        # Extract and convert metadata values
        outcome_val = str(metadata.get("outcome", "unknown")) if metadata else "unknown"
        outcome: Literal["success", "failure", "unknown"] = (
            outcome_val
            if outcome_val in ("success", "failure", "unknown")
            else "unknown"  # type: ignore[assignment]
        )
        tags_val = str(metadata.get("tags", "")) if metadata else ""
        timestamp_val = (
            str(metadata.get("timestamp", datetime.now().isoformat()))
            if metadata
            else datetime.now().isoformat()
        )
        deriv_val = (
            str(metadata.get("derivation_type", "extraction"))
            if metadata
            else "extraction"
        )
        derivation: Literal["extraction", "derivation"] = (
            deriv_val if deriv_val in ("extraction", "derivation") else "extraction"  # type: ignore[assignment]
        )

        return Event(
            id=event_id,
            content=content,
            outcome=outcome,
            tags=tags_val.split(",") if tags_val else [],
            timestamp=datetime.fromisoformat(timestamp_val),
            metadata={
                k: v
                for k, v in metadata.items()
                if k
                not in ("outcome", "tags", "timestamp", "parent_ids", "derivation_type")
            }
            if metadata
            else {},
            parent_ids=parent_ids,
            derivation_type=derivation,
        )

    def get_children(self, parent_id: str) -> list[Event]:
        """Get all events derived from a parent memory.

        Args:
            parent_id: Parent memory ID

        Returns:
            List of events that have this parent in their parent_ids
        """
        # Get all documents and filter by parent_id
        result = self.collection.get(include=["documents", "metadatas"])

        children = []
        ids = result.get("ids", [])
        documents = result.get("documents", [])
        metadatas = result.get("metadatas", [])

        for i, event_id in enumerate(ids):
            metadata = metadatas[i] if metadatas and i < len(metadatas) else {}
            parent_ids_str = str(metadata.get("parent_ids", "[]")) if metadata else "[]"
            parent_ids = json.loads(parent_ids_str) if parent_ids_str else []

            if parent_id in parent_ids:
                content = documents[i] if documents and i < len(documents) else ""
                outcome_val = (
                    str(metadata.get("outcome", "unknown")) if metadata else "unknown"
                )
                outcome: Literal["success", "failure", "unknown"] = (
                    outcome_val
                    if outcome_val in ("success", "failure", "unknown")
                    else "unknown"  # type: ignore[assignment]
                )
                tags_val = str(metadata.get("tags", "")) if metadata else ""
                timestamp_val = (
                    str(metadata.get("timestamp", datetime.now().isoformat()))
                    if metadata
                    else datetime.now().isoformat()
                )
                deriv_val = (
                    str(metadata.get("derivation_type", "extraction"))
                    if metadata
                    else "extraction"
                )
                derivation: Literal["extraction", "derivation"] = (
                    deriv_val
                    if deriv_val in ("extraction", "derivation")
                    else "extraction"  # type: ignore[assignment]
                )
                children.append(
                    Event(
                        id=event_id,
                        content=content,
                        outcome=outcome,
                        tags=tags_val.split(",") if tags_val else [],
                        timestamp=datetime.fromisoformat(timestamp_val),
                        metadata={},
                        parent_ids=parent_ids,
                        derivation_type=derivation,
                    )
                )

        return children

    def get_lineage(self, event_id: str, max_depth: int = 3) -> list[str]:
        """Get the provenance chain for an event.

        Args:
            event_id: Event to trace
            max_depth: Maximum depth to traverse

        Returns:
            List of ancestor memory IDs
        """
        lineage: list[str] = []
        visited: set[str] = set()
        queue = [(event_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if depth > max_depth or current_id in visited:
                continue
            visited.add(current_id)

            event = self.get_by_id(current_id)
            if event and event.parent_ids:
                for parent_id in event.parent_ids:
                    if parent_id not in visited:
                        lineage.append(parent_id)
                        queue.append((parent_id, depth + 1))

        return lineage

    def get_stats(self) -> dict[str, Any]:
        """Get store statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "total_events": self.count(),
            "insertions": self.insertion_count,
        }
