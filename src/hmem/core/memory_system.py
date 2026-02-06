"""MemorySystem - Core orchestrator for the unified Neo4j memory architecture.

Simplified to use only Neo4jUnifiedStore as the single storage backend.
All memory types (Event, Fact, Principle, Skill) are stored as graph nodes
with complete provenance chains.
"""

import threading
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

import structlog

from hmem.agents.llm import LLMClient
from hmem.config import MemoryConfig
from hmem.core.conversation_processor import ConversationProcessor
from hmem.core.evolution_engine import EvolutionEngine
from hmem.hippocampus.encoder import MemoryEncoder
from hmem.hippocampus.retrieval_engine import RetrievalEngine, extract_memory_ids
from hmem.interfaces import MemorySystem as MemorySystemInterface
from hmem.models import (
    Conversation,
    ConsolidationResult,
    Memory,
    Message,
    Principle,
)
from hmem.storage.neo4j_unified import Neo4jUnifiedStore

logger = structlog.get_logger()


class MemorySystem(MemorySystemInterface):
    """Cognitive Agent Memory System (CAMS) - Core Interface.

    Simplified architecture using unified Neo4j storage:
    - Layer 1: Conversation ingestion and event extraction
    - Layer 2: Hippocampus processing (Encoder, Retrieval)
    - Layer 3: Unified Neo4j storage with complete provenance chain

    Design Philosophy:
    - Unix Rule of Silence: All complexity hidden in config
    - Event Sourcing: Complete provenance from conversations to derived knowledge
    - Unified Storage: Single Neo4j backend for all memory types

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

        # Unified Neo4j store
        self._store = Neo4jUnifiedStore(
            uri=self.config.storage.neo4j_uri,
            username=self.config.storage.neo4j_username,
            password=self.config.storage.neo4j_password,
            database=self.config.storage.neo4j_database,
        )

        # LLM client
        self._llm_client = LLMClient(
            model=self.config.llm.model,
            temperature=self.config.llm.temperature,
        )

        # Hippocampus components
        self._encoder = MemoryEncoder(llm_client=self._llm_client)

        # Evolution engine
        self._evolution = EvolutionEngine(
            store=self._store,
            llm=self._llm_client,
            alpha=self.config.q_learning.alpha,
        )

        # Conversation processor
        self._processor = ConversationProcessor(
            store=self._store,
            encoder=self._encoder,
            evolution=self._evolution,
        )

        # Retrieval engine
        self._retrieval_engine = RetrievalEngine(
            store=self._store,
            llm_client=self._llm_client,
            enable_relevance_filter=self.config.retrieval.enable_relevance_filter,
            min_relevance_score=self.config.retrieval.min_relevance_score,
        )

        # Async processing infrastructure
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="hmem_async"
        )
        self._consolidation_lock = threading.Lock()

        # Session tracking
        self._current_session_id: str | None = None
        self._remember_count = 0
        self._last_evolution_at: datetime | None = None

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
            session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            return Conversation(
                id=f"conv_{uuid.uuid4().hex[:12]}",
                session_id=session_id,
                messages=conversation,
            )

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
        """Store conversation into memory with provenance tracking.

        Pipeline:
        1. Normalize conversation format and ensure ID
        2. Process via ConversationProcessor (extract events, facts, store in Neo4j)
        3. Schedule async feedback extraction
        4. Optionally trigger evolution

        Args:
            conversation: Conversation or list of Message objects

        Returns:
            session_id: Session identifier
        """
        conversation = self._normalize_conversation(conversation)
        conv_id = conversation.id
        assert conv_id is not None

        # Process conversation (extract events, facts, store in Neo4j)
        result = self._processor.process_single(conversation)

        if result.errors:
            logger.warning(
                "remember_with_errors",
                conv_id=conv_id,
                errors=result.errors,
            )

        # Schedule async feedback extraction
        self._schedule_async_feedback_processing(conversation)

        # Check evolution triggers
        self._remember_count += 1
        self._maybe_trigger_evolution()

        logger.info(
            "conversation_remembered",
            conv_id=conv_id,
            session_id=conversation.session_id,
            entities=result.entities_extracted,
            attributes=result.attributes_extracted,
            processes=result.processes_extracted,
        )

        return conversation.session_id

    def recall(
        self,
        query: str | Message | Conversation,
        limit: int = 10,
        filters: dict[str, str] | None = None,
    ) -> Iterator[Memory]:
        """Retrieve relevant memories with provenance information.

        Uses hybrid retrieval: vector search + fulltext + graph traversal.

        Args:
            query: Search query - supports str, Message, or Conversation
            limit: Maximum results to return
            filters: Optional filters

        Yields:
            Memory objects ranked by relevance
        """
        query_text = self._convert_query_to_text(query)
        yield from self._retrieval_engine.retrieve(query_text, limit, filters)

    def get_lineage(self, memory_id: str, max_depth: int = 3) -> list[dict]:
        """Get the provenance chain for a memory.

        Args:
            memory_id: ID of the memory to trace
            max_depth: Maximum depth to traverse

        Returns:
            List of ancestor nodes with relationship info
        """
        return self._store.get_lineage(memory_id, max_depth)

    def get_derived(self, memory_id: str) -> list[dict]:
        """Get all memories derived from a source memory.

        Args:
            memory_id: ID of the source memory

        Returns:
            List of descendant node dicts
        """
        return self._store.get_descendants(memory_id)

    def consolidate(self, session_id: str) -> ConsolidationResult:
        """Trigger memory consolidation for a session.

        In the unified architecture, consolidation is handled by the
        ConversationProcessor during remember(). This method is kept
        for interface compatibility.

        Args:
            session_id: Session to consolidate

        Returns:
            ConsolidationResult with statistics
        """
        return ConsolidationResult(
            success=True,
            stored_events=0,
            updated_facts=0,
            conflicts_resolved=0,
            errors=[],
        )

    def reflect(self) -> list[Principle]:
        """Trigger principle induction from stored events.

        Returns:
            List of induced Principle objects
        """
        # TODO: Implement via EvolutionEngine.induce_principles
        return []

    def health(self) -> dict[str, str | int]:
        """Get system health status.

        Returns:
            Health metrics from the unified store
        """
        stats = self._store.get_stats()
        return {
            "status": "healthy",
            "version": "0.2.0",
            "conversations": stats.get("conversations", 0),
            "events": stats.get("events", 0),
            "facts": stats.get("facts", 0),
            "active_facts": stats.get("active_facts", 0),
            "principles": stats.get("principles", 0),
            "skills": stats.get("skills", 0),
        }

    def health_check(self) -> dict[str, Any]:
        """Deep system health check.

        Returns:
            Detailed health report
        """
        import time

        health_report: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "status": "healthy",
            "version": "0.2.0",
            "components": {},
            "warnings": [],
            "errors": [],
        }

        try:
            start = time.time()
            stats = self._store.get_stats()
            latency = (time.time() - start) * 1000

            health_report["components"]["neo4j"] = {
                "status": "healthy",
                "backend": "neo4j_unified",
                "check_latency_ms": round(latency, 2),
                **stats,
            }
        except Exception as e:
            health_report["components"]["neo4j"] = {
                "status": "error",
                "error": str(e),
            }
            health_report["errors"].append(f"Neo4j store: {e}")
            health_report["status"] = "degraded"

        return health_report

    def rebuild_from_conversations(
        self, conversations: list[Conversation]
    ) -> dict[str, int]:
        """Cold start: rebuild all indexes from historical conversations.

        Args:
            conversations: List of historical conversations to process

        Returns:
            Statistics about the rebuild process
        """
        result = self._processor.process_batch(conversations)
        return {
            "total_processed": result.total_processed,
            "total_entities": result.total_entities,
            "total_attributes": result.total_attributes,
            "total_processes": result.total_processes,
            "principles_induced": result.principles_induced,
            "skills_induced": result.skills_induced,
            "errors": len(result.errors),
        }

    def _convert_query_to_text(self, query: str | Message | Conversation) -> str:
        """Convert different query types to text."""
        if isinstance(query, str):
            return query
        elif isinstance(query, Message):
            return query.content
        elif isinstance(query, Conversation):
            messages_text = " ".join(
                f"{msg.role}: {msg.content}" for msg in query.messages[-3:]
            )
            return messages_text
        else:
            return str(query)

    def _schedule_async_feedback_processing(self, conversation: Conversation) -> None:
        """Schedule async feedback signal extraction and processing.

        Args:
            conversation: Conversation to analyze for feedback
        """
        full_text = "\n".join(m.content for m in conversation.messages)
        recalled_memory_ids = set(extract_memory_ids(full_text))

        metadata_ids = conversation.metadata.get("used_memory_ids", [])
        if metadata_ids:
            recalled_memory_ids.update(metadata_ids)

        if not recalled_memory_ids:
            return

        def _async_feedback_work() -> None:
            try:
                signals = self._llm_client.extract_feedback_signals(
                    full_text, list(recalled_memory_ids)
                )

                memories_with_feedback: set[str] = set()

                if signals:
                    for signal in signals:
                        memories_with_feedback.add(signal["memory_id"])
                        self._apply_feedback(
                            memory_id=signal["memory_id"],
                            outcome=signal["outcome"],
                        )

                # Apply "unknown_ignored" to recalled memories without feedback
                ignored_memories = recalled_memory_ids - memories_with_feedback
                for mem_id in ignored_memories:
                    self._apply_feedback(
                        memory_id=mem_id,
                        outcome="unknown_ignored",
                    )

            except Exception as e:
                logger.warning("async_feedback_processing_failed", error=str(e))

        self._executor.submit(_async_feedback_work)

    def _apply_feedback(self, memory_id: str, outcome: str) -> None:
        """Apply feedback to a memory using the evolution engine.

        Args:
            memory_id: Memory identifier
            outcome: "success", "failure", "unknown_used", or "unknown_ignored"
        """
        # Determine node type from ID prefix
        node_type = self._infer_node_type(memory_id)
        self._evolution.apply_feedback(memory_id, node_type, outcome)

        # Propagate along provenance chain
        self._evolution.propagate_feedback(memory_id, success=(outcome == "success"))

    def _infer_node_type(self, memory_id: str) -> str:
        """Infer Neo4j node type from memory ID prefix.

        Args:
            memory_id: Memory ID (e.g., "evt_xxx", "fact_xxx", "prin_xxx", "skill_xxx")

        Returns:
            Node type string
        """
        if memory_id.startswith("evt_"):
            return "Event"
        elif memory_id.startswith("fact_"):
            return "Fact"
        elif memory_id.startswith("prin_") or memory_id.startswith("principle_"):
            return "Principle"
        elif memory_id.startswith("skill_"):
            return "Skill"
        else:
            return "Event"  # Default

    def _maybe_trigger_evolution(self) -> None:
        """Check if evolution should be triggered."""
        if self._evolution.should_trigger(
            self._remember_count, self._last_evolution_at
        ):
            self._last_evolution_at = datetime.now()
            self._remember_count = 0

            def _async_evolve() -> None:
                try:
                    stats = self._evolution.execute_evolution()
                    logger.info("evolution_complete", stats=stats)
                except Exception as e:
                    logger.error("evolution_failed", error=str(e))

            self._executor.submit(_async_evolve)

    def end_session(self, session_id: str | None = None) -> ConsolidationResult:
        """End a session.

        Args:
            session_id: Session to end (uses current if None)

        Returns:
            ConsolidationResult
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

        if sid == self._current_session_id:
            self._current_session_id = None

        return ConsolidationResult(
            success=True,
            stored_events=0,
            updated_facts=0,
            conflicts_resolved=0,
            errors=[],
        )

    def shutdown(self, wait: bool = True, timeout: float = 30.0) -> None:
        """Gracefully shutdown the memory system.

        Args:
            wait: If True, waits for pending tasks to complete
            timeout: Maximum seconds to wait
        """
        if wait:
            self._executor.shutdown(wait=True)
        else:
            self._executor.shutdown(wait=False, cancel_futures=True)

        self._store.close()

        logger.info("memory_system_shutdown")

    def __del__(self) -> None:
        """Cleanup on destruction."""
        try:
            self.shutdown(wait=False)
        except Exception:
            pass
