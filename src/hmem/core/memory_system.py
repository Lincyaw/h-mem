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
    IndexProfile,
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
from hmem.strategies.q_learning import QValueUpdater
from hmem.strategies.evolution import CompositeEvolutionHook, BatchEvolutionHook, TimeBasedHook
from hmem.strategies.refine import determine_refine_action, create_refined_profile, RefineAction
from hmem.core.event_log import EventLog
from hmem.observability.tracer import get_tracer
from hmem.observability.adaptive import AdaptiveThresholdManager
from hmem.models import SystemStats
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

        # Q-value updater for feedback processing
        self._q_updater = QValueUpdater(alpha=self.config.q_learning.alpha)

        # Initialize reflection policy from config
        self._reflection_policy = MultiScalePolicy(
            immediate_threshold=self.config.reflection.immediate_threshold,
            daily_interval=self.config.reflection.daily_interval,
            weekly_interval=self.config.reflection.weekly_interval,
        )

        # Reflection tracking (for policy-based triggering)
        self._last_reflection_count = 0
        self._last_reflection_time: datetime | None = None

        # Remember counter for evolution triggering
        self._remember_count = 0

        # Evolution system infrastructure
        self._evolution_hooks = CompositeEvolutionHook(
            hooks=[
                BatchEvolutionHook(batch_size=50),
                TimeBasedHook(interval_hours=24),
            ],
            mode="any",  # Trigger if either condition is met
        )
        self._system_stats = SystemStats()
        self._last_evolution_at: datetime | None = None

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

            Q-value updates based on LLM analysis:
            - Memory detected as successful → Q-value increases toward 1.0
            - Memory detected as failed → Q-value decreases toward 0.0
            - Memory recalled but ignored → slight Q-value decrease

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

        # [Sync] Log conversation to event log (single source of truth) - fast return
        self._event_log.append(conversation)

        # [Async] Schedule feedback extraction (uses LLM to analyze outcome signals)
        self._schedule_async_feedback_processing(conversation)

        # [Async] Schedule incremental processing (extract events + consolidation + evolution)
        self._schedule_incremental_processing()

        self._remember_count += 1
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

    def _schedule_incremental_processing(self) -> None:
        """Schedule async incremental processing of new conversations.

        This implements the lightweight sync + incremental async pattern:
        - remember() writes to Event Log synchronously (fast)
        - This method processes unprocessed conversations asynchronously

        Processing pipeline for each unprocessed conversation:
        1. Extract structured events via MemoryEncoder
        2. Write events to episodic store (with embeddings)
        3. Run consolidation (fact extraction, conflict resolution, forgetting)
        4. Mark conversation as processed in Event Log
        5. Optionally trigger reflection and evolution
        """

        def _async_work() -> None:
            unprocessed = self._event_log.get_unprocessed_conversations(limit=100)

            for entry_id, conversation in unprocessed:
                try:
                    conv_id = conversation.id
                    session_id = conversation.session_id

                    # Extract structured events from conversation
                    events = self._encoder.extract_events(conversation)

                    # Write events to episodic store (with embedding)
                    for event in events:
                        # Add provenance link to source conversation
                        if conv_id and conv_id not in event.parent_ids:
                            event.parent_ids.append(conv_id)
                        self._episodic_store.add_event(event)

                    # Run consolidator (fact extraction, conflict resolution, forgetting)
                    self._consolidator.consolidate(session_id, events)

                    # Mark as processed
                    self._event_log.mark_processed(entry_id)

                    logger.debug(
                        "incremental_processing_complete",
                        entry_id=entry_id,
                        session_id=session_id,
                        events_extracted=len(events),
                    )

                except Exception as e:
                    logger.error(
                        "incremental_processing_failed",
                        entry_id=entry_id,
                        error=str(e),
                    )

            # After batch processing, check for reflection and evolution triggers
            if unprocessed:
                self._maybe_trigger_reflection()
                self._maybe_trigger_evolution()

        self._executor.submit(_async_work)

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
        """Apply feedback to a memory using Q-value updates.

        Uses QValueUpdater to update the memory's IndexProfile Q-value
        based on the outcome signal.

        Args:
            memory_id: Memory identifier
            outcome: "success", "failure", "unknown_used", or "unknown_ignored"
            confidence: Confidence in the outcome assessment (0-1)
        """
        reward = self._q_updater.reward_from_outcome(outcome)  # type: ignore[arg-type]
        profile = self._get_index_profile(memory_id)
        if profile:
            self._q_updater.update(profile, reward)
            self._persist_index_profile(memory_id, profile)

        # Propagate along provenance chain
        self._propagate_feedback(memory_id, outcome == "success")

        logger.info(
            "feedback_applied",
            memory_id=memory_id,
            outcome=outcome,
            q_value=profile.q_value if profile else None,
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

    def _maybe_trigger_evolution(self) -> None:
        """Check if evolution should be triggered based on system stats.

        Evolution evaluates memories with low Q-value and high usage for
        potential refinement or deprecation.

        Uses CompositeEvolutionHook to determine timing:
        - BatchEvolutionHook: Trigger every 50 remember operations
        - TimeBasedHook: Trigger every 24 hours

        When triggered, runs _execute_evolution() asynchronously.
        """
        # Update system stats
        self._system_stats.remember_count = self._remember_count
        self._system_stats.total_memories = self._episodic_store.count()
        self._system_stats.last_evolution_at = self._last_evolution_at

        if self._evolution_hooks.should_trigger(self._system_stats):
            logger.info(
                "evolution_triggered",
                remember_count=self._remember_count,
                total_memories=self._system_stats.total_memories,
            )
            self._executor.submit(self._execute_evolution)

    def _execute_evolution(self) -> None:
        """Execute evolution process: collect candidates and apply actions.

        Pipeline:
        1. Collect candidate memories (skills with low Q + high usage)
        2. Determine action for each: REFINE, DEPRECATE, KEEP
        3. Execute actions (refine or deprecate)
        4. Update last_evolution_at timestamp
        """
        try:
            candidates = self._collect_evolution_candidates()

            refine_count = 0
            deprecate_count = 0

            for mem_id, profile in candidates:
                action = determine_refine_action(profile)

                if action == RefineAction.REFINE_LOW_QUALITY:
                    self._refine_memory(mem_id, profile)
                    refine_count += 1
                elif action == RefineAction.DEPRECATE:
                    self._deprecate_memory(mem_id)
                    deprecate_count += 1

            self._last_evolution_at = datetime.now()
            self._system_stats.last_evolution_at = self._last_evolution_at

            logger.info(
                "evolution_complete",
                candidates_found=len(candidates),
                refined=refine_count,
                deprecated=deprecate_count,
            )

        except Exception as e:
            logger.error("evolution_failed", error=str(e))

    def _collect_evolution_candidates(self) -> list[tuple[str, IndexProfile]]:
        """Collect memory candidates for evolution evaluation.

        Currently collects:
        - Skills with IndexProfile data (most structured)

        Returns:
            List of (memory_id, IndexProfile) tuples
        """
        candidates: list[tuple[str, IndexProfile]] = []

        # Collect from skill store
        try:
            skills = self._skill_store.list_all()
            for skill in skills:
                if skill.id and skill.index_profile and skill.index_profile.q_update_count >= 5:
                    candidates.append((skill.id, skill.index_profile))
        except Exception as e:
            logger.warning("evolution_skill_collection_failed", error=str(e))

        return candidates

    def _refine_memory(self, memory_id: str, profile: IndexProfile) -> None:
        """Refine a memory using LLM to generate improved version.

        Creates a new version of the memory with:
        - Updated content from LLM
        - New IndexProfile (reset or inherited Q based on reason)
        - Provenance link to old version (successor_id)

        Args:
            memory_id: ID of memory to refine
            profile: Current IndexProfile
        """
        try:
            if memory_id.startswith("skill_"):
                skill = self._skill_store.get_skill_by_id(memory_id)
                if skill:
                    # Create refined profile (reset Q for low quality refinement)
                    new_profile = create_refined_profile(
                        profile, reason=RefineAction.REFINE_LOW_QUALITY
                    )

                    # Update skill with new profile (mark for potential future LLM refinement)
                    self._skill_store.update_index_profile(memory_id, new_profile)

                    logger.info(
                        "memory_refined",
                        memory_id=memory_id,
                        old_q=profile.q_value,
                        new_q=new_profile.q_value,
                    )
        except Exception as e:
            logger.error("refine_memory_failed", memory_id=memory_id, error=str(e))

    def _deprecate_memory(self, memory_id: str) -> None:
        """Mark a memory as deprecated (doesn't participate in ranking).

        Args:
            memory_id: ID of memory to deprecate
        """
        try:
            if memory_id.startswith("skill_"):
                skill = self._skill_store.get_skill_by_id(memory_id)
                if skill:
                    # Mark skill as deprecated
                    self._skill_store.deprecate_skill(memory_id)

                    logger.info(
                        "memory_deprecated",
                        memory_id=memory_id,
                        q_value=skill.index_profile.q_value if skill.index_profile else None,
                    )
        except Exception as e:
            logger.error("deprecate_memory_failed", memory_id=memory_id, error=str(e))

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
        """Recursively propagate Q-value feedback along the provenance chain.

        Strengthens memories that contributed to successful outcomes,
        weakens those that led to failures. The effect diminishes
        as we traverse up the ancestry chain.

        Args:
            memory_id: Starting memory ID (skill, event, or principle)
            success: Whether the outcome was successful
            max_depth: Maximum depth to traverse up the lineage
            decay_factor: Multiplier for reward at each level
        """
        reward = 1.0 if success else 0.0
        visited: set[str] = set()

        def _propagate(mem_id: str, depth: int, current_reward: float) -> None:
            if depth >= max_depth or mem_id in visited:
                return
            visited.add(mem_id)

            profile = self._get_index_profile(mem_id)
            if profile:
                # Use decayed reward for parent nodes
                decayed_reward = 0.5 + (current_reward - 0.5) * decay_factor
                self._q_updater.update(profile, decayed_reward)
                self._persist_index_profile(mem_id, profile)

            # Get parent_ids and continue propagation
            parent_ids = self._get_parent_ids(mem_id)
            for pid in parent_ids:
                _propagate(pid, depth + 1, decayed_reward if profile else current_reward)

        _propagate(memory_id, 0, reward)

    def _get_index_profile(self, memory_id: str) -> IndexProfile | None:
        """Get IndexProfile for a memory by routing to the appropriate store.

        Args:
            memory_id: Memory identifier (prefix determines store)

        Returns:
            IndexProfile if found, None otherwise
        """
        if memory_id.startswith("skill_"):
            skill = self._skill_store.get_skill_by_id(memory_id)
            return skill.index_profile if skill else None
        event = self._episodic_store.get_by_id(memory_id)
        if event:
            return event.metadata.get("index_profile")
        return None

    def _persist_index_profile(self, memory_id: str, profile: IndexProfile) -> None:
        """Persist updated IndexProfile to the appropriate store.

        Args:
            memory_id: Memory identifier
            profile: Updated IndexProfile to persist
        """
        if memory_id.startswith("skill_"):
            self._skill_store.update_index_profile(memory_id, profile)

    def _get_parent_ids(self, memory_id: str) -> list[str]:
        """Get parent_ids for provenance-based feedback propagation.

        Args:
            memory_id: Memory identifier

        Returns:
            List of parent memory IDs
        """
        skill = self._skill_store.get_skill_by_id(memory_id)
        if skill and skill.parent_ids:
            return skill.parent_ids
        event = self._episodic_store.get_by_id(memory_id)
        if event and event.parent_ids:
            return event.parent_ids
        return []
