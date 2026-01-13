"""Text processing utilities for query normalization and term extraction.

Provides shared text processing functions used across retrieval and encoding components.
"""

import re
from collections import Counter

# Common English stop words for filtering
STOP_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "need",
        "dare",
        "ought",
        "used",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "also",
        "now",
        "i",
        "me",
        "my",
        "myself",
        "we",
        "our",
        "ours",
        "ourselves",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
        "he",
        "him",
        "his",
        "himself",
        "she",
        "her",
        "hers",
        "herself",
        "it",
        "its",
        "itself",
        "they",
        "them",
        "their",
        "theirs",
        "themselves",
        "what",
        "which",
        "who",
        "whom",
        "this",
        "that",
        "these",
        "those",
        "am",
        "and",
        "but",
        "if",
        "or",
        "because",
        "until",
        "while",
        "although",
        "though",
        "since",
        "unless",
    }
)


def normalize_query(query: str) -> str:
    """Normalize query for consistent filtering and caching.

    Transformations:
    - Lowercase
    - Remove punctuation (except hyphens in compound words)
    - Collapse multiple whitespace
    - Strip leading/trailing whitespace

    Args:
        query: Raw query string

    Returns:
        Normalized query string
    """
    # Lowercase and strip
    normalized = query.lower().strip()

    # Remove punctuation except hyphens in compound words
    # Keep alphanumeric, whitespace, and hyphens between words
    normalized = re.sub(r"[^\w\s-]", "", normalized)

    # Collapse multiple whitespace
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized.strip()


def extract_query_terms(query: str, min_length: int = 2) -> list[str]:
    """Extract significant terms from a query for filtering.

    Removes stop words and short words to get meaningful search terms.

    Args:
        query: Query string to process
        min_length: Minimum word length to include

    Returns:
        List of significant query terms
    """
    words = normalize_query(query).split()
    return [w for w in words if len(w) > min_length and w not in STOP_WORDS]


def extract_significant_terms(
    content: str, max_terms: int = 10, min_length: int = 3
) -> list[str]:
    """Extract significant terms from content using word frequency.

    Filters stop words and short words, then returns the most frequent
    remaining terms.

    Args:
        content: Text content to analyze
        max_terms: Maximum number of terms to return
        min_length: Minimum word length to consider

    Returns:
        List of significant terms ordered by frequency
    """
    # Normalize and split
    normalized = normalize_query(content)
    words = normalized.split()

    # Filter stop words and short words
    significant = [w for w in words if len(w) >= min_length and w not in STOP_WORDS]

    # Return most common terms
    term_counts = Counter(significant)
    return [term for term, _ in term_counts.most_common(max_terms)]


def normalize_tag(tag: str) -> str:
    """Normalize a tag to snake_case format.

    Args:
        tag: Raw tag string

    Returns:
        Normalized snake_case tag
    """
    # Lowercase, replace spaces and hyphens with underscores
    normalized = tag.lower().strip()
    normalized = re.sub(r"[\s-]+", "_", normalized)
    # Remove any remaining non-alphanumeric characters except underscores
    normalized = re.sub(r"[^\w]", "", normalized)
    # Collapse multiple underscores
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")
