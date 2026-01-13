# **System Acceptance Plan**

To verify whether this design achieves "cognitive intelligence" goals, execute the following standardized test cases.

## **Test Case A: Memory Persistence & Summarization Test (The "Goldfish" Test)**

* **Purpose:** Verify that the **Memory Folding** mechanism of the Perception Layer effectively prevents forgetting without exceeding Token limit.
* **Prerequisites:**
  * Empty Session context.
  * Token limit set to small value (e.g., 4k tokens).

| **Step** | **Operation Description** | **Expected Outcome** |
|---------|-------------|--------------------------------|
| 1 | User inputs name "Alice" and goal "learn Python". | Agent confirms receipt. |
| 2 | Conduct 50 rounds of irrelevant chat (Token padding). | System log shows MemorySystem triggered Folding Strategy; original conversation compressed into Summary. |
| 3 | User asks: "Who am I? What do I want to do?" | 1. Agent accurately answers "You are Alice, you want to learn Python". 2. Answer source marked as Summary Token. |

**Pytest implementation framework:**

```python
import pytest
from hmem import MemorySystem
from hmem.perception import SensoryBuffer
from hmem.perception.strategies import TokenBasedFolder

@pytest.fixture
def mock_llm(mocker):
    """Mock LLM responses"""
    llm = mocker.patch('hmem.agents.llm.LiteLLM')
    # Recorded real responses
    llm.summarize.return_value = "User is Alice, wants to learn Python"
    return llm

def test_goldfish_memory_folding(mock_llm):
    """Verify Memory Folding mechanism"""
    # Arrange
    memory = MemorySystem()
    folder = TokenBasedFolder(trigger_ratio=0.8)
    buffer = SensoryBuffer(max_size=1000)

    # Act: Add initial information
    memory.chat("My name is Alice")
    memory.chat("I want to learn Python")

    # Act: Fill 50 rounds of chat
    for i in range(50):
        memory.chat(f"Random chat {i}")

    # Assert: Check if folding triggered
    assert folder.was_triggered, "Should trigger folding"
    # Verify critical information preserved
    assert "Python" in ctx.summary

    # Act: Query early information
    results = memory.retrieve("Who am I and what do I want?")

    # Assert: Verify recall
    assert len(results) > 0
    assert any("Alice" in m.content for m in results), "Should recall name"
    assert any("Python" in m.content for m in results), "Should recall goal"
```

---

## **Test Case B: Experience Reuse Test (The "Don't Repeat Mistakes" Test)**

* **Purpose:** Verify that **Episodic Store** enables Agent to avoid repeating specific mistakes.
* **Prerequisites:**
  * Episodic DB is empty.

| **Step** | **Operation Description** | **Expected Outcome** |
|---------|-------------|--------------------------------|
| 1 | **Session 1:** User requests web scraper. Agent uses outdated method A (fails), corrects to method B (succeeds). | Conversation ends. |
| 2 | Wait for background consolidation to complete. | New record added to Episodic DB, with failure tag for method A and success tag for method B. |
| 3 | **Session 2:** User requests scraper for another website. | 1. Retrieval Engine recalls Session 1 record. 2. Agent **directly** uses method B, succeeds without trial-and-error. |

**Pytest implementation framework:**

```python
def test_dont_repeat_mistakes():
    """Verify Agent doesn't repeat mistakes"""
    memory = MemorySystem()

    # Session 1: Record failure experience
    session1_events = [
        Event(
            content="Tried requests.get() on dynamic site - failed",
            outcome="failure",
            tags=["web_scraping", "method_A"]
        ),
        Event(
            content="Switched to selenium - success",
            outcome="success",
            tags=["web_scraping", "method_B"]
        )
    ]

    memory.ingest(session_id="s1", events=session1_events)
    result = memory.consolidate(session_id="s1")  # Synchronous consolidation

    assert result.success
    assert result.stored_events == 2

    # Session 2: Retrieval should recall historical experience
    retrieved = memory.retrieve(
        query="How to scrape a website?",
        limit=5
    )

    # Verify recall of successful method
    assert len(retrieved) > 0
    assert any("selenium" in m.content.lower() for m in retrieved), \
        "Should recall successful method B (selenium)"

    # Verify successful method ranks higher
    success_score = next(m.score for m in retrieved if "selenium" in m.content.lower())
    failure_score = next((m.score for m in retrieved if "requests.get" in m.content.lower()), 0)
    assert success_score > failure_score, "Success should rank higher than failure"
```

---

## **Test Case C: Knowledge Update Test (The "Change of Mind" Test)**

* **Purpose:** Verify **Semantic Store**'s conflict resolution and update mechanism.
* **Prerequisites:**
  * Semantic DB contains (User)-[EATS]->(Vegetarian).

| **Step** | **Operation Description** | **Expected Outcome** |
|---------|-------------|--------------------------------|
| 1 | User informs: "Doctor recommended I eat fish for protein." | Agent confirms preference change. |
| 2 | Wait for background consolidation. | 1. Graph DB: (User)-[EATS]->(Vegetarian) weight lowered or end timestamp added. 2. New: (User)-[EATS]->(Pescatarian) relationship added. |
| 3 | User asks: "What should I eat tonight?" | Agent recommends fish-containing recipes, without vegetarian restriction in System Prompt. |

**Pytest implementation framework:**

```python
def test_change_of_mind():
    """Verify semantic conflict resolution"""
    memory = MemorySystem()
    semantic_store = memory.storage.semantic

    # Initialize: User is vegetarian
    semantic_store.add_fact(
        subject="User",
        predicate="EATS",
        object="Vegetarian",
        weight=1.0
    )

    # User changes mind: Doctor recommends fish
    new_event = Event(
        content="Doctor recommends fish for protein",
        outcome="success",
        tags=["diet_change"]
    )
    memory.remember(new_event)
    memory.consolidate()

    # Verify new relationship added
    pescatarian_fact = semantic_store.query(
        subject="User",
        predicate="EATS",
        object="Pescatarian"
    )
    assert pescatarian_fact is not None, "Should add new Pescatarian fact"

    # Verify old relationship downweighted (or marked expired)
    vegetarian_fact = semantic_store.query(
        subject="User",
        predicate="EATS",
        object="Vegetarian"
    )
    # Weight should decrease or have end timestamp
    assert vegetarian_fact.weight < 1.0 or vegetarian_fact.end_time is not None, \
        "Old vegetarian fact should be deprecated"
```

---

## **Test Case D: Philosophy Induction Test (The "Sherlock" Test)**

* **Purpose:** Verify **Reflector**'s cross-task induction capability (from experience to wisdom).
* **Prerequisites:**
  * 3 historical data analysis tasks, all failed due to skipping data cleaning.

| **Step** | **Operation Description** | **Expected Outcome** |
|---------|-------------|--------------------------------|
| 1 | Manually trigger `reflect_and_induce("Data Analysis")`. | Reflector generates principle: *"Data analysis tasks must start with data cleaning."* and writes to Semantic DB. |
| 2 | **Session N:** Start new data prediction task (user didn't mention cleaning). | 1. Retrieval Engine recalls above principle. 2. Agent **proactively** lists "data cleaning" step in Plan phase. |

**Pytest implementation framework:**

```python
def test_induction_sherlock():
    """Verify cross-task induction capability"""
    memory = MemorySystem()
    reflector = memory.reflector

    # Prepare: 3 data analysis tasks, all fail due to missing data cleaning
    for i in range(3):
        event = Event(
            content=f"Tried to analyze dataset {i} without cleaning - failed with data quality issues",
            outcome="failure",
            tags=["data_analysis", "cleaning_missing"]
        )
        memory.remember(event, session_id=f"session_{i}")
        memory.consolidate(session_id=f"session_{i}")

    # Manually trigger reflection induction
    principles = reflector.induce_principles(topic="Data Analysis", min_episodes=3)

    # Verify principles generated
    assert len(principles) > 0, "Should generate principles"

    # Verify principle content includes "data cleaning" or similar keywords
    principle_texts = [p.content for p in principles]
    assert any("clean" in p.lower() for p in principle_texts), \
        "Should induct principle about data cleaning"

    # Verify principle stored in Semantic Store
    retrieved = memory.recall("How should I start a data analysis?")
    assert any("clean" in m.content.lower() for m in retrieved), \
        "Should recall cleaning principle when asked about data analysis"
```

---

**Related Documents:**
- [System Design Philosophy](design.md) - Design philosophy and core concepts
- [Interface Definitions](interfaces.md) - Data models and API definitions
- [Core Workflows](workflows.md) - How the system works
