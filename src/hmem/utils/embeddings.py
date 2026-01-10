"""Embedding generation utilities."""

import hashlib
import numpy as np
from numpy.typing import NDArray


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

    def __init__(self, dim: int = 384) -> None:
        """Initialize embedding generator.

        Args:
            dim: Embedding dimension
        """
        self.dim = dim

    def embed(self, text: str) -> np.ndarray:
        """Generate embedding for text using deterministic hashing.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (shape: (dim,))
        """
        text_hash = hashlib.md5(text.encode()).hexdigest()
        seed = int(text_hash[:8], 16)
        rng = np.random.RandomState(seed)
        
        base_vector = rng.randn(self.dim).astype(np.float32)
        
        words = text.lower().split()
        for word in words:
            word_hash = hashlib.md5(word.encode()).hexdigest()
            word_seed = int(word_hash[:8], 16)
            word_rng = np.random.RandomState(word_seed)
            word_vector = word_rng.randn(self.dim).astype(np.float32)
            base_vector += word_vector * 0.1
        
        norm = np.linalg.norm(base_vector)
        if norm > 0:
            base_vector = base_vector / norm
        
        return base_vector

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
