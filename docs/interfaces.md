# **关键接口定义 (Key Interfaces)**

基于简洁性原则，接口设计遵循"少即是多"的 Unix 哲学。所有数据交换使用 Pydantic 模型确保类型安全。

## **数据模型**

### **Memory (单条记忆)**

```python
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class Memory(BaseModel):
    """单条记忆 - 支持溯源链
    
    ✅ 更新: source 字段新增 'principle' 类型，用于 recall 标记
    
    这使得 Agent 可以区分不同来源的记忆:
    - <memory>...</memory> → episodic
    - <fact>...</fact> → semantic  
    - <skill>...</skill> → skill
    - <principle>...</principle> → principle
    
    **重要设计说明**: Memory 对象本身**没有** outcome 字段。
    当系统返回记忆给 Agent 时，会包装为 XML 标记（如 <skill id="xxx" outcome="pending">）。
    Agent 在使用后更新 outcome 属性（success/failure），系统的 LLM 通过分析对话文本
    提取这些反馈信号，而非从 Memory 对象属性中读取。
    """
    id: Optional[str] = Field(default=None, description="唯一记忆标识符")
    content: str
    score: float = Field(ge=0, le=1, description="相关性分数")
    source: Literal["episodic", "semantic", "skill", "principle"] = Field(
        description="来源类型，用于 recall 标记和反馈追溯"
    )
    timestamp: datetime
    metadata: dict = {}
    # 溯源字段
    parent_ids: List[str] = Field(default_factory=list, description="父记忆ID列表")
    derivation_type: Optional[Literal["extraction", "derivation", "induction", "supersession"]] = Field(
        default=None,
        description="""派生类型（根据source不同有不同允许值）:
        - extraction: 从原始数据提取
        - derivation: 从其他记忆推导
        - induction: 从多个记忆归纳（仅principle）
        - supersession: 替换旧记忆（仅semantic triple）
        """
    )
```

### **Event (情景事件)**

```python
class Event(BaseModel):
    """情景事件 - 业务层数据模型
    
    Note:
        - embedding/vector 由存储层自动生成，不属于业务模型
        - 统一使用 'content' 而非 'text' 或 'raw_text'
        - Event.outcome 记录实际事件的结果（如任务成功/失败）
        - 这与反馈机制中的 outcome 不同：反馈 outcome 是 Agent 在 XML 标记中添加的，
          用于表示**记忆使用**的效果，由 LLM 从对话中提取
    """
    id: Optional[str] = Field(default=None, description="唯一事件标识符")
    content: str = Field(description="事件的文本描述")
    outcome: str = Field(description="事件实际结果: success/failure/unknown")
    tags: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict, description="扩展字段，如 session_id, user_query 等")
    # 溯源字段
    parent_ids: List[str] = Field(default_factory=list, description="源记忆ID列表 (如原始对话ID)")
    derivation_type: Literal["extraction", "derivation"] = Field(
        default="extraction",
        description="""派生类型（Event仅支持两种）:
        - extraction: 从对话中提取事件
        - derivation: 从其他Event推导新Event
        """
    )
```

### **ConsolidationResult (巩固结果)**

```python
class ConsolidationResult(BaseModel):
    """巩固结果统计"""
    success: bool
    stored_events: int
    updated_facts: int
    conflicts_resolved: int
    errors: List[str] = []
```

### **Principle (提炼的原则)**

```python
class Principle(BaseModel):
    """提炼的原则 - 支持多证据溯源
    
    ✅ 新增: 支持使用反馈追踪和版本演进
    """
    id: Optional[str] = Field(default=None, description="唯一原则标识符")
    content: str
    evidence_count: int = Field(description="支持该原则的 Episode 数量")
    confidence: float = Field(ge=0, le=1)
    created_at: datetime = Field(default_factory=datetime.now)
    # 溯源字段
    parent_ids: List[str] = Field(default_factory=list, description="证据记忆ID列表")
    derivation_type: Literal["induction"] = Field(
        default="induction",
        description="派生类型（Principle固定为induction，表示从多个Event归纳而来）"
    )
    # 反馈与精炼字段
    weight: float = Field(default=1.0, description="使用效果权重，范围 [0, 10]")
    usage_count: int = Field(default=0, description="总使用次数")
    success_count: int = Field(default=0, description="成功使用次数")
    version: str = Field(default="v1", description="版本号")
    deprecated: bool = Field(default=False, description="是否已被新版本替代")
    successor_id: Optional[str] = Field(default=None, description="后继版本的ID")
```

### **Skill (程序化技能)**

```python
class Skill(BaseModel):
    """程序化技能 - 支持模版化和反馈优化
    
    ✅ 新增: 支持使用反馈追踪和版本演进
    """
    id: Optional[str] = Field(default=None, description="唯一技能标识符")
    name: str
    trigger_pattern: str = Field(description="触发条件描述或正则")
    code_template: str = Field(description="代码模版或执行步骤")
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    # 溯源字段
    parent_ids: List[str] = Field(default_factory=list, description="源记忆ID列表")
    derivation_type: Literal["induction"] = Field(
        default="induction",
        description="派生类型（Skill固定为induction，表示从多个成功案例中归纳技能模板）"
    )
    # 反馈与精炼字段
    weight: float = Field(default=1.0, description="使用效果权重，范围 [0, 10]")
    usage_count: int = Field(default=0, description="总使用次数")
    success_count: int = Field(default=0, description="成功使用次数")
    version: str = Field(default="v1", description="版本号")
    deprecated: bool = Field(default=False, description="是否已被新版本替代")
    successor_id: Optional[str] = Field(default=None, description="后继版本的ID")
```

### **Feedback Mechanism (反馈机制说明)**

**重要**: 系统**不使用**独立的 UsageFeedback 模型来存储反馈。

反馈信号通过以下方式提取和应用:

1. **系统返回带 XML 标记的记忆** (仅用于追踪):
   ```xml
   <skill id="skill_abc">使用 Selenium 爬取动态网站</skill>
   ```

2. **Agent 在对话中使用这些记忆，用户通过对话表达结果**:
   - 显式: "成功了！"、"失败了"、"完美解决"
   - 隐式: 继续后续步骤 vs. 请求替代方案

3. **系统通过 LLM 分析对话语义提取反馈信号**:
   - 从 XML 标记提取使用了哪些记忆 (memory IDs)
   - LLM 分析对话上下文判断每个记忆的使用效果
   - 无需依赖 XML 中的 outcome 属性（XML 中也没有这个属性）

4. **直接更新记忆权重**:
   - Skill: success → +1 success_count, +0.1 weight; failure → +1 failure_count, -0.1 weight
   - Principle: success → +0.1 weight; failure → -0.2 weight
   - 反馈沿溯源链传播（衰减系数 0.8）

反馈数据隐式存储在记忆对象的 weight、usage_count、success_count 字段中，
无需单独的 feedback 表。

### **Derivation Type 枚举总结**

不同模型支持的 `derivation_type` 值不同，反映了记忆的派生路径：

| 模型 | 允许值 | 说明 |
|------|--------|------|
| **Memory** | `extraction` \| `derivation` \| `induction` \| `supersession` \| `None` | 检索返回的记忆可能来自任何层级，支持所有派生类型 |
| **Event** | `extraction` \| `derivation` | Event只能从对话提取或从其他Event推导 |
| **Principle** | `induction` (固定) | Principle只能通过归纳产生，从多个Event抽象 |
| **Skill** | `induction` (固定) | Skill只能通过归纳产生，从多个成功案例中提炼 |
| **SemanticTriple** | `extraction` \| `derivation` \| `supersession` | Triple可提取、推导或被新版本替换 |

**派生类型语义:**

- **extraction**: 从原始数据(Conversation)中首次提取
- **derivation**: 从已有记忆推导出新记忆(同层级或跨层级)
- **induction**: 从多个低层记忆归纳出高层规律(仅用于Principle/Skill)
- **supersession**: 新版本替换旧版本(仅用于SemanticTriple的版本演进)

**层级关系示例:**

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
    """记忆系统基础异常"""
    pass

class RetrievalError(MemoryError):
    """检索失败"""
    pass

class ConsolidationError(MemoryError):
    """巩固失败"""
    pass

class ReflectionError(MemoryError):
    """反思失败"""
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

## **策略接口: RetrievalRanker**

```python
class RetrievalRanker(ABC):
    """检索结果排序策略 [Stable - 可插拔]"""
    
    @abstractmethod
    def rank(self, candidates: List[Memory], query: str) -> List[Memory]:
        """对候选记忆排序"""
        pass

class HybridRanker(RetrievalRanker):
    """混合排序: 相似度 + 时效性 + 重要性 (可配置权重)
    
    默认权重基于信息检索领域的经验值，但应通过A/B测试优化。
    """
    
    def __init__(
        self,
        similarity_weight: float = 0.6,
        recency_weight: float = 0.2,
        importance_weight: float = 0.2,
        importance_normalizer: float = 100.0
    ):
        """初始化混合排序器
        
        Args:
            similarity_weight: 相似度权重 (推荐范围: 0.5-0.7)
                - 事实查询: 可提高到 0.7
                - 经验查询: 可降低到 0.5
            recency_weight: 时效性权重 (推荐范围: 0.1-0.3)
            importance_weight: 重要性权重 (推荐范围: 0.1-0.3)
            importance_normalizer: 访问次数归一化因子，建议根据系统规模调整:
                - 小规模 (<1万记忆): 10-50
                - 中规模 (1-10万): 100-500
                - 大规模 (>10万): 1000+
        
        Note:
            三个权重之和应接近1.0以保持分数可解释性。
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
            # 重要性归一化到 [0, 1] 区间
            importance = min(1.0, mem.metadata.get('access_count', 0) / self.importance_normalizer)
            
            mem.score = (
                self.weights["similarity"] * mem.score +
                self.weights["recency"] * recency +
                self.weights["importance"] * importance
            )
        return sorted(candidates, key=lambda m: m.score, reverse=True)
```

---

**关联文档：**
- [系统设计理念](design.md) - 设计哲学和核心概念
- [组件详情](components.md) - 各个组件的职责和实现
- [记忆溯源](provenance.md) - 记忆溯源与层次语义图
