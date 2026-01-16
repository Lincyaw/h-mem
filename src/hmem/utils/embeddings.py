"""Embedding generation utilities.

Supports multiple backends:
- Local: Hash-based deterministic embeddings (development/testing)
- OpenAI: text-embedding-3-small (production)
- Custom: Any embedding function via callback

Usage:
    # Default (hash-based for development)
    from hmem.utils.embeddings import get_embedding
    vector = get_embedding("user prefers dark mode")

    # Configure OpenAI backend
    from hmem.utils.embeddings import configure_embedding_backend
    configure_embedding_backend("openai", model="text-embedding-3-small")
    vector = get_embedding("user prefers dark mode")
"""

import hashlib
import os
from typing import Any, Callable, Literal

import numpy as np
import structlog

from hmem.constants import EMBEDDING_DEFAULT_DIMENSION, EMBEDDING_WORD_SCALE_FACTOR

logger = structlog.get_logger()

# Type for embedding backend
EmbeddingBackend = Literal["hash", "openai", "custom"]


class HashEmbeddingGenerator:
    """Generate embeddings using deterministic hashing (development/testing).

    Fast and reproducible but not semantically meaningful.
    Use for development and testing only.

    Example:
        >>> generator = HashEmbeddingGenerator(dim=384)
        >>> vector = generator.embed("user prefers dark mode")
        >>> vector.shape
        (384,)
    """

    def __init__(self, dim: int = EMBEDDING_DEFAULT_DIMENSION) -> None:
        """Initialize hash embedding generator.

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


class OpenAIEmbeddingGenerator:
    """Generate embeddings using OpenAI API (production).

    Uses text-embedding-3-small by default for cost efficiency.
    Requires OPENAI_API_KEY environment variable.

    Example:
        >>> generator = OpenAIEmbeddingGenerator(model="text-embedding-3-small")
        >>> vector = generator.embed("user prefers dark mode")
        >>> len(vector)
        1536
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        dimensions: int | None = None,
        api_key: str | None = None,
    ) -> None:
        """Initialize OpenAI embedding generator.

        Args:
            model: OpenAI embedding model name
            dimensions: Output dimensions (if model supports it)
            api_key: API key (defaults to OPENAI_API_KEY env var)
        """
        self.model = model
        self.dimensions = dimensions
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._client: Any = None

    @property
    def client(self) -> Any:
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            try:
                import openai
            except ImportError:
                raise ImportError(
                    "OpenAI package not installed. Install with: pip install openai"
                )

            if not self.api_key:
                raise ValueError(
                    "OpenAI API key not found. "
                    "Set OPENAI_API_KEY environment variable or pass api_key."
                )

            self._client = openai.OpenAI(api_key=self.api_key)

        return self._client

    def embed(self, text: str) -> list[float]:
        """Generate embedding for text using OpenAI API.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        # Handle empty text
        if not text or not text.strip():
            logger.warning("empty_text_for_embedding")
            # Return zero vector with correct dimensions
            dim = self.dimensions or 1536
            return [0.0] * dim

        try:
            kwargs: dict[str, str | int] = {
                "model": self.model,
                "input": text,
            }
            if self.dimensions:
                kwargs["dimensions"] = self.dimensions

            response = self.client.embeddings.create(**kwargs)  # type: ignore[arg-type]
            embedding = response.data[0].embedding

            logger.debug(
                "openai_embedding_generated",
                model=self.model,
                text_length=len(text),
                embedding_dim=len(embedding),
            )

            return list(embedding)

        except Exception as e:
            logger.error("openai_embedding_failed", error=str(e), text_length=len(text))
            raise

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Uses batch API for efficiency.

        Args:
            texts: List of texts

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Filter empty texts and track indices
        valid_texts = []
        valid_indices = []
        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text)
                valid_indices.append(i)

        if not valid_texts:
            dim = self.dimensions or 1536
            return [[0.0] * dim for _ in texts]

        try:
            kwargs: dict[str, str | int | list[str]] = {
                "model": self.model,
                "input": valid_texts,
            }
            if self.dimensions:
                kwargs["dimensions"] = self.dimensions

            response = self.client.embeddings.create(**kwargs)  # type: ignore[arg-type]

            # Build result with correct ordering
            dim = len(response.data[0].embedding)
            results: list[list[float]] = [[0.0] * dim for _ in texts]

            for i, embedding_data in enumerate(response.data):
                original_idx = valid_indices[i]
                results[original_idx] = list(embedding_data.embedding)

            logger.debug(
                "openai_batch_embedding_generated",
                model=self.model,
                batch_size=len(valid_texts),
                embedding_dim=dim,
            )

            return results

        except Exception as e:
            logger.error(
                "openai_batch_embedding_failed",
                error=str(e),
                batch_size=len(texts),
            )
            raise


class EmbeddingManager:
    """Manages embedding generation with configurable backends.

    Supports switching between hash-based (development) and
    OpenAI (production) embeddings at runtime.

    Example:
        >>> manager = EmbeddingManager()
        >>> manager.configure("openai", model="text-embedding-3-small")
        >>> vector = manager.embed("user prefers dark mode")
    """

    def __init__(self) -> None:
        """Initialize embedding manager with hash backend."""
        self._backend: EmbeddingBackend = "hash"
        self._hash_generator = HashEmbeddingGenerator()
        self._openai_generator: OpenAIEmbeddingGenerator | None = None
        self._custom_fn: Callable[[str], list[float]] | None = None
        self._dimension = EMBEDDING_DEFAULT_DIMENSION

    def configure(
        self,
        backend: EmbeddingBackend,
        model: str = "text-embedding-3-small",
        dimensions: int | None = None,
        api_key: str | None = None,
        custom_fn: Callable[[str], list[float]] | None = None,
    ) -> None:
        """Configure embedding backend.

        Args:
            backend: "hash", "openai", or "custom"
            model: Model name for OpenAI backend
            dimensions: Output dimensions (optional)
            api_key: API key for OpenAI (optional, uses env var by default)
            custom_fn: Custom embedding function for "custom" backend
        """
        self._backend = backend

        if backend == "openai":
            self._openai_generator = OpenAIEmbeddingGenerator(
                model=model,
                dimensions=dimensions,
                api_key=api_key,
            )
            self._dimension = dimensions or 1536
            logger.info(
                "embedding_backend_configured",
                backend="openai",
                model=model,
                dimensions=self._dimension,
            )

        elif backend == "custom":
            if custom_fn is None:
                raise ValueError("custom_fn required for custom backend")
            self._custom_fn = custom_fn
            logger.info("embedding_backend_configured", backend="custom")

        else:
            # Hash backend
            if dimensions:
                self._hash_generator = HashEmbeddingGenerator(dim=dimensions)
                self._dimension = dimensions
            logger.info(
                "embedding_backend_configured",
                backend="hash",
                dimensions=self._dimension,
            )

    def embed(self, text: str) -> list[float]:
        """Generate embedding for text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        if self._backend == "openai" and self._openai_generator:
            return self._openai_generator.embed(text)
        elif self._backend == "custom" and self._custom_fn:
            return self._custom_fn(text)
        else:
            return self._hash_generator.embed(text).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts

        Returns:
            List of embedding vectors
        """
        if self._backend == "openai" and self._openai_generator:
            return self._openai_generator.embed_batch(texts)
        elif self._backend == "custom" and self._custom_fn:
            return [self._custom_fn(text) for text in texts]
        else:
            return [self._hash_generator.embed(text).tolist() for text in texts]

    @property
    def dimension(self) -> int:
        """Get current embedding dimension."""
        return self._dimension

    @property
    def backend(self) -> EmbeddingBackend:
        """Get current backend type."""
        return self._backend


# Global embedding manager instance
_embedding_manager = EmbeddingManager()


def configure_embedding_backend(
    backend: EmbeddingBackend,
    model: str = "text-embedding-3-small",
    dimensions: int | None = None,
    api_key: str | None = None,
    custom_fn: Callable[[str], list[float]] | None = None,
) -> None:
    """Configure the global embedding backend.

    Args:
        backend: "hash", "openai", or "custom"
        model: Model name for OpenAI backend
        dimensions: Output dimensions (optional)
        api_key: API key for OpenAI (optional, uses env var by default)
        custom_fn: Custom embedding function for "custom" backend

    Example:
        >>> configure_embedding_backend("openai", model="text-embedding-3-small")
        >>> vector = get_embedding("user prefers dark mode")
    """
    _embedding_manager.configure(
        backend=backend,
        model=model,
        dimensions=dimensions,
        api_key=api_key,
        custom_fn=custom_fn,
    )


def get_embedding(text: str) -> list[float]:
    """Get embedding for text using configured backend.

    Args:
        text: Input text

    Returns:
        Embedding as list of floats
    """
    return _embedding_manager.embed(text)


def get_embedding_batch(texts: list[str]) -> list[list[float]]:
    """Get embeddings for multiple texts using configured backend.

    Args:
        texts: List of input texts

    Returns:
        List of embeddings
    """
    return _embedding_manager.embed_batch(texts)


def get_embedding_dimension() -> int:
    """Get current embedding dimension.

    Returns:
        Embedding dimension
    """
    return _embedding_manager.dimension


def get_embedding_backend() -> EmbeddingBackend:
    """Get current embedding backend type.

    Returns:
        Backend type: "hash", "openai", or "custom"
    """
    return _embedding_manager.backend


# Backward compatibility alias
EmbeddingGenerator = HashEmbeddingGenerator
_default_generator = HashEmbeddingGenerator()
