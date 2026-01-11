# **核心交互流程 (Core Workflows)**

## **流程 1：热路径 - 两阶段检索 (The Retrieval Loop)**

*场景：Agent 正在生成回复时。支持渐进式返回结果。*

**两阶段设计：**
- **Phase 1 (同步快速检索):** 查询内存缓存 + Bloom Filter，P95 < 50ms
- **Phase 2 (异步深度检索):** 向量相似度 + 图关系查询，P95 < 500ms

用户通过迭代器可选择：
1. 早期中断 - 只使用首批缓存结果（低延迟场景）
2. 完整等待 - 获取所有深度检索结果（高准确率场景）

```mermaid
sequenceDiagram  
    participant U as User  
    participant CM as Context Manager  
    participant RE as Retrieval Engine  
    participant GDB as Semantic (GraphDB)  
    participant VDB as Episodic (VectorDB)  
    participant LLM as Agent Core

    U->>CM: 发送 Query ("帮我写个爬虫")  
    activate CM  
    CM->>CM: 提取元数据 (Time, Intent)  
      
    CM->>RE: 请求记忆 (Query + Meta)  
    activate RE  
      
    par 并行检索  
        RE->>GDB: 搜索实体 & 原则 (Cypher Query)  
        RE->>VDB: 搜索相似历史任务 (Vector Search)  
    end  
      
    GDB-->>RE: 返回 Facts & Principles  
    VDB-->>RE: 返回 Top-K Episodes  
      
    RE->>RE: 重排序 (Score = Sim + Recency + Importance)  
    RE-->>CM: 返回增强上下文 (Augmented Context)  
    deactivate RE  
      
    CM->>LLM: 组装 Prompt (System + Memory + Query)  
    LLM-->>U: 生成回复  
    deactivate CM
```

---

## **流程 2：冷路径 - 巩固与刷新 (The Consolidation Loop)**

*场景：对话结束或系统空闲时。异步执行。*

```mermaid
sequenceDiagram  
    participant Trigger as Scheduler/SessionEnd  
    participant CM as Context Manager  
    participant ENC as Memory Encoder  
    participant CON as Consolidator  
    participant GDB as Semantic (GraphDB)  
    participant VDB as Episodic (VectorDB)

    Trigger->>CM: 触发巩固  
    CM->>ENC: 获取 Session 完整日志  
    activate ENC  
    ENC->>ENC: 提取事实 (Facts) & 事件 (Events)  
    ENC-->>CON: 返回结构化数据  
    deactivate ENC  
      
    activate CON  
    loop 处理每一个 Fact  
        CON->>GDB: 检查是否存在/冲突  
        alt 冲突 (e.g. 偏好变更)  
            GDB->>GDB: 更新节点, 标记旧边为失效  
        else 一致  
            GDB->>GDB: 增加权重 (Reinforce)  
        end  
    end  
      
    loop 处理每一个使用反馈 (Skill/Principle Usage)
        CON->>GDB: 查找被引用的 Skill/Principle
        alt 正向反馈 (成功使用)
            GDB->>GDB: 权重 += delta, 记录成功案例
        else 负向反馈 (失败/无效)
            GDB->>GDB: 权重 -= delta, 记录失败原因
        end
        CON->>CON: 检查是否达到 Refinement 阈值
        alt 反馈数量充足 && 需要优化
            CON->>REF: 触发 Skill/Principle 精炼任务
        end
    end
      
    CON->>VDB: 存入新 Event (Embedding)  
      
    CON->>GDB: 执行遗忘清理 (删除低权重节点)  
    deactivate CON
```

---

## **流程 3：进化路径 - 归纳与哲学提取 (The Induction Loop)**

*场景：定期（如每周）或任务累计 N 次后。*

```mermaid
sequenceDiagram  
    participant SCH as Scheduler  
    participant REF as Deep Reflection Agent  
    participant VDB as Episodic (VectorDB)  
    participant GDB as Semantic (GraphDB)

    SCH->>REF: 触发归纳 (Topic: "Debugging")  
    activate REF  
    REF->>VDB: 聚类获取最近 N 个相似任务  
    VDB-->>REF: 返回 Episode List  
      
    REF->>REF: LLM 分析共性 (Abstraction)  
    Note right of REF: "发现：先写测试再改代码成功率高"  
      
    REF->>GDB: 写入新原则 (Principle Node)  
    Note right of GDB: 创建关系: (Agent)-[FOLLOWS]->(Rule)  
    deactivate REF
```

---

## **流程 4：反馈驱动的权重更新与精炼 (Feedback-Driven Weight Update & Refinement)**

*场景：当 Skill 或 Principle 被使用后，根据使用效果更新权重，并在积累足够反馈后触发精炼。*

```mermaid
sequenceDiagram
    participant Agent as Agent/LLM
    participant CM as Context Manager
    participant CON as Consolidator
    participant GDB as Semantic Store
    participant REF as Deep Reflection Agent

    Note over Agent: Agent 在任务中使用了某个 Skill/Principle
    
    Agent->>CM: 记录使用结果 (成功/失败 + 详细原因)
    CM->>CM: 附加 source_id (指向被使用的 Skill/Principle)
    
    Note over CM: Session 结束，触发巩固
    
    CM->>CON: 提交 Session Log (包含使用反馈)
    activate CON
    
    loop 处理每条 Skill/Principle 使用反馈
        CON->>GDB: 查询对应的 Skill/Principle 节点
        
        alt 正向反馈 (成功)
            CON->>GDB: UPDATE weight += delta_positive
            CON->>GDB: 记录成功案例到 usage_history
            Note right of GDB: 示例: {"timestamp": "...", "outcome": "success", "context": "..."}
        else 负向反馈 (失败/无效)
            CON->>GDB: UPDATE weight -= delta_negative
            CON->>GDB: 记录失败案例和原因到 usage_history
            Note right of GDB: 示例: {"timestamp": "...", "outcome": "failure", "reason": "边界条件未处理"}
        end
        
        CON->>GDB: 查询反馈统计 (总使用次数, 成功率, 权重方差)
        GDB-->>CON: 返回统计数据
        
        alt 达到 Refinement 阈值
            Note over CON: 条件: 使用次数 ≥ 10 且 (成功率 < 60% 或 权重波动大)
            CON->>REF: 触发精炼任务 (传递 Skill/Principle ID + usage_history)
            activate REF
            
            REF->>GDB: 获取所有使用案例 (成功 + 失败)
            GDB-->>REF: 返回详细案例列表
            
            REF->>REF: LLM 分析模式
            Note right of REF: 成功案例的共性？<br/>失败案例的边界条件？<br/>如何改进？
            
            REF->>REF: 生成精炼版本
            Note right of REF: 版本 v2: 添加前置检查，<br/>修正错误逻辑，<br/>添加边界条件处理
            
            REF->>GDB: 创建新版本节点 (version = v2)
            REF->>GDB: 建立溯源关系: v2 -[REFINED_FROM]-> v1
            REF->>GDB: 标记旧版本: deprecated = true, successor_id = v2_id
            
            deactivate REF
        end
    end
    
    deactivate CON
```

**权重更新策略:**

```python
class WeightUpdateStrategy:
    """权重更新策略配置"""
    
    # 权重变化量 (可基于置信度动态调整)
    delta_positive: float = 0.1      # 成功时增加
    delta_negative: float = 0.15     # 失败时减少 (惩罚略大于奖励)
    
    # 权重边界
    weight_min: float = 0.0
    weight_max: float = 10.0
    
    # 自适应调整 (可选)
    adaptive: bool = True
    confidence_multiplier: float = 2.0  # 高置信度时放大变化量
    
    def calculate_delta(self, outcome: str, confidence: float) -> float:
        """计算权重变化量
        
        Args:
            outcome: 'success' or 'failure'
            confidence: 0.0-1.0, 表示使用结果的确定性
        
        Returns:
            权重变化值 (正数表示增加，负数表示减少)
        """
        base_delta = self.delta_positive if outcome == 'success' else -self.delta_negative
        
        if self.adaptive:
            # 高置信度的结果对权重影响更大
            return base_delta * (1 + confidence * self.confidence_multiplier)
        else:
            return base_delta

class RefinementTrigger:
    """Refinement 触发条件配置"""
    
    min_usage_count: int = 10           # 最小使用次数
    min_success_rate: float = 0.6       # 低于此成功率触发精炼
    max_weight_variance: float = 2.0    # 权重方差超过此值触发精炼
    time_window_days: int = 30          # 只考虑最近 N 天的反馈
    negative_feedback_ratio: float = 0.3  # 负反馈占比超过此值优先触发
    
    def should_refine(self, stats: dict) -> tuple[bool, str]:
        """判断是否应触发精炼"""
        if stats['usage_count'] < self.min_usage_count:
            return False, "insufficient_usage"
        
        if stats['negative_ratio'] >= self.negative_feedback_ratio:
            return True, f"high_failure_rate_{stats['negative_ratio']:.1%}"
        
        if stats['success_rate'] < self.min_success_rate:
            return True, f"low_success_rate_{stats['success_rate']:.1%}"
        
        if stats['weight_variance'] > self.max_weight_variance:
            return True, f"unstable_performance_var_{stats['weight_variance']:.2f}"
        
        return False, "stable"
```

---

## **记忆状态流转 (Memory Lifecycle)**

描述信息在系统中如何从瞬时感知转化为持久智慧。

```mermaid
stateDiagram-v2  
    [*] --> SensoryBuffer: 用户输入/环境感知  
      
    state "Working Memory" as WM {  
        SensoryBuffer --> ContextWindow: 注入处理  
        ContextWindow --> MemoryFolding: 容量溢出  
        MemoryFolding --> ContextWindow: 摘要回填  
    }

    ContextWindow --> Consolidation: Session 结束  
      
    state "Long-Term Consolidation" as LC {  
        Consolidation --> FactExtraction: 提取语义  
        Consolidation --> EventEncoding: 提取情景  
          
        FactExtraction --> SemanticStore: 写入/更新  
        EventEncoding --> EpisodicStore: 写入  
    }

    SemanticStore --> Induction: 积累足够样本  
    EpisodicStore --> Induction: 积累足够样本  
      
    state "Evolution" as Evo {  
        Induction --> PrincipleGeneration: 提炼哲学  
        PrincipleGeneration --> SemanticStore: 存回作为指导原则  
    }
```

---

**关联文档：**
- [系统设计理念](design.md) - 设计哲学和核心概念
- [系统架构](architecture.md) - 整体架构、约束和技术选型
- [组件详情](components.md) - 各个组件的职责和实现
- [记忆溯源](provenance.md) - 记忆溯源与层次语义图设计
