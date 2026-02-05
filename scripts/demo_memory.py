#!/usr/bin/env python3
"""Interactive Memory System Demo.

This script provides an interactive demo of the h-mem memory system.

Usage:
    uv run python scripts/demo_memory.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hmem.core.memory_system import MemorySystem
from hmem.models import Conversation, Message


def main():
    print("=" * 60)
    print(" H-MEM Interactive Demo")
    print("=" * 60)

    print("\nInitializing memory system...")
    memory = MemorySystem()

    print("\n[1] Storing test memories...")

    # Store some test memories
    test_data = [
        {
            "session_id": "demo_pref_1",
            "messages": [
                ("user", "I prefer using Vim keybindings in all my editors."),
                (
                    "assistant",
                    "Got it! I'll use Vim keybindings when configuring editors.",
                ),
            ],
        },
        {
            "session_id": "demo_tech_1",
            "messages": [
                (
                    "user",
                    "Our backend uses FastAPI with PostgreSQL and Redis for caching.",
                ),
                (
                    "assistant",
                    "Understood. FastAPI + PostgreSQL + Redis is your stack.",
                ),
            ],
        },
        {
            "session_id": "demo_exp_1",
            "messages": [
                ("user", "The connection pooling fix worked! No more timeout errors."),
                ("assistant", "Great! Connection pooling resolved the timeout issues."),
            ],
        },
    ]

    for data in test_data:
        conv = Conversation(
            session_id=data["session_id"],
            messages=[
                Message(role=role, content=content)
                for role, content in data["messages"]
            ],
        )
        memory.remember(conv)
        memory.consolidate(data["session_id"])
        print(f"  Stored: {data['session_id']}")

    print("\n[2] Testing recall with relevant queries...")

    test_queries = [
        "What editor keybindings does the user prefer?",
        "What database do we use?",
        "How did we fix the timeout errors?",
        "What's the capital of France?",  # Unrelated - should return empty
    ]

    for query in test_queries:
        print(f"\n  Query: {query}")
        results = list(memory.recall(query, limit=3))

        if results:
            for i, r in enumerate(results, 1):
                content_preview = r.content[:80].replace("\n", " ")
                print(f"    [{i}] (score={r.score:.2f}) {content_preview}...")
        else:
            print("    No relevant memories found.")

    print("\n[3] Memory system stats...")
    health = memory.health_check()
    print(f"  Episodic store: {health.get('episodic', 'N/A')}")
    print(f"  Semantic store: {health.get('semantic', 'N/A')}")
    print(f"  Skill store: {health.get('skill', 'N/A')}")

    print("\n[4] Shutting down...")
    memory.shutdown()

    print("\nDemo complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
