"""Main MemorySystem class - the unified interface for cognitive memory.

This is the primary entry point following Unix philosophy: "Do One Thing Well"
Provides only 2 core methods: remember() and recall()
"""

from collections.abc import Iterator

from hmem.config import MemoryConfig
from hmem.models import Conversation, Memory, Message
from hmem.hippocampus.encoder import MemoryEncoder
from hmem.hippocampus.consolidator import Consolidator
from hmem.hippocampus.retrieval_engine import RetrievalEngine
from hmem.storage.episodic import EpisodicStore
from hmem.core.event_log import EventLog


class MemorySystem:
    """Cognitive Agent Memory System (CAMS) - Core Interface.

    This class orchestrates all three layers:
    - Layer 1: Perception & Working Memory (Context Manager)
    - Layer 2: Hippocampus Processing (Encoder, Consolidator, Reflector)
    - Layer 3: Long-Term Storage (Episodic, Semantic, Skill)

    Design Philosophy:
    - Unix Rule of Silence: All complexity hidden in config
    - Unix Rule of Modularity: Internal components replaceable via protocols
    - Event Sourcing: Single source of truth (append-only event log)

    Example:
        >>> from hmem.models import Message, Conversation
        >>> memory = MemorySystem()
        >>> conversation = Conversation(
        ...     session_id="sess_001",
        ...     messages=[Message(role="user", content="I prefer dark mode")]
        ... )
        >>> memory.remember(conversation)
        >>> results = list(memory.recall("user preferences"))
    """

    def __init__(self, config: MemoryConfig | None = None) -> None:
        """Initialize memory system with optional config.

        Args:
            config: Configuration object. If None, loads from default path.
        """
        self.config = config or MemoryConfig()
        self._initialized = False
        
        # Initialize components
        self._event_log = EventLog()
        self._encoder = MemoryEncoder()
        self._episodic_store = EpisodicStore(persist_dir=None)
        self._consolidator = Consolidator()
        self._retrieval_engine = RetrievalEngine(self._episodic_store)

    @classmethod
    def from_config(cls, config_path: str) -> "MemorySystem":
        """Create instance from config file.

        Args:
            config_path: Path to YAML config file

        Returns:
            Configured MemorySystem instance
        """
        config = MemoryConfig.from_file(config_path)
        return cls(config)

    def remember(
        self,
        conversation: Conversation | list[Message],
        auto_consolidate: bool = True,
    ) -> str:
        """Store conversation into memory (single write interface).

        This triggers:
        1. Append to Event Log (single source of truth)
        2. Extract events from conversation
        3. Store in episodic memory
        4. Optionally consolidate

        Args:
            conversation: Conversation or list of Message objects
            auto_consolidate: If True, consolidates immediately (Phase 1 sync mode)

        Returns:
            session_id: Session identifier

        Raises:
            MemoryError: If event log write fails
        """
        # Convert list[Message] to Conversation if needed
        if isinstance(conversation, list):
            # Generate session_id from timestamp
            from datetime import datetime
            session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            conversation = Conversation(
                session_id=session_id,
                messages=conversation,
            )
        
        # Log conversation to event log
        self._event_log.append(conversation)
        
        # Extract events from conversation
        events = self._encoder.extract_events(conversation)
        
        # Store events in episodic memory
        for event in events:
            self._episodic_store.add_event(event)
        
        # Consolidate if requested (Phase 1: synchronous)
        if auto_consolidate:
            self._consolidator.consolidate(conversation.session_id, events)
        
        return conversation.session_id

    def recall(
        self,
        query: str | Message | Conversation,
        limit: int = 10,
        filters: dict[str, str] | None = None,
    ) -> Iterator[Memory]:
        """Retrieve relevant memories (single read interface).

        Two-phase retrieval:
        - Phase 1 (sync): Cache + Bloom Filter (P95 < 50ms)
        - Phase 2 (async): Vector + Graph search (P95 < 500ms)

        Args:
            query: Search query - supports str, Message, or Conversation
                  - str: Simple text query for single search
                  - Message: Single message with context
                  - Conversation: Full conversation for proactive prompting
            limit: Maximum results to return
            filters: Optional filters (e.g., session_id, date_range)

        Yields:
            Memory objects ranked by relevance

        Raises:
            RetrievalError: If retrieval fails
        """
        # Convert query to string
        query_text = self._convert_query_to_text(query)
        
        # Delegate to retrieval engine
        yield from self._retrieval_engine.retrieve(query_text, limit, filters)
    
    def _convert_query_to_text(self, query: str | Message | Conversation) -> str:
        """Convert different query types to text.
        
        Args:
            query: Query in any supported format
            
        Returns:
            Text representation of query
        """
        if isinstance(query, str):
            return query
        elif isinstance(query, Message):
            return query.content
        elif isinstance(query, Conversation):
            # Use last few messages for context
            messages_text = " ".join(
                f"{msg.role}: {msg.content}" 
                for msg in query.messages[-3:]  # Last 3 messages
            )
            return messages_text
        else:
            return str(query)

    def consolidate(self, session_id: str) -> dict[str, int]:
        """Trigger memory consolidation (cold path).

        This is called:
        - Synchronously at session end (Phase 1)
        - Asynchronously by scheduler (Phase 3)

        Args:
            session_id: Session to consolidate

        Returns:
            Statistics: {"events_processed": N, "facts_extracted": M, ...}

        Raises:
            ConsolidationError: If consolidation fails
        """
        # Get events for session
        events = self._event_log.get_session_events(session_id)
        
        # Consolidate
        result = self._consolidator.consolidate(session_id, events)
        
        return {
            "events_processed": result.stored_events,
            "facts_extracted": result.updated_facts,
            "conflicts_resolved": result.conflicts_resolved,
        }

    def health(self) -> dict[str, str | int]:
        """Get system health status.

        Returns:
            Health metrics: status, memory_count, latency_p95, etc.
        """
        episodic_stats = self._episodic_store.get_stats()
        
        return {
            "status": "healthy",
            "version": "0.1.0",
            "episodic_count": episodic_stats.get("total_count", 0),
            "semantic_count": 0,
        }

    def explain_recall(self, query: str) -> dict[str, str | float]:
        """Explain how a query would be processed (observability).

        Args:
            query: Query to explain

        Returns:
            Explanation with threshold, cache status, estimated latency
        """
        raise NotImplementedError("Phase 3 implementation")
