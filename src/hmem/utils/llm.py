"""LLM integration using LiteLLM for fact extraction and reflection."""

import json

try:
    from litellm import completion

    HAS_LITELLM = True
except ImportError:
    HAS_LITELLM = False

from hmem.models import SemanticTriple, Principle, Event
from hmem.exceptions import MemoryError


class MockLLMClient:
    """Mock LLM client for testing without API credentials."""

    def extract_facts(self, content: str) -> list[SemanticTriple]:
        """Extract semantic triples from content (mock implementation)."""
        words = content.lower().split()

        facts = []

        if "prefer" in words or "like" in words:
            if "dark" in words and "mode" in words:
                facts.append(
                    SemanticTriple(
                        subject="user",
                        predicate="prefers",
                        object="dark_mode",
                        weight=1.0,
                    )
                )

        if "python" in words:
            facts.append(
                SemanticTriple(
                    subject="user", predicate="learns", object="python", weight=1.0
                )
            )

        if "scraping" in words or "scrape" in words:
            facts.append(
                SemanticTriple(
                    subject="user",
                    predicate="works_on",
                    object="web_scraping",
                    weight=1.0,
                )
            )

        return facts

    def summarize(self, messages: list[dict[str, str]]) -> str:
        """Summarize conversation messages (mock implementation)."""
        if not messages:
            return "Empty conversation"

        key_points = []
        for msg in messages[:3]:
            content = msg.get("content", "")
            if len(content) > 50:
                key_points.append(content[:50] + "...")
            else:
                key_points.append(content)

        return " | ".join(key_points)

    def reflect(self, episodes: list[Event]) -> Principle:
        """Generate principle from episodes (mock implementation)."""
        if not episodes:
            return Principle(
                content="No episodes to reflect on", evidence_count=0, confidence=0.0
            )

        success_count = sum(1 for e in episodes if e.outcome == "success")
        total = len(episodes)

        common_tags = set()
        for event in episodes:
            common_tags.update(event.tags)

        content = f"Based on {total} episodes"
        if common_tags:
            content += f" related to {', '.join(list(common_tags)[:3])}"
        if success_count > total / 2:
            content += ": successful patterns identified"

        return Principle(
            content=content,
            evidence_count=total,
            confidence=success_count / total if total > 0 else 0.0,
        )


class LLMClient:
    """LLM client using LiteLLM for real API calls."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.1,
        use_mock: bool = True,
    ):
        """Initialize LLM client.

        Args:
            model: Model identifier
            temperature: Sampling temperature
            use_mock: Whether to use mock implementation
        """
        self.model = model
        self.temperature = temperature
        self.use_mock = use_mock or not HAS_LITELLM

        if self.use_mock:
            self.mock = MockLLMClient()

    def extract_facts(self, content: str) -> list[SemanticTriple]:
        """Extract semantic facts from content.

        Args:
            content: Text content to analyze

        Returns:
            List of extracted semantic triples
        """
        if self.use_mock:
            return self.mock.extract_facts(content)

        try:
            response = completion(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Extract semantic facts as JSON array of {subject, predicate, object} triples.",
                    },
                    {"role": "user", "content": content},
                ],
                temperature=self.temperature,
            )

            facts_json = json.loads(response.choices[0].message.content)
            return [
                SemanticTriple(
                    subject=f["subject"],
                    predicate=f["predicate"],
                    object=f["object"],
                    weight=1.0,
                )
                for f in facts_json
            ]
        except Exception as e:
            raise MemoryError(f"LLM fact extraction failed: {e}") from e

    def summarize(self, messages: list[dict[str, str]]) -> str:
        """Summarize conversation messages.

        Args:
            messages: List of conversation messages

        Returns:
            Summary text
        """
        if self.use_mock:
            return self.mock.summarize(messages)

        try:
            conversation_text = "\n".join(
                [f"{msg['role']}: {msg['content']}" for msg in messages]
            )

            response = completion(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Summarize the following conversation concisely, preserving key information.",
                    },
                    {"role": "user", "content": conversation_text},
                ],
                temperature=self.temperature,
            )

            return response.choices[0].message.content
        except Exception as e:
            raise MemoryError(f"LLM summarization failed: {e}") from e

    def reflect(self, episodes: list[Event]) -> Principle:
        """Generate general principle from specific episodes.

        Args:
            episodes: List of related episodes

        Returns:
            Extracted principle
        """
        if self.use_mock:
            return self.mock.reflect(episodes)

        try:
            episodes_text = "\n".join(
                [
                    f"Episode {i + 1}: {e.content} (outcome: {e.outcome})"
                    for i, e in enumerate(episodes)
                ]
            )

            response = completion(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Analyze these episodes and extract a general principle or pattern. Return JSON with {content, confidence}.",
                    },
                    {"role": "user", "content": episodes_text},
                ],
                temperature=self.temperature,
            )

            result = json.loads(response.choices[0].message.content)
            return Principle(
                content=result["content"],
                evidence_count=len(episodes),
                confidence=result.get("confidence", 0.5),
            )
        except Exception as e:
            raise MemoryError(f"LLM reflection failed: {e}") from e


llm_client = LLMClient(use_mock=True)


def get_llm_client(use_mock: bool = True) -> LLMClient:
    """Get LLM client instance.

    Args:
        use_mock: Whether to use mock implementation

    Returns:
        LLM client instance
    """
    return LLMClient(use_mock=use_mock)
