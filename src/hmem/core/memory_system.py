from hmem.agents.llm import LLMClient

import threading
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
import uuid
from typing import Any

from datetime import datetime

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

from hmem.hippocampus.retrieval_engine import RetrievalEngine
from hmem.hippocampus.policies.reflection import (
    MultiScalePolicy,
    ReflectionContext,
)
from hmem.agents.reflection import ReflectionAgent
from hmem.storage.chroma_episodic import ChromaEpisodicStore
from hmem.storage import create_semantic_store
from hmem.storage.skill import SkillStore
from hmem.strategies.locks import (
    LockProvider,
    create_lock_provider,
)
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

        # Initialize Stores - use ChromaDB for persistent episodic storage
        self._episodic_store = ChromaEpisodicStore()
        self._chroma_store = self._episodic_store  # Alias for backward compatibility

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

        # Initialize Observability (before retrieval engine)
        self._tracer = get_tracer()
        self._threshold_manager = AdaptiveThresholdManager()

        # Initialize Retrieval Engine with all stores (hybrid retrieval)
        # Pass threshold manager if adaptive threshold is enabled
        threshold_mgr = (
            self._threshold_manager
            if self.config.retrieval.adaptive_threshold
            else None
        )
        self._retrieval_engine = RetrievalEngine(
            episodic_store=self._episodic_store,
            semantic_store=self._semantic_store,
            skill_store=self._skill_store,
            threshold_manager=threshold_mgr,
            llm_client=self._llm_agent,
            enable_relevance_filter=self.config.retrieval.enable_relevance_filter,
            min_relevance_score=self.config.retrieval.min_relevance_score,
        )

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
        self._pending_consolidations: dict[str, Future[ConsolidationResult]] = {}
        self._consolidation_lock = threading.Lock()

        # Sensory buffer for raw inputs
        self._sensory_buffer = SensoryBuffer(max_size=1000)

        # Initialize reflection policy from config
        self._reflection_policy = MultiScalePolicy(
            immediate_threshold=self.config.reflection.immediate_threshold,
            daily_interval=self.config.reflection.daily_interval,
            weekly_interval=self.config.reflection.weekly_interval,
        )

        # Reflection tracking (for policy-based triggering)
        self._last_reflection_count = 0
        self._last_reflection_time: datetime | None = None

    def _create_lock_provider(self) -> LockProvider:
        """Create lock provider based on configuration.

        Supports:
        - file:// - File-based locks (single machine)
        - redis:// - Redis distributed locks (Phase 3)

        Returns:
            Configured LockProvider instance
        """
        backend = self.config.lock.backend
        return create_lock_provider(backend)

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

    def _normalize_conversation(
        self, conversation: Conversation | list[Message]
    ) -> Conversation:
        """Convert list[Message] to Conversation and ensure it has an ID."""
        if isinstance(conversation, list):
            from datetime import datetime

            session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            return Conversation(
                id=f"conv_{uuid.uuid4().hex[:12]}",
                session_id=session_id,
                messages=conversation,
            )

        # Ensure conversation has an ID for provenance
        if not conversation.id:
            return Conversation(
                id=f"conv_{uuid.uuid4().hex[:12]}",
                session_id=conversation.session_id,
                messages=conversation.messages,
                metadata=conversation.metadata,
            )

        return conversation

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
        # Normalize conversation format and ensure ID
        conversation = self._normalize_conversation(conversation)
        conv_id = conversation.id
        assert (
            conv_id is not None
        )  # Type guard: _normalize_conversation ensures ID exists

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

        def _async_work() -> ConsolidationResult:
            try:
                result = self._do_consolidate(session_id)
                self._maybe_trigger_reflection()
                return result
            except Exception as e:
                logger.error(
                    "async_consolidation_failed",
                    session_id=session_id,
                    error=str(e),
                )
                raise
            finally:
                with self._consolidation_lock:
                    self._pending_consolidations.pop(session_id, None)

        future = self._executor.submit(_async_work)
        with self._consolidation_lock:
            self._pending_consolidations[session_id] = future

    def _schedule_async_feedback_processing(self, conversation: Conversation) -> None:
        """Schedule async feedback signal extraction and processing.

        Extracts memory IDs from conversation (via XML tags) and uses LLM to
        analyze conversation semantics to determine which memories were helpful.

        Enhanced to track "recalled but ignored" memories (Gemini feedback fix):
        - Memories with explicit feedback signals get success/failure outcome
        - Memories that were recalled but not referenced get "unknown_ignored" outcome
        - This helps the system learn which memories are actually useful vs
          just taking up context window space

        Args:
            conversation: Conversation to analyze for feedback
        """
        # Extract memory IDs from conversation text (from XML tags)
        full_text = "\n".join(m.content for m in conversation.messages)

        # Also check metadata for explicitly tracked memory IDs
        from hmem.hippocampus.retrieval_engine import extract_memory_ids

        recalled_memory_ids = set(extract_memory_ids(full_text))

        # Merge with any IDs explicitly tracked in metadata
        metadata_ids = conversation.metadata.get("used_memory_ids", [])
        if metadata_ids:
            recalled_memory_ids.update(metadata_ids)

        if not recalled_memory_ids:
            return

        def _async_feedback_work() -> None:
            try:
                # LLM analyzes conversation semantics to determine outcomes
                signals = self._llm_agent.extract_feedback_signals(
                    full_text, list(recalled_memory_ids)
                )

                # Track which memories got explicit feedback
                memories_with_feedback: set[str] = set()

                if signals:
                    logger.info(
                        "feedback_signals_extracted",
                        count=len(signals),
                        signals=[(s["memory_id"], s["outcome"]) for s in signals],
                    )

                    for signal in signals:
                        memories_with_feedback.add(signal["memory_id"])
                        self._apply_feedback(
                            memory_id=signal["memory_id"],
                            outcome=signal["outcome"],
                        )

                # Apply "unknown_ignored" to recalled memories without feedback
                # (Gemini feedback fix: penalize memories that were recalled but not used)
                ignored_memories = recalled_memory_ids - memories_with_feedback
                if ignored_memories:
                    logger.info(
                        "ignored_memories_detected",
                        count=len(ignored_memories),
                        memory_ids=list(ignored_memories)[:5],  # Log first 5
                    )
                    for mem_id in ignored_memories:
                        self._apply_feedback(
                            memory_id=mem_id,
                            outcome="unknown_ignored",
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

    def record_retrieval_feedback(
        self,
        query: str,
        accepted: bool,
        result_count: int = 0,
    ) -> None:
        """Record user feedback for adaptive threshold adjustment.

        Call this method when you can determine whether the retrieval
        results were useful to the user. This helps the system learn
        per-topic thresholds.

        Args:
            query: Original query that was executed
            accepted: Whether user found the results useful
            result_count: Number of results that were shown

        Example:
            >>> # User found results helpful
            >>> memory.record_retrieval_feedback("web scraping", accepted=True, result_count=5)
            >>>
            >>> # User rejected all results
            >>> memory.record_retrieval_feedback("python tips", accepted=False, result_count=10)
        """
        self._retrieval_engine.record_feedback(query, accepted, result_count)

        # Also record in threshold manager directly for stats
        topic = query[:50]
        threshold = self._threshold_manager.get_threshold(topic)
        logger.info(
            "retrieval_feedback_recorded",
            query=query[:50],
            accepted=accepted,
            result_count=result_count,
            current_threshold=threshold,
        )

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

        If an async consolidation is already in progress for this session,
        waits for it to complete instead of starting a new one.

        Args:
            session_id: Session to consolidate

        Returns:
            ConsolidationResult with statistics

        Raises:
            ConsolidationError: If consolidation fails
        """
        # Check if there's already a pending consolidation for this session
        with self._consolidation_lock:
            pending_future = self._pending_consolidations.get(session_id)

        if pending_future is not None:
            # Wait for the pending consolidation to complete
            logger.debug(
                "consolidation_waiting_for_pending",
                session_id=session_id,
            )
            try:
                return pending_future.result(timeout=60.0)
            except Exception as e:
                logger.warning(
                    "pending_consolidation_failed",
                    session_id=session_id,
                    error=str(e),
                )
                # Fall through to do a fresh consolidation

        return self._do_consolidate(session_id)

    def _do_consolidate(self, session_id: str) -> ConsolidationResult:
        """Execute consolidation for a session.

        Internal method that does the actual consolidation work.

        Args:
            session_id: Session to consolidate

        Returns:
            ConsolidationResult with statistics
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
        # SemanticStoreProtocol requires get_stats method
        return self._semantic_store.get_stats()

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

    def health_check(self) -> dict[str, Any]:
        """Deep system health check (Phase 3 Diagnostic).

        Performs comprehensive checks on all system components:
        - Database connectivity and health
        - Index integrity
        - Memory usage
        - Performance metrics
        - Pending operations

        Returns:
            Detailed health report with component statuses
        """
        import os
        import time

        try:
            import psutil  # type: ignore[import-untyped]

            psutil_available = True
        except ImportError:
            psutil_available = False

        health_report: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "status": "healthy",
            "version": "0.1.0",
            "components": {},
            "metrics": {},
            "warnings": [],
            "errors": [],
        }

        # Check Episodic Store (ChromaDB)
        try:
            start = time.time()
            episodic_stats = self._episodic_store.get_stats()
            episodic_latency = (time.time() - start) * 1000

            health_report["components"]["episodic"] = {
                "status": "healthy",
                "backend": "chromadb",
                "total_count": episodic_stats.get("total_count", 0),
                "check_latency_ms": round(episodic_latency, 2),
            }
        except Exception as e:
            health_report["components"]["episodic"] = {
                "status": "error",
                "error": str(e),
            }
            health_report["errors"].append(f"Episodic store: {e}")
            health_report["status"] = "degraded"

        # Check Semantic Store (Neo4j)
        try:
            start = time.time()
            semantic_stats = self._semantic_store.get_stats()
            semantic_latency = (time.time() - start) * 1000

            health_report["components"]["semantic"] = {
                "status": "healthy",
                "backend": "neo4j",
                "total_triples": semantic_stats.get("total_triples", 0),
                "superseded_triples": semantic_stats.get("superseded_triples", 0),
                "check_latency_ms": round(semantic_latency, 2),
            }
        except Exception as e:
            health_report["components"]["semantic"] = {
                "status": "error",
                "error": str(e),
            }
            health_report["errors"].append(f"Semantic store: {e}")
            health_report["status"] = "degraded"

        # Check Skill Store (SQLite)
        try:
            start = time.time()
            skill_stats = self._skill_store.get_stats()
            skill_latency = (time.time() - start) * 1000

            health_report["components"]["skill"] = {
                "status": "healthy",
                "backend": "sqlite",
                "total_skills": skill_stats.get("total_skills", 0),
                "check_latency_ms": round(skill_latency, 2),
            }
        except Exception as e:
            health_report["components"]["skill"] = {
                "status": "error",
                "error": str(e),
            }
            health_report["errors"].append(f"Skill store: {e}")
            health_report["status"] = "degraded"

        # Check Event Log
        try:
            event_log_stats = self._event_log.count()
            health_report["components"]["event_log"] = {
                "status": "healthy",
                "total_entries": event_log_stats.get("total_entries", 0),
                "sessions": event_log_stats.get("sessions", 0),
            }
        except Exception as e:
            health_report["components"]["event_log"] = {
                "status": "error",
                "error": str(e),
            }
            health_report["warnings"].append(f"Event log: {e}")

        # Performance metrics
        tracer_stats = self._tracer.get_stats()
        health_report["metrics"]["retrieval"] = {
            "p50_ms": tracer_stats.get("p50_ms", 0.0),
            "p95_ms": tracer_stats.get("p95_ms", 0.0),
            "p99_ms": tracer_stats.get("p99_ms", 0.0),
            "total_calls": tracer_stats.get("total_calls", 0),
        }

        # Adaptive threshold stats
        threshold_stats = self._threshold_manager.get_stats()
        health_report["metrics"]["adaptive_threshold"] = {
            "topics_tracked": threshold_stats.get("topics_tracked", 0),
            "total_feedback": threshold_stats.get("total_feedback", 0),
        }

        # Memory usage
        if psutil_available:
            try:
                process = psutil.Process(os.getpid())
                memory_info = process.memory_info()
                health_report["metrics"]["memory"] = {
                    "rss_mb": round(memory_info.rss / 1024 / 1024, 2),
                    "vms_mb": round(memory_info.vms / 1024 / 1024, 2),
                }
            except Exception:
                health_report["metrics"]["memory"] = {
                    "error": "failed to get memory info"
                }
        else:
            health_report["metrics"]["memory"] = {"error": "psutil not installed"}

        # Pending operations
        with self._consolidation_lock:
            pending_count = len(self._pending_consolidations)
        health_report["metrics"]["pending_operations"] = {
            "consolidations": pending_count,
        }

        # Warnings
        if health_report["components"]["episodic"].get("total_count", 0) > 100000:
            health_report["warnings"].append(
                "Episodic store has >100k entries - consider pruning"
            )

        if tracer_stats.get("p95_ms", 0) > 500:
            health_report["warnings"].append(
                f"Retrieval P95 latency ({tracer_stats.get('p95_ms', 0):.0f}ms) exceeds target (500ms)"
            )

        return health_report

    def explain_recall(self, query: str) -> dict[str, Any]:
        """Explain how a query would be processed (Phase 3 Diagnostic).

        Provides detailed information about the retrieval process including:
        - Query analysis and topic extraction
        - Adaptive threshold for this topic
        - Cache status
        - Source breakdown (which stores would be queried)
        - Estimated latency
        - Sample results (if any)

        Args:
            query: Query to explain

        Returns:
            Detailed explanation of retrieval process
        """
        import time

        # Topic extraction (simple hash for now)
        topic = query[:50]
        threshold = self._threshold_manager.get_threshold(topic)
        effectiveness = self._threshold_manager.get_effectiveness(topic)

        # Check cache
        cache_key = f"{query}:10"  # Default limit
        cache_hit = cache_key in self._retrieval_engine._cache

        # Get store stats
        episodic_stats = self._episodic_store.get_stats()
        semantic_stats = self._get_semantic_stats()
        skill_stats = self._skill_store.get_stats()

        # Performance stats
        tracer_stats = self._tracer.get_stats()

        # Sample retrieval (limited) to show what would be returned
        sample_results: list[dict[str, Any]] = []
        try:
            start = time.time()
            results = list(self.recall(query, limit=3))
            actual_latency = (time.time() - start) * 1000

            for mem in results:
                sample_results.append(
                    {
                        "id": mem.id,
                        "source": mem.source,
                        "score": round(mem.score, 3),
                        "content_preview": mem.content[:100] + "..."
                        if len(mem.content) > 100
                        else mem.content,
                    }
                )
        except Exception as e:
            actual_latency = 0.0
            sample_results = [{"error": str(e)}]

        return {
            "query": query,
            "analysis": {
                "topic": topic,
                "query_length": len(query),
                "word_count": len(query.split()),
            },
            "threshold": {
                "current": threshold,
                "effectiveness": effectiveness,
                "feedback_count": self._threshold_manager._accept_counts.get(topic, 0)
                + self._threshold_manager._reject_counts.get(topic, 0),
            },
            "cache": {
                "enabled": True,
                "hit": cache_hit,
                "size": len(self._retrieval_engine._cache),
            },
            "sources": {
                "episodic": {
                    "available": True,
                    "total_count": episodic_stats.get("total_count", 0),
                },
                "semantic": {
                    "available": self._semantic_store is not None,
                    "total_triples": semantic_stats.get("total_triples", 0),
                },
                "skill": {
                    "available": self._skill_store is not None,
                    "total_skills": skill_stats.get("total_skills", 0),
                },
            },
            "latency": {
                "estimated_p95_ms": tracer_stats.get("p95_ms", 50.0),
                "actual_ms": round(actual_latency, 2),
            },
            "sample_results": sample_results,
            "retrieval_path": [
                "1. Check cache (sync)",
                "2. Query episodic store (vector search)",
                "3. Query semantic store (graph search)",
                "4. Query skill store (pattern match)",
                "5. Hybrid ranking (similarity + recency + quality)",
                "6. Apply adaptive threshold",
                "7. Return top-k results",
            ],
        }

    def reflect(self) -> list[Principle]:
        """Manually trigger reflection on a topic or all topics.

        Args:
            topic: Optional topic to focus reflection on. If None, reflects on all topics.

        Returns:
            List of extracted Principle objects
        """
        return self._reflection_agent.reflect()

    def _maybe_trigger_reflection(self) -> None:
        """Check if reflection should be triggered based on policy.

        Called after consolidation to potentially trigger automatic reflection.
        Uses MultiScalePolicy for intelligent triggering based on:
        - Immediate: event count threshold
        - Daily: 24-hour interval
        - Weekly: 7-day interval

        Memory hierarchy compression:
        - Level 1 (Episodic Events) accumulates
        - When policy triggers → Level 3 (Principle) extraction
        - This creates automatic "compression" as memories build up

        Runs asynchronously to avoid blocking the main thread.
        """
        total_memories = self._chroma_store.count()
        new_events = total_memories - self._last_reflection_count

        # Build context for policy evaluation
        context = ReflectionContext(
            episode_count=new_events,
            time_span_days=0.0,  # Not tracked currently
            avg_similarity=0.0,  # Not tracked currently
            last_reflection_time=self._last_reflection_time,
        )

        # Use policy to decide if reflection should trigger
        if self._reflection_policy.should_reflect(context):
            self._last_reflection_count = total_memories
            self._last_reflection_time = datetime.now()

            logger.info(
                "reflection_triggered",
                event_count=new_events,
                total_memories=total_memories,
                policy="MultiScalePolicy",
            )

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
            "memory_system_shutdown",
            pending_tasks=len(self._pending_consolidations),
        )

    def __del__(self) -> None:
        """Cleanup on destruction."""
        try:
            self.shutdown(wait=False)
        except Exception:
            pass  # Best effort cleanup

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
            if skill and skill.parent_ids:
                parent_ids.extend(skill.parent_ids)

            # Check episodic store
            event = self._episodic_store.get_by_id(mem_id)
            if event and event.parent_ids:
                parent_ids.extend(event.parent_ids)

            # Recursively propagate to parents with decayed weight
            next_delta = current_delta * decay_factor
            for parent_id in parent_ids:
                _propagate_recursive(parent_id, depth + 1, next_delta)

        _propagate_recursive(memory_id, 0, base_delta)

    def _update_weight_in_store(
        self,
        store: Any,
        memory_id: str,
        delta: float,
        min_weight: float,
        max_weight: float,
        store_name: str,
    ) -> bool:
        """Update weight in a specific store with boundary checks."""
        current_weight = store.get_weight(memory_id)
        if current_weight is None:
            return False

        new_weight = current_weight + delta
        clamped_weight = max(min_weight, min(max_weight, new_weight))
        actual_delta = clamped_weight - current_weight

        if abs(actual_delta) <= 1e-6:
            return False

        if store.update_weight(memory_id, actual_delta):
            logger.debug(
                "memory_weight_updated",
                memory_id=memory_id,
                store=store_name,
                current_weight=current_weight,
                requested_delta=delta,
                actual_delta=actual_delta,
                new_weight=clamped_weight,
            )
            return True

        return False

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

        Note:
            Both ChromaEpisodicStore and Neo4jSemanticStore implement update_weight
            and get_weight methods. This is enforced by design.
        """
        # Try episodic store first
        if self._update_weight_in_store(
            self._episodic_store, memory_id, delta, min_weight, max_weight, "episodic"
        ):
            return True

        # Try semantic store
        if self._update_weight_in_store(
            self._semantic_store, memory_id, delta, min_weight, max_weight, "semantic"
        ):
            return True

        # Memory not found in any store (not an error - could be skill which has its own tracking)
        return False
