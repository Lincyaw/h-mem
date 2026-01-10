"""LLM client for intelligent text processing tasks.

Provides simple methods for different LLM operations:
- extract_facts: Extract semantic triples from text
- summarize: Summarize conversation messages
- reflect: Generate principles from episodes
- generate_topic_label: Create topic labels from samples
- generate_skill: Convert principles to actionable skills
"""

import json
import os
from typing import Any

import structlog
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from hmem.exceptions import MemoryError
from hmem.models import Event, Principle, SemanticTriple

# Load environment variables from .env file
load_dotenv()

logger = structlog.get_logger()


class LLMClient:
    """Simple LLM client for text processing operations.

    This is a lightweight wrapper around LangChain chat models,
    providing domain-specific methods for memory system tasks.

    Example:
        >>> client = LLMClient()
        >>> facts = client.extract_facts("User prefers dark mode")
        >>> principle = client.reflect(episodes)
    """

    def __init__(
        self,
        model: str | None = None,
        temperature: float = 0.1,
    ) -> None:
        """Initialize LLM client.

        Args:
            model: Model identifier in format 'provider:model_name'
                   e.g., 'openai:gpt-4o-mini', 'openai:ep-xxx-endpoint-id'
                   If None, uses default from LLMConfig.
            temperature: Sampling temperature
        """
        from hmem.config import LLMConfig

        # Use default from config if not provided
        if model is None:
            model = LLMConfig().model

        # Configure OpenAI-compatible base URL from environment
        api_base = os.getenv("OPENAI_API_BASE")
        if api_base:
            os.environ["OPENAI_BASE_URL"] = api_base

        self.llm: BaseChatModel = init_chat_model(model, temperature=temperature)
        self.logger = logger.bind(component="llm_client")

    def extract_facts(self, content: str) -> list[SemanticTriple]:
        """Extract semantic facts from content.

        Args:
            content: Text to analyze

        Returns:
            List of extracted semantic triples
        """
        try:
            messages = [
                SystemMessage(
                    content="""Extract semantic facts from the following text as a JSON array.
Each fact should be an object with "subject", "predicate", and "object" fields.
If no clear facts can be extracted, return an empty array: []
Respond ONLY with the JSON array, no additional text.

Example output:
[{"subject": "Alice", "predicate": "prefers", "object": "dark mode"}]"""
                ),
                HumanMessage(content=content),
            ]
            response = self.llm.invoke(messages)

            response_text = str(response.content).strip()

            # Handle empty or invalid responses
            if not response_text:
                self.logger.warning("llm_empty_response", content=content[:100])
                return []

            # Try to extract JSON from response (handle markdown code blocks)
            if response_text.startswith("```"):
                # Extract content between code blocks
                lines = response_text.split("\n")
                json_lines = []
                in_block = False
                for line in lines:
                    if line.startswith("```"):
                        in_block = not in_block
                        continue
                    if in_block:
                        json_lines.append(line)
                response_text = "\n".join(json_lines)

            facts_json = json.loads(response_text)

            # Handle case where response is not a list
            if not isinstance(facts_json, list):
                self.logger.warning(
                    "llm_unexpected_format", response=response_text[:100]
                )
                return []

            return [
                SemanticTriple(
                    subject=f["subject"],
                    predicate=f["predicate"],
                    object=f["object"],
                    weight=1.0,
                )
                for f in facts_json
                if isinstance(f, dict)
                and "subject" in f
                and "predicate" in f
                and "object" in f
            ]
        except json.JSONDecodeError as e:
            self.logger.warning(
                "llm_json_parse_error", error=str(e), content=content[:100]
            )
            return []  # Return empty list instead of raising
        except Exception as e:
            raise MemoryError(f"LLM fact extraction failed: {e}") from e

    def summarize(self, messages: list[dict[str, str]]) -> str:
        """Summarize conversation messages.

        Args:
            messages: List of conversation messages

        Returns:
            Summary text
        """
        try:
            conversation_text = "\n".join(
                [f"{msg['role']}: {msg['content']}" for msg in messages]
            )

            lc_messages = [
                SystemMessage(
                    content="Summarize the following conversation concisely, preserving key information."
                ),
                HumanMessage(content=conversation_text),
            ]
            response = self.llm.invoke(lc_messages)

            return str(response.content)
        except Exception as e:
            raise MemoryError(f"LLM summarization failed: {e}") from e

    def reflect(self, episodes: list[Event]) -> Principle:
        """Generate principle from episodes.

        Args:
            episodes: List of related episodes

        Returns:
            Extracted principle
        """
        try:
            episodes_text = "\n".join(
                [
                    f"Episode {i + 1}: {e.content} (outcome: {e.outcome})"
                    for i, e in enumerate(episodes)
                ]
            )

            messages = [
                SystemMessage(
                    content="Analyze these episodes and extract a general principle or pattern. Return JSON with {content, confidence}."
                ),
                HumanMessage(content=episodes_text),
            ]
            response = self.llm.invoke(messages)

            result = json.loads(response.content)  # type: ignore[arg-type]
            return Principle(
                content=result["content"],
                evidence_count=len(episodes),
                confidence=result.get("confidence", 0.5),
            )
        except Exception as e:
            raise MemoryError(f"LLM reflection failed: {e}") from e

    def generate_topic_label(self, samples: list[Event]) -> str:
        """Generate topic label from samples.

        Args:
            samples: Representative episodes

        Returns:
            Topic label string in snake_case
        """
        try:
            samples_text = "\n".join([f"- {s.content[:200]}" for s in samples[:3]])

            messages = [
                SystemMessage(
                    content="Analyze these conversation snippets and generate ONE concise topic label (2-4 words). Respond with ONLY the topic label in snake_case, no explanation."
                ),
                HumanMessage(content=samples_text),
            ]
            response = self.llm.invoke(messages)

            label = str(response.content).strip()
            return label.lower().replace(" ", "_").replace("-", "_")
        except Exception as e:
            raise MemoryError(f"LLM topic label generation failed: {e}") from e

    def generate_skill(self, principle: Principle, topic: str) -> dict[str, Any] | None:
        """Generate skill from principle.

        Args:
            principle: Principle to convert
            topic: Topic domain

        Returns:
            Skill template dict or None if not actionable
        """
        try:
            system_prompt = """Analyze this principle and determine if it's actionable.
If actionable, return a JSON skill template with:
{
    "is_actionable": true,
    "name": "short_skill_name",
    "trigger_pattern": "patterns|that|trigger|this|skill",
    "description": "Human readable description",
    "steps": [{"action": "step_name", "description": "what to do"}],
    "confidence": 0.0-1.0
}
If not actionable (too abstract or observational), return:
{"is_actionable": false}"""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(
                    content=f"Topic: {topic}\nPrinciple: {principle.content}\nEvidence count: {principle.evidence_count}\nConfidence: {principle.confidence}"
                ),
            ]
            response = self.llm.invoke(messages)

            result = json.loads(response.content)  # type: ignore[arg-type]

            if not result.get("is_actionable", False):
                return None

            return {
                "name": result.get("name", f"auto_{topic}"),
                "trigger_pattern": result.get("trigger_pattern", topic),
                "description": result.get("description", principle.content),
                "steps": result.get("steps", []),
                "confidence": result.get("confidence", principle.confidence),
            }
        except Exception as e:
            raise MemoryError(f"LLM skill generation failed: {e}") from e


def get_llm_agent(
    model: str = "openai:gpt-4o-mini",
    temperature: float = 0.1,
) -> LLMClient:
    """Get LLM client instance.

    Args:
        model: Model identifier
        temperature: Sampling temperature

    Returns:
        LLM client instance
    """
    return LLMClient(model=model, temperature=temperature)
