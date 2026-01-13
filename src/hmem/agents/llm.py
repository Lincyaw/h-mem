"""LLM client for intelligent text processing tasks.

Provides simple methods for different LLM operations:
- extract_facts: Extract semantic triples from text
- summarize: Summarize conversation messages
- reflect: Generate principles from episodes
- generate_topic_label: Create topic labels from samples
- generate_skill: Convert principles to actionable skills
- infer_outcome: Infer task outcome (success/failure) from content
- extract_tags: Extract semantic tags from content
- extract_conversation_topics: Extract main topics from conversation
"""

import json
import os
from typing import Any, Literal

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

    def extract_feedback_signals(
        self, content: str, memory_ids: list[str]
    ) -> list[dict[str, str]]:
        """Extract feedback signals from conversation using LLM.

        Analyzes conversation content to determine if any previously used
        memories (skills, principles, facts) were helpful or not.

        IMPORTANT: This extracts outcomes from conversation semantics and XML markup,
        NOT from Memory object attributes. The LLM infers success/failure from:
        1. Explicit XML markup: <skill id="xxx" outcome="success">...
        2. Implicit signals: "that worked!", "it failed", etc.

        Args:
            content: Conversation text to analyze (may contain agent-added XML markup)
            memory_ids: List of memory IDs that were used in this context

        Returns:
            List of feedback signals extracted from conversation, each containing:
            - memory_id: The memory that received feedback
            - outcome: "success" or "failure" (extracted from conversation, not Memory)
            - reason: Brief explanation of why
        """
        if not memory_ids:
            return []

        try:
            system_prompt = """Analyze the conversation to determine if any referenced memories were helpful.

For each memory ID provided, determine if the conversation indicates:
- "success": The memory was useful, accurate, or led to a good outcome
- "failure": The memory was wrong, unhelpful, or led to problems
- Skip memories with no clear signal

Return a JSON array of objects with: memory_id, outcome, reason
Return empty array [] if no clear feedback signals found.

Example output:
[{"memory_id": "skill_abc", "outcome": "success", "reason": "User confirmed the approach worked"}]"""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(
                    content=f"Memory IDs to check: {memory_ids}\n\nConversation:\n{content}"
                ),
            ]
            response = self.llm.invoke(messages)
            response_text = str(response.content).strip()

            if not response_text:
                return []

            # Extract JSON from response
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()

            result = json.loads(response_text)
            if not isinstance(result, list):
                return []

            # Validate and filter results
            valid_signals = []
            for signal in result:
                if (
                    isinstance(signal, dict)
                    and "memory_id" in signal
                    and "outcome" in signal
                    and signal["outcome"] in ("success", "failure")
                ):
                    valid_signals.append(signal)

            return valid_signals

        except Exception as e:
            self.logger.warning("feedback_extraction_failed", error=str(e))
            return []

    def infer_outcome(self, content: str) -> Literal["success", "failure", "unknown"]:
        """Infer task outcome from content using LLM.

        Analyzes text semantically to determine if it indicates a successful
        or failed outcome, beyond simple keyword matching.

        Args:
            content: Message content to analyze

        Returns:
            Inferred outcome: "success", "failure", or "unknown"
        """
        try:
            system_prompt = """Analyze this message and determine the task outcome.
Return ONLY one word: "success", "failure", or "unknown"

Indicators of success: task completed, problem solved, goal achieved, positive confirmation,
  things working as expected, user satisfaction, successful execution
Indicators of failure: error occurred, task failed, problem unsolved, negative outcome,
  crashes, bugs, exceptions, user frustration, unsuccessful attempts
Return "unknown" if: the message is a question, a request, informational,
  or doesn't clearly indicate a task outcome."""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=content[:2000]),  # Limit content length
            ]
            response = self.llm.invoke(messages)
            result = str(response.content).strip().lower()

            # Validate response
            if result in ("success", "failure", "unknown"):
                return result  # type: ignore[return-value]

            # Handle variations
            if "success" in result:
                return "success"
            elif "failure" in result or "fail" in result:
                return "failure"
            else:
                return "unknown"

        except Exception as e:
            self.logger.warning("outcome_inference_failed", error=str(e))
            return "unknown"

    def extract_tags(self, content: str, max_tags: int = 5) -> list[str]:
        """Extract semantic tags from content using LLM.

        Generates contextually relevant tags for content categorization
        and retrieval. Tags are returned in snake_case format.

        Args:
            content: Text to analyze
            max_tags: Maximum number of tags to return (1-10)

        Returns:
            List of snake_case tags (e.g., ["web_scraping", "python", "debugging"])
        """
        try:
            system_prompt = f"""Extract relevant topic tags from this content.
Return a JSON array of 1-{max_tags} tags in snake_case format.
Tags should be:
- Specific enough to be useful for retrieval
- General enough to group similar content
- Related to technologies, concepts, actions, or domains mentioned

Example tags: web_scraping, python_debugging, data_analysis, api_integration,
  error_handling, database_queries, file_processing, user_authentication

Return ONLY the JSON array, no explanation.
Example output: ["web_scraping", "python", "error_handling"]"""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=content[:2000]),
            ]
            response = self.llm.invoke(messages)
            response_text = str(response.content).strip()

            # Extract JSON from response
            if response_text.startswith("```"):
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

            tags = json.loads(response_text)

            if not isinstance(tags, list):
                self.logger.warning(
                    "extract_tags_invalid_format", response=response_text[:100]
                )
                return []

            # Normalize tags to snake_case and limit count
            normalized_tags = []
            for tag in tags[:max_tags]:
                if isinstance(tag, str) and tag.strip():
                    normalized = tag.lower().strip().replace(" ", "_").replace("-", "_")
                    normalized_tags.append(normalized)

            return normalized_tags

        except json.JSONDecodeError as e:
            self.logger.warning("extract_tags_json_error", error=str(e))
            return []
        except Exception as e:
            self.logger.warning("extract_tags_failed", error=str(e))
            return []

    def extract_conversation_topics(
        self, content: str, max_topics: int = 3
    ) -> list[str]:
        """Extract main topics from conversation content using LLM.

        Identifies the primary themes or subjects being discussed
        for topic-based grouping and summarization.

        Args:
            content: Conversation text to analyze
            max_topics: Maximum number of topics to extract (1-5)

        Returns:
            List of topic labels in snake_case (e.g., ["api_authentication", "error_handling"])
        """
        try:
            system_prompt = f"""Analyze this conversation and extract the {max_topics} most important topics.
Return a JSON array of short topic labels (2-4 words each) in snake_case.
Topics should capture the main themes or subjects being discussed.

Return ONLY the JSON array, no explanation.
Example output: ["api_authentication", "database_optimization", "error_handling"]"""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=content[:3000]),
            ]
            response = self.llm.invoke(messages)
            response_text = str(response.content).strip()

            # Extract JSON from response
            if response_text.startswith("```"):
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

            topics = json.loads(response_text)

            if not isinstance(topics, list):
                self.logger.warning(
                    "extract_topics_invalid_format", response=response_text[:100]
                )
                return []

            # Normalize topics
            normalized_topics = []
            for topic in topics[:max_topics]:
                if isinstance(topic, str) and topic.strip():
                    normalized = (
                        topic.lower().strip().replace(" ", "_").replace("-", "_")
                    )
                    normalized_topics.append(normalized)

            return normalized_topics

        except json.JSONDecodeError as e:
            self.logger.warning("extract_topics_json_error", error=str(e))
            return []
        except Exception as e:
            self.logger.warning("extract_topics_failed", error=str(e))
            return []


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
