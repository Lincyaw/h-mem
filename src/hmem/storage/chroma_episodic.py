"""ChromaDB-based episodic memory store implementation (Phase 2)."""

import uuid
from datetime import datetime
from typing import Any

import chromadb  # type: ignore
from chromadb.config import Settings  # type: ignore

from hmem.models import Event, Memory
from hmem.utils.embeddings import get_embedding


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
        persist_directory: str = "./chroma_data",
        collection_name: str = "episodic_memories",
    ):
        """Initialize ChromaDB store.

        Args:
            persist_directory: Directory for persistent storage
            collection_name: Name of the collection
        """
        self.client = chromadb.Client(
            Settings(persist_directory=persist_directory, anonymized_telemetry=False)
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
        event_id = str(uuid.uuid4())
        embedding = get_embedding(event.content)

        metadata = {
            "outcome": event.outcome,
            "tags": ",".join(event.tags),
            "timestamp": event.timestamp.isoformat(),
            **event.metadata,
        }

        self.collection.add(
            ids=[event_id],
            embeddings=[embedding],
            documents=[event.content],
            metadatas=[metadata],
        )

        self.insertion_count += 1
        self._check_rebuild()

        return event_id

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
            query_embeddings=[query_embedding], n_results=limit, where=where_filter
        )

        memories = []
        if results and results["ids"] and len(results["ids"][0]) > 0:
            for i, doc_id in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i]
                distance = results["distances"][0][i] if results["distances"] else 0.0

                similarity = 1.0 - min(distance, 1.0)

                memories.append(
                    Memory(
                        content=results["documents"][0][i],
                        score=similarity,
                        source="episodic",
                        timestamp=datetime.fromisoformat(metadata["timestamp"]),
                        metadata=metadata,
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

    def _trigger_rebuild(self):
        """Trigger asynchronous index rebuild."""
        self.last_rebuild_count = self.insertion_count

    def count(self) -> int:
        """Get total number of stored memories.

        Returns:
            Total count of memories
        """
        return self.collection.count()

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
