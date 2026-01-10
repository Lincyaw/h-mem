"""Episodic Store - Vector database for experiences."""

from pathlib import Path

from hmem.models import Event, Memory
from hmem.storage.base import BaseStore


class EpisodicStore(BaseStore):
    """ChromaDB-based episodic memory storage.

    Stores concrete experiences with automatic embedding generation.

    Schema (auto-managed by ChromaDB):
    - content: Event description
    - embedding: 768-dim vector (auto-generated)
    - metadata: {outcome, tags, timestamp, session_id}

    Capacity guidance:
    - <100k: Embedded mode (recommended)
    - 100k-500k: Embedded + periodic cleanup
    - >500k: Migrate to Milvus distributed

    Example:
        >>> store = EpisodicStore(persist_dir="./data/chroma")
        >>> store.add_event(Event(...))
        >>> results = store.search("web scraping errors", limit=5)
    """

    def __init__(self, persist_dir: Path) -> None:
        """Initialize episodic store.

        Args:
            persist_dir: ChromaDB persistence directory
        """
        self.persist_dir = persist_dir

    def add_event(self, event: Event) -> str:
        """Add event to vector store.

        Args:
            event: Event to store

        Returns:
            Event ID (UUID)
        """
        raise NotImplementedError("Phase 1 implementation pending")

    def search(self, query: str, limit: int = 10) -> list[Memory]:
        """Vector similarity search.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            Similar memories ranked by cosine similarity
        """
        raise NotImplementedError("Phase 1 implementation pending")

    def health_check(self) -> dict[str, str | int]:
        """Check ChromaDB health."""
        return {"status": "healthy", "count": 0}

    def get_stats(self) -> dict[str, int]:
        """Get storage statistics."""
        return {"total_count": 0, "size_mb": 0}
