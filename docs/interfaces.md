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
    
    当 Agent 在对话中使用某个 skill/principle 并记录结果时，
    可通过 source 标记追溯到原始记忆进行权重调整。
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
    derivation_type: Optional[str] = Field(
        default=None,
        description="派生类型: extraction/derivation/induction/supersession"
    )
```

### **Event (情景事件)**

```python
class Event(BaseModel):
    """情景事件 - 业务层数据模型
    
    Note:
        - embedding/vector 由存储层自动生成，不属于业务模型
        - 统一使用 'content' 而非 'text' 或 'raw_text'
    """
    id: Optional[str] = Field(default=None, description="唯一事件标识符")
    content: str = Field(description="事件的文本描述")
    outcome: str = Field(description="success/failure/unknown")
    tags: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict, description="扩展字段，如 session_id, user_query 等")
    # 溯源字段
    parent_ids: List[str] = Field(default_factory=list, description="源记忆ID列表 (如原始对话ID)")
    derivation_type: str = Field(default="extraction", description="派生类型")
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
    derivation_type: str = Field(default="induction", description="派生类型: induction")
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
    derivation_type: str = Field(default="induction", description="派生类型")
    # 反馈与精炼字段
    weight: float = Field(default=1.0, description="使用效果权重，范围 [0, 10]")
    usage_count: int = Field(default=0, description="总使用次数")
    success_count: int = Field(default=0, description="成功使用次数")
    version: str = Field(default="v1", description="版本号")
    deprecated: bool = Field(default=False, description="是否已被新版本替代")
    successor_id: Optional[str] = Field(default=None, description="后继版本的ID")
```

### **UsageFeedback (使用反馈)**

```python
class UsageFeedback(BaseModel):
    """Skill/Principle 使用反馈
    
    用于追踪每次使用的结果，支持后续的权重更新和精炼分析
    """
    id: Optional[str] = Field(default=None, description="唯一反馈标识符")
    memory_id: str = Field(description="被使用的 Skill/Principle ID")
    memory_type: Literal["skill", "principle"] = Field(description="记忆类型")
    outcome: Literal["success", "failure", "partial"] = Field(description="使用结果")
    confidence: float = Field(ge=0, le=1, description="结果置信度")
    context: str = Field(description="使用场景描述")
    failure_reason: Optional[str] = Field(default=None, description="失败时的原因分析")
    timestamp: datetime = Field(default_factory=datetime.now)
    session_id: Optional[str] = Field(default=None, description="所属会话ID")
    metadata: dict = Field(default_factory=dict, description="额外信息")
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
        content: str,
        context: Optional[dict] = None,
        session_id: Optional[str] = None
    ) -> str:
        """
        统一的记忆存储接口 - "Do One Thing Well"
        
        Args:
            content: 要记忆的内容（对话、事件、观察）
            context: 可选的上下文信息 (timestamp, tags, outcome 等)
            session_id: 会话标识，用于批量巩固（可选，自动生成）
        
        Returns:
            记忆 ID，用于后续引用或删除
        
        Raises:
            MemoryError: 存储失败时（LLM 不可用或数据库错误）
        
        Note:
            - 内部自动决定同步/异步巩固策略
            - 内部触发事件编码和语义提取
            - 幂等性：相同 content + session_id 不会重复存储
        
        Example:
            >>> memory.remember(
            ...     "User prefers dark mode",
            ...     context={"tags": ["preference", "ui"]}
            ... )
            'mem_abc123'
        """
        pass
    
    def recall(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[dict] = None
    ) -> Iterator[Memory]:
        """
        统一的记忆检索接口 - 流式返回，支持早期中断
        
        Args:
            query: 查询文本（自然语言）
            limit: 最大返回数量 (1-100)
            filters: 可选过滤器 (time_range, tags, source, min_score)
        
        Returns:
            记忆迭代器，按相关性排序。支持两种使用模式：
            - 快速模式: 立即返回首批结果 (缓存命中)
            - 深度模式: 继续迭代获取向量+图查询结果
        
        Raises:
            RetrievalError: 检索失败时（数据库不可用）
        
        Performance:
            - 首批结果 (≤3条): P95 < 50ms
            - 完整结果: P95 < 500ms, P99 < 2s
        
        Note:
            - 内部自适应选择检索策略（缓存/向量/图）
            - 内部触发预测性预取（基于会话上下文）
            - 内部可能触发反思归纳（当发现模式时）
        
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
