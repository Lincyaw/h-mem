"""Pytest configuration and shared fixtures.

This module provides common fixtures and utilities for testing the memory system.
"""

import pytest
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file at the start of tests
load_dotenv()

# Enable Phoenix tracing for observability
from hmem.observability.phoenix import setup_phoenix

setup_phoenix("h-mem-tests")

from hmem.config import MemoryConfig, LLMConfig
from hmem.core.memory_system import MemorySystem
from hmem.models import Event, Memory, SemanticTriple, Message, Conversation


@pytest.fixture
def memory_config(tmp_path: Path) -> MemoryConfig:
    """Create test configuration for memory system with temp directory."""
    from hmem.config import StorageConfig

    storage = StorageConfig(
        episodic_path=str(tmp_path / "episodic"),
        semantic_path=str(tmp_path / "semantic.db"),
        skill_path=str(tmp_path / "skills.db"),
    )
    # Use the real LLM model from config for acceptance tests
    # ByteDance Ark API requires endpoint ID instead of model name
    llm = LLMConfig(model="openai:ep-20251110181330-f8sjl")
    return MemoryConfig(storage=storage, llm=llm)


@pytest.fixture
def memory_system(memory_config: MemoryConfig) -> MemorySystem:
    """Create MemorySystem instance for testing.

    Note: This fixture will evolve as implementation progresses.
    Currently returns a basic instance with mocked dependencies.
    """
    return MemorySystem(config=memory_config)


@pytest.fixture
def mock_llm(mocker):
    """Mock LLM for testing without external API calls.

    Provides canned responses for common operations:
    - Summarization: Returns a condensed version
    - Embedding: Returns dummy vectors
    - Fact extraction: Returns predefined facts
    """
    llm = mocker.MagicMock()

    # Mock summarization
    llm.summarize.return_value = "User is Alice, wants to learn Python"

    # Mock embedding generation
    llm.embed.return_value = [0.1] * 768

    # Mock fact extraction
    llm.extract_facts.return_value = [
        {"subject": "User", "predicate": "NAME", "object": "Alice"},
        {"subject": "User", "predicate": "GOAL", "object": "learn Python"},
    ]

    return llm


@pytest.fixture
def sample_messages() -> list[Message]:
    """Create sample messages for testing."""
    return [
        Message(
            role="user",
            content="My name is Alice",
            timestamp=datetime(2026, 1, 10, 10, 0, 0),
        ),
        Message(
            role="assistant",
            content="Nice to meet you, Alice!",
            timestamp=datetime(2026, 1, 10, 10, 0, 5),
        ),
        Message(
            role="user",
            content="I want to learn Python",
            timestamp=datetime(2026, 1, 10, 10, 1, 0),
        ),
    ]


@pytest.fixture
def sample_conversation(sample_messages: list[Message]) -> Conversation:
    """Create a sample conversation for testing."""
    return Conversation(
        session_id="test_session_123",
        messages=sample_messages,
        metadata={"user_id": "test_user"},
    )


@pytest.fixture
def sample_events() -> list[Event]:
    """Create sample events for testing."""
    return [
        Event(
            content="Tried requests.get() on dynamic site - failed",
            outcome="failure",
            tags=["web_scraping", "method_A"],
            timestamp=datetime(2026, 1, 10, 10, 0, 0),
            metadata={"session_id": "s1", "user_query": "write a scraper"},
        ),
        Event(
            content="Switched to selenium - success",
            outcome="success",
            tags=["web_scraping", "method_B"],
            timestamp=datetime(2026, 1, 10, 10, 5, 0),
            metadata={"session_id": "s1"},
        ),
    ]


@pytest.fixture
def sample_memories() -> list[Memory]:
    """Create sample memories for testing retrieval."""
    return [
        Memory(
            content="User prefers dark mode",
            score=0.95,
            source="semantic",
            timestamp=datetime(2026, 1, 10, 9, 0, 0),
            metadata={"session_id": "s0"},
        ),
        Memory(
            content="Successfully used selenium for web scraping",
            score=0.88,
            source="episodic",
            timestamp=datetime(2026, 1, 10, 10, 5, 0),
            metadata={"session_id": "s1", "outcome": "success"},
        ),
    ]


@pytest.fixture
def sample_semantic_triple() -> SemanticTriple:
    """Create a sample semantic triple for testing."""
    return SemanticTriple(
        subject="User",
        predicate="PREFERS",
        object="dark_mode",
        weight=1.0,
        version=1,
    )
