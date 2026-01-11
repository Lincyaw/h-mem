# **系统验收方案 (System Acceptance Plan)**

为了验证本设计是否达成"认知智能"目标，需执行以下标准化测试用例。

## **用例 A: 记忆持久性与摘要测试 (The "Goldfish" Test)**

* **目的:** 验证感知层的 **Memory Folding** 机制是否有效防止遗忘且不爆 Token。  
* **前置条件:**  
  * 空的 Session 上下文。  
  * Token 限制设置为较小值（如 4k tokens）。

| **步骤** | **操作描述** | **预期结果 (Expected Outcome)** |
|---------|-------------|--------------------------------|
| 1 | 用户输入姓名 "Alice" 和目标 "学习 Python"。 | Agent 确认收到。 |
| 2 | 进行 50 轮无关的闲聊（填充 Token）。 | 系统日志显示 Context Manager 触发 fold() 操作；原始对话被压缩为 Summary。 |
| 3 | 用户询问："我是谁？我要做什么？" | 1\. Agent 准确回答 "你是 Alice，你要学 Python"。 2\. 答案来源标记为 Summary Token。 |

**pytest 实现框架:**

```python
import pytest
from h_mem import MemorySystem, ContextManager

@pytest.fixture
def mock_llm(mocker):
    """Mock LLM 响应"""
    llm = mocker.patch('h_mem.llm.LiteLLM')
    # 录制的真实响应
    llm.summarize.return_value = "User is Alice, wants to learn Python"
    return llm

def test_goldfish_memory_folding(mock_llm):
    """验证 Memory Folding 机制"""
    # Arrange
    memory = MemorySystem()
    ctx = ContextManager(token_limit=4000)
    
    # Act: 添加初始信息
    ctx.add_message(user="My name is Alice")
    ctx.add_message(assistant="Nice to meet you, Alice")
    ctx.add_message(user="I want to learn Python")
    
    # Act: 填充 50 轮闲聊
    for i in range(50):
        ctx.add_message(user=f"Random chat {i}")
        ctx.add_message(assistant=f"Response {i}")
    
    # Assert: 检查是否触发折叠
    assert ctx.was_folded, "Should trigger folding"
    assert "Alice" in ctx.summary, "Summary should contain key info"
    assert "Python" in ctx.summary
    
    # Act: 查询早期信息
    results = memory.retrieve("Who am I and what do I want?")
    
    # Assert: 验证召回
    assert len(results) > 0
    assert any("Alice" in m.content for m in results), "Should recall name"
    assert any("Python" in m.content for m in results), "Should recall goal"
```

---

## **用例 B: 经验复用测试 (The "Don't Repeat Mistakes" Test)**

* **目的:** 验证 **Episodic Store** 能够让 Agent 避免重犯具体错误。  
* **前置条件:**  
  * Episodic DB 为空。

| **步骤** | **操作描述** | **预期结果 (Expected Outcome)** |
|---------|-------------|--------------------------------|
| 1 | **Session 1:** 用户要求写爬虫。Agent 使用过时方法 A 报错，修正为方法 B 后成功。 | 对话结束。 |
| 2 | 等待后台巩固流程完成。 | Episodic DB 中新增一条记录，包含方法 A 的失败标签和方法 B 的成功标签。 |
| 3 | **Session 2:** 用户要求写另一个网站的爬虫。 | 1\. Retrieval Engine 召回 Session 1 的记录。 2\. Agent **直接**使用方法 B，零试错成功。 |

**pytest 实现框架:**

```python
def test_dont_repeat_mistakes():
    """验证 Agent 不会重犯错误"""
    memory = MemorySystem()
    
    # Session 1: 记录失败经验
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
    result = memory.consolidate(session_id="s1")  # 同步巩固
    
    assert result.success
    assert result.stored_events == 2
    
    # Session 2: 检索应召回历史经验
    retrieved = memory.retrieve(
        query="How to scrape a website?",
        limit=5
    )
    
    # 验证召回了成功方法
    assert len(retrieved) > 0
    assert any("selenium" in m.content.lower() for m in retrieved), \
        "Should recall successful method B (selenium)"

    # 验证成功方法排名更高
    success_score = next(m.score for m in retrieved if "selenium" in m.content.lower())
    failure_score = next((m.score for m in retrieved if "requests.get" in m.content.lower()), 0)
    assert success_score > failure_score, "Success should rank higher than failure"
```

---

## **用例 C: 知识更新测试 (The "Change of Mind" Test)**

* **目的:** 验证 **Semantic Store** 的冲突解决与更新机制。  
* **前置条件:**  
  * Semantic DB 中已存在 (User)-[EATS]->(Vegetarian)。

| **步骤** | **操作描述** | **预期结果 (Expected Outcome)** |
|---------|-------------|--------------------------------|
| 1 | 用户告知："医生建议我开始吃鱼肉补充蛋白质。" | Agent 确认偏好变更。 |
| 2 | 等待后台巩固流程完成。 | 1\. Graph DB 中 (User)-[EATS]->(Vegetarian) 权重降低或增加结束时间戳。 2\. 新增 (User)-[EATS]->(Pescatarian) 关系。 |
| 3 | 用户询问："今晚吃什么？" | Agent 推荐包含鱼肉的菜谱，且不在 System Prompt 中包含纯素食限制。 |

**pytest 实现框架:**

```python
def test_change_of_mind():
    """验证语义冲突解决"""
    memory = MemorySystem()
    semantic_store = memory.storage.semantic
    
    # 初始化：用户是素食者
    semantic_store.add_fact(
        subject="User",
        predicate="EATS",
        object="Vegetarian",
        weight=1.0
    )
    
    # 用户改变想法：医生建议吃鱼肉
    new_event = Event(
        content="Doctor recommends fish for protein",
        outcome="success",
        tags=["diet_change"]
    )
    memory.remember(new_event)
    memory.consolidate()
    
    # 验证新关系被添加
    pescatarian_fact = semantic_store.query(
        subject="User",
        predicate="EATS",
        object="Pescatarian"
    )
    assert pescatarian_fact is not None, "Should add new Pescatarian fact"
    
    # 验证旧关系被降权 (或标记为过期)
    vegetarian_fact = semantic_store.query(
        subject="User",
        predicate="EATS",
        object="Vegetarian"
    )
    # 权重应该降低或有结束时间戳
    assert vegetarian_fact.weight < 1.0 or vegetarian_fact.end_time is not None, \
        "Old vegetarian fact should be deprecated"
```

---

## **用例 D: 哲学归纳测试 (The "Sherlock" Test)**

* **目的:** 验证 **Reflector** 的跨任务归纳能力（从经验到智慧）。  
* **前置条件:**  
  * 历史记录中有 3 次数据分析任务，均因未清洗数据导致初期失败。

| **步骤** | **操作描述** | **预期结果 (Expected Outcome)** |
|---------|-------------|--------------------------------|
| 1 | 手动触发 `reflect_and_induce("Data Analysis")`。 | Reflector 生成原则：*"Data analysis tasks must start with data cleaning."* 并写入 Semantic DB。 |
| 2 | **Session N:** 开启一个新的数据预测任务（用户未提清洗）。 | 1\. Retrieval Engine 召回上述原则。 2\. Agent 在 Plan 阶段**主动**列出"数据清洗"步骤。 |

**pytest 实现框架:**

```python
def test_induction_sherlock():
    """验证跨任务归纳能力"""
    memory = MemorySystem()
    reflector = memory.reflector
    
    # 准备：3 次数据分析任务，都因未清洗数据失败
    for i in range(3):
        event = Event(
            content=f"Tried to analyze dataset {i} without cleaning - failed with data quality issues",
            outcome="failure",
            tags=["data_analysis", "cleaning_missing"]
        )
        memory.remember(event, session_id=f"session_{i}")
        memory.consolidate(session_id=f"session_{i}")
    
    # 手动触发反思归纳
    principles = reflector.induce_principles(topic="Data Analysis", min_episodes=3)
    
    # 验证生成了原则
    assert len(principles) > 0, "Should generate principles"
    
    # 验证原则内容包含 "data cleaning" 或类似关键词
    principle_texts = [p.content for p in principles]
    assert any("clean" in p.lower() for p in principle_texts), \
        "Should induct principle about data cleaning"
    
    # 验证原则被存储到 Semantic Store
    retrieved = memory.recall("How should I start a data analysis?")
    assert any("clean" in m.content.lower() for m in retrieved), \
        "Should recall cleaning principle when asked about data analysis"
```

---

**关联文档：**
- [系统设计理念](design.md) - 设计哲学和核心概念
- [接口定义](interfaces.md) - 数据模型和API定义
- [核心流程](workflows.md) - 系统的运作方式
