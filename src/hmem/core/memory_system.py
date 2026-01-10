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

from collections.abc import Iterator
from pathlib import Path
import uuid

from hmem.config import MemoryConfig
from hmem.interfaces import MemorySystem as MemorySystemInterface
from hmem.models import Conversation, ConsolidationResult, Memory, Message, Principle
from hmem.hippocampus.encoder import MemoryEncoder
from hmem.hippocampus.consolidator import Consolidator
from hmem.hippocampus.projector import EventProjector
from hmem.hippocampus.retrieval_engine import RetrievalEngine, extract_feedback_signals
from hmem.agents.reflection import ReflectionAgent
from hmem.storage.episodic import EpisodicStore
from hmem.storage.chroma_episodic import ChromaEpisodicStore
from hmem.storage.sqlite_semantic import SQLiteSemanticStore
from hmem.storage.skill import SkillStore
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

        # Get semantic path from config
        semantic_path = Path(self.config.storage.semantic_path)
        semantic_path.parent.mkdir(parents=True, exist_ok=True)
        self._semantic_store = SQLiteSemanticStore(f"sqlite:///{semantic_path}")

        # Initialize Skill Store (Phase 3)
        skill_path = Path(self.config.storage.skill_path)
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        self._skill_store = SkillStore(skill_path)

        self._llm_agent = LLMClient(
            model=self.config.llm.model,
            temperature=self.config.llm.temperature,
        )

        # Initialize Hippocampus components
        self._encoder = MemoryEncoder(llm_client=self._llm_agent)
        self._consolidator = Consolidator(
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
            llm_client=self._llm_agent,
        )

        # Active session for chat mode
        self._current_session_id: str | None = None

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
        """Store conversation into memory with provenance tracking and feedback processing.

        This triggers:
        1. Assign unique ID to conversation (if not provided)
        2. Extract and process feedback signals from XML-marked memories
        3. Append to Event Log (single source of truth)
        4. Extract events from conversation (with parent_ids set)
        5. Store in episodic memory
        6. Optionally consolidate (sync or async based on config)

        Feedback Loop:
            If the conversation contains XML-marked memories with outcome attributes,
            the system automatically updates the corresponding memory weights:
            - <skill id="xxx" outcome="success">...</skill> → +1 success count
            - <skill id="xxx" outcome="failure">...</skill> → +1 failure count
            - <principle id="xxx" outcome="success">...</principle> → +0.1 weight
            - <principle id="xxx" outcome="failure">...</principle> → -0.2 weight

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

        # Extract and process feedback signals from conversation content
        self._process_feedback_signals(conversation)

        # Log conversation to event log
        self._event_log.append(conversation)

        # Extract events from conversation (encoder sets parent_ids)
        events = self._encoder.extract_events(conversation)

        # Store events in episodic memory
        for event in events:
            self._episodic_store.add_event(event)

        # Consolidate based on config mode
        if auto_consolidate:
            if self.config.consolidation.mode == "asynchronous":
                self._consolidator.consolidate_async(conversation.session_id, events)
            else:
                self._consolidator.consolidate(conversation.session_id, events)

        # Auto-trigger reflection based on memory count
        # Extracts tags from events and checks if any topic hit the threshold
        self._maybe_trigger_reflection(events)

        return conversation.session_id

    def _process_feedback_signals(self, conversation: Conversation) -> None:
        """Extract and process feedback signals from conversation content.

        Looks for XML-marked memories with outcome attributes and updates
        the corresponding memory weights/statistics.

        Args:
            conversation: Conversation to scan for feedback signals
        """
        # Collect all message content
        full_text = "\n".join(m.content for m in conversation.messages)

        # Extract feedback signals
        signals = extract_feedback_signals(full_text)

        if not signals:
            return

        logger.info(
            "feedback_signals_detected",
            count=len(signals),
            signals=[(s.memory_id, s.memory_type, s.outcome) for s in signals],
        )

        # Process each signal
        for signal in signals:
            try:
                if signal.memory_type == "skill":
                    self._apply_skill_feedback(signal.memory_id, signal.outcome)
                elif signal.memory_type == "principle":
                    self._apply_principle_feedback(signal.memory_id, signal.outcome)
                elif signal.memory_type == "semantic":
                    self._apply_semantic_feedback(signal.memory_id, signal.outcome)
                elif signal.memory_type == "episodic":
                    self._apply_episodic_feedback(signal.memory_id, signal.outcome)
            except Exception as e:
                logger.warning(
                    "feedback_processing_failed",
                    memory_id=signal.memory_id,
                    error=str(e),
                )

    def _apply_skill_feedback(self, skill_id: str, outcome: str) -> None:
        """Update skill statistics based on usage outcome.

        Args:
            skill_id: Skill identifier
            outcome: "success" or "failure"
        """
        if outcome == "success":
            updated = self._skill_store.record_success(skill_id)
        else:
            updated = self._skill_store.record_failure(skill_id)

        if updated:
            logger.info(
                "skill_feedback_applied",
                skill_id=skill_id,
                outcome=outcome,
            )
        else:
            logger.warning(
                "skill_feedback_not_found",
                skill_id=skill_id,
            )

    def _apply_principle_feedback(self, principle_id: str, outcome: str) -> None:
        """Update principle weight based on usage outcome.

        Args:
            principle_id: Fact/principle identifier
            outcome: "success" or "failure"
        """
        # Success strengthens (+0.1), failure weakens (-0.2)
        delta = 0.1 if outcome == "success" else -0.2

        updated = self._semantic_store.update_weight(principle_id, delta)

        if updated:
            logger.info(
                "principle_feedback_applied",
                principle_id=principle_id,
                outcome=outcome,
                weight_delta=delta,
            )
        else:
            logger.warning(
                "principle_feedback_not_found",
                principle_id=principle_id,
            )

    def _apply_semantic_feedback(self, fact_id: str, outcome: str) -> None:
        """Update semantic fact weight based on usage outcome.

        Args:
            fact_id: Semantic fact identifier
            outcome: "success" or "failure"
        """
        # Success strengthens (+0.1), failure weakens (-0.15)
        delta = 0.1 if outcome == "success" else -0.15

        updated = self._semantic_store.update_weight(fact_id, delta)

        if updated:
            logger.info(
                "semantic_feedback_applied",
                fact_id=fact_id,
                outcome=outcome,
                weight_delta=delta,
            )
        else:
            logger.warning(
                "semantic_feedback_not_found",
                fact_id=fact_id,
            )

    def _apply_episodic_feedback(self, event_id: str, outcome: str) -> None:
        """Update episodic event weight based on usage outcome.

        Positive feedback reinforces the memory, making it more likely
        to be recalled in similar contexts.

        Args:
            event_id: Event identifier
            outcome: "success" or "failure"
        """
        # Success strengthens (+0.1), failure weakens (-0.1)
        delta = 0.1 if outcome == "success" else -0.1

        updated = self._episodic_store.update_weight(event_id, delta)

        if updated:
            logger.info(
                "episodic_feedback_applied",
                event_id=event_id,
                outcome=outcome,
                weight_delta=delta,
            )
        else:
            logger.warning(
                "episodic_feedback_not_found",
                event_id=event_id,
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
        # SQLiteSemanticStore may not have get_stats, provide fallback
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

    def reflect(self, topic: str) -> list[Principle]:
        """Trigger deep reflection to extract principles on a specific topic.

        Note: The new LangGraph-based agent automatically discovers topics
        via semantic clustering. The topic parameter is kept for backward
        compatibility but the agent will analyze all available memories.

        Args:
            topic: Topic hint (used for logging, agent discovers topics automatically)

        Returns:
            List of extracted Principle objects
        """
        logger.info("manual_reflection_triggered", topic_hint=topic)
        return self._reflection_agent.reflect(
            min_cluster_size=self.config.reflection.min_episodes,
        )

    def auto_reflect(self) -> list[Principle]:
        """Run auto-reflection on all topics.

        Uses semantic clustering to discover topics automatically
        and extracts principles from each cluster.

        Returns:
            List of extracted Principle objects
        """
        return self._reflection_agent.reflect()

    def _maybe_trigger_reflection(self, events: list) -> None:
        """Check if reflection should be triggered based on memory accumulation.

        Called after remember() to potentially trigger automatic reflection.
        The new LangGraph-based agent uses semantic clustering to discover
        topics automatically, so we trigger based on total memory count
        rather than specific tags.

        Memory hierarchy compression:
        - Level 1 (Episodic Events) accumulates
        - When count hits threshold → Level 3 (Principle) extraction
        - This creates automatic "compression" as memories build up

        Args:
            events: Newly added events from remember()
        """
        # Only trigger reflection periodically based on memory count
        total_memories = self._chroma_store.count()
        trigger_threshold = self.config.reflection.trigger_threshold

        # Check if we've crossed a threshold multiple
        if total_memories > 0 and total_memories % trigger_threshold == 0:
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

    def record_skill_outcome(
        self,
        skill_id: str,
        success: bool,
        propagate_feedback: bool = True,
    ) -> bool:
        """Record the outcome of a skill execution with feedback propagation.

        This updates the skill's success rate and optionally propagates
        feedback along the provenance chain to strengthen/weaken related
        memories and principles.

        Args:
            skill_id: Skill identifier
            success: Whether execution was successful
            propagate_feedback: If True, update weights of related memories

        Returns:
            True if recorded, False if skill not found
        """
        # Update skill success/failure count
        if success:
            result = self._skill_store.record_success(skill_id)
        else:
            result = self._skill_store.record_failure(skill_id)

        if not result:
            return False

        # Propagate feedback along provenance chain
        if propagate_feedback:
            self._propagate_feedback(skill_id, success)

        return True

    def _propagate_feedback(self, memory_id: str, success: bool) -> None:
        """Propagate feedback signal along the provenance chain.

        Strengthens memories that contributed to successful outcomes,
        weakens those that led to failures.

        Args:
            memory_id: Starting memory ID (skill, event, or principle)
            success: Whether the outcome was successful
        """
        # Determine weight delta based on outcome
        weight_delta = 0.1 if success else -0.05

        # Get the skill and its parent_ids
        skill = self._skill_store.get_skill_by_id(memory_id)
        parent_ids = []

        if skill and skill.get("parent_ids"):
            parent_ids = skill["parent_ids"]

        # Also check episodic store
        event = self._episodic_store.get_by_id(memory_id)
        if event and event.parent_ids:
            parent_ids.extend(event.parent_ids)

        # Update weights of parent memories
        for parent_id in parent_ids:
            self._update_memory_weight(parent_id, weight_delta)

    def _update_memory_weight(self, memory_id: str, delta: float) -> bool:
        """Update the weight of a memory by ID.

        Handles different memory types (episodic, semantic).

        Args:
            memory_id: Memory identifier
            delta: Weight change

        Returns:
            True if updated successfully
        """
        updated = False

        # Try episodic store
        if self._episodic_store.update_weight(memory_id, delta):
            updated = True

        # Try semantic store
        if self._semantic_store.update_weight(memory_id, delta):
            updated = True

        if updated:
            logger.debug(
                "memory_weight_updated",
                memory_id=memory_id,
                delta=delta,
            )

        return updated

    def record_memory_outcome(
        self,
        memory_id: str,
        success: bool,
        feedback: str | None = None,
    ) -> bool:
        """Record outcome for any memory (episodic, semantic, or skill).

        This is the explicit feedback interface for users to mark memories
        as helpful or unhelpful. The feedback propagates to strengthen or
        weaken related memories in the provenance chain.

        Args:
            memory_id: Memory identifier (event, fact, or skill ID)
            success: Whether the memory was helpful/correct
            feedback: Optional feedback text for context

        Returns:
            True if feedback was recorded

        Example:
            >>> # User finds a memory helpful
            >>> memory.record_memory_outcome("evt_abc123", success=True)
            >>>
            >>> # User marks a skill as unhelpful
            >>> memory.record_memory_outcome("skill_xyz789", success=False,
            ...     feedback="This approach didn't work for my case")
        """
        weight_delta = 0.15 if success else -0.1

        # Update the target memory
        updated = self._update_memory_weight(memory_id, weight_delta)

        # Also check if it's a skill
        if memory_id.startswith("skill_"):
            if success:
                self._skill_store.record_success(memory_id)
            else:
                self._skill_store.record_failure(memory_id)
            updated = True

        # Propagate feedback to parent memories
        self._propagate_feedback(memory_id, success)

        # Log feedback for future analysis
        if feedback:
            logger.info(
                "memory_feedback_recorded",
                memory_id=memory_id,
                success=success,
                feedback=feedback[:100],  # Truncate for log
            )

        return updated
