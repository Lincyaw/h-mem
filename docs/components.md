# **Component Details & Responsibilities**

## **Layer 1: Perception & Working Memory**

Responsible for processing current interaction flows (inside-trail) and maintaining continuity of "consciousness".

### **A. Perception Layer Components** `[Layer 1]`

#### **SensoryBuffer - Sensory Buffer**

* **Responsibility:** Temporarily store raw conversation records, waiting for background consolidation processing.
* **实现位置:** `src/hmem/perception/sensory_buffer.py`
* **Data Structure:** FIFO queue (implemented using deque)
* **Capacity Limit:** Default 1000 messages (configurable)

```python
class SensoryBuffer:
    def push(self, raw_log: dict[str, str]) -> None:
        """Add raw conversation to buffer"""
    
    def pop_batch(self, size: int) -> list[dict[str, str]]:
        """Batch extract conversations for processing"""
```

#### **MemorySystem.chat() - 交互式对话**

* **职责:** 维护会话上下文，检索相关记忆，应用折叠策略。
* **实现位置:** `src/hmem/core/memory_system.py::chat()`
* **输入:** 用户消息、会话ID（可选）
* **输出:** 相关记忆列表、会话ID

```python
class MemorySystem:
    def chat(self, message: str | Message, session_id: str | None = None) -> tuple[list[Memory], str]:
        """Interactive chat with automatic memory retrieval.
        
        Features:
        - Retrieves relevant memories from all stores
        - Maintains session context
        - Applies folding strategies when needed
        - Stores messages for future recall
        """
```

#### **FoldingStrategy - 折叠策略**

* **职责:** 防止上下文溢出，通过智能压缩保留关键信息。
* **实现位置:** `src/hmem/perception/strategies/`
* **核心机制:** 策略模式，支持可插拔实现

**可插拔策略接口:**

✅ **实现状态**: 已完成统一接口设计，所有策略位于 `hmem.perception.strategies`

```python
# 单一真实来源: hmem/perception/strategies/folding.py
from abc import ABC, abstractmethod
from typing import Any

class FoldingStrategy(ABC):
    """记忆折叠策略抽象基类 - 单一接口定义
    
    所有折叠实现必须继承此类，确保接口一致性。
    位置: src/hmem/perception/strategies/folding.py
    """
    
    @abstractmethod
    def should_fold(self, messages: list[dict[str, Any]], token_count: int, limit: int) -> bool:
        """判断是否需要折叠"""
        pass
    
    @abstractmethod
    def compress(self, messages: list[dict[str, Any]]) -> str:
        """执行压缩，返回摘要文本"""
        pass
    
    def estimate_tokens(self, text: str) -> int:
        """估算文本的 token 数量 (可选重写)"""
        return len(text) // 4  # 默认: 约 4 字符/token

# ============ 具体策略实现 ============

class TokenBasedFolder(FoldingStrategy):
    """基于 Token 阈值的折叠策略 (默认)
    
    位置: src/hmem/perception/strategies/token_based.py
    
    阈值设计考虑:
    - 太低(如0.6): 频繁折叠，丢失细节
    - 太高(如0.95): 折叠太晚，可能溢出
    - 0.8: 经验平衡点，为突发长消息预留20%缓冲
    """
    
    def __init__(self, trigger_ratio: float = 0.8):
        if not (0.5 <= trigger_ratio <= 0.95):
            raise ValueError("trigger_ratio 应在 0.5-0.95 之间")
        self.trigger_ratio = trigger_ratio
    
    def should_fold(self, messages, token_count, limit):
        return token_count > limit * self.trigger_ratio
    
    def compress(self, messages):
        # Phase 1: 简单摘要
        # Phase 2+: 使用 LLM 生成智能摘要
        return f"[Summarized {len(messages)} messages]"

class TimeWindowFolder(FoldingStrategy):
    """基于时间窗口的折叠策略
    
    位置: src/hmem/perception/strategies/time_window.py
    ✅ 实现状态: 已完成
    
    适用场景:
    - 跨越多小时/天的长对话
    - 时间上下文比 token 数量更重要的场景
    """
    
    def __init__(self, window_hours: float = 24.0):
        self.window_hours = window_hours
    
    def should_fold(self, messages, token_count, limit):
        if not messages:
            return False
        oldest_timestamp = messages[0].get('timestamp')
        if not oldest_timestamp:
            return False
        from datetime import datetime, timedelta
        return (datetime.now() - oldest_timestamp) > timedelta(hours=self.window_hours)
    
    def compress(self, messages):
        # 包含时间范围的摘要
        return f"[Summarized {len(messages)} messages from past {self.window_hours}h]"
```

**配置示例:**
```yaml
memory:
  folding_strategy: "h_mem.strategies.TokenBasedFolder"
  folding_threshold: 0.8
```

### **B. Sensory Buffer**

* **职责:** 暂存原始的多模态日志（Raw Logs），作为"海马体"处理的原材料。  
* **机制:** 简单的 FIFO 队列或 Redis 列表。

---

## **Layer 2: Hippocampus Processing**

This is the system's **scheduling center**, responsible for transforming short-term memory into long-term memory and extracting wisdom.

### **C. Memory Encoder**

* **Responsibility:** Transform unstructured conversations into structured data.  
* **机制:** 区分处理。  
  * **事实提取:** 识别实体关系（如 User → Location → Beijing）。  
  * **事件提取:** 识别完整的 Task-Action-Result 链条。

### **D. Consolidator & Refresher** `[Stable]`

* **Responsibility:** Simulate the "sleep" process, handling memory writing, conflict correction, and forgetting.  
* **触发:** 同步执行 (Phase 1), 异步执行 (Phase 3)。  
* **输入:** 结构化的事件和事实。  
* **输出:** 数据库的增删改操作 + 统计报告。  

**Transaction Management & Concurrency Control:**

```python
import fcntl
from contextlib import contextmanager
from sqlalchemy import exc

class Consolidator:
    
    @contextmanager
    def _session_lock(self, session_id: str):
        """防止同一 session 并发巩固 (可插拔锁后端)"""
        # 使用抽象的 LockProvider，支持单机和分布式场景
        with self.lock_provider.acquire(f"consolidate:{session_id}", timeout=30):
            yield

class LockProvider(ABC):
    """锁抽象层 - 支持从单机到分布式的平滑迁移"""
    
    @abstractmethod
    @contextmanager
    def acquire(self, key: str, timeout: float) -> Iterator[None]:
        """获取锁，超时抛出 LockTimeoutError"""
        pass

class FileLockProvider(LockProvider):
    """文件锁实现 (默认，适用于单机部署)"""
    def acquire(self, key, timeout):
        lock_file = f"/tmp/h-mem-{key}.lock"
        with open(lock_file, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

class RedisLockProvider(LockProvider):
    """Redis 分布式锁 (可选，适用于多实例部署)"""
    def acquire(self, key, timeout):
        lock = self.redis.lock(f"h-mem:lock:{key}", timeout=timeout)
        with lock:
            yield

# 配置示例
config = {
    "lock_backend": "file:///tmp",  # 或 "redis://localhost:6379"
}
    
    def consolidate(self, session_id: str, events: List[Event]) -> ConsolidationResult:
        """执行巩固，保证原子性"""
        with self._session_lock(session_id):
            try:
                # Step 1: 写入 Vector DB (优先)
                vector_ids = self._write_to_chromadb(events)
                
                # Step 2: 写入 Semantic Graph (可能失败)
                try:
                    self._update_graph(events)
                except GraphConflictError as e:
                    # 冲突解决: 使用乐观锁
                    self._resolve_conflict(e)
                
                # Step 3: 提交事务
                self.db.commit()
                return ConsolidationResult(success=True, stored=len(events))
                
            except Exception as e:
                # 回滚 Vector DB (标记为 deleted)
                self._rollback_vectors(vector_ids)
                self.db.rollback()
                logger.error("consolidation_failed", session_id=session_id, error=str(e))
                raise ConsolidationError(f"Failed to consolidate: {e}")
```

**Conflict Resolution Strategy (Optimistic Locking):**

```sql
-- Semantic Graph 表结构
CREATE TABLE semantic_facts (
    id INTEGER PRIMARY KEY,
    subject TEXT,
    predicate TEXT,
    object TEXT,
    weight REAL DEFAULT 1.0,
    version INTEGER DEFAULT 1,  -- 乐观锁版本号
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- 更新时检查版本
UPDATE semantic_facts 
SET weight = weight + 0.1, version = version + 1
WHERE id = ? AND version = ?;  -- 如果 version 不匹配则更新失败
```

**Error Handling Strategy:**

- **LLM API 失败:** 直接抛出 MemoryError，不做降级（假设 LLM 可用）
- **数据库写入失败:** 写入 Event Log 失败时立即抛错；派生视图失败时记录日志并异步重试
- **重试策略:** Exponential backoff (1s, 2s, 4s, 最多 3 次)，仅针对瞬时网络错误
- **熔断保护:** 当连续失败 5 次时触发 Circuit Breaker，快速失败避免级联

**Event Sourcing Architecture:**

解决 ChromaDB 与 Neo4j 双写一致性问题，采用单一真实来源设计：

```sql
-- Event Log 作为单一真实来源 (append-only)
CREATE TABLE event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT,  -- 'remember', 'update', 'forget'
    payload JSON,     -- 完整的事件数据
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT FALSE
);

-- ✅ New: 使用反馈表 (支持 Skill/Principle 精炼)
-- 注意: outcome 是从对话中提取的反馈信号，不是 Memory 对象的属性
-- LLM 通过分析对话文本和 XML 标记来提取这些反馈信号
CREATE TABLE usage_feedback (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,        -- 被使用的 Skill/Principle ID
    memory_type TEXT NOT NULL,      -- 'skill' 或 'principle'
    outcome TEXT NOT NULL,          -- 'success', 'failure', 'partial' (从对话中提取)
    confidence REAL NOT NULL,       -- 0.0 - 1.0 (LLM 推断的置信度)
    context TEXT NOT NULL,          -- 使用场景描述 (对话片段)
    failure_reason TEXT,            -- 失败原因 (可选，LLM 提取)
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    session_id TEXT,
    metadata JSON,                  -- 额外信息
    INDEX idx_memory_id (memory_id),
    INDEX idx_timestamp (timestamp),
    INDEX idx_outcome (outcome)
);
```

**Advantages:**
- 写入操作只需成功追加到 Event Log（单次事务）
- 派生视图异步构建，失败不影响主流程
- 支持完整审计和时间旅行（回溯到任意时刻的记忆状态）
- 数据迁移零风险：重放 Event Log 即可重建所有视图

### **E. Deep Reflection Agent** `[Experimental]`

* **职责:** **跨任务归纳 (Induction)** 和 **经验精炼 (Refinement)**。这是 Agent 产生"处事哲学"并持续优化的核心。  
* **机制:**  
  1. **聚类:** 定期扫描情景记忆，找出最近相似的 N 个任务。  
  2. **抽象:** 忽略细节，提炼共同的成功模式或失败原因。  
  3. **生成:** 输出一条通用的"原则 (Principle)"或"技能模版 (Skill Skeleton)"。  
  4. **精炼 (Refinement):** 当某个 Skill 或 Principle 积累足够反馈时，触发深度复盘：
     - **正反馈聚合:** 分析成功案例中的共同特征，增强有效部分
     - **负反馈分析:** 识别失败模式和边界条件，添加约束或修正逻辑
     - **版本演进:** 生成改进后的新版本，保留溯源链以支持回滚
* **输入:** 一组相似的历史 Episode 或带反馈的 Skill/Principle 使用记录。  
* **输出:** 一条语义记忆（原则）或一条程序化记忆（技能），或其精炼后的新版本。

**Refinement Trigger Conditions:**
- **反馈数量阈值:** Skill/Principle 被使用次数 ≥ N (默认 10)
- **负反馈占比:** 负反馈比例 ≥ threshold (默认 30%) 时优先触发
- **时间窗口:** 在最近 T 天内的反馈 (避免使用过时数据)
- **置信度波动:** 权重方差超过阈值，表明使用效果不稳定

**Pluggable Reflection Strategies:**

```python
class ReflectionPolicy(ABC):
    """反思触发策略 - 多时间尺度自适应"""
    
    @abstractmethod
    def should_trigger(self, topic: str, context: ReflectionContext) -> bool:
        pass

class ReflectionContext(BaseModel):
    """反思上下文信息"""
    episode_count: int
    time_span_days: float
    avg_similarity: float  # 主题内记忆的相似度
    last_reflection_time: Optional[datetime]

class MultiScalePolicy(ReflectionPolicy):
    """多时间尺度反思策略 (默认)
    
    阈值设计原则:
    - 即时级: 确保单次会话内有足够样本识别模式
    - 日级: 平衡计算成本与归纳质量
    - 周级: 避免过早泛化，需要充分证据
    
    默认阈值基于以下假设:
    - 单次会话平均轮数: 10-20 轮
    - 日活跃会话数: 5-10 个
    - 周记忆增长率: ~100 条
    
    不同应用场景应通过配置文件调整。
    """
    def __init__(
        self,
        immediate_threshold: int = 10,      # 建议范围: 5-20
        daily_threshold: int = 50,          # 建议范围: 30-100
        weekly_threshold: int = 100,        # 建议范围: 50-200
        similarity_threshold: float = 0.75  # 建议范围: 0.7-0.85
    ):
        if not (immediate_threshold < daily_threshold < weekly_threshold):
            raise ValueError("阈值必须递增: immediate < daily < weekly")
        
        self.thresholds = {
            "immediate": immediate_threshold,
            "daily": daily_threshold,
            "weekly": weekly_threshold
        }
        self.similarity_threshold = similarity_threshold
    
    def should_trigger(self, topic, context):
        # 即时反思：会话内记忆聚类
        if context.episode_count >= self.thresholds["immediate"] and \
           context.time_span_days < 1 and \
           context.avg_similarity > self.similarity_threshold:
            logger.info(
                "reflection_triggered",
                level="immediate",
                episodes=context.episode_count,
                similarity=context.avg_similarity
            )
            return True
        
        # 日级反思：跨会话模式识别
        if context.episode_count >= self.thresholds["daily"] and \
           context.time_span_days >= 1 and \
           context.time_span_days < 7:
            logger.info("reflection_triggered", level="daily", episodes=context.episode_count)
            return True
        
        # 周级反思：深度哲学提炼
        if context.episode_count >= self.thresholds["weekly"] and \
           context.time_span_days >= 7:
            logger.info("reflection_triggered", level="weekly", episodes=context.episode_count)
            return True
        
        return False
```

---

## **Layer 3: Long-Term Storage**

Hybrid database architecture, storing different types of data in separate databases. Uses lightweight technology stack, prioritizing embedded solutions.

| **Storage Components** | **Current Implementation** | **Optional Upgrade** | **Storage Content** | **Typical Use** | **Corresponding Cognitive Type** |
|--------------|-----|---------|---------|---------|---------|
| **Episodic Store** | ChromaDB (嵌入式) | Milvus (分布式) | Event {content, outcome, tags, timestamp, metadata} + embedding | "遇到这种报错,我上次是怎么修的?" | 情景记忆 (经历) |

**注**: Event.outcome 记录实际事件结果 (如任务成功/失败)，与反馈机制中的 outcome 不同。反馈 outcome 是 Agent 在 XML 标记中添加的，表示记忆使用效果，由 LLM 从对话中提取。
| **Semantic Store** | Neo4j (原生图) | PostgreSQL+AGE | Triple {subject, predicate, object, weight, version} + 向量索引 | "用户的偏好是什么?" "公司的报销流程原则是什么?" | 语义记忆 (事实/原则) |
| **Skill Store** | SQLite (JSON 列) | Redis (KV) | Skill {name, trigger_pattern, code_template} | "给我一个标准的搜索-总结流程模版。" | 程序化记忆 (技能) |

**Storage Implementation Details:**

```python
# Episodic Store (ChromaDB) - 带索引生命周期管理
class EpisodicStore:
    def __init__(self):
        self.active_collection = chromadb.Collection(name="episodic_v1")
        self.building_collection = None  # 后台重建的索引
        self.insertion_count = 0
        self.last_rebuild_count = 0
    
    def add(self, documents, embeddings, metadatas, ids):
        """添加记忆，自动触发索引重建"""
        self.active_collection.add(documents, embeddings, metadatas, ids)
        self.insertion_count += len(ids)
        
        # 当新增量达到 10% 时触发索引重建
        if self.insertion_count - self.last_rebuild_count > self.active_collection.count() * 0.1:
            self._trigger_rebuild()
    
    def _trigger_rebuild(self):
        """后台异步重建索引，完成后原子切换"""
        if self.building_collection is not None:
            return  # 已有重建任务在运行
        
        # 创建新的 collection 副本
        self.building_collection = chromadb.Collection(name=f"episodic_v{int(time.time())}")
        
        # 异步任务：重新导入所有数据
        async_rebuild_task = self._rebuild_index_async()
        async_rebuild_task.add_done_callback(self._on_rebuild_complete)
    
    def _on_rebuild_complete(self, future):
        """重建完成后原子切换"""
        if future.exception():
            logger.error("index_rebuild_failed", error=str(future.exception()))
            self.building_collection = None  # 保持使用旧索引
        else:
            # 原子切换
            old_collection = self.active_collection
            self.active_collection = self.building_collection
            self.building_collection = None
            self.last_rebuild_count = self.insertion_count
            
            # 异步删除旧索引
            chromadb.delete_collection(old_collection.name)

# Semantic Store (Neo4j) - 原生图查询支持
class Neo4jSemanticStore:
    """Neo4j 原生图数据库实现
    
    Advantages:
    - Native graph traversal, no precomputed closure tables needed
    - Cypher query language is concise and intuitive
    - Supports vector indexing (Neo4j 5.x+)
    - Built-in multi-hop relationship reasoning
    
    ✅ New: Skill 和 Principle 节点支持反馈追踪
    """
    MAX_QUERY_DEPTH = 3  # 硬限制查询深度，防止递归爆炸
```

---

**关联文档：**
- [系统设计理念](design.md) - 设计哲学和核心概念
- [系统架构](architecture.md) - 整体架构、约束和技术选型
- [核心流程](workflows.md) - 系统如何运作
