"""Episodic Store - Vector database for experiences with provenance tracking."""

from pathlib import Path
import uuid

from hmem.models import Event, Memory
from hmem.storage.base import BaseStore


class EpisodicStore(BaseStore):
    """In-memory episodic memory storage (Phase 1) with provenance support.

    Stores concrete experiences with simple text matching.
    Phase 2 will add ChromaDB for vector embeddings.

    Schema:
    - id: Unique event ID
    - content: Event description
    - outcome: success/failure/unknown
    - tags: List of tags
    - timestamp: When event occurred
    - metadata: Additional context
    - parent_ids: Source memory IDs (provenance)
    - derivation_type: How this event was derived

    Example:
        >>> store = EpisodicStore()
        >>> store.add_event(Event(...))
        >>> results = store.search("web scraping errors", limit=5)
    """

    def __init__(self, persist_dir: Path | None = None) -> None:
        """Initialize episodic store.

        Args:
            persist_dir: ChromaDB persistence directory (unused in Phase 1)
        """
        self.persist_dir = persist_dir
        self._storage: dict[str, tuple[Event, Memory]] = {}  # id -> (event, memory)

    def add_event(self, event: Event) -> str:
        """Add event to vector store with provenance tracking.

        Args:
            event: Event to store (may include parent_ids for provenance)

        Returns:
            Event ID (UUID or provided ID)
        """
        # Use provided ID or generate new one
        event_id = event.id if event.id else f"evt_{uuid.uuid4().hex[:12]}"

        # Update event with generated ID if not provided
        if not event.id:
            event = Event(
                id=event_id,
                content=event.content,
                outcome=event.outcome,
                tags=event.tags,
                timestamp=event.timestamp,
                metadata=event.metadata,
                parent_ids=event.parent_ids,
                derivation_type=event.derivation_type,
            )

        # Create corresponding memory for retrieval with provenance
        memory = Memory(
            id=event_id,
            content=event.content,
            score=1.0,  # Default score
            source="episodic",
            timestamp=event.timestamp,
            metadata={
                **event.metadata,
                "outcome": event.outcome,
                "tags": ",".join(event.tags),
            },
            parent_ids=event.parent_ids,
            derivation_type=event.derivation_type,
        )

        self._storage[event_id] = (event, memory)
        return event_id

    def get_by_id(self, event_id: str) -> Event | None:
        """Get event by ID.

        Args:
            event_id: Event identifier

        Returns:
            Event if found, None otherwise
        """
        if event_id in self._storage:
            return self._storage[event_id][0]
        return None

    def get_children(self, parent_id: str) -> list[Event]:
        """Get all events derived from a parent memory.

        Args:
            parent_id: Parent memory ID

        Returns:
            List of events that have this parent in their parent_ids
        """
        children = []
        for _, (event, _) in self._storage.items():
            if parent_id in event.parent_ids:
                children.append(event)
        return children

    def get_lineage(self, event_id: str, max_depth: int = 3) -> list[str]:
        """Get the provenance chain for an event.

        Args:
            event_id: Event to trace
            max_depth: Maximum depth to traverse

        Returns:
            List of ancestor memory IDs (ordered from immediate parent to root)
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

    def search(
        self, query: str, limit: int = 10, filters: dict[str, str] | None = None
    ) -> list[Memory]:
        """Text similarity search (Phase 1 = simple keyword matching).

        Args:
            query: Search query
            limit: Maximum results
            filters: Optional filters (session_id, etc.)

        Returns:
            Similar memories ranked by relevance (with provenance info)
        """
        query_lower = query.lower()
        results = []

        for event_id, (event, memory) in self._storage.items():
            # Simple keyword matching
            content_lower = event.content.lower()

            # Calculate simple relevance score
            score = 0.0
            query_words = query_lower.split()
            for word in query_words:
                if word in content_lower:
                    score += 1.0

            if score > 0:
                # Apply filters if provided
                if filters:
                    skip = False
                    for key, value in filters.items():
                        if (
                            key == "session_id"
                            and event.metadata.get("session_id") != value
                        ):
                            skip = True
                            break
                    if skip:
                        continue

                # Normalize score
                score = min(score / len(query_words), 1.0) if query_words else 0.0

                # Create memory with computed score (preserving provenance)
                scored_memory = Memory(
                    id=memory.id,
                    content=memory.content,
                    score=score,
                    source=memory.source,
                    timestamp=memory.timestamp,
                    metadata=memory.metadata,
                    parent_ids=memory.parent_ids,
                    derivation_type=memory.derivation_type,
                )
                results.append(scored_memory)

        # Sort by score descending
        results.sort(key=lambda m: m.score, reverse=True)

        return results[:limit]

    def health_check(self) -> dict[str, str | int]:
        """Check store health."""
        return {
            "status": "healthy",
            "count": len(self._storage),
        }

    def get_stats(self) -> dict[str, int]:
        """Get storage statistics."""
        return {
            "total_count": len(self._storage),
            "size_mb": 0,  # Placeholder for Phase 1
        }
