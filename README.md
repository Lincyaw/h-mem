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

## 📮 联系方式

- GitHub Issues: [提交问题](https://github.com/Lincyaw/h-mem/issues)
- 作者: Lincyaw

---

**注**: 当前版本处于早期开发阶段，API 可能会有变化。
