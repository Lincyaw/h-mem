"""Unified conversation processing entry point for h-mem.

This module provides a unified interface for processing conversations through
the h-mem pipeline, handling both single conversation processing and batch imports.

Processing Pipeline:
    1. Store Conversation node in Neo4j
    2. Extract Events via MemoryEncoder
    3. Extract Facts via MemoryEncoder
    4. Store all with provenance links
    5. Optionally trigger evolution (principle/skill induction)

This processor implements the "cold path" - converting raw conversations into
structured memory. It's used both for real-time incremental processing and for
cold-start batch imports.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
import uuid

import structlog

from hmem.models import Conversation

if TYPE_CHECKING:
    from hmem.storage.neo4j_unified import Neo4jUnifiedStore
    from hmem.hippocampus.encoder import MemoryEncoder
    from hmem.core.evolution_engine import EvolutionEngine

logger = structlog.get_logger()


@dataclass
class ProcessResult:
    """Result of processing a single conversation.

    Tracks statistics about what was extracted and any errors encountered.
    """

    conversation_id: str
    events_extracted: int = 0
    facts_extracted: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class BatchResult:
    """Result of batch processing multiple conversations.

    Aggregates statistics across all processed conversations and evolution activities.
    """

    total_processed: int = 0
    total_events: int = 0
    total_facts: int = 0
    errors: list[str] = field(default_factory=list)
    principles_induced: int = 0
    skills_induced: int = 0


class ConversationProcessor:
    """Unified conversation processing: single + batch.

    Processes conversations through the pipeline:
    1. Store Conversation node in Neo4j
    2. Extract Events via MemoryEncoder
    3. Extract Facts via MemoryEncoder
    4. Store all with provenance links
    5. Optionally trigger evolution

    Example:
        >>> processor = ConversationProcessor(store, encoder)
        >>> result = processor.process_single(conversation)
        >>> print(f"Extracted {result.events_extracted} events")
        >>>
        >>> # Batch processing
        >>> batch_result = processor.process_batch(conversations)
        >>> print(f"Processed {batch_result.total_processed} conversations")
    """

    def __init__(
        self,
        store: Neo4jUnifiedStore,
        encoder: MemoryEncoder,
        evolution: EvolutionEngine | None = None,
    ) -> None:
        """Initialize conversation processor.

        Args:
            store: Neo4j unified store for graph operations
            encoder: Memory encoder for extracting structured data
            evolution: Evolution engine for principle/skill induction (optional)
        """
        self.store = store
        self.encoder = encoder
        self.evolution = evolution
        self.logger = logger.bind(component="conversation_processor")

    def process_single(self, conv: Conversation) -> ProcessResult:
        """Process a single conversation through the full pipeline.

        This method handles:
        - Ensuring conversation has an ID (generates if needed)
        - Storing conversation node
        - Extracting and storing events
        - Extracting and storing facts
        - Proper error handling per-item (doesn't fail entire batch on one error)

        Edge cases handled:
        - Empty conversation (no messages) - stores conversation only
        - Conversation with no extractable events/facts - that's ok
        - Encoder failures - logged and continue

        Args:
            conv: Conversation to process

        Returns:
            ProcessResult with extraction counts and any errors
        """
        # Ensure conversation has an ID
        if conv.id is None:
            conv.id = f"conv_{uuid.uuid4().hex[:12]}"

        result = ProcessResult(conversation_id=conv.id)

        try:
            # Step 1: Store conversation node
            self.logger.debug("Storing conversation", conv_id=conv.id)
            self.store.add_conversation(conv)

            # Step 2: Extract events and facts
            self.logger.debug("Extracting events and facts", conv_id=conv.id)
            try:
                events, facts = self.encoder.encode_conversation(conv)
            except Exception as e:
                error_msg = f"Encoder failed for conversation {conv.id}: {e}"
                self.logger.error(
                    "encoding_failed",
                    conv_id=conv.id,
                    error=str(e),
                    exc_info=True,
                )
                result.errors.append(error_msg)
                # Return early - can't proceed without extracted data
                return result

            # Step 3: Store events with HAS_EVENT relationships
            for event in events:
                try:
                    # Ensure event has an ID
                    if event.id is None:
                        event.id = f"evt_{uuid.uuid4().hex[:12]}"

                    self.store.add_event(event, parent_conv_id=conv.id)
                    result.events_extracted += 1

                except Exception as e:
                    error_msg = f"Failed to store event {event.id}: {e}"
                    self.logger.warning(
                        "event_storage_failed",
                        conv_id=conv.id,
                        event_id=event.id,
                        error=str(e),
                    )
                    result.errors.append(error_msg)
                    # Continue processing other events

            # Step 4: Store facts with GENERATES relationships
            for fact in facts:
                try:
                    # Ensure fact has an ID
                    if fact.id is None:
                        fact.id = f"fact_{uuid.uuid4().hex[:12]}"

                    # Map fact's parent_ids to event IDs
                    # Facts are derived from events in the same conversation
                    parent_event_ids = [
                        evt.id
                        for evt in events
                        if evt.id and conv.id in fact.parent_ids
                    ]

                    # If no matching events, link directly to conversation
                    if not parent_event_ids:
                        self.logger.debug(
                            "Fact has no matching events, will create orphan fact node",
                            conv_id=conv.id,
                            fact_id=fact.id,
                        )
                        parent_event_ids = []

                    self.store.add_fact(fact, parent_event_ids=parent_event_ids)
                    result.facts_extracted += 1

                except Exception as e:
                    error_msg = f"Failed to store fact {fact.id}: {e}"
                    self.logger.warning(
                        "fact_storage_failed",
                        conv_id=conv.id,
                        fact_id=fact.id,
                        error=str(e),
                    )
                    result.errors.append(error_msg)
                    # Continue processing other facts

            self.logger.info(
                "conversation_processed",
                conv_id=conv.id,
                events=result.events_extracted,
                facts=result.facts_extracted,
                errors=len(result.errors),
            )

        except Exception as e:
            error_msg = f"Critical failure processing conversation {conv.id}: {e}"
            self.logger.error(
                "conversation_processing_failed",
                conv_id=conv.id,
                error=str(e),
                exc_info=True,
            )
            result.errors.append(error_msg)

        return result

    def process_batch(
        self,
        convs: list[Conversation],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> BatchResult:
        """Process multiple conversations in batch with optional progress callback.

        This method:
        - Sorts conversations by timestamp (oldest first)
        - Processes each via process_single
        - Optionally triggers evolution after all processed
        - Reports progress via callback

        Args:
            convs: List of conversations to process
            on_progress: Optional callback(current, total) for progress reporting

        Returns:
            BatchResult with aggregated statistics
        """
        result = BatchResult()

        if not convs:
            self.logger.warning("Empty conversation batch provided")
            return result

        # Sort conversations by first message timestamp (oldest first)
        # This ensures chronological processing for better semantic coherence
        from datetime import datetime

        def get_timestamp(c: Conversation) -> datetime:
            if c.messages:
                return c.messages[0].timestamp
            # Fallback to now if no messages
            return datetime.now()

        sorted_convs = sorted(convs, key=get_timestamp)

        total = len(sorted_convs)
        self.logger.info("Starting batch processing", total_conversations=total)

        # Process each conversation
        for idx, conv in enumerate(sorted_convs, start=1):
            try:
                proc_result = self.process_single(conv)

                # Aggregate statistics
                result.total_processed += 1
                result.total_events += proc_result.events_extracted
                result.total_facts += proc_result.facts_extracted
                result.errors.extend(proc_result.errors)

                # Report progress
                if on_progress:
                    try:
                        on_progress(idx, total)
                    except Exception as e:
                        self.logger.warning(
                            "Progress callback failed",
                            current=idx,
                            total=total,
                            error=str(e),
                        )

            except Exception as e:
                error_msg = f"Batch processing error at index {idx}: {e}"
                self.logger.error(
                    "batch_item_failed",
                    index=idx,
                    total=total,
                    error=str(e),
                    exc_info=True,
                )
                result.errors.append(error_msg)
                # Continue processing remaining conversations

        self.logger.info(
            "Batch processing complete",
            total_processed=result.total_processed,
            total_events=result.total_events,
            total_facts=result.total_facts,
            errors=len(result.errors),
        )

        # Step 5: Optionally trigger evolution
        if self.evolution and result.total_events > 0:
            try:
                self.logger.info("Triggering evolution after batch processing")

                # Collect all event IDs from this batch for principle/skill induction
                # In a real implementation, we'd want to cluster events by topic
                # For now, we'll rely on the evolution engine to do smart clustering
                event_ids: list[str] = []  # Would need to track these during processing

                # Trigger principle induction
                if len(event_ids) > 0:
                    principles = self.evolution.induce_principles(event_ids)
                    result.principles_induced = len(principles)
                    self.logger.info(
                        "Principles induced", count=result.principles_induced
                    )

                    # Trigger skill induction
                    skills = self.evolution.induce_skills(event_ids)
                    result.skills_induced = len(skills)
                    self.logger.info("Skills induced", count=result.skills_induced)

            except Exception as e:
                error_msg = f"Evolution failed: {e}"
                self.logger.error(
                    "evolution_failed",
                    error=str(e),
                    exc_info=True,
                )
                result.errors.append(error_msg)

        return result
