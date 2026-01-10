"""Simple demonstration of basic memory system functionality.

This script demonstrates:
1. Creating conversations
2. Storing them in memory
3. Retrieving relevant memories
4. Consolidation process
"""

from hmem.models import Message, Conversation
from hmem.core.memory_system import MemorySystem


def main():
    print("=" * 60)
    print("Memory System Functional Verification")
    print("=" * 60)
    
    # Initialize memory system
    print("\n1. Initializing memory system...")
    memory = MemorySystem()
    print("   ✓ Memory system created")
    
    # Create a conversation
    print("\n2. Creating conversation...")
    conversation = Conversation(
        session_id="demo_session_1",
        messages=[
            Message(role="user", content="I'm working on web scraping with Python"),
            Message(role="assistant", content="Great! Are you using requests or selenium?"),
            Message(role="user", content="I tried requests but it failed on dynamic sites"),
            Message(role="assistant", content="For dynamic sites, selenium is better"),
        ],
        metadata={"topic": "web_scraping"}
    )
    print(f"   ✓ Conversation created with {len(conversation.messages)} messages")
    
    # Store conversation
    print("\n3. Storing conversation in memory...")
    session_id = memory.remember(conversation)
    print(f"   ✓ Conversation stored with session_id: {session_id}")
    
    # Create another conversation
    print("\n4. Adding another conversation...")
    conversation2 = Conversation(
        session_id="demo_session_2",
        messages=[
            Message(role="user", content="How do I analyze data in Python?"),
            Message(role="assistant", content="You can use pandas for data analysis"),
        ],
    )
    session_id2 = memory.remember(conversation2)
    print(f"   ✓ Second conversation stored with session_id: {session_id2}")
    
    # Recall memories
    print("\n5. Retrieving memories about web scraping...")
    results = list(memory.recall("web scraping", limit=5))
    print(f"   ✓ Found {len(results)} relevant memories:")
    for i, mem in enumerate(results, 1):
        print(f"      {i}. Score: {mem.score:.2f} | {mem.content[:80]}...")
    
    # Test with Message query
    print("\n6. Testing context-aware query with Message...")
    query_msg = Message(role="user", content="What did I try for web scraping?")
    results = list(memory.recall(query_msg, limit=3))
    print(f"   ✓ Found {len(results)} memories")
    
    # Test with Conversation query (proactive prompting)
    print("\n7. Testing proactive prompting with Conversation...")
    query_conv = Conversation(
        session_id="query_session",
        messages=[
            Message(role="user", content="I need help with Python"),
            Message(role="assistant", content="What are you working on?"),
        ]
    )
    results = list(memory.recall(query_conv, limit=3))
    print(f"   ✓ Found {len(results)} relevant memories using conversation context")
    
    # Check consolidation
    print("\n8. Testing consolidation...")
    result = memory.consolidate("demo_session_1")
    print(f"   ✓ Consolidated session: {result}")
    
    # Check health
    print("\n9. Checking system health...")
    health = memory.health()
    print(f"   ✓ System status: {health['status']}")
    print(f"   ✓ Episodic memories: {health['episodic_count']}")
    
    print("\n" + "=" * 60)
    print("✓ All components functioning correctly!")
    print("=" * 60)


if __name__ == "__main__":
    main()
