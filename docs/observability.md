# **可观测性设计 (Observability)**

确保系统可监控、可调试、可优化。

## **关键指标 (Metrics)**

### **性能指标**
- `memory.retrieve.latency` (Histogram): 检索延迟分布 (P50/P95/P99)
- `memory.retrieve.throughput` (Counter): 每秒检索次数
- `memory.consolidate.duration` (Histogram): 巩固耗时
- `memory.consolidate.success_rate` (Gauge): 巩固成功率

### **容量指标**
- `memory.episodic.count` (Gauge): 情景记忆总数
- `memory.semantic.node_count` (Gauge): 语义图节点数
- `memory.semantic.edge_count` (Gauge): 关系边数

### **成本指标**
- `memory.llm.tokens_consumed` (Counter): LLM Token 消耗
- `memory.llm.cost_usd` (Counter): LLM 费用(美元)

### **质量指标**
- `memory.retrieval.recall` (Gauge): 检索召回率(需定期评估)
- `memory.consolidation.conflicts` (Counter): 冲突次数

---

## **结构化日志 (Structured Logging)**

使用 `structlog` 实现全链路追踪:

```python
import structlog

logger = structlog.get_logger()

# 每次操作分配 trace_id
trace_id = str(uuid.uuid4())

logger.info(
    "memory_retrieve_start",
    trace_id=trace_id,
    query=query,
    user_id=user_id
)

# ... 执行检索 ...

logger.info(
    "memory_retrieve_complete",
    trace_id=trace_id,
    results_count=len(results),
    latency_ms=elapsed * 1000,
    sources={"episodic": 3, "semantic": 2}
)
```

**日志字段标准:**
- `trace_id`: 贯穿整个操作链路
- `session_id`: 会话标识
- `user_id`: 用户标识
- `component`: 组件名称 (retrieval/consolidation/reflection)
- `duration_ms`: 操作耗时

---

## **监控端点 (Monitoring Endpoints)**

提供 Prometheus 兼容的 metrics 端点:

```python
from prometheus_client import Counter, Histogram, Gauge

retrieve_latency = Histogram(
    'memory_retrieve_latency_seconds',
    'Retrieval latency in seconds',
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
)

consolidate_success = Counter(
    'memory_consolidate_total',
    'Total consolidation attempts',
    ['status']  # success/failure
)

episodic_count = Gauge(
    'memory_episodic_total',
    'Total episodic memories'
)
```

---

## **质量监控 (Quality Assurance)**

### **Golden Dataset 回归测试**

建立人工标注的标准查询集，确保代码变更不破坏检索质量：

```python
class MemoryQualityMonitor:
    """记忆质量监控"""
    
    def check_retrieval_quality(self):
        """检查检索准确率 - 基于 Golden Dataset"""
        golden_dataset = load_golden_queries()  # 至少 100 条人工标注
        
        # 细分统计：按记忆类型、时间跨度、主题分布
        stats = {
            "episodic": {"total": 0, "correct": 0},
            "semantic": {"total": 0, "correct": 0},
            "skill": {"total": 0, "correct": 0}
        }
        
        for query, expected_memories, memory_type in golden_dataset:
            results = list(memory_system.recall(query, limit=5))
            if self._has_overlap(results, expected_memories):
                stats[memory_type]["correct"] += 1
            stats[memory_type]["total"] += 1
        
        # 计算各类型召回率
        for mem_type, stat in stats.items():
            recall = stat["correct"] / stat["total"] if stat["total"] > 0 else 0
            logger.info("recall_by_type", type=mem_type, recall=recall)
            
            # 低于最低可接受标准(80%)触发告警
            if recall < 0.80:
                alert_ops(f"CRITICAL: {mem_type} recall dropped to {recall:.2%}")
            # 低于期望目标(85%)发出警告
            elif recall < 0.85:
                logger.warn(f"WARNING: {mem_type} recall below target: {recall:.2%}")
    
    def check_graph_health(self):
        """检查语义图健康度"""
        # 检测孤立节点、环路、权重异常等
        orphan_nodes = db.query("SELECT * FROM nodes WHERE degree = 0")
        if len(orphan_nodes) > 100:
            logger.warn("graph_orphans", count=len(orphan_nodes))
```

### **CI/CD 集成**

```yaml
# .github/workflows/quality-gate.yml
- name: Golden Dataset Regression
  run: |
    pytest tests/test_golden_dataset.py --strict
    # 如果召回率下降 >5%，阻止合并
```

---

## **因果追踪与诊断 (Causal Tracing)**

当检索质量下降时，需要快速定位瓶颈环节：

```python
class RetrievalTracer:
    """检索全链路追踪"""
    
    def trace_recall(self, query: str, trace_id: str):
        """记录每个环节的耗时和结果"""
        trace = {
            "trace_id": trace_id,
            "query": query,
            "stages": []
        }
        
        # Stage 1: Query 编码
        start = time.time()
        embedding = self.embed(query)
        trace["stages"].append({
            "name": "embedding",
            "duration_ms": (time.time() - start) * 1000,
            "output_dim": len(embedding)
        })
        
        # Stage 2: 向量检索
        start = time.time()
        vector_results = self.vector_db.search(embedding, k=20)
        trace["stages"].append({
            "name": "vector_search",
            "duration_ms": (time.time() - start) * 1000,
            "candidates": len(vector_results)
        })
        
        # Stage 3: 图扩展
        start = time.time()
        graph_results = self.graph_db.expand(vector_results)
        trace["stages"].append({
            "name": "graph_expansion",
            "duration_ms": (time.time() - start) * 1000,
            "additional": len(graph_results) - len(vector_results)
        })
        
        # Stage 4: 重排序
        start = time.time()
        final_results = self.reranker.rank(vector_results + graph_results)
        trace["stages"].append({
            "name": "reranking",
            "duration_ms": (time.time() - start) * 1000,
            "final_count": len(final_results)
        })
        
        # 记录完整 trace
        logger.info("retrieval_trace", **trace)
        return final_results
```

**Grafana 可视化:**
- P99 延迟分解图：显示每个 stage 的耗时占比
- 召回率下降时自动高亮异常 stage
- Canary 查询：每小时执行固定查询集，监控趋势

### **监控频率**
- 实时指标: 每次操作更新
- 质量检查: 每日定时执行
- 容量报警: 达到 80% 上限时触发

---

## **元认知机制 (Meta-Cognitive Mechanisms)**

系统对自身记忆质量的自我评估和自适应优化。

### **自适应检索阈值 (Adaptive Retrieval Threshold)**

**问题:** 固定的 `score_threshold=0.5` 无法适应不同场景。过高导致漏召，过低导致噪声。

**解决方案:** 跟踪检索结果的"有效性"，动态调整阈值。

```python
class AdaptiveThresholdManager:
    """检索阈值自适应管理器
    
    effectiveness 度量方法:
    1. 显式引用检测 (可靠但不全面):
       - 检查LLM输出是否包含记忆的关键词
       - 使用简单的TF-IDF匹配
    
    2. 隐式评估 (实验性):
       - 对比"有记忆"vs"无记忆"的回复质量
       - 需要人工标注或用户反馈
    
    当前实现: 仅使用方法1 (保守但可靠)
    """
    
    def __init__(self, initial_threshold: float = 0.5):
        self.threshold = initial_threshold
        self.effectiveness_tracker = []  # (query, threshold, effectiveness)
    
    def track_effectiveness(
        self,
        query: str,
        results: List[Memory],
        llm_output: str,
        feedback: Optional[float] = None  # 可选的用户反馈 (0-1)
    ):
        """记录检索结果的实际使用情况"""
        if feedback is not None:
            # 优先使用真实反馈
            effectiveness = feedback
        else:
            # 退化到启发式检测
            used_count = self._detect_explicit_references(results, llm_output)
            effectiveness = used_count / len(results) if results else 0
    
    def recalibrate(self):
        """每日重新校准阈值"""
        if len(self.effectiveness_tracker) < 50:
            return  # 样本不足
        
        recent = self.effectiveness_tracker[-100:]  # 最近 100 次查询
        avg_effectiveness = sum(r["effectiveness"] for r in recent) / len(recent)
        
        # 目标: 有效性 > 60%
        if avg_effectiveness < 0.6:
            # 提高阈值，过滤低质量结果
            self.threshold = min(0.8, self.threshold + 0.05)
            logger.info("threshold_increased", new=self.threshold, reason="low_effectiveness")
        elif avg_effectiveness > 0.8:
            # 降低阈值，增加召回
            self.threshold = max(0.3, self.threshold - 0.05)
            logger.info("threshold_decreased", new=self.threshold, reason="high_effectiveness")
```

### **预测性记忆预取 (Predictive Prefetching)**

基于会话上下文预测下一步可能的查询，预热相关记忆到缓存。

```python
class PredictivePrefetcher:
    """预测性记忆预取器"""
    
    def observe_query(self, session_id: str, query: str):
        """观察查询，预测并预取下一步"""
        predicted_queries = self.ngram_model.predict_next(session_id, top_k=3)
        
        # 异步预取(不阻塞当前查询)
        for pred_query, confidence in predicted_queries:
            if confidence > 0.3:
                asyncio.create_task(self._prefetch(pred_query))
```

**性能效果:**
- 缓存命中时: P50 < 10ms（相比常规的 500ms 提升 50 倍）
- 命中率: 30-40%（基于 bigram 模型）

---

**关联文档：**
- [系统设计理念](design.md) - 设计哲学和核心概念
- [系统架构](architecture.md) - 整体架构、约束和技术选型
