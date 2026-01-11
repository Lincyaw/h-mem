"""Main MemorySystem class - the unified interface for cognitive memory.

This is the primary entry point following Unix philosophy: "Do One Thing Well"
Provides only 2 core methods: remember() and recall()

Memory Lineage Architecture:
- Level 0: Raw conversations (source)
- Level 1: Episodic events (derived from conversations)
- Level 2: Semantic facts (derived from events)
- Level 3: Principles (induced from multiple memories)

All derived memories maintain parent_ids for provenance tracking.
"""

from hmem.agents.llm import LLMClient

import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import uuid

from hmem.config import MemoryConfig
from hmem.perception.sensory_buffer import SensoryBuffer
from hmem.interfaces import MemorySystem as MemorySystemInterface
from hmem.models import (
    Conversation,
    ConsolidationResult,
    Event,
    Memory,
    Message,
    Principle,
)
from hmem.hippocampus.encoder import MemoryEncoder
from hmem.hippocampus.consolidator import Consolidator
from hmem.hippocampus.projector import EventProjector
from hmem.hippocampus.retrieval_engine import RetrievalEngine
from hmem.agents.reflection import ReflectionAgent
from hmem.storage.episodic import EpisodicStore
from hmem.storage.chroma_episodic import ChromaEpisodicStore
from hmem.storage import create_semantic_store
from hmem.storage.skill import SkillStore
from hmem.strategies.locks import FileLockProvider
from hmem.core.event_log import EventLog
from hmem.observability.tracer import get_tracer
from hmem.observability.adaptive import AdaptiveThresholdManager
import structlog

logger = structlog.get_logger()


class MemorySystem(MemorySystemInterface):
    """Cognitive Agent Memory System (CAMS) - Core Interface.

    This class orchestrates all three layers:
    - Layer 1: Perception & Working Memory (Context Manager)
    - Layer 2: Hippocampus Processing (Encoder, Consolidator, Reflector)
    - Layer 3: Long-Term Storage (Episodic, Semantic, Skill)

    Design Philosophy:
    - Unix Rule of Silence: All complexity hidden in config
    - Unix Rule of Modularity: Internal components replaceable via protocols
    - Event Sourcing: Single source of truth (append-only event log)
    - Memory Lineage: All derived memories link to their sources

    Example:
        >>> from hmem.models import Message, Conversation
        >>> memory = MemorySystem()
        >>> conversation = Conversation(
        ...     session_id="sess_001",
        ...     messages=[Message(role="user", content="I prefer dark mode")]
        ... )
        >>> memory.remember(conversation)
        >>> results = list(memory.recall("user preferences"))
        >>> # results[0].parent_ids contains the conversation ID
    """

    def __init__(self, config: MemoryConfig | None = None) -> None:
        """Initialize memory system with optional config.

        Args:
            config: Configuration object. If None, loads from default path.
        """
        self.config = config or MemoryConfig()
        self._initialized = False

        # Initialize Event Log (single source of truth)
        self._event_log = EventLog()

        # Initialize Stores
        self._episodic_store = EpisodicStore(persist_dir=None)
        self._chroma_store = ChromaEpisodicStore()

        # Initialize semantic store using factory pattern
        semantic_path = Path(self.config.storage.semantic_path)
        semantic_path.parent.mkdir(parents=True, exist_ok=True)
        self._semantic_store = create_semantic_store(
            backend="neo4j",  # type: ignore[arg-type]
            database_url=f"sqlite:///{semantic_path}",
            uri=self.config.storage.neo4j_uri,
            username=self.config.storage.neo4j_username,
            password=self.config.storage.neo4j_password,
            database=self.config.storage.neo4j_database,
        )

        # Initialize Skill Store (Phase 3)
        skill_path = Path(self.config.storage.skill_path)
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        self._skill_store = SkillStore(skill_path)

        self._llm_agent = LLMClient(
            model=self.config.llm.model,
            temperature=self.config.llm.temperature,
        )

        # Initialize lock provider based on config
        lock_provider = self._create_lock_provider()

        # Initialize Hippocampus components
        self._encoder = MemoryEncoder(llm_client=self._llm_agent)
        self._consolidator = Consolidator(
            lock_provider=lock_provider,
            semantic_store=self._semantic_store,
            encoder=self._encoder,
        )
        self._projector = EventProjector(
            event_log=self._event_log,
            episodic_store=self._chroma_store,  # type: ignore[arg-type]
            semantic_store=self._semantic_store,
        )

        # Initialize Retrieval Engine with all stores (hybrid retrieval)
        self._retrieval_engine = RetrievalEngine(
            episodic_store=self._episodic_store,
            semantic_store=self._semantic_store,
            skill_store=self._skill_store,
        )

        # Initialize Observability
        self._tracer = get_tracer()
        self._threshold_manager = AdaptiveThresholdManager()

        # Initialize Reflection Agent (LangGraph-based)
        self._reflection_agent = ReflectionAgent(
            episodic_store=self._chroma_store,
            semantic_store=self._semantic_store,
            skill_store=self._skill_store,
            llm_client=self._llm_agent,
        )

        # Active session for chat mode
        self._current_session_id: str | None = None

        # Async processing infrastructure
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="hmem_async"
        )
        self._pending_consolidations: set[str] = set()
        self._consolidation_lock = threading.Lock()

        # Sensory buffer for raw inputs
        self._sensory_buffer = SensoryBuffer(max_size=1000)

        # Reflection tracking (for threshold-based triggering)
        self._last_reflection_count = 0

    def _create_lock_provider(self) -> FileLockProvider:
        """Create lock provider based on configuration.

        Returns:
            Configured LockProvider instance
        """
        backend = self.config.lock.backend

        if backend.startswith("file://"):
            lock_dir = backend.replace("file://", "")
            return FileLockProvider(lock_dir=lock_dir)
        elif backend.startswith("redis://"):
            # Redis not yet implemented
            logger.warning(
                "redis_lock_not_implemented",
                backend=backend,
                fallback="file:///tmp/h-mem-locks",
            )
            return FileLockProvider(lock_dir="/tmp/h-mem-locks")
        else:
            # Default to file-based
            return FileLockProvider(lock_dir="/tmp/h-mem-locks")

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
    ) -> str:
        """Store conversation into memory with provenance tracking and feedback processing.

        This is a FAST operation (hot path) that:
        1. Assigns unique ID to conversation (if not provided)
        2. Extracts and processes feedback signals from XML-marked memories
        3. Appends to Event Log (single source of truth)
        4. Stores raw conversation in episodic memory (no LLM calls)
        5. Schedules async consolidation and reflection (non-blocking)

        The actual LLM-based fact extraction happens during consolidate(),
        which always runs asynchronously to keep remember() fast and non-blocking.

        Feedback Loop:
            If the conversation contains references to previously retrieved memories
            (via XML tags like <skill id="xxx">...</skill>), the LLM analyzes the
            conversation context to determine if those memories were helpful:

            The LLM extracts feedback by analyzing conversation semantics:
            - Explicit signals: "that worked!", "it failed", "successfully completed"
            - Implicit signals: task completion, error patterns, user satisfaction
            - Contextual clues: follow-up questions, alternative requests, confirmations

            Example weight updates based on LLM analysis:
            - Skill detected as successful → +1 success_count, +0.1 weight
            - Skill detected as failed → +1 failure_count, -0.1 weight
            - Principle detected as successful → +0.1 weight
            - Principle detected as failed → -0.2 weight

            Note: Feedback is NOT extracted from XML attributes. XML tags only track
            which memories were used. The LLM determines outcomes from conversation analysis.

        Args:
            conversation: Conversation or list of Message objects

        Returns:
            session_id: Session identifier

        Raises:
            MemoryError: If event log write fails
        """
        # Convert list[Message] to Conversation if needed
        if isinstance(conversation, list):
            from datetime import datetime

            session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            conversation = Conversation(
                id=f"conv_{uuid.uuid4().hex[:12]}",
                session_id=session_id,
                messages=conversation,
            )

        # Ensure conversation has an ID for provenance
        if not conversation.id:
            conversation = Conversation(
                id=f"conv_{uuid.uuid4().hex[:12]}",
                session_id=conversation.session_id,
                messages=conversation.messages,
                metadata=conversation.metadata,
            )

        # At this point conversation.id is guaranteed to be set
        assert conversation.id is not None
        conv_id: str = conversation.id  # Type-safe capture

        # Schedule async feedback extraction (uses LLM to analyze outcome signals)
        self._schedule_async_feedback_processing(conversation)

        # Log conversation to event log (single source of truth)
        self._event_log.append(conversation)

        # Store raw conversation content in episodic memory (fast, no LLM)
        # This allows immediate recall of recent conversations
        for message in conversation.messages:
            if message.role == "user":
                event = Event(
                    content=message.content,
                    outcome="unknown",
                    tags=[],
                    timestamp=message.timestamp,
                    metadata={
                        "session_id": conversation.session_id,
                        "conversation_id": conv_id,
                        "role": message.role,
                    },
                    parent_ids=[conv_id],
                    derivation_type="extraction",
                )
                self._episodic_store.add_event(event)

        # Always async consolidation (non-blocking, where LLM extraction happens)
        self._schedule_async_consolidation(conversation.session_id)

        return conversation.session_id

    def _schedule_async_consolidation(self, session_id: str) -> None:
        """Schedule async consolidation for a session.

        Prevents duplicate consolidation of the same session.

        Args:
            session_id: Session to consolidate
        """
        with self._consolidation_lock:
            if session_id in self._pending_consolidations:
                logger.debug("consolidation_already_pending", session_id=session_id)
                return
            self._pending_consolidations.add(session_id)

        def _async_work() -> None:
            try:
                self.consolidate(session_id=session_id)
                self._maybe_trigger_reflection()
            except Exception as e:
                logger.error(
                    "async_consolidation_failed",
                    session_id=session_id,
                    error=str(e),
                )
            finally:
                with self._consolidation_lock:
                    self._pending_consolidations.discard(session_id)

        self._executor.submit(_async_work)

    def _schedule_async_feedback_processing(self, conversation: Conversation) -> None:
        """Schedule async feedback signal extraction and processing.

        Extracts memory IDs from conversation (via XML tags) and uses LLM to
        analyze conversation semantics to determine which memories were helpful.

        Args:
            conversation: Conversation to analyze for feedback
        """
        # Extract memory IDs from conversation text (from XML tags)
        full_text = "\n".join(m.content for m in conversation.messages)

        # Also check metadata for explicitly tracked memory IDs
        from hmem.hippocampus.retrieval_engine import extract_memory_ids

        used_memory_ids = list(extract_memory_ids(full_text))

        # Merge with any IDs explicitly tracked in metadata
        metadata_ids = conversation.metadata.get("used_memory_ids", [])
        if metadata_ids:
            used_memory_ids.extend(metadata_ids)
            used_memory_ids = list(set(used_memory_ids))  # Deduplicate

        if not used_memory_ids:
            return

        def _async_feedback_work() -> None:
            try:
                # LLM analyzes conversation semantics to determine outcomes
                signals = self._llm_agent.extract_feedback_signals(
                    full_text, used_memory_ids
                )

                if not signals:
                    return

                logger.info(
                    "feedback_signals_extracted",
                    count=len(signals),
                    signals=[(s["memory_id"], s["outcome"]) for s in signals],
                )

                for signal in signals:
                    self._apply_feedback(
                        memory_id=signal["memory_id"],
                        outcome=signal["outcome"],
                    )
            except Exception as e:
                logger.warning("async_feedback_processing_failed", error=str(e))

        self._executor.submit(_async_feedback_work)

    def _apply_feedback(
        self, memory_id: str, outcome: str, confidence: float = 1.0
    ) -> None:
        """Apply feedback to a memory based on outcome.

        Updates weights and success/failure counts appropriately based on
        memory type (inferred from ID prefix).

        Args:
            memory_id: Memory identifier
            outcome: "success" or "failure"
            confidence: Confidence in the outcome assessment (0-1)
        """
        success = outcome == "success"

        # Skill-specific handling
        if memory_id.startswith("skill_"):
            if success:
                self._skill_store.record_success(memory_id)
            else:
                self._skill_store.record_failure(memory_id)

        # Adaptive weight adjustment based on outcome and memory type
        # Using confidence multiplier for more intelligent updates
        confidence_multiplier = 2.0  # Amplify confident feedback
        base_delta_positive = 0.1
        base_delta_negative = -0.15  # Slightly larger penalty for failures

        if success:
            delta = base_delta_positive * (1 + confidence * confidence_multiplier)
        else:
            delta = base_delta_negative * (1 + confidence * confidence_multiplier)

        # Memory type specific adjustments
        if memory_id.startswith("principle_"):
            # Principles are more conservative with changes
            delta *= 0.8

        # Apply delta with boundary check [0, 10]
        self._update_memory_weight(memory_id, delta, min_weight=0.0, max_weight=10.0)

        # Propagate along provenance chain
        self._propagate_feedback(memory_id, success)

        logger.info(
            "feedback_applied",
            memory_id=memory_id,
            outcome=outcome,
            weight_delta=delta,
            confidence=confidence,
        )

    def recall(
        self,
        query: str | Message | Conversation,
        limit: int = 10,
        filters: dict[str, str] | None = None,
    ) -> Iterator[Memory]:
        """Retrieve relevant memories with provenance information.

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
            Memory objects ranked by relevance (with parent_ids for provenance)

        Raises:
            RetrievalError: If retrieval fails
        """
        # Convert query to string
        query_text = self._convert_query_to_text(query)

        # Delegate to retrieval engine
        yield from self._retrieval_engine.retrieve(query_text, limit, filters)

    def get_lineage(self, memory_id: str, max_depth: int = 3) -> list[str]:
        """Get the provenance chain for a memory.

        Traverse the parent_ids to find the complete derivation history
        of a memory, from derived to raw source.

        Args:
            memory_id: ID of the memory to trace
            max_depth: Maximum depth to traverse

        Returns:
            List of ancestor memory IDs (ordered from immediate parent to root)
        """
        return self._episodic_store.get_lineage(memory_id, max_depth)

    def get_derived(self, memory_id: str) -> list[Memory]:
        """Get all memories derived from a source memory.

        Find all memories that have memory_id in their parent_ids.

        Args:
            memory_id: ID of the source memory

        Returns:
            List of derived memories
        """
        events = self._episodic_store.get_children(memory_id)
        return [
            Memory(
                id=e.id,
                content=e.content,
                score=1.0,
                source="episodic",
                timestamp=e.timestamp,
                metadata=e.metadata,
                parent_ids=e.parent_ids,
                derivation_type=e.derivation_type,
            )
            for e in events
        ]

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

    def consolidate(self, session_id: str) -> ConsolidationResult:
        """Trigger memory consolidation (cold path).

        This is called:
        - Synchronously at session end (Phase 1)
        - Asynchronously by scheduler (Phase 3)

        Args:
            session_id: Session to consolidate

        Returns:
            ConsolidationResult with statistics

        Raises:
            ConsolidationError: If consolidation fails
        """
        # Get events for session
        events = self._event_log.get_session_events(session_id)

        # Consolidate
        return self._consolidator.consolidate(session_id, events)

    def _get_semantic_stats(self) -> dict[str, int]:
        """Get semantic store statistics.

        Returns:
            Statistics dictionary
        """
        if hasattr(self._semantic_store, "get_stats"):
            return self._semantic_store.get_stats()
        return {"total_triples": 0}

    def health(self) -> dict[str, str | int]:
        """Get system health status.

        Returns:
            Health metrics: status, memory_count, latency_p95, etc.
        """
        episodic_stats = self._episodic_store.get_stats()
        semantic_stats = self._get_semantic_stats()
        skill_stats = self._skill_store.get_stats()
        tracer_stats = self._tracer.get_stats()

        return {
            "status": "healthy",
            "version": "0.1.0",
            "episodic_count": episodic_stats.get("total_count", 0),
            "semantic_count": semantic_stats.get("total_triples", 0),
            "skill_count": skill_stats.get("total_skills", 0),
            "retrieval_p95_ms": tracer_stats.get("p95_ms", 0.0),
        }

    def explain_recall(self, query: str) -> dict[str, str | float]:
        """Explain how a query would be processed (observability).

        Args:
            query: Query to explain

        Returns:
            Explanation with threshold, cache status, estimated latency
        """
        # Get topic hash for threshold lookup
        topic = query[:50]  # Simple topic extraction
        threshold = self._threshold_manager.get_threshold(topic)
        effectiveness = self._threshold_manager.get_effectiveness(topic)
        stats = self._tracer.get_stats()

        return {
            "query": query,
            "topic": topic,
            "threshold": threshold,
            "effectiveness": effectiveness,
            "estimated_latency_ms": stats.get("p95_ms", 50.0),
            "cache_enabled": True,
        }

    def chat(
        self,
        message: str | Message,
        session_id: str | None = None,
    ) -> tuple[list[Memory], str]:
        """Interactive chat with memory context retrieval.

        This integrates ContextManager functionality for interactive use.
        Automatically retrieves relevant memories and maintains session context.

        Args:
            message: User message (str or Message object)
            session_id: Session ID (auto-creates if None)

        Returns:
            Tuple of (relevant_memories, session_id)
        """
        # Convert string to Message
        if isinstance(message, str):
            message = Message(role="user", content=message)

        # Manage session
        if session_id:
            self._current_session_id = session_id
        elif not self._current_session_id:
            from datetime import datetime

            self._current_session_id = (
                f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )

        # Retrieve relevant memories for context
        with self._tracer.trace(f"chat_{self._current_session_id}") as ctx:
            with ctx.timed_stage("memory_retrieval"):
                memories = list(self.recall(message, limit=5))

            # Store this message in event log for future recall
            with ctx.timed_stage("message_storage"):
                from hmem.models import Event
                from datetime import datetime

                event = Event(
                    content=message.content,
                    outcome="success",
                    tags=["chat", self._current_session_id or "unknown"],
                    timestamp=datetime.now(),
                    metadata={
                        "session_id": self._current_session_id or "unknown",
                        "role": message.role,
                        "type": "chat_message",
                    },
                )
                self._episodic_store.add_event(event)

        logger.debug(
            "chat_processed",
            session_id=self._current_session_id,
            memories_found=len(memories),
        )

        return memories, self._current_session_id

    def reflect(self) -> list[Principle]:
        """Manually trigger reflection on a topic or all topics.

        Args:
            topic: Optional topic to focus reflection on. If None, reflects on all topics.

        Returns:
            List of extracted Principle objects
        """
        return self._reflection_agent.reflect()

    def auto_reflect(self) -> list[Principle]:
        """Run auto-reflection on all topics.

        Uses semantic clustering to discover topics automatically
        and extracts principles from each cluster.

        Returns:
            List of extracted Principle objects
        """
        return self._reflection_agent.reflect()

    def _maybe_trigger_reflection(self) -> None:
        """Check if reflection should be triggered based on memory accumulation.

        Called after consolidation to potentially trigger automatic reflection.
        The new LangGraph-based agent uses semantic clustering to discover
        topics automatically, so we trigger based on total memory count
        rather than specific tags.

        Memory hierarchy compression:
        - Level 1 (Episodic Events) accumulates
        - When count hits threshold → Level 3 (Principle) extraction
        - This creates automatic "compression" as memories build up

        Runs asynchronously to avoid blocking the main thread.
        """
        total_memories = self._chroma_store.count()
        trigger_threshold = self.config.reflection.trigger_threshold

        # Use delta-based triggering instead of modulo
        if total_memories - self._last_reflection_count >= trigger_threshold:
            self._last_reflection_count = total_memories

            def _async_reflect() -> None:
                try:
                    principles = self._reflection_agent.reflect(
                        min_cluster_size=self.config.reflection.min_episodes
                    )

                    if principles:
                        logger.info(
                            "auto_reflection_complete",
                            memory_count=total_memories,
                            principles_extracted=len(principles),
                        )
                except Exception as e:
                    # Reflection failure should not break remember()
                    logger.warning("auto_reflection_failed", error=str(e))

            self._executor.submit(_async_reflect)

    def end_session(self, session_id: str | None = None) -> ConsolidationResult:
        """End a session and trigger consolidation.

        Args:
            session_id: Session to end (uses current if None)

        Returns:
            Consolidation result with statistics
        """
        sid = session_id or self._current_session_id
        if not sid:
            return ConsolidationResult(
                success=True,
                stored_events=0,
                updated_facts=0,
                conflicts_resolved=0,
                errors=["No active session"],
            )

        result = self.consolidate(sid)

        if sid == self._current_session_id:
            self._current_session_id = None

        return result

    def shutdown(self, wait: bool = True, timeout: float = 30.0) -> None:
        """Gracefully shutdown the memory system.

        Waits for pending async consolidations and reflections to complete.

        Args:
            wait: If True, waits for pending tasks to complete
            timeout: Maximum seconds to wait for pending tasks
        """
        if wait:
            # Wait for pending consolidations
            self._executor.shutdown(wait=True)
        else:
            self._executor.shutdown(wait=False, cancel_futures=True)

        logger.info(
            "memory_system_shutdown", pending_tasks=len(self._pending_consolidations)
        )

    def __del__(self) -> None:
        """Cleanup on destruction."""
        try:
            self.shutdown(wait=False)
        except Exception:
            pass  # Best effort cleanup

    def rebuild_from_log(self) -> dict[str, int]:
        """Rebuild all derived views from event log.

        Use this for recovery after data corruption or schema changes.

        Returns:
            Statistics about rebuilt data
        """
        return self._projector.rebuild_from_log()

    # ============ Skill Store Methods (Phase 3) ============

    def add_skill(
        self,
        name: str,
        trigger_pattern: str,
        code_template: dict[str, str],
        description: str | None = None,
        parent_ids: list[str] | None = None,
    ) -> str:
        """Add a new skill template to procedural memory.

        Skills are reusable patterns that can be triggered when similar
        queries are detected. They represent the "how to do things" knowledge.

        Args:
            name: Unique skill identifier (e.g., "web_scraping")
            trigger_pattern: Pattern to match for activation (supports | for OR)
            code_template: Template with steps/parameters for the skill
            description: Human-readable description
            parent_ids: Source memory IDs (for provenance tracking)

        Returns:
            skill_id: Unique identifier for the skill

        Example:
            >>> skill_id = memory.add_skill(
            ...     name="search_summarize",
            ...     trigger_pattern="search and summarize|find and summarize",
            ...     code_template={"steps": ["search", "filter", "summarize"]},
            ...     description="Search for info then summarize results"
            ... )
        """
        return self._skill_store.add_skill(
            name=name,
            trigger_pattern=trigger_pattern,
            code_template=code_template,
            description=description,
            parent_ids=parent_ids,
        )

    def get_skill(self, name: str) -> dict[str, str] | None:
        """Retrieve a skill by name.

        Args:
            name: Skill identifier

        Returns:
            Skill template dictionary or None if not found
        """
        return self._skill_store.get_skill(name)

    def search_skills(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        """Search for relevant skills based on query.

        Matches query against trigger patterns and returns skills
        sorted by match score and success rate.

        Args:
            query: User query to match
            limit: Maximum results

        Returns:
            List of matching skill templates
        """
        return self._skill_store.search_by_trigger(query, limit)

    def _propagate_feedback(
        self,
        memory_id: str,
        success: bool,
        max_depth: int = 3,
        decay_factor: float = 0.8,
    ) -> None:
        """Recursively propagate feedback signal along the provenance chain.

        Strengthens memories that contributed to successful outcomes,
        weakens those that led to failures. The effect diminishes
        as we traverse up the ancestry chain.

        Args:
            memory_id: Starting memory ID (skill, event, or principle)
            success: Whether the outcome was successful
            max_depth: Maximum depth to traverse up the lineage
            decay_factor: Multiplier for weight delta at each level
        """
        base_delta = 0.1 if success else -0.05
        visited: set[str] = set()

        def _propagate_recursive(mem_id: str, depth: int, current_delta: float) -> None:
            if depth >= max_depth or abs(current_delta) < 0.01:
                return
            if mem_id in visited:
                return
            visited.add(mem_id)

            # Update this memory's weight
            self._update_memory_weight(mem_id, current_delta)

            # Collect parent IDs from all possible sources
            parent_ids: list[str] = []

            # Check skill store
            skill = self._skill_store.get_skill_by_id(mem_id)
            if skill and skill.get("parent_ids"):
                parent_ids.extend(skill["parent_ids"])

            # Check episodic store
            event = self._episodic_store.get_by_id(mem_id)
            if event and event.parent_ids:
                parent_ids.extend(event.parent_ids)

            # Recursively propagate to parents with decayed weight
            next_delta = current_delta * decay_factor
            for parent_id in parent_ids:
                _propagate_recursive(parent_id, depth + 1, next_delta)

        _propagate_recursive(memory_id, 0, base_delta)

    def _update_memory_weight(
        self,
        memory_id: str,
        delta: float,
        min_weight: float = 0.0,
        max_weight: float = 10.0,
    ) -> bool:
        """Update the weight of a memory by ID with boundary checks.

        Handles different memory types (episodic, semantic) and ensures
        weights stay within configured bounds.

        Args:
            memory_id: Memory identifier
            delta: Weight change
            min_weight: Minimum allowed weight
            max_weight: Maximum allowed weight

        Returns:
            True if updated successfully
        """
        updated = False
        stores_to_check = [
            ("episodic", self._episodic_store),
            ("semantic", self._semantic_store),
        ]

        for store_name, store in stores_to_check:
            # Check if store has get_weight method
            if not hasattr(store, "get_weight"):
                # Fallback: update without boundary check
                if store.update_weight(memory_id, delta):
                    updated = True
                    logger.debug(
                        "memory_weight_updated_without_clamp",
                        memory_id=memory_id,
                        delta=delta,
                        store=store_name,
                        reason="get_weight not supported",
                    )
                continue

            # Get current weight
            current_weight = store.get_weight(memory_id)
            if current_weight is None:
                continue  # Memory not in this store

            # Calculate new weight with boundary checks
            new_weight = current_weight + delta
            clamped_weight = max(min_weight, min(max_weight, new_weight))
            actual_delta = clamped_weight - current_weight

            # Only update if delta is non-zero after clamping
            if abs(actual_delta) > 1e-6:
                if store.update_weight(memory_id, actual_delta):
                    updated = True
                    logger.debug(
                        "memory_weight_updated",
                        memory_id=memory_id,
                        store=store_name,
                        current_weight=current_weight,
                        requested_delta=delta,
                        actual_delta=actual_delta,
                        new_weight=clamped_weight,
                        clamped=abs(actual_delta - delta) > 1e-6,
                    )
            else:
                # Weight already at boundary
                logger.debug(
                    "memory_weight_at_boundary",
                    memory_id=memory_id,
                    store=store_name,
                    current_weight=current_weight,
                    requested_delta=delta,
                    min_weight=min_weight,
                    max_weight=max_weight,
                )

        return updated
