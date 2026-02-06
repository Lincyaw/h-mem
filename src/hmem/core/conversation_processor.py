"""Unified conversation processing entry point for h-mem.

This module provides a unified interface for processing conversations through
the h-mem pipeline, handling both single conversation processing and batch imports.

Processing Pipeline:
    1. Store Conversation node in Neo4j
    2. Extract Entities, Attributes, Processes via MemoryEncoder
    3. Store all with provenance links
    4. Optionally trigger evolution (skill induction from processes)

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
    entities_extracted: int = 0
    attributes_extracted: int = 0
    processes_extracted: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class BatchResult:
    """Result of batch processing multiple conversations.

    Aggregates statistics across all processed conversations and evolution activities.
    """

    total_processed: int = 0
    total_entities: int = 0
    total_attributes: int = 0
    total_processes: int = 0
    errors: list[str] = field(default_factory=list)
    principles_induced: int = 0
    skills_induced: int = 0


class ConversationProcessor:
    """Unified conversation processing: single + batch.

    Processes conversations through the entity-centric pipeline:
    1. Store Conversation node in Neo4j
    2. Extract Entities, Attributes, Processes via MemoryEncoder
    3. Store all with provenance links
    4. Optionally trigger skill induction from processes

    Example:
        >>> processor = ConversationProcessor(store, encoder)
        >>> result = processor.process_single(conversation)
        >>> print(f"Extracted {result.entities_extracted} entities")
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
            evolution: Evolution engine for skill induction (optional)
        """
        self.store = store
        self.encoder = encoder
        self.evolution = evolution
        self.logger = logger.bind(component="conversation_processor")

    def process_single(self, conv: Conversation) -> ProcessResult:
        """Process a single conversation through the full pipeline.

        This method handles:
        - Ensuring conversation has an ID (generates if needed)
        - Checking if conversation already exists (by session_id)
        - Storing conversation node
        - Extracting and storing entities, attributes, processes
        - Proper error handling per-item (doesn't fail entire batch on one error)

        Edge cases handled:
        - Empty conversation (no messages) - stores conversation only
        - Conversation with no extractable data - that's ok
        - Encoder failures - logged and continue
        - Duplicate conversation (same session_id) - skip extraction

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
            # Check if conversation with same session_id already exists
            if conv.session_id:
                existing = self.store.find_conversation_by_session_id(conv.session_id)
                if existing:
                    self.logger.info(
                        "Conversation already exists, skipping",
                        session_id=conv.session_id,
                        existing_id=existing.get("id"),
                    )
                    result.conversation_id = existing.get("id", conv.id)
                    return result

            # Step 1: Store conversation node
            self.logger.debug("Storing conversation", conv_id=conv.id)
            self.store.add_conversation(conv)

            # Step 2: Extract using encoder
            self.logger.debug("Extracting structured knowledge", conv_id=conv.id)
            try:
                extracted = self.encoder.encode_conversation(conv)
            except Exception as e:
                error_msg = f"Encoder failed for conversation {conv.id}: {e}"
                self.logger.error(
                    "encoding_failed",
                    conv_id=conv.id,
                    error=str(e),
                    exc_info=True,
                )
                result.errors.append(error_msg)
                return result

            entities = extracted.get("entities", [])
            attributes = extracted.get("attributes", [])
            processes = extracted.get("processes", [])

            # Step 3: Store entities and build name->id mapping
            entity_name_to_id: dict[str, str] = {}
            for entity in entities:
                try:
                    # Check if entity already exists (by name or alias)
                    existing = self.store.find_entity_by_name(entity.canonical_name)
                    if existing:
                        entity_id = existing["id"]
                        self.logger.debug(
                            "Entity already exists",
                            name=entity.canonical_name,
                            id=entity_id,
                        )
                    else:
                        if entity.id is None:
                            entity.id = f"entity_{uuid.uuid4().hex[:12]}"
                        entity_id = self.store.add_entity(entity)
                        result.entities_extracted += 1

                    entity_name_to_id[entity.canonical_name] = entity_id

                except Exception as e:
                    result.errors.append(f"Failed to store entity: {e}")

            # Step 4: Store attributes with entity resolution
            for attr_dict in attributes:
                try:
                    attr = attr_dict["attribute"]
                    entity_name = attr_dict["entity_name"]

                    # Resolve entity name to ID
                    entity_id = entity_name_to_id.get(entity_name)
                    if not entity_id:
                        # Try to find existing entity
                        existing = self.store.find_entity_by_name(entity_name)
                        if existing:
                            entity_id = existing["id"]
                        else:
                            # Create new entity for this name
                            from hmem.models import Entity as EntityModel

                            new_entity = EntityModel(
                                canonical_name=entity_name,
                                entity_type="CONCEPT",
                                needs_resolution=True,
                            )
                            entity_id = self.store.add_entity(new_entity)
                            entity_name_to_id[entity_name] = entity_id
                            result.entities_extracted += 1

                    if attr.id is None:
                        attr.id = f"fact_{uuid.uuid4().hex[:12]}"

                    self.store.add_attribute(
                        attr, entity_id=entity_id, source_conv_id=conv.id
                    )
                    result.attributes_extracted += 1

                except Exception as e:
                    result.errors.append(f"Failed to store attribute: {e}")

            # Step 5: Store processes
            for proc in processes:
                try:
                    if proc.id is None:
                        proc.id = f"proc_{uuid.uuid4().hex[:12]}"
                    self.store.add_process(proc, source_conv_id=conv.id)
                    result.processes_extracted += 1
                except Exception as e:
                    result.errors.append(f"Failed to store process: {e}")

            self.logger.info(
                "conversation_processed",
                conv_id=conv.id,
                entities=result.entities_extracted,
                attributes=result.attributes_extracted,
                processes=result.processes_extracted,
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
        - Optionally triggers skill induction after all processed
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
                result.total_entities += proc_result.entities_extracted
                result.total_attributes += proc_result.attributes_extracted
                result.total_processes += proc_result.processes_extracted
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
            total_entities=result.total_entities,
            total_attributes=result.total_attributes,
            total_processes=result.total_processes,
            errors=len(result.errors),
        )

        # Trigger skill induction from processes
        if self.evolution and result.total_processes > 0:
            try:
                self.logger.info("Triggering skill induction after batch processing")
                induction_stats = self.evolution.run_skill_induction_task()
                result.skills_induced = induction_stats.get("skills_induced", 0)
                self.logger.info(
                    "Skill induction completed",
                    skills_induced=result.skills_induced,
                )
            except Exception as e:
                error_msg = f"Skill induction failed: {e}"
                self.logger.error(
                    "skill_induction_failed",
                    error=str(e),
                    exc_info=True,
                )
                result.errors.append(error_msg)

        return result
