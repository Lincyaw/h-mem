# h-mem: 认知型 Agent 记忆系统

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Cognitive Agent Memory System (CAMS)** - 一个基于认知神经科学原理的 AI Agent 记忆系统。

## 🌟 核心特性

- **认知架构**: 基于 Atkinson-Shiffrin 记忆模型的三层架构
  - 感觉记忆 (Sensory Memory)
  - 工作记忆 (Working Memory)
  - 长期记忆 (Long-Term Memory)

- **智能进化**: 不仅记住，更能学习
  - 情景记忆：避免重犯错误
  - 语义记忆：动态更新知识
  - 程序化记忆：提炼可复用技能
  - 跨任务归纳：从经验中提炼智慧

- **Unix 哲学**: 简洁的接口，强大的内部实现
  ```python
  memory = MemorySystem()
  memory.remember("User prefers dark mode")
  results = list(memory.recall("user preferences"))
  ```

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/Lincyaw/h-mem.git
cd h-mem

# 安装依赖（使用 uv）
uv pip install -e .

# 或安装开发依赖
uv pip install -e ".[dev]"
```

### 基础使用

```python
from hmem import MemorySystem

# 创建记忆系统实例
memory = MemorySystem.from_config("config/memory.yaml")

# 存储记忆
memory.remember(
    "User Alice wants to learn Python",
    session_id="session_1"
)

# 检索记忆
for mem in memory.recall("What does Alice want?"):
    print(f"{mem.content} (score: {mem.score})")
```

## 📖 文档

- [设计文档](docs/design.md) - 完整的系统设计方案
- [架构说明](ARCHITECTURE.md) - 代码框架和实施计划
- API 文档 (待完成)

## 🧪 测试驱动开发

本项目采用测试驱动开发（TDD）方式：

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_models.py

# 运行验收测试（对应设计文档）
pytest tests/test_acceptance.py -m acceptance

# 查看测试覆盖率
pytest --cov=src/hmem --cov-report=html
```

### 验收测试

基于设计文档定义的四个标准测试：

1. **Goldfish Test** - 记忆持久性与摘要测试
2. **Don't Repeat Mistakes Test** - 经验复用测试
3. **Change of Mind Test** - 知识更新测试
4. **Sherlock Test** - 哲学归纳测试

## 🏗️ 实施阶段

### Phase 1: MVP 核心（2-3周）
- [x] 基础数据模型和接口定义
- [x] 配置管理系统
- [x] 完整的测试框架
- [ ] 基础 MemorySystem 实现
- [ ] Episodic Store (ChromaDB)
- [ ] 同步巩固机制

### Phase 2: 语义层（3-4周）
- [ ] Semantic Store (SQLite 图数据库)
- [ ] Memory Encoder（事实提取）
- [ ] 冲突检测与解决

### Phase 3: 智能进化（4-6周）
- [ ] Deep Reflection Agent
- [ ] 原则归纳机制
- [ ] 异步巩固

## 🛠️ 技术栈

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| **Vector Store** | ChromaDB | 嵌入式、零配置 |
| **Semantic Store** | SQLite | 单文件、事务支持 |
| **LLM 接口** | LiteLLM | 统一 API |
| **数据模型** | Pydantic | Schema 验证 |
| **测试** | Pytest | 完整的测试覆盖 |
| **类型检查** | Mypy | 严格模式 |

## 📊 项目结构

```
h-mem/
├── src/hmem/              # 源代码
│   ├── models.py          # 数据模型
│   ├── exceptions.py      # 异常定义
│   ├── interfaces.py      # 核心接口
│   └── config.py          # 配置管理
├── tests/                 # 测试代码
│   ├── test_models.py
│   ├── test_interfaces.py
│   └── test_acceptance.py
├── config/                # 配置文件
│   └── memory.yaml
└── docs/                  # 文档
    └── design.md
```

## 🤝 贡献

欢迎贡献！请查看我们的贡献指南。

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

本项目的设计灵感来自：
- Atkinson-Shiffrin 记忆模型
- 认知神经科学的记忆巩固理论
- Unix 设计哲学

● h-mem 记忆系统改进报告

  项目概述

  h-mem 是一个认知代理记忆系统 (Cognitive Agent Memory System)，基于 Atkinson-Shiffrin 记忆模型实现三层记忆架构。本次改进主要解决三个核心问题：

  1. 记忆少时检索不精准 - 召回不相关内容
  2. 记忆时不够智能 - 什么都记进去
  3. 关键词匹配过于粗糙 - 需要全部改为 LLM 智能判断

  ---
  一、核心代码改进

  Phase 1: 移除关键词匹配，全面 LLM 化
  ┌─────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────────┐
  │              文件               │                                               改动                                                │
  ├─────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ src/hmem/hippocampus/encoder.py │ 删除 _infer_outcome_keywords() 和 _extract_tags_keywords() 方法，outcome 和 tags 提取完全依赖 LLM │
  ├─────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ src/hmem/agents/llm.py          │ 增强 infer_outcome() 和 extract_facts() 的 prompt，提高语义理解能力                               │
  └─────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────────┘
  Phase 2: 智能化记忆筛选
  ┌────────────────────────┬──────────────────────────────────────────────────────────────────┐
  │          文件          │                               改动                               │
  ├────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ src/hmem/agents/llm.py │ 新增 assess_memory_importance() 方法，评估内容是否值得记忆       │
  ├────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ src/hmem/models.py     │ 为 SemanticTriple 添加 importance (1-5) 和 confidence (0-1) 字段 │
  └────────────────────────┴──────────────────────────────────────────────────────────────────┘
  Phase 3: 智能化检索过滤
  ┌──────────────────────────────────────────┬──────────────────────────────────────────────────────────────────┐
  │                   文件                   │                               改动                               │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ src/hmem/agents/llm.py                   │ 新增 filter_relevant_memories() 方法，LLM 判断记忆与查询的相关性 │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ src/hmem/hippocampus/retrieval_engine.py │ 新增 _filter_by_relevance() 方法，检索后进行 LLM 相关性过滤      │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ src/hmem/config.py                       │ 新增 enable_relevance_filter 和 min_relevance_score 配置项       │
  └──────────────────────────────────────────┴──────────────────────────────────────────────────────────────────┘
  Phase 4: Q 值冷启动优化
  ┌───────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────┐
  │               文件                │                                        改动                                        │
  ├───────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┤
  │ src/hmem/strategies/q_learning.py │ 基于内容类型设置初始 Q 值：preference=0.7, experience=0.6, fact=0.5, temporary=0.3 │
  └───────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────┘
  ---
  二、评估结果

  创建了 scripts/evaluate_memory.py 评估脚本，测试结果：
  ┌────────────────────────────────────┬────────┐
  │               测试项               │ 准确率 │
  ├────────────────────────────────────┼────────┤
  │ Memory Importance (记忆重要性评估) │ 87.5%  │
  ├────────────────────────────────────┼────────┤
  │ Outcome Inference (结果推理)       │ 100%   │
  ├────────────────────────────────────┼────────┤
  │ Tag Extraction (标签提取)          │ 100%   │
  ├────────────────────────────────────┼────────┤
  │ Retrieval Precision (检索精度)     │ 100%   │
  ├────────────────────────────────────┼────────┤
  │ 总体准确率                         │ 93.8%  │
  └────────────────────────────────────┴────────┘
  ---
  三、Claude Code 自定义命令

  创建了三个 h-mem 相关的 slash commands：
  ┌───────────────┬────────────────────────────────────────┬────────────────────────┐
  │     命令      │                  位置                  │          功能          │
  ├───────────────┼────────────────────────────────────────┼────────────────────────┤
  │ /remember     │ ~/.claude/skills/remember/SKILL.md     │ 手动存储当前对话到记忆 │
  ├───────────────┼────────────────────────────────────────┼────────────────────────┤
  │ /recall       │ ~/.claude/skills/recall/SKILL.md       │ 检索相关记忆           │
  ├───────────────┼────────────────────────────────────────┼────────────────────────┤
  │ /memory-stats │ ~/.claude/skills/memory-stats/SKILL.md │ 显示记忆系统统计信息   │
  └───────────────┴────────────────────────────────────────┴────────────────────────┘
  ---
  四、无感记忆系统

  实现了基于 Claude Code Hooks 的自动记忆机制：

  架构

  Claude Code Session
          │
          │ Stop Hook 触发
          ▼
  ┌─────────────────────────────────────┐
  │  auto_remember.sh (wrapper)         │
  │           │                         │
  │           ▼                         │
  │  auto_remember.py                   │
  │  ┌─────────────────────────────┐    │
  │  │ 1. 读取 session JSONL       │    │
  │  │ 2. 对比 checkpoint          │    │
  │  │ 3. 过滤排除模式             │    │
  │  │ 4. LLM 评估重要性           │    │
  │  │ 5. 存储到 h-mem             │    │
  │  │ 6. 更新 checkpoint          │    │
  │  └─────────────────────────────┘    │
  └─────────────────────────────────────┘
          │
          ▼
      h-mem Storage

  文件清单
  ┌─────────────────────────────────┬───────────────┐
  │              文件               │     说明      │
  ├─────────────────────────────────┼───────────────┤
  │ scripts/hooks/auto_remember.py  │ 主逻辑脚本    │
  ├─────────────────────────────────┼───────────────┤
  │ scripts/hooks/auto_remember.sh  │ Hook 包装脚本 │
  ├─────────────────────────────────┼───────────────┤
  │ scripts/hooks/config.json       │ 配置文件      │
  ├─────────────────────────────────┼───────────────┤
  │ ~/.claude/settings.json         │ Hook 注册     │
  ├─────────────────────────────────┼───────────────┤
  │ ~/.claude/h-mem-checkpoint.json │ 处理进度记录  │
  └─────────────────────────────────┴───────────────┘
  配置选项

  {
    "enabled": true,
    "min_content_length": 100,
    "max_message_length": 2000,
    "exclude_patterns": ["^ls ", "^cd ", "^pwd$", "^git status$"],
    "importance_threshold": 3,
    "auto_filter": true
  }

  工作流程

  1. 会话结束时 Stop hook 触发
  2. 读取 ~/.claude/projects/<hash>/<session>.jsonl
  3. 对比 checkpoint，提取新增条目
  4. 过滤简单命令 (ls, cd 等)
  5. LLM 评估重要性 (importance >= 3 才存储)
  6. 调用 MemorySystem.remember() 存储
  7. 更新 checkpoint 避免重复处理

  ---
  五、Bug 修复
  ┌──────────────────────────────────────┬────────────────────────────┐
  │                 问题                 │            修复            │
  ├──────────────────────────────────────┼────────────────────────────┤
  │ MemorySystem 没有 initialize() 方法  │ 移除调用，构造时自动初始化 │
  ├──────────────────────────────────────┼────────────────────────────┤
  │ MemorySystem 没有 store() 方法       │ 改用 remember() 同步 API   │
  ├──────────────────────────────────────┼────────────────────────────┤
  │ 脚本使用 async/await 但 API 是同步的 │ 移除所有 async/await       │
  └──────────────────────────────────────┴────────────────────────────┘
  ---
  六、总结

  本次改进实现了：

  1. 全面 LLM 化 - 移除所有关键词匹配，依赖语义理解
  2. 智能筛选 - 只记忆重要内容，避免过度记忆
  3. 精准检索 - LLM 相关性过滤，记忆少时不返回不相关内容
  4. 无感记忆 - 基于 Hooks 自动记忆，无需手动操作
  5. 自定义命令 - /remember, /recall, /memory-stats 便于手动控制