"""Episodic Store - Vector database for experiences."""

from pathlib import Path
from datetime import datetime
import uuid

from hmem.models import Event, Memory
from hmem.storage.base import BaseStore


class EpisodicStore(BaseStore):
    """In-memory episodic memory storage (Phase 1).

    Stores concrete experiences with simple text matching.
    Phase 2 will add ChromaDB for vector embeddings.

    Schema:
    - id: Unique event ID
    - content: Event description
    - outcome: success/failure/unknown
    - tags: List of tags
    - timestamp: When event occurred
    - metadata: Additional context

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
        """Add event to vector store.

        Args:
            event: Event to store

        Returns:
            Event ID (UUID)
        """
        event_id = str(uuid.uuid4())
        
        # Create corresponding memory for retrieval
        memory = Memory(
            content=event.content,
            score=1.0,  # Default score
            source="episodic",
            timestamp=event.timestamp,
            metadata={
                **event.metadata,
                "outcome": event.outcome,
                "tags": ",".join(event.tags),
            },
        )
        
        self._storage[event_id] = (event, memory)
        return event_id

    def search(
        self, 
        query: str, 
        limit: int = 10,
        filters: dict[str, str] | None = None
    ) -> list[Memory]:
        """Text similarity search (Phase 1 = simple keyword matching).

        Args:
            query: Search query
            limit: Maximum results
            filters: Optional filters (session_id, etc.)

        Returns:
            Similar memories ranked by relevance
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
                        if key == "session_id" and event.metadata.get("session_id") != value:
                            skip = True
                            break
                    if skip:
                        continue
                
                # Normalize score
                score = min(score / len(query_words), 1.0) if query_words else 0.0
                
                # Create memory with computed score
                scored_memory = Memory(
                    content=memory.content,
                    score=score,
                    source=memory.source,
                    timestamp=memory.timestamp,
                    metadata=memory.metadata,
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
