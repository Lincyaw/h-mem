# **认知型 Agent 记忆系统 (CAMS) - 设计文档导航**

欢迎来到 h-mem（认知型 Agent 记忆系统）的完整设计文档。本系统基于认知神经科学，为 AI Agent 提供类似人类大脑的记忆管理能力。

---

## **📚 文档导航**

### **入门必读**

1. **[系统设计理念 - 完整版](design-philosophy.md)** ⭐
   - 了解系统的核心设计哲学
   - 认知神经科学基础 (Atkinson-Shiffrin 模型)
   - 系统解决的核心问题
   - Unix 哲学在设计中的体现

2. **[系统架构与约束](architecture.md)**
   - 三层架构设计 (感知层 → 处理层 → 存储层)
   - 系统性能边界和 SLA 定义
   - 技术选型和实施阶段规划

### **深入理解**

3. **[组件详情与职责](components.md)**
   - 5 大核心组件的详细说明
   - 事务管理和并发控制
   - 事件溯源架构设计

4. **[核心交互流程](workflows.md)** 
   - 4 个核心工作流程
   - 热路径 (检索)、冷路径 (巩固)、进化路径 (反思)
   - 反馈驱动的权重更新机制

5. **[记忆溯源与层次图谱](provenance.md)**
   - 记忆的完整生命周期
   - 多层级记忆关联架构
   - 溯源链应用场景分析

### **API 与测试**

6. **[关键接口定义](interfaces.md)**
   - 核心数据模型 (Memory, Event, Principle, Skill 等)
   - 异常定义
   - MemorySystem 核心 API

7. **[系统验收方案](acceptance-testing.md)**
   - 4 个标准化测试用例
   - "Goldfish Test", "Don't Repeat Mistakes Test", "Change of Mind Test", "Sherlock Test"
   - pytest 实现框架

### **高级话题**

8. **[可观测性设计](observability.md)**
   - 关键指标 (性能、容量、成本、质量)
   - 结构化日志和追踪
   - 自适应阈值管理
   - 预测性预取机制

9. **[设计哲学 - Unix 原则](design-philosophy.md)**
   - "Do One Thing Well": 接口最小化
   - "Rule of Silence": 配置驱动
   - "Rule of Modularity": 组件可替换
   - "Rule of Transparency": 可观测性内置

### **参考资料**

10. **[实现改进与演进历史](implementation-history.md)** 📝
    - 反馈机制完整实现
    - Neo4j 语义存储迁移
    - 历史决策记录和教训
