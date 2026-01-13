"""Advanced topic extraction using semantic clustering.

This module provides intelligent topic discovery from episodic memories
without relying on manual tags. Uses HDBSCAN clustering for better
handling of varying density clusters.
"""

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import structlog
from hdbscan import HDBSCAN  # type: ignore

from hmem.models import Event
from hmem.utils.embeddings import get_embedding
from hmem.agents.llm import LLMClient

logger = structlog.get_logger()


@dataclass
class TopicCluster:
    """Discovered topic cluster from semantic analysis."""

    topic_id: str
    label: str
    episodes: list[Event]
    centroid: np.ndarray
    confidence: float
    parent_topic: str | None = None

    def __post_init__(self) -> None:
        """Ensure numpy array for centroid."""
        if not isinstance(self.centroid, np.ndarray):
            self.centroid = np.array(self.centroid)


class TopicExtractor(Protocol):
    """Topic extraction strategy interface."""

    def extract_topics(
        self, episodes: list[Event], min_cluster_size: int = 3
    ) -> list[TopicCluster]:
        """Extract topics from episodes.

        Args:
            episodes: Episodes to analyze
            min_cluster_size: Minimum cluster size

        Returns:
            List of discovered topic clusters
        """
        ...


@dataclass
class SemanticTopicExtractor:
    """Extract topics using semantic clustering + LLM labeling.

    Workflow:
    1. Embed all episodes using vector representations
    2. Cluster using HDBSCAN (handles varying density better than DBSCAN)
    3. Extract representative samples from each cluster
    4. Use LLM to generate meaningful topic labels
    5. Build optional hierarchical topic structure
    """

    min_cluster_size: int = 5
    min_samples: int = 3
    hierarchy_similarity_threshold: float = 0.7
    llm_client: object = field(default=None)

    def __post_init__(self) -> None:
        """Initialize LLM client if not provided."""
        if self.llm_client is None:
            self.llm_client = LLMClient()

    def extract_topics(
        self, episodes: list[Event], min_cluster_size: int | None = None
    ) -> list[TopicCluster]:
        """Extract topics via semantic clustering.

        Args:
            episodes: Episodes to cluster
            min_cluster_size: Override for minimum cluster size

        Returns:
            List of TopicCluster objects
        """
        effective_min_size = min_cluster_size or self.min_cluster_size

        if len(episodes) < effective_min_size:
            logger.info(
                "insufficient_episodes_for_clustering",
                count=len(episodes),
                required=effective_min_size,
            )
            return []

        embeddings = self._embed_episodes(episodes)
        labels = self._cluster_embeddings(embeddings, effective_min_size)
        clusters = self._build_clusters(episodes, embeddings, labels)

        if len(clusters) > 1:
            self._build_topic_hierarchy(clusters)

        logger.info(
            "topics_extracted",
            total_episodes=len(episodes),
            topics_found=len(clusters),
            noise_count=sum(1 for label in labels if label == -1),
        )

        return clusters

    def _embed_episodes(self, episodes: list[Event]) -> np.ndarray:
        """Generate embeddings for all episodes."""
        return np.array([get_embedding(e.content) for e in episodes])

    def _cluster_embeddings(
        self, embeddings: np.ndarray, min_cluster_size: int
    ) -> np.ndarray:
        """Cluster embeddings using HDBSCAN."""
        clusterer = HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=self.min_samples,
            metric="euclidean",
            cluster_selection_method="eom",
        )
        return clusterer.fit_predict(embeddings)

    def _build_clusters(
        self,
        episodes: list[Event],
        embeddings: np.ndarray,
        labels: np.ndarray,
    ) -> list[TopicCluster]:
        """Build TopicCluster objects from clustering results."""
        clusters = []
        unique_labels = set(labels)
        unique_labels.discard(-1)

        for label_id in unique_labels:
            cluster_mask = labels == label_id
            cluster_episodes = [e for i, e in enumerate(episodes) if cluster_mask[i]]
            cluster_embeddings = embeddings[cluster_mask]

            centroid = cluster_embeddings.mean(axis=0)
            samples = self._get_representative_samples(
                cluster_episodes, cluster_embeddings, centroid
            )
            topic_label = self._generate_topic_label(samples)
            confidence = self._calculate_cluster_confidence(
                cluster_embeddings, centroid
            )

            clusters.append(
                TopicCluster(
                    topic_id=f"topic_{label_id}",
                    label=topic_label,
                    episodes=cluster_episodes,
                    centroid=centroid,
                    confidence=confidence,
                )
            )

        return clusters

    def _get_representative_samples(
        self,
        episodes: list[Event],
        embeddings: np.ndarray,
        centroid: np.ndarray,
        n_samples: int = 3,
    ) -> list[Event]:
        """Get episodes closest to cluster centroid."""
        distances = np.linalg.norm(embeddings - centroid, axis=1)
        representative_indices = np.argsort(distances)[:n_samples]
        return [episodes[i] for i in representative_indices]

    def _generate_topic_label(self, samples: list[Event]) -> str:
        """Use LLM to generate concise topic label."""
        try:
            return self.llm_client.generate_topic_label(samples)  # type: ignore
        except Exception as e:
            logger.warning("topic_label_generation_failed", error=str(e))
            return self._fallback_topic_label(samples)

    def _fallback_topic_label(self, samples: list[Event]) -> str:
        """Generate topic label using TF-IDF when LLM fails.

        Uses Term Frequency-Inverse Document Frequency to identify
        the most distinctive terms across samples.
        """
        import math
        from collections import Counter

        from hmem.utils.text_processing import STOP_WORDS

        if not samples:
            return "unknown_topic"

        # Collect words from all samples with document frequency tracking
        all_words: list[str] = []
        doc_frequencies: Counter[str] = Counter()
        sample_words: list[set[str]] = []

        for sample in samples:
            words_in_sample: set[str] = set()
            for word in sample.content.lower().split():
                cleaned = "".join(c for c in word if c.isalnum())
                if cleaned and cleaned not in STOP_WORDS and len(cleaned) > 2:
                    all_words.append(cleaned)
                    words_in_sample.add(cleaned)
            sample_words.append(words_in_sample)
            doc_frequencies.update(words_in_sample)

        if not all_words:
            return "unknown_topic"

        # Calculate TF-IDF scores
        word_counts = Counter(all_words)
        n_docs = len(samples)

        tfidf_scores: dict[str, float] = {}
        for word, count in word_counts.items():
            # Term frequency: count / total words
            tf = count / len(all_words)
            # Inverse document frequency: log(n_docs / docs_containing_word)
            df = doc_frequencies[word]
            idf = math.log(n_docs / max(df, 1)) + 1  # +1 to avoid zero
            tfidf_scores[word] = tf * idf

        # Get top terms by TF-IDF score
        top_terms = sorted(tfidf_scores.items(), key=lambda x: -x[1])[:2]

        if not top_terms:
            return "unknown_topic"

        return "_".join(term for term, _ in top_terms)

    def _calculate_cluster_confidence(
        self, embeddings: np.ndarray, centroid: np.ndarray
    ) -> float:
        """Calculate cluster quality score (0-1)."""
        distances = np.linalg.norm(embeddings - centroid, axis=1)
        avg_distance = float(distances.mean())
        return 1.0 / (1.0 + avg_distance)

    def _build_topic_hierarchy(self, clusters: list[TopicCluster]) -> None:
        """Build parent-child relationships between topics.

        Uses cosine similarity between cluster centroids to identify
        potential parent-child relationships. Larger clusters with
        similar centroids may be parent topics.

        Args:
            clusters: List of topic clusters to organize hierarchically
        """
        sorted_clusters = sorted(clusters, key=lambda c: len(c.episodes), reverse=True)

        for i, child in enumerate(sorted_clusters):
            max_similarity = 0.0
            best_parent: TopicCluster | None = None

            # Normalize child centroid for cosine similarity
            child_norm = np.linalg.norm(child.centroid)
            if child_norm == 0:
                continue
            child_normalized = child.centroid / child_norm

            for parent in sorted_clusters[:i]:
                # Normalize parent centroid
                parent_norm = np.linalg.norm(parent.centroid)
                if parent_norm == 0:
                    continue
                parent_normalized = parent.centroid / parent_norm

                # Cosine similarity via dot product of normalized vectors
                similarity = float(np.dot(child_normalized, parent_normalized))

                if (
                    similarity > max_similarity
                    and similarity > self.hierarchy_similarity_threshold
                ):
                    max_similarity = similarity
                    best_parent = parent

            if best_parent is not None:
                child.parent_topic = best_parent.label
                logger.debug(
                    "topic_hierarchy_link",
                    child=child.label,
                    parent=best_parent.label,
                    similarity=max_similarity,
                )
