"""Deep reflection agent for principle extraction (Phase 3)."""

import numpy as np
from sklearn.cluster import DBSCAN

from hmem.models import Event, Principle
from hmem.storage.chroma_episodic import ChromaEpisodicStore
from hmem.storage.sqlite_semantic import SQLiteSemanticStore
from hmem.utils.llm import LLMClient
from hmem.exceptions import ReflectionError
import structlog

logger = structlog.get_logger()


class ReflectionPolicy:
    """Base class for reflection triggering policies."""

    def should_trigger(
        self,
        topic: str,
        episode_count: int,
        time_span_days: float,
        avg_similarity: float,
    ) -> bool:
        """Determine if reflection should be triggered.

        Args:
            topic: Topic/tag to reflect on
            episode_count: Number of episodes with this topic
            time_span_days: Time span of episodes in days
            avg_similarity: Average similarity between episodes

        Returns:
            True if reflection should be triggered
        """
        raise NotImplementedError


class MultiScaleReflectionPolicy(ReflectionPolicy):
    """Multi-time-scale reflection policy (immediate, daily, weekly)."""

    def __init__(
        self,
        immediate_threshold: int = 10,
        daily_threshold: int = 50,
        weekly_threshold: int = 100,
        similarity_threshold: float = 0.75,
    ):
        """Initialize multi-scale reflection policy.

        Args:
            immediate_threshold: Threshold for immediate (within-session) reflection
            daily_threshold: Threshold for daily reflection
            weekly_threshold: Threshold for weekly reflection
            similarity_threshold: Minimum similarity for clustering
        """
        if not (immediate_threshold < daily_threshold < weekly_threshold):
            raise ValueError(
                "Thresholds must be increasing: immediate < daily < weekly"
            )

        self.thresholds = {
            "immediate": immediate_threshold,
            "daily": daily_threshold,
            "weekly": weekly_threshold,
        }
        self.similarity_threshold = similarity_threshold

    def should_trigger(
        self,
        topic: str,
        episode_count: int,
        time_span_days: float,
        avg_similarity: float,
    ) -> bool:
        """Check if reflection should be triggered."""
        if (
            episode_count >= self.thresholds["immediate"]
            and time_span_days < 1
            and avg_similarity > self.similarity_threshold
        ):
            logger.info(
                "reflection_triggered",
                level="immediate",
                topic=topic,
                episodes=episode_count,
                similarity=avg_similarity,
            )
            return True

        if episode_count >= self.thresholds["daily"] and 1 <= time_span_days < 7:
            logger.info(
                "reflection_triggered",
                level="daily",
                topic=topic,
                episodes=episode_count,
            )
            return True

        if episode_count >= self.thresholds["weekly"] and time_span_days >= 7:
            logger.info(
                "reflection_triggered",
                level="weekly",
                topic=topic,
                episodes=episode_count,
            )
            return True

        return False


class DeepReflectionAgent:
    """Deep reflection agent for cross-task induction and principle extraction.

    Implements the "systems consolidation" process from design.md.
    """

    def __init__(
        self,
        episodic_store: ChromaEpisodicStore,
        semantic_store: SQLiteSemanticStore,
        llm_client: LLMClient | None = None,
        policy: ReflectionPolicy | None = None,
    ):
        """Initialize reflection agent.

        Args:
            episodic_store: Episodic memory store
            semantic_store: Semantic memory store
            llm_client: LLM client for principle generation
            policy: Reflection triggering policy
        """
        self.episodic_store = episodic_store
        self.semantic_store = semantic_store
        self.llm_client = llm_client or LLMClient(use_mock=True)
        self.policy = policy or MultiScaleReflectionPolicy()

    def reflect_on_topic(self, topic: str, min_episodes: int = 10) -> Principle | None:
        """Reflect on a specific topic and extract principle.

        Args:
            topic: Topic/tag to reflect on
            min_episodes: Minimum episodes required

        Returns:
            Extracted principle or None if insufficient data
        """
        try:
            episodes = self._fetch_episodes_by_topic(topic, min_episodes)

            if len(episodes) < min_episodes:
                logger.info(
                    "insufficient_episodes",
                    topic=topic,
                    found=len(episodes),
                    required=min_episodes,
                )
                return None

            clustered = self._cluster_episodes(episodes)

            largest_cluster = max(clustered, key=len) if clustered else episodes

            if len(largest_cluster) < 3:
                return None

            principle = self.llm_client.reflect(largest_cluster)

            self._store_principle(topic, principle)

            logger.info(
                "principle_extracted",
                topic=topic,
                episodes_analyzed=len(largest_cluster),
                confidence=principle.confidence,
            )

            return principle

        except Exception as e:
            logger.error("reflection_failed", topic=topic, error=str(e))
            raise ReflectionError(f"Failed to reflect on {topic}: {e}") from e

    def _fetch_episodes_by_topic(self, topic: str, limit: int = 100) -> list[Event]:
        """Fetch episodes related to a topic.

        Args:
            topic: Topic to search for
            limit: Maximum episodes to fetch

        Returns:
            List of relevant episodes
        """
        memories = self.episodic_store.search(topic, limit=limit)

        events = []
        for mem in memories:
            event = Event(
                content=mem.content,
                outcome=mem.metadata.get("outcome", "unknown"),
                tags=mem.metadata.get("tags", "").split(","),
                timestamp=mem.timestamp,
                metadata=mem.metadata,
            )
            events.append(event)

        return events

    def _cluster_episodes(
        self, episodes: list[Event], eps: float = 0.3, min_samples: int = 3
    ) -> list[list[Event]]:
        """Cluster similar episodes using DBSCAN.

        Args:
            episodes: Episodes to cluster
            eps: DBSCAN epsilon parameter
            min_samples: Minimum cluster size

        Returns:
            List of episode clusters
        """
        if len(episodes) < min_samples:
            return [episodes]

        from hmem.utils.embeddings import get_embedding

        embeddings = np.array([get_embedding(e.content) for e in episodes])

        clustering = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine")
        labels = clustering.fit_predict(embeddings)

        clusters = {}
        for idx, label in enumerate(labels):
            if label == -1:
                continue
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(episodes[idx])

        return list(clusters.values()) if clusters else [episodes]

    def _store_principle(self, topic: str, principle: Principle):
        """Store extracted principle in semantic store.

        Args:
            topic: Topic the principle relates to
            principle: Principle to store
        """
        from hmem.models import SemanticTriple

        triple = SemanticTriple(
            subject="agent",
            predicate=f"principle_{topic}",
            object=principle.content,
            weight=principle.confidence,
        )

        self.semantic_store.add_or_update(triple)

    def auto_reflect(self) -> list[Principle]:
        """Automatically reflect on all topics based on policy.

        Returns:
            List of newly extracted principles
        """
        topics = self._discover_topics()

        principles = []
        for topic in topics:
            episodes = self._fetch_episodes_by_topic(topic, limit=200)

            if len(episodes) < 3:
                continue

            time_span = self._calculate_time_span(episodes)
            avg_similarity = self._calculate_avg_similarity(episodes)

            if self.policy.should_trigger(
                topic=topic,
                episode_count=len(episodes),
                time_span_days=time_span,
                avg_similarity=avg_similarity,
            ):
                principle = self.reflect_on_topic(topic, min_episodes=5)
                if principle:
                    principles.append(principle)

        return principles

    def _discover_topics(self) -> list[str]:
        """Discover all topics from episodic memories.

        Returns:
            List of unique topics/tags
        """
        return ["web_scraping", "debugging", "learning"]

    def _calculate_time_span(self, episodes: list[Event]) -> float:
        """Calculate time span of episodes in days.

        Args:
            episodes: List of episodes

        Returns:
            Time span in days
        """
        if len(episodes) < 2:
            return 0.0

        timestamps = [e.timestamp for e in episodes]
        span = max(timestamps) - min(timestamps)
        return span.total_seconds() / 86400

    def _calculate_avg_similarity(self, episodes: list[Event]) -> float:
        """Calculate average pairwise similarity.

        Args:
            episodes: List of episodes

        Returns:
            Average similarity score (0-1)
        """
        if len(episodes) < 2:
            return 1.0

        from hmem.utils.embeddings import get_embedding
        import numpy as np

        embeddings = np.array([get_embedding(e.content) for e in episodes])

        similarities = []
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                sim = np.dot(embeddings[i], embeddings[j])
                similarities.append(sim)

        return float(np.mean(similarities)) if similarities else 0.0
