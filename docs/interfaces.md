# **Key Interface Definitions**

Based on the principle of simplicity, interface design follows the Unix philosophy of "less is more". All data exchange uses Pydantic models to ensure type safety.

## **Data Models**

### **Memory (Single Memory)**

```python
from typing import Any
from pydantic import BaseModel, Field
from datetime import datetime

class Memory(BaseModel):
    """Single Memory - Supports Provenance Chain
    
    ✅ Update: source field added 'principle' type for recall marking
    
    This allows the Agent to distinguish memories from different sources:
    - <memory>...</memory> → episodic
    - <fact>...</fact> → semantic  
    - <skill>...</skill> → skill
    - <principle>...</principle> → principle
    
    **Important Design Note**: The Memory object itself **does not have** an outcome field.
    When the system returns memories to the Agent, they are wrapped as XML tags (such as <skill id="xxx" outcome="pending">).
    The Agent updates the outcome attribute after use (success/failure), and the system LLM extracts these feedback signals by analyzing conversation text
    extracts these feedback signals, rather than reading from Memory object attributes.
    """
    id: str | None = Field(default=None, description="Unique Memory Identifier")
    content: str
    score: float = Field(ge=0, le=1, description="Relevance Score")
    source: Literal["episodic", "semantic", "skill", "principle"] = Field(
        description="Source type for recall marking and feedback traceability"
    )
    timestamp: datetime
    metadata: dict = {}
    # 溯源字段
    parent_ids: list[str] = Field(default_factory=list, description="List of Parent Memory IDs")
    derivation_type: Literal["extraction", "derivation", "induction", "supersession"]] = Field(
        default=None,
        description="""派生类型（根据source不同有不同Allowed Values）:
        - extraction: Extracted from raw data
        - derivation: Derived from other memories
        - induction: Induced from multiple memories (principle only)
        - supersession: Replace old memory (semantic triple only)
        """
    )
```

### **Event (Episodic Event)**

```python
class Event(BaseModel):
    """Episodic Event - Business Layer Data Model
    
    Note:
        - embedding/vector 由存储层自动生成，不属于业务Model
        - Consistently use 'content' instead of 'text' or 'raw_text'
        - Event.outcome records the actual result of the event (such as task success/failure)
        - This is different from the outcome in the feedback mechanism: feedback outcome is added by the Agent in XML tags,
          used to represent the effect of **memory usage**, extracted by LLM from conversation
    """
    id: str | None = Field(default=None, description="唯一事件标识符")
    content: str = Field(description="Text description of the event")
    outcome: str = Field(description="Event actual result: success/failure/unknown")
    tags: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict, description="Extended fields, such as session_id, user_query, etc.")
    # 溯源字段
    parent_ids: list[str] = Field(default_factory=list, description="List of source memory IDs (如原始对话ID)")
    derivation_type: Literal["extraction", "derivation"] = Field(
        default="extraction",
        description="""Derivation type (Event only supports two types):
        - extraction: Extract event from conversation
        - derivation: Derive new Event from other Events
        """
    )
```

### **ConsolidationResult (Consolidation Result)**

```python
class ConsolidationResult(BaseModel):
    """Consolidation Result Statistics"""
    success: bool
    stored_events: int
    updated_facts: int
    conflicts_resolved: int
    errors: list[str] = []
```

### **Principle (Extracted Principle)**

```python
class Principle(BaseModel):
    """Extracted Principle - Supports Multi-Evidence Provenance
    
    ✅ New: Supports usage feedback tracking and version evolution
    """
    id: str | None = Field(default=None, description="Unique Principle Identifier")
    content: str
    evidence_count: int = Field(description="Number of Episodes supporting this principle")
    confidence: float = Field(ge=0, le=1)
    created_at: datetime = Field(default_factory=datetime.now)
    # 溯源字段
    parent_ids: list[str] = Field(default_factory=list, description="List of Evidence Memory IDs")
    derivation_type: Literal["induction"] = Field(
        default="induction",
        description="Derivation type (Principle is fixed as induction, meaning induced from multiple Events)"
    )
    # 反馈与精炼字段
    weight: float = Field(default=1.0, description="Usage effectiveness weight, range [0, 10]")
    usage_count: int = Field(default=0, description="Total usage count")
    success_count: int = Field(default=0, description="Successful usage count")
    version: str = Field(default="v1", description="Version number")
    deprecated: bool = Field(default=False, description="Whether superseded by new version")
    successor_id: str | None = Field(default=None, description="Successor version ID")
```

### **Skill (Procedural Skill)**

```python
class Skill(BaseModel):
    """Procedural Skill - Supports templating and feedback optimization
    
    ✅ New: Supports usage feedback tracking and version evolution
    """
    id: str | None = Field(default=None, description="Unique Skill Identifier")
    name: str
    trigger_pattern: str = Field(description="Trigger condition description or regex")
    code_template: str = Field(description="Code template or execution steps")
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    # 溯源字段
    parent_ids: list[str] = Field(default_factory=list, description="List of source memory IDs")
    derivation_type: Literal["induction"] = Field(
        default="induction",
        description="Derivation type (Skill is fixed as induction, meaning skill template induced from multiple successful cases)"
    )
    # 反馈与精炼字段
    weight: float = Field(default=1.0, description="Usage effectiveness weight, range [0, 10]")
    usage_count: int = Field(default=0, description="Total usage count")
    success_count: int = Field(default=0, description="Successful usage count")
    version: str = Field(default="v1", description="Version number")
    deprecated: bool = Field(default=False, description="Whether superseded by new version")
    successor_id: str | None = Field(default=None, description="Successor version ID")
```

### **Feedback Mechanism Description**

**Important**: The system **does not use** a separate UsageFeedback model to store feedback.

Feedback signals are extracted and applied through the following methods:

1. **System returns memories with XML tags** (仅用于追踪):
   ```xml
   <skill id="skill_abc">使用 Selenium 爬取动态网站</skill>
   ```

2. **Agent uses these memories in conversation, and users express results through conversation**:
   - 显式: "成功了！"、"失败了"、"完美解决"
   - 隐式: 继续后续步骤 vs. 请求替代方案

3. **System extracts feedback signals by analyzing conversation semantics through LLM**:
   - 从 XML 标记提取使用了哪些记忆 (memory IDs)
   - LLM 分析对话上下文判断每个记忆的使用效果
   - 无需依赖 XML 中的 outcome 属性（XML 中也没有这个属性）

4. **Directly update memory weights**:
   - Skill: success → +1 success_count, +0.1 weight; failure → +1 failure_count, -0.1 weight
   - Principle: success → +0.1 weight; failure → -0.2 weight
   - 反馈沿溯源链传播（衰减系数 0.8）

Feedback data is implicitly stored in the weight, usage_count, success_count fields of memory objects,
no separate feedback table needed.

### **Derivation Type Enumeration Summary**

Different models support `derivation_type` values, reflecting memory derivation paths:

| Model | Allowed Values | Description |
|------|--------|------|
| **Memory** | `extraction` \| `derivation` \| `induction` \| `supersession` \| `None` | Retrieved memories may come from any level, supporting all derivation types |
| **Event** | `extraction` \| `derivation` | Event can only be extracted from conversation or derived from other Events |
| **Principle** | `induction` (固定) | Principle can only be created through induction, abstracted from multiple Events |
| **Skill** | `induction` (固定) | Skill can only be created through induction, refined from multiple successful cases |
| **SemanticTriple** | `extraction` \| `derivation` \| `supersession` | Triple can be extracted, derived, or replaced by new version |

**Derivation Type Semantics:**

- **extraction**: First extraction from raw data (Conversation)
- **derivation**: Derive new memory from existing memories (same level or cross-level)
- **induction**: Induce high-level patterns from multiple low-level memories (only for Principle/Skill)
- **supersession**: New version replaces old version (only for SemanticTriple version evolution)

**Level Relationship Example:**

```
Level 0 (Raw): Conversation
    ↓ [extraction]
Level 1 (Episodic): Event
    ↓ [extraction/derivation]
Level 2 (Semantic): SemanticTriple
    ↓ [induction]
Level 3 (Principles): Principle/Skill
```

---

## **异常定义**

```python
class MemoryError(Exception):
    """Memory System Base Exception"""
    pass

class RetrievalError(MemoryError):
    """Retrieval Failed"""
    pass

class ConsolidationError(MemoryError):
    """Consolidation Failed"""
    pass

class ReflectionError(MemoryError):
    """Reflection Failed"""
    pass
```

---

## **核心接口: MemorySystem**

```python
class MemorySystem(MemorySystemInterface):
    """认知记忆系统核心接口 [Core - 接口稳定]
    
    遵循 Unix 哲学: 简洁的接口，精细的内部实现。
    用户只需理解两个核心操作：记忆存储和记忆检索。
    所有智能决策（巩固、反思、降级）均为内部策略。
    
    ✅ 实现状态: 
    - 位置: src/hmem/core/memory_system.py
    - 显式继承 hmem.interfaces.MemorySystem 抽象接口
    - 确保类型安全和接口一致性
    """
    
    def remember(
        self,
        conversation: Conversation | list[Message],
    ) -> str:
        """
        Store conversation into memory system (single write interface).
        
        This method accepts a conversation record and internalizes it into the memory system.
        The conversation is processed through:
        1. Sensory buffer (immediate storage)
        2. Event encoding (extracting events and facts)
        3. Async consolidation (non-blocking, runs in background)
        4. Async feedback extraction (LLM-based, if used_memory_ids present)
        
        Args:
            conversation: Either a Conversation object or list of Message objects.
                         If list provided, a session_id will be auto-generated.
        
        Returns:
            session_id: Unique identifier for this conversation session
        
        Raises:
            MemoryError: Raised when storage fails
        
        Example:
            >>> from hmem.models import Message, Conversation
            >>> memory = MemorySystem()
            >>>
            >>> # Option 1: Using Conversation object
            >>> conv = Conversation(
            ...     session_id="session_123",
            ...     messages=[
            ...         Message(role="user", content="My name is Alice"),
            ...         Message(role="assistant", content="Nice to meet you, Alice!"),
            ...     ]
            ... )
            >>> session_id = memory.remember(conv)
            >>>
            >>> # Option 2: Using list of messages
            >>> messages = [
            ...     Message(role="user", content="I want to learn Python"),
            ...     Message(role="assistant", content="Great choice!"),
            ... ]
            >>> session_id = memory.remember(messages)
        
        Note:
            - Automatically triggers async consolidation and feedback extraction
            - Session ID is used to group related messages for consolidation
            - Type-safe: Uses Pydantic models instead of raw dictionaries
        """
        pass
    
    def recall(
        self,
        query: str | Message | Conversation,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> Iterator[Memory]:
        """
        Retrieve relevant memories (single read interface).
        
        Searches existing memories and returns relevant content.
        Accepts string, Message, or Conversation for flexible querying.
        
        Args:
            query: Search query with multiple formats:
                  - str: Simple text query for single search
                  - Message: Single message with role/metadata for context
                  - Conversation: Full conversation for proactive prompting
                    (uses conversation context to find relevant memories)
            limit: Maximum number of results to return (1-100)
            filters: Optional filter conditions:
                    - session_id: Filter by specific session
                    - source: Filter by memory type (episodic/semantic/skill)
                    - time_range: Filter by time period
                    - tags: Filter by tags
                    - min_score: Minimum relevance threshold
        
        Yields:
            Memory: Memories sorted by relevance score
        
        Raises:
            RetrievalError: Raised when retrieval fails
        
        Example:
            >>> # Simple string query (single search)
            >>> for memory in memory.recall("user preferences", limit=5):
            ...     print(f"{memory.content} (score: {memory.score})")
            >>>
            >>> # Context-aware query with Message
            >>> query_msg = Message(role="user", content="What do I like?")
            >>> results = list(memory.recall(query_msg, limit=10))
            >>>
            >>> # Proactive prompting with Conversation
            >>> conversation = Conversation(
            ...     session_id="s1",
            ...     messages=[
            ...         Message(role="user", content="I'm working on web scraping"),
            ...         Message(role="assistant", content="Great! What site?"),
            ...     ]
            ... )
            >>> results = list(memory.recall(conversation, limit=10))
            >>>
            >>> # Filtered query
            >>> results = list(memory.recall(
            ...     "web scraping",
            ...     filters={"source": "episodic", "session_id": "s1"}
            ... ))
        
        Performance:
            - First batch (≤3 results): P95 < 50ms
            - Full results: P95 < 500ms, P99 < 2s
        
        Note:
            - Adaptive retrieval strategy (cache/vector/graph)
            - Context-aware: Conversation queries enable proactive memory retrieval
            - Type-safe: Uses modern Python type hints (dict[str, Any] | None)
        
        Example:
            >>> # 快速模式：只取前 3 条
            >>> results = list(islice(memory.recall("web scraping"), 3))
            >>> 
            >>> # 完整模式：等待所有结果
            >>> results = list(memory.recall("user preferences", limit=10))
        """
        pass
```

---

## **Strategy Interface: RetrievalRanker**

```python
class RetrievalRanker(ABC):
    """Retrieval Result Ranking Strategy [Stable - 可插拔]"""
    
    @abstractmethod
    def rank(self, candidates: list[Memory], query: str) -> list[Memory]:
        """Sort candidate memories"""
        pass

class HybridRanker(RetrievalRanker):
    """混合排序: 相似度 + 时效性 + Important性 (可配置权重)
    
    Default weights are based on empirical values in information retrieval field, but should be optimized through A/B testing.
    """
    
    def __init__(
        self,
        similarity_weight: float = 0.6,
        recency_weight: float = 0.2,
        importance_weight: float = 0.2,
        importance_normalizer: float = 100.0
    ):
        """Initialize Hybrid Ranker
        
        Args:
            similarity_weight: Similarity weight (recommended range: 0.5-0.7)
                - Factual queries: can increase to 0.7
                - Experience queries: can decrease to 0.5
            recency_weight: Recency weight (recommended range: 0.1-0.3)
            importance_weight: Important性权重 (推荐范围: 0.1-0.3)
            importance_normalizer: Access count normalization factor, recommended to adjust based on system scale:
                - Small scale (<10k memories): 10-50
                - Medium scale (10k-100k): 100-500
                - Large scale (>100k): 1000+
        
        Note:
            Sum of three weights should be close to 1.0 to maintain score interpretability.
        """
        assert abs(similarity_weight + recency_weight + importance_weight - 1.0) < 0.01, \
            "权重之和应为1.0"
        self.weights = {
            "similarity": similarity_weight,
            "recency": recency_weight,
            "importance": importance_weight
        }
        self.importance_normalizer = importance_normalizer
    
    def rank(self, candidates, query):
        for mem in candidates:
            recency = self._time_decay(mem.timestamp)
            # Important性归一化到 [0, 1] 区间
            importance = min(1.0, mem.metadata.get('access_count', 0) / self.importance_normalizer)
            
            mem.score = (
                self.weights["similarity"] * mem.score +
                self.weights["recency"] * recency +
                self.weights["importance"] * importance
            )
        return sorted(candidates, key=lambda m: m.score, reverse=True)
```

---

**Related Documents:**
- [系统设计理念](design.md) - 设计哲学和核心概念
- [组件详情](components.md) - 各个组件的职责和实现
- [记忆溯源](provenance.md) - 记忆溯源与层次语义图
