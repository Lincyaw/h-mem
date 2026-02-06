"""Prompt templates for the ReAct Agent Loop.

These templates structure the agent's reasoning and actions
in the ReAct format: Thought → Action → Observation.
"""

# Main system prompt for ReAct agents
REACT_SYSTEM_PROMPT = """\
You are a ReAct (Reasoning + Acting) agent. You solve tasks by alternating between:
1. **Thought**: Analyze the current situation and plan your next step
2. **Action**: Execute one or more tools to gather information or make changes
3. **Observation**: Process the results and update your understanding

## Your Task
{objective}

## Available Tools
{tool_descriptions}

## Response Format
You MUST respond with valid JSON in this exact format:
```json
{{
  "thought": {{
    "reasoning": "Your analysis of the current situation",
    "plan": "What you will do next and why",
    "confidence": 0.0-1.0
  }},
  "actions": [
    {{
      "tool_name": "tool_name",
      "arguments": {{"arg1": "value1"}}
    }}
  ],
  "is_complete": false,
  "final_answer": null
}}
```

When you have completed the task, set `is_complete` to `true` and provide `final_answer`.

## Rules
1. Always think before acting
2. You may call multiple tools in parallel when they are independent
3. If a tool fails, analyze the error and try a different approach
4. If you're stuck, explicitly reason about alternative approaches
5. Never guess or make up data - use tools to verify
6. When complete, summarize what you accomplished

## Context
{context}

{skill_section}

Begin!"""

# Prompt section for loaded skills
SKILL_SECTION_TEMPLATE = """\
## Active Skills
The following skills have been loaded and provide guidance for this task:

{skill_contents}

Follow the guidance in these skills when applicable."""

# Prompt for format error recovery
FORMAT_ERROR_RECOVERY_PROMPT = """\
Your previous response could not be parsed as valid JSON.

Error: {error_message}

Please respond with VALID JSON in this exact format:
```json
{{
  "thought": {{
    "reasoning": "Your analysis",
    "plan": "Your plan",
    "confidence": 0.5
  }},
  "actions": [
    {{"tool_name": "name", "arguments": {{}}}}
  ],
  "is_complete": false,
  "final_answer": null
}}
```

Previous raw output (for reference):
{raw_output}"""

# Task-specific objective templates
EXTRACTION_OBJECTIVE = """\
Extract structured knowledge from the following conversation.

WORKFLOW:
1. FIRST: Use skill_search to find "knowledge-extraction", then skill_load to get guidance
2. Follow the skill's guidance for what to extract and filtering rules
3. Optionally: Use entity_lookup to check for duplicates
4. FINAL: Set is_complete=true with your extraction as final_answer

Conversation to analyze:
{conversation_text}

OUTPUT CONTRACT - Your final_answer MUST be a JSON object with this structure:
{{
    "entities": [
        {{"name": "EntityName", "type": "PERSON|PROJECT|TOOL|ORGANIZATION|CONCEPT", "is_reference": false}}
    ],
    "attributes": [
        {{
            "entity_name": "EntityName",
            "slot": "property.name",
            "value": "property value",
            "cardinality": "single|multi",
            "scope": "universal|project|task",
            "scope_context": null,
            "confidence": 0.9
        }}
    ],
    "processes": [
        {{
            "trigger": "When X happens",
            "action": "Do Y",
            "outcome": "Result Z",
            "is_generalizable": true,
            "confidence": 0.8
        }}
    ],
    "summary": "Brief description of what was extracted"
}}

If no meaningful knowledge found, return empty arrays - that's valid!"""

INDUCTION_OBJECTIVE = """\
Induce reusable skills from accumulated processes.

WORKFLOW:
1. FIRST: Use skill_search to find "learning-from-experience", then skill_load for guidance
2. Search for similar processes with common trigger patterns (use process_similarity)
3. Identify clusters of 2+ processes that follow the same pattern
4. Create skills that generalize these patterns
5. FINAL: Set is_complete=true with induced skills as final_answer

OUTPUT CONTRACT - Your final_answer MUST be a JSON object with this structure:
{{
    "skills": [
        {{
            "name": "skill-name",
            "description": "What this skill does",
            "trigger_pattern": "When to use this skill",
            "content": "Full skill content in markdown",
            "source_process_ids": ["proc-123", "proc-456"]
        }}
    ],
    "summary": "Brief description of induction results"
}}

ITERATION LIMIT: Complete within 8 iterations.
Only create skills for truly reusable patterns with 2+ supporting processes."""

RETRIEVAL_OBJECTIVE = """\
Find relevant memories to answer the following query.

Query: {query}
Context: {context}

WORKFLOW:
1. Use vector_search for semantically similar memories
2. Use fulltext_search for keyword matches
3. Combine and rank results by relevance
4. FINAL: Set is_complete=true with ranked results as final_answer

OUTPUT CONTRACT - Your final_answer MUST be a JSON object with this structure:
{{
    "results": [
        {{
            "memory_id": "mem-123",
            "content": "Memory content",
            "relevance_score": 0.9,
            "explanation": "Why this is relevant"
        }}
    ],
    "summary": "Brief description of retrieval results"
}}

ITERATION LIMIT: Complete within 5 iterations."""

# Continuation prompt after observations
CONTINUATION_PROMPT = """\
## Observations from Previous Actions
{observations}

**Iterations remaining: {remaining}/{max_iterations}**{urgency_warning}

Based on these results, continue your reasoning and decide on next steps.
Remember to respond with valid JSON."""

# Urgency warning when iterations are running low
URGENCY_WARNING_LOW = """
⚠️ RUNNING LOW ON ITERATIONS - Consider completing soon with is_complete=true and final_answer."""

URGENCY_WARNING_CRITICAL = """
🚨 CRITICAL: Only {remaining} iteration(s) left! You MUST set is_complete=true and provide final_answer NOW or your work will be lost."""

# Final summary prompt
FINAL_SUMMARY_PROMPT = """\
Summarize the results of your task execution.

Task: {objective}
Steps taken: {step_count}
Final status: {status}

Provide a concise summary of:
1. What was accomplished
2. Key findings or results
3. Any issues encountered"""


def format_observations(observations: list[dict]) -> str:
    """Format observations for inclusion in prompts.

    Args:
        observations: List of observation dicts

    Returns:
        Formatted string for prompt inclusion
    """
    lines = []
    for obs in observations:
        status = "✓" if obs.get("success") else "✗"
        tool = obs.get("tool_name", "unknown")
        if obs.get("success"):
            result = obs.get("result", "")
            # Truncate long results
            if isinstance(result, str) and len(result) > 500:
                result = result[:500] + "... (truncated)"
            lines.append(f"{status} {tool}: {result}")
        else:
            error = obs.get("error", "Unknown error")
            lines.append(f"{status} {tool}: ERROR - {error}")
    return "\n".join(lines)


def format_skill_section(skill_contents: dict[str, str]) -> str:
    """Format loaded skills for prompt inclusion.

    Args:
        skill_contents: Mapping of skill name to content

    Returns:
        Formatted skill section, or empty string if no skills
    """
    if not skill_contents:
        return ""

    skill_blocks = []
    for name, content in skill_contents.items():
        skill_blocks.append(f"### {name}\n{content}")

    contents = "\n\n".join(skill_blocks)
    return SKILL_SECTION_TEMPLATE.format(skill_contents=contents)


def build_system_prompt(
    objective: str,
    tool_descriptions: str,
    context: dict | None = None,
    skill_contents: dict[str, str] | None = None,
) -> str:
    """Build the complete system prompt for a ReAct agent.

    Args:
        objective: What the agent should accomplish
        tool_descriptions: Formatted tool documentation
        context: Additional context dict
        skill_contents: Loaded skill content by name

    Returns:
        Complete system prompt
    """
    context_str = ""
    if context:
        context_parts = [f"- {k}: {v}" for k, v in context.items()]
        context_str = "\n".join(context_parts)

    skill_section = format_skill_section(skill_contents or {})

    return REACT_SYSTEM_PROMPT.format(
        objective=objective,
        tool_descriptions=tool_descriptions,
        context=context_str or "No additional context provided.",
        skill_section=skill_section,
    )
