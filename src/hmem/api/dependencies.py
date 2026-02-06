"""Dependency injection for h-mem API."""

from functools import lru_cache
from pathlib import Path

from hmem.core.memory_system import MemorySystem
from hmem.storage.neo4j_unified import Neo4jUnifiedStore

DEFAULT_CONFIG_PATH = "config/memory.yaml"


@lru_cache(maxsize=1)
def get_memory_system() -> MemorySystem:
    """Get or create the singleton MemorySystem instance."""
    config_path = Path(DEFAULT_CONFIG_PATH)
    if config_path.exists():
        return MemorySystem.from_config(str(config_path))
    return MemorySystem()


def get_store() -> Neo4jUnifiedStore:
    """Get the Neo4jUnifiedStore from the MemorySystem."""
    return get_memory_system()._store
