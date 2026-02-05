#!/usr/bin/env python3
"""Memory System Quality Evaluation Script.

This script evaluates the h-mem memory system quality by testing:
1. Memory filtering - Does it correctly filter out irrelevant content?
2. Retrieval precision - Does it return relevant memories for queries?
3. Outcome inference - Does it correctly infer success/failure?
4. Tag extraction - Does it extract meaningful tags?

Usage:
    uv run python scripts/evaluate_memory.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hmem.core.memory_system import MemorySystem
from hmem.models import Conversation, Message
from hmem.agents.llm import LLMClient


def create_test_conversations() -> list[dict]:
    """Create test conversations for evaluation."""
    return [
        # Test 1: Should remember - clear user preference
        {
            "id": "eval_preference",
            "description": "User states clear preference",
            "messages": [
                {"role": "user", "content": "I always prefer using TypeScript over JavaScript for my projects."},
                {"role": "assistant", "content": "Got it! I'll use TypeScript for your projects."},
            ],
            "expected": {
                "should_remember": True,
                "memory_type": "preference",
                "tags_should_contain": ["typescript"],
            },
        },
        # Test 2: Should NOT remember - greeting
        {
            "id": "eval_greeting",
            "description": "Simple greeting - should not remember",
            "messages": [
                {"role": "user", "content": "Hi there!"},
                {"role": "assistant", "content": "Hello! How can I help you today?"},
            ],
            "expected": {
                "should_remember": False,
            },
        },
        # Test 3: Should remember - technical decision
        {
            "id": "eval_technical",
            "description": "Technical decision",
            "messages": [
                {"role": "user", "content": "Our team uses PostgreSQL for the database and Redis for caching."},
                {"role": "assistant", "content": "Understood. I'll keep that in mind for database-related tasks."},
            ],
            "expected": {
                "should_remember": True,
                "memory_type": "fact",
                "tags_should_contain": ["database", "postgresql"],
            },
        },
        # Test 4: Should NOT remember - test message
        {
            "id": "eval_test",
            "description": "Test message - should not remember",
            "messages": [
                {"role": "user", "content": "test"},
                {"role": "assistant", "content": "I see you're testing. How can I help?"},
            ],
            "expected": {
                "should_remember": False,
            },
        },
        # Test 5: Success outcome
        {
            "id": "eval_success",
            "description": "Successful task completion",
            "messages": [
                {"role": "user", "content": "Can you help me fix the login bug?"},
                {"role": "assistant", "content": "I've added the null check. Try it now."},
                {"role": "user", "content": "Perfect! That fixed it. The login works now."},
            ],
            "expected": {
                "should_remember": True,
                "outcome": "success",
                "memory_type": "experience",
            },
        },
        # Test 6: Failure outcome
        {
            "id": "eval_failure",
            "description": "Failed task",
            "messages": [
                {"role": "user", "content": "The API keeps returning 500 errors after your change."},
                {"role": "assistant", "content": "Let me check what went wrong."},
                {"role": "user", "content": "It's still broken. Let's try a different approach."},
            ],
            "expected": {
                "should_remember": True,
                "outcome": "failure",
            },
        },
        # Test 7: Should NOT remember - temporary choice
        {
            "id": "eval_temporary",
            "description": "Temporary choice - should not remember as permanent",
            "messages": [
                {"role": "user", "content": "Let's try using Flask for now, just to test this quickly."},
                {"role": "assistant", "content": "Sure, I'll set up a quick Flask server."},
            ],
            "expected": {
                "should_remember": False,  # "for now" indicates temporary
            },
        },
        # Test 8: User correction - should remember
        {
            "id": "eval_correction",
            "description": "User correction",
            "messages": [
                {"role": "user", "content": "No, I meant Python 3.11, not 3.10. We always use 3.11."},
                {"role": "assistant", "content": "Got it, I'll use Python 3.11."},
            ],
            "expected": {
                "should_remember": True,
                "memory_type": "preference",
            },
        },
    ]


def evaluate_memory_importance(llm: LLMClient, test_cases: list[dict]) -> dict:
    """Evaluate memory importance assessment."""
    results = {
        "total": len(test_cases),
        "correct": 0,
        "details": [],
    }

    for test in test_cases:
        content = "\n".join([f"{m['role']}: {m['content']}" for m in test["messages"]])
        assessment = llm.assess_memory_importance(content)

        expected_remember = test["expected"].get("should_remember", True)
        actual_remember = assessment["should_remember"]

        is_correct = expected_remember == actual_remember

        if is_correct:
            results["correct"] += 1

        results["details"].append({
            "id": test["id"],
            "description": test["description"],
            "expected_remember": expected_remember,
            "actual_remember": actual_remember,
            "importance": assessment["importance"],
            "memory_type": assessment["memory_type"],
            "confidence": assessment["confidence"],
            "reason": assessment["reason"],
            "correct": is_correct,
        })

    results["accuracy"] = results["correct"] / results["total"] if results["total"] > 0 else 0
    return results


def evaluate_outcome_inference(llm: LLMClient, test_cases: list[dict]) -> dict:
    """Evaluate outcome inference."""
    outcome_tests = [t for t in test_cases if "outcome" in t["expected"]]
    results = {
        "total": len(outcome_tests),
        "correct": 0,
        "details": [],
    }

    for test in outcome_tests:
        # Use the last user message for outcome inference
        last_user_msg = [m for m in test["messages"] if m["role"] == "user"][-1]
        outcome = llm.infer_outcome(last_user_msg["content"])

        expected_outcome = test["expected"]["outcome"]
        is_correct = outcome == expected_outcome

        if is_correct:
            results["correct"] += 1

        results["details"].append({
            "id": test["id"],
            "description": test["description"],
            "content": last_user_msg["content"][:100],
            "expected_outcome": expected_outcome,
            "actual_outcome": outcome,
            "correct": is_correct,
        })

    results["accuracy"] = results["correct"] / results["total"] if results["total"] > 0 else 0
    return results


def evaluate_tag_extraction(llm: LLMClient, test_cases: list[dict]) -> dict:
    """Evaluate tag extraction."""
    tag_tests = [t for t in test_cases if "tags_should_contain" in t["expected"]]
    results = {
        "total": len(tag_tests),
        "correct": 0,
        "details": [],
    }

    for test in tag_tests:
        content = "\n".join([m["content"] for m in test["messages"]])
        tags = llm.extract_tags(content)

        expected_tags = set(test["expected"]["tags_should_contain"])
        actual_tags = set(tags)

        # Check if expected tags are present (partial match is OK)
        found_tags = expected_tags & actual_tags
        is_correct = len(found_tags) > 0

        if is_correct:
            results["correct"] += 1

        results["details"].append({
            "id": test["id"],
            "description": test["description"],
            "expected_tags": list(expected_tags),
            "actual_tags": list(actual_tags),
            "found_tags": list(found_tags),
            "correct": is_correct,
        })

    results["accuracy"] = results["correct"] / results["total"] if results["total"] > 0 else 0
    return results


def evaluate_retrieval_precision(memory: MemorySystem) -> dict:
    """Evaluate retrieval precision with stored memories."""
    # First, store some test memories
    test_memories = [
        {
            "session_id": "eval_store_1",
            "messages": [
                {"role": "user", "content": "I prefer dark mode for all my IDEs and editors."},
                {"role": "assistant", "content": "Noted! I'll use dark mode settings."},
            ],
        },
        {
            "session_id": "eval_store_2",
            "messages": [
                {"role": "user", "content": "We use pytest for all our Python testing."},
                {"role": "assistant", "content": "Got it, I'll use pytest for tests."},
            ],
        },
        {
            "session_id": "eval_store_3",
            "messages": [
                {"role": "user", "content": "The web scraping with Selenium worked perfectly."},
                {"role": "assistant", "content": "Great! Selenium is reliable for dynamic sites."},
            ],
        },
    ]

    # Store memories
    for mem in test_memories:
        conv = Conversation(
            session_id=mem["session_id"],
            messages=[
                Message(role=m["role"], content=m["content"])
                for m in mem["messages"]
            ],
        )
        memory.remember(conv)
        memory.consolidate(mem["session_id"])

    # Test queries
    test_queries = [
        {
            "query": "What IDE theme does the user prefer?",
            "should_find": "dark mode",
            "should_not_find": "pytest",
        },
        {
            "query": "What testing framework do we use?",
            "should_find": "pytest",
            "should_not_find": "Selenium",
        },
        {
            "query": "How do we scrape websites?",
            "should_find": "Selenium",
            "should_not_find": "dark mode",
        },
        {
            "query": "What's the weather like?",  # Unrelated query
            "should_find": None,  # Should return empty or low relevance
        },
    ]

    results = {
        "total": len(test_queries),
        "correct": 0,
        "details": [],
    }

    for test in test_queries:
        memories = list(memory.recall(test["query"], limit=5))

        # Check results
        memory_contents = " ".join([m.content.lower() for m in memories])

        if test["should_find"]:
            found_expected = test["should_find"].lower() in memory_contents
            if "should_not_find" in test:
                not_found_unexpected = test["should_not_find"].lower() not in memory_contents
                is_correct = found_expected and not_found_unexpected
            else:
                is_correct = found_expected
        else:
            # For unrelated queries, we expect few or no results
            is_correct = len(memories) == 0 or all(m.score < 0.5 for m in memories)

        if is_correct:
            results["correct"] += 1

        results["details"].append({
            "query": test["query"],
            "should_find": test["should_find"],
            "memories_found": len(memories),
            "top_scores": [m.score for m in memories[:3]],
            "correct": is_correct,
        })

    results["accuracy"] = results["correct"] / results["total"] if results["total"] > 0 else 0
    return results


def print_results(title: str, results: dict):
    """Print evaluation results."""
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}")
    print(f"Accuracy: {results['accuracy']:.1%} ({results['correct']}/{results['total']})")
    print("-" * 60)

    for detail in results["details"]:
        status = "✓" if detail["correct"] else "✗"
        print(f"{status} {detail.get('id', detail.get('query', 'N/A'))}")
        if not detail["correct"]:
            # Print more details for failures
            for key, value in detail.items():
                if key not in ["id", "correct", "description", "query"]:
                    print(f"    {key}: {value}")


def main():
    """Run memory system evaluation."""
    print("=" * 60)
    print(" H-MEM Memory System Quality Evaluation")
    print("=" * 60)
    print(f"Time: {datetime.now().isoformat()}")

    # Initialize components
    print("\nInitializing LLM client...")
    llm = LLMClient()

    print("Creating test cases...")
    test_cases = create_test_conversations()

    # Run evaluations
    print("\n" + "=" * 60)
    print(" Running Evaluations...")
    print("=" * 60)

    # 1. Memory Importance Assessment
    print("\n[1/4] Evaluating memory importance assessment...")
    importance_results = evaluate_memory_importance(llm, test_cases)
    print_results("Memory Importance Assessment", importance_results)

    # 2. Outcome Inference
    print("\n[2/4] Evaluating outcome inference...")
    outcome_results = evaluate_outcome_inference(llm, test_cases)
    print_results("Outcome Inference", outcome_results)

    # 3. Tag Extraction
    print("\n[3/4] Evaluating tag extraction...")
    tag_results = evaluate_tag_extraction(llm, test_cases)
    print_results("Tag Extraction", tag_results)

    # 4. Retrieval Precision (requires full memory system)
    print("\n[4/4] Evaluating retrieval precision...")
    try:
        memory = MemorySystem()
        retrieval_results = evaluate_retrieval_precision(memory)
        print_results("Retrieval Precision", retrieval_results)
        memory.shutdown()
    except Exception as e:
        print(f"  Skipped (error: {e})")
        retrieval_results = {"accuracy": 0, "total": 0, "correct": 0, "details": []}

    # Summary
    print("\n" + "=" * 60)
    print(" SUMMARY")
    print("=" * 60)
    total_tests = (
        importance_results["total"]
        + outcome_results["total"]
        + tag_results["total"]
        + retrieval_results["total"]
    )
    total_correct = (
        importance_results["correct"]
        + outcome_results["correct"]
        + tag_results["correct"]
        + retrieval_results["correct"]
    )
    overall_accuracy = total_correct / total_tests if total_tests > 0 else 0

    print(f"Memory Importance: {importance_results['accuracy']:.1%}")
    print(f"Outcome Inference: {outcome_results['accuracy']:.1%}")
    print(f"Tag Extraction:    {tag_results['accuracy']:.1%}")
    print(f"Retrieval:         {retrieval_results['accuracy']:.1%}")
    print("-" * 60)
    print(f"Overall Accuracy:  {overall_accuracy:.1%} ({total_correct}/{total_tests})")

    # Return exit code based on accuracy
    if overall_accuracy >= 0.7:
        print("\n✓ Memory system quality is GOOD")
        return 0
    elif overall_accuracy >= 0.5:
        print("\n⚠ Memory system quality is ACCEPTABLE")
        return 0
    else:
        print("\n✗ Memory system quality needs improvement")
        return 1


if __name__ == "__main__":
    sys.exit(main())
