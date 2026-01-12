"""Embedding generation utilities."""

import hashlib
import numpy as np

from hmem.constants import EMBEDDING_DEFAULT_DIMENSION, EMBEDDING_WORD_SCALE_FACTOR


class EmbeddingGenerator:
    """Generate embeddings using simple hashing (Phase 1/2).

    In production (Phase 3), replace with:
    - OpenAI: text-embedding-3-small
    - Cohere: embed-english-v3.0
    - Local: sentence-transformers via Ollama

    Example:
        >>> generator = EmbeddingGenerator(dim=384)
        >>> vector = generator.embed("user prefers dark mode")
        >>> vector.shape
        (384,)
    """

    def __init__(self, dim: int = EMBEDDING_DEFAULT_DIMENSION) -> None:
        """Initialize embedding generator.

        Args:
            dim: Embedding dimension
        """
        self.dim = dim

    def _generate_vector_from_text(self, text: str, scale: float = 1.0) -> np.ndarray:
        """Generate a deterministic vector from text using hashing."""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        seed = int(text_hash[:8], 16)
        rng = np.random.RandomState(seed)
        return rng.randn(self.dim).astype(np.float32) * scale

    def embed(self, text: str) -> np.ndarray:
        """Generate embedding for text using deterministic hashing.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (shape: (dim,))
        """
        # Base vector from full text
        base_vector = self._generate_vector_from_text(text)

        # Add word-level vectors for finer granularity
        words = text.lower().split()
        for word in words:
            word_vector = self._generate_vector_from_text(
                word, scale=EMBEDDING_WORD_SCALE_FACTOR
            )
            base_vector += word_vector

        # Normalize to unit length
        norm = np.linalg.norm(base_vector)
        return base_vector / norm if norm > 0 else base_vector

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts

        Returns:
            Embedding matrix (shape: (len(texts), dim))
        """
        return np.array([self.embed(text) for text in texts])


_default_generator = EmbeddingGenerator()


def get_embedding(text: str) -> list[float]:
    """Get embedding for text using default generator.

    Args:
        text: Input text

    Returns:
        Embedding as list of floats
    """
    return _default_generator.embed(text).tolist()
