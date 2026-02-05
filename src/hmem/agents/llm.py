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

    def _extract_text(self, content: Any) -> str:
        """Extract text from LLM response content.

        Handles both string and list (multimodal) response formats.

        Args:
            content: Response content from LLM

        Returns:
            Extracted text as string
        """
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif isinstance(block, dict) and "text" in block:
                    text_parts.append(block["text"])
            return "".join(text_parts).strip()
        return str(content).strip()

    def extract_facts(self, content: str) -> list[SemanticTriple]:
        """Extract semantic facts from content.

        Only extracts facts that are explicitly stated by the user,
        not assistant suggestions or temporary information.

        Args:
            content: Text to analyze

        Returns:
            List of extracted semantic triples with confidence scores
        """
        try:
            messages = [
                SystemMessage(
                    content=[
                        {
                            "type": "text",
                            "text": """Extract semantic facts from the following text as a JSON array.

CRITICAL: First assess if the content has meaningful, PERMANENT information worth storing.

EXTRACT FACTS ONLY FROM:
1. User's explicit preferences: "I prefer dark mode", "I always use vim"
2. User's stated facts: "Our database is PostgreSQL", "The API limit is 100/min"
3. User's corrections: "No, I meant Python 3.11, not 3.10"
4. Confirmed decisions: "Yes, let's use that approach"
5. Entity relationships: "Alice leads the backend team"

DO NOT EXTRACT:
- Greetings or small talk: "hi", "hello", "thanks", "ok", "yes", "no"
- Test messages: "test", "testing", "asdf"
- Questions: "how do I...?", "what is...?"
- Assistant suggestions (unless user confirms them)
- Temporary choices: "let's try this first", "for now"
- Vague statements without specific information

Each fact should be an object with:
- "subject": The entity (e.g., "User", "System", "Alice")
- "predicate": The relationship (e.g., "prefers", "uses", "leads")
- "object": The value (e.g., "dark_mode", "PostgreSQL", "backend_team")
- "confidence": 0.0-1.0 (how certain is this fact?)
  - 1.0: Explicitly stated by user
  - 0.7-0.9: Strongly implied
  - 0.5-0.6: Inferred, may need confirmation
  - Below 0.5: Don't extract, too uncertain

Respond ONLY with the JSON array, no additional text.
Return empty array [] if no facts worth extracting.

Example - HAS extractable facts:
Input: "I prefer using TypeScript for all my projects and our team uses PostgreSQL"
Output: [
  {"subject": "User", "predicate": "prefers", "object": "TypeScript", "confidence": 1.0},
  {"subject": "Team", "predicate": "uses", "object": "PostgreSQL", "confidence": 1.0}
]

Example - NO extractable facts:
Input: "hi, can you help me?"
Output: []

Input: "maybe we could try using Redis?"
Output: []""",
                        }
                    ]
                ),
                HumanMessage(content=[{"type": "text", "text": content}]),
            ]
            response = self.llm.invoke(messages)

            response_text = self._extract_text(response.content)

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
                    weight=f.get("confidence", 1.0),
                )
                for f in facts_json
                if isinstance(f, dict)
                and "subject" in f
                and "predicate" in f
                and "object" in f
                and f.get("confidence", 1.0) >= 0.5  # Filter low confidence
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
                    content=[
                        {
                            "type": "text",
                            "text": "Summarize the following conversation concisely, preserving key information.",
                        }
                    ]
                ),
                HumanMessage(content=[{"type": "text", "text": conversation_text}]),
            ]
            response = self.llm.invoke(lc_messages)

            return self._extract_text(response.content)
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
                    content=[
                        {
                            "type": "text",
                            "text": "Analyze these episodes and extract a general principle or pattern. Return JSON with {content, confidence}.",
                        }
                    ]
                ),
                HumanMessage(content=[{"type": "text", "text": episodes_text}]),
            ]
            response = self.llm.invoke(messages)

            result = json.loads(self._extract_text(response.content))
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
                    content=[
                        {
                            "type": "text",
                            "text": "Analyze these conversation snippets and generate ONE concise topic label (2-4 words). Respond with ONLY the topic label in snake_case, no explanation.",
                        }
                    ]
                ),
                HumanMessage(content=[{"type": "text", "text": samples_text}]),
            ]
            response = self.llm.invoke(messages)

            label = self._extract_text(response.content)
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
                SystemMessage(content=[{"type": "text", "text": system_prompt}]),
                HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": f"Topic: {topic}\nPrinciple: {principle.content}\nEvidence count: {principle.evidence_count}\nConfidence: {principle.confidence}",
                        }
                    ]
                ),
            ]
            response = self.llm.invoke(messages)

            result = json.loads(self._extract_text(response.content))

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
                SystemMessage(content=[{"type": "text", "text": system_prompt}]),
                HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": f"Memory IDs to check: {memory_ids}\n\nConversation:\n{content}",
                        }
                    ]
                ),
            ]
            response = self.llm.invoke(messages)
            response_text = self._extract_text(response.content)

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
        or failed outcome. Considers both explicit and implicit signals.

        Args:
            content: Message content to analyze

        Returns:
            Inferred outcome: "success", "failure", or "unknown"
        """
        try:
            system_prompt = """Analyze this message and determine the task outcome.
Return ONLY one word: "success", "failure", or "unknown"

EXPLICIT SUCCESS INDICATORS:
- Task completed, problem solved, goal achieved
- Positive confirmation: "it works", "that fixed it", "perfect"
- User satisfaction, successful execution
- User moves on to next task (implicit completion)

EXPLICIT FAILURE INDICATORS:
- Error occurred, task failed, problem unsolved
- Crashes, bugs, exceptions mentioned
- User frustration, unsuccessful attempts
- User asks for alternative approach (implicit failure)

IMPLICIT SUCCESS SIGNALS (analyze context):
- User continues building on the solution
- User thanks and moves to unrelated topic
- No complaints after trying the suggestion

IMPLICIT FAILURE SIGNALS (analyze context):
- User asks "why doesn't this work?"
- User tries a different approach
- User abandons the task

Return "unknown" if:
- The message is a question or request (not an outcome)
- The message is purely informational
- There's no clear indication of task completion or failure
- The message is a greeting or small talk"""

            messages = [
                SystemMessage(content=[{"type": "text", "text": system_prompt}]),
                HumanMessage(
                    content=[{"type": "text", "text": content[:2000]}]
                ),  # Limit content length
            ]
            response = self.llm.invoke(messages)
            result = self._extract_text(response.content).lower().strip()

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
                SystemMessage(content=[{"type": "text", "text": system_prompt}]),
                HumanMessage(content=[{"type": "text", "text": content[:2000]}]),
            ]
            response = self.llm.invoke(messages)
            response_text = self._extract_text(response.content)

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
                SystemMessage(content=[{"type": "text", "text": system_prompt}]),
                HumanMessage(content=[{"type": "text", "text": content[:3000]}]),
            ]
            response = self.llm.invoke(messages)
            response_text = self._extract_text(response.content)

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

    def filter_relevant_memories(
        self, query: str, memories: list[dict[str, str]], min_relevance: float = 0.5
    ) -> list[dict[str, Any]]:
        """Filter memories by relevance to query using LLM judgment.

        Uses LLM to determine if each candidate memory is truly relevant
        to the query, not just superficially similar. This prevents returning
        irrelevant memories when the memory store is small.

        Args:
            query: The user's query/question
            memories: List of candidate memories, each with "id" and "content" keys
            min_relevance: Minimum relevance score (0-1) to include memory

        Returns:
            List of relevant memories with relevance scores:
            [{"id": "...", "content": "...", "relevance": 0.8, "reason": "..."}]
        """
        if not memories:
            return []

        try:
            # Format memories for LLM
            memories_text = "\n".join(
                [f"[{m['id']}]: {m['content'][:200]}" for m in memories[:20]]
            )

            system_prompt = f"""Evaluate if each memory is TRULY relevant to answering the query.

QUERY: {query}

For each memory, determine:
1. Is this memory actually useful for answering the query? (not just superficially related)
2. Relevance score (0.0-1.0):
   - 1.0: Directly answers or is essential for the query
   - 0.7-0.9: Highly relevant, provides useful context
   - 0.5-0.6: Somewhat relevant, might be helpful
   - 0.3-0.4: Tangentially related, probably not useful
   - 0.0-0.2: Not relevant at all

IMPORTANT: Be strict! Only mark memories as relevant if they would genuinely help.
When in doubt, give a lower score. It's better to return nothing than irrelevant memories.

Return a JSON array with objects containing:
- id: memory ID
- relevance: score 0.0-1.0
- reason: brief explanation (10 words max)

Only include memories with relevance >= {min_relevance}.
Return empty array [] if no memories are truly relevant.

Example output:
[{{"id": "mem_123", "relevance": 0.85, "reason": "Directly addresses the question"}}]"""

            messages = [
                SystemMessage(content=[{"type": "text", "text": system_prompt}]),
                HumanMessage(content=[{"type": "text", "text": memories_text}]),
            ]
            response = self.llm.invoke(messages)
            response_text = self._extract_text(response.content)

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

            result = json.loads(response_text)

            if not isinstance(result, list):
                self.logger.warning(
                    "filter_relevant_invalid_format", response=response_text[:100]
                )
                return []

            # Validate and filter results
            valid_results = []
            memory_map = {m["id"]: m for m in memories}
            for item in result:
                if (
                    isinstance(item, dict)
                    and "id" in item
                    and "relevance" in item
                    and item["id"] in memory_map
                    and isinstance(item["relevance"], (int, float))
                    and item["relevance"] >= min_relevance
                ):
                    valid_results.append(
                        {
                            "id": item["id"],
                            "content": memory_map[item["id"]]["content"],
                            "relevance": float(item["relevance"]),
                            "reason": item.get("reason", ""),
                        }
                    )

            # Sort by relevance descending
            valid_results.sort(key=lambda x: x["relevance"], reverse=True)

            self.logger.debug(
                "filter_relevant_memories",
                query=query[:50],
                input_count=len(memories),
                output_count=len(valid_results),
            )

            return valid_results

        except json.JSONDecodeError as e:
            self.logger.warning("filter_relevant_json_error", error=str(e))
            return []
        except Exception as e:
            self.logger.warning("filter_relevant_failed", error=str(e))
            return []

    def assess_memory_importance(
        self, content: str, context: str = ""
    ) -> dict[str, Any]:
        """Assess whether content is worth remembering and its importance.

        Evaluates content to determine if it should be stored as a memory,
        distinguishing between permanent preferences, temporary choices,
        and transient information.

        Args:
            content: The content to assess
            context: Optional conversation context for better judgment

        Returns:
            Assessment dict with:
            - should_remember: bool (whether to store this memory)
            - importance: int 1-5 (1=trivial, 5=critical)
            - memory_type: "preference" | "fact" | "experience" | "temporary"
            - confidence: float 0-1 (confidence in assessment)
            - reason: str (explanation for the decision)
        """
        try:
            system_prompt = """Assess if this content should be stored as a long-term memory.

CONTENT TO ASSESS:
{content}

{context_section}

Evaluate based on these criteria:

SHOULD REMEMBER (high importance):
- User's explicit preferences: "I prefer...", "I always want...", "I like..."
- Technical decisions: "We use PostgreSQL", "Our API uses REST"
- Learned facts: "The rate limit is 100/min", "Alice is the team lead"
- Successful solutions: "Adding retry logic fixed the timeout"
- User corrections: "No, I meant X not Y"

SHOULD NOT REMEMBER (low importance):
- Greetings and small talk: "hi", "thanks", "ok"
- Test messages: "test", "asdf", "hello world"
- Temporary choices: "let's try this first", "for now use X"
- Questions without assertions: "how do I...?", "what is...?"
- Assistant suggestions not confirmed by user
- Repetitive or redundant information

MEMORY TYPES:
- preference: User's stated preferences or settings
- fact: Factual information about entities or systems
- experience: Task outcomes, solutions, lessons learned
- temporary: Transient information, likely to change

Return JSON:
{{
    "should_remember": true/false,
    "importance": 1-5,
    "memory_type": "preference"|"fact"|"experience"|"temporary",
    "confidence": 0.0-1.0,
    "reason": "brief explanation"
}}"""

            context_section = (
                f"CONTEXT:\n{context[:500]}" if context else "No additional context."
            )
            formatted_prompt = system_prompt.format(
                content=content[:1000], context_section=context_section
            )

            messages = [
                SystemMessage(content=[{"type": "text", "text": formatted_prompt}]),
                HumanMessage(
                    content=[{"type": "text", "text": "Assess this content."}]
                ),
            ]
            response = self.llm.invoke(messages)
            response_text = self._extract_text(response.content)

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

            result = json.loads(response_text)

            # Validate and normalize result
            return {
                "should_remember": bool(result.get("should_remember", False)),
                "importance": max(1, min(5, int(result.get("importance", 1)))),
                "memory_type": result.get("memory_type", "temporary"),
                "confidence": max(0.0, min(1.0, float(result.get("confidence", 0.5)))),
                "reason": str(result.get("reason", "")),
            }

        except json.JSONDecodeError as e:
            self.logger.warning("assess_importance_json_error", error=str(e))
            return {
                "should_remember": False,
                "importance": 1,
                "memory_type": "temporary",
                "confidence": 0.0,
                "reason": f"JSON parse error: {e}",
            }
        except Exception as e:
            self.logger.warning("assess_importance_failed", error=str(e))
            return {
                "should_remember": False,
                "importance": 1,
                "memory_type": "temporary",
                "confidence": 0.0,
                "reason": f"Assessment failed: {e}",
            }


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
