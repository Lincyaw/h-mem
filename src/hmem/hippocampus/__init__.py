"""Layer 2: Hippocampus Processing.

The scheduling center that converts short-term to long-term memory
and extracts wisdom through reflection.
"""

from hmem.hippocampus.consolidator import Consolidator
from hmem.hippocampus.encoder import MemoryEncoder
from hmem.hippocampus.retrieval_engine import RetrievalEngine
from hmem.hippocampus.topic_extraction import SemanticTopicExtractor, TopicCluster

__all__ = [
    "MemoryEncoder",
    "Consolidator",
    "RetrievalEngine",
    "SemanticTopicExtractor",
    "TopicCluster",
]
