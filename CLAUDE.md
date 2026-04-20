# LLM Wiki Schema - AI 操作手册

> **版本**: 1.0.0
> **最后更新**: 2026-04-15
> **适用**: Claude Code / GPT-4 / 其他 LLM 编程助手

---

## 🎯 核心理念

**类比**: Obsidian 是 IDE，LLM 是程序员，wiki 是编译后的代码库。

- **你（Human）**: 筛选资料、定方向、审质量、迭代规则
- **我（LLM）**: 总结提取、建立关联、归档格式、严格按规则执行

---

## 📁 项目结构

```
my-wiki/
├── raw/                    # 原始层：只读、不可变、事实基准
│   ├── articles/          # 网页剪藏、博客文章
│   ├── papers/            # 学术论文、技术报告
│   ├── assets/            # 图片、附件（本地存储）
│   └── _meta.json         # 原始资料元数据索引
│
├── wiki/                   # 知识层：我（LLM）全权维护
│   ├── concepts/          # 概念页（术语、方法、原理）
│   ├── entities/          # 实体页（人物、公司、项目、论文）
│   ├── comparisons/       # 对比页（横向对比、优劣分析）
│   ├── sources/           # 资料摘要页（raw 文件的摘要）
│   ├── index.md           # 主页、目录树
│   ├── _log.md            # 变更日志
│   ├── _graph.json        # 知识图谱数据
│   └── _dependencies.json # 页面依赖关系图
│
├── scripts/                # 工具层：自动化脚本
│   ├── ingest.py          # 录入工作流
│   ├── update.py          # 更新工作流
│   ├── query.py           # 查询工具
│   ├── healthcheck.py     # 体检工具
│   ├── dedup.py           # 去重检测与合并
│   ├── classify.py        # 实体分类与概念归并
│   └── llm_client.py      # LLM API 客户端
│
└── CLAUDE.md               # 本文件：Schema 层（我的操作手册）
```

---

## 🏷️ 分类体系

### 实体分类 (entity_type)

| 类型 | 标识 | 说明 | 示例 |
|------|------|------|------|
| 👤 人物 | `person` | 研究者、工程师、创始人 | Karpathy, Hinton |
| 🏢 组织/公司 | `organization` | 公司、研究机构、大学 | OpenAI, DeepMind |
| 🤖 模型/产品 | `model` | AI 模型或产品名称 | GPT-4, Claude, Gemini |
| 🧠 算法/架构 | `algorithm` | 神经网络架构、算法 | Transformer, GRU, MoE |
| 📊 数据集 | `dataset` | 公开数据集、基准测试 | BDD100K, nuScenes |
| 📚 会议/期刊 | `venue` | 学术出版场所 | NeurIPS, CVPR, arXiv |
| 🔧 工具/框架 | `tool` | 软件工具、开发框架 | PyTorch, Zotero, LaTeX |
| 📦 项目/系统 | `project` | 开源项目、软件系统 | CARLA, SUMO, llama.cpp |
| 🖥️ 硬件/设备 | `hardware` | 硬件设备、芯片 | Jetson Nano, H100 |

### 概念分类 (concept_category)

| 类别 | 标识 | 说明 | 示例 |
|------|------|------|------|
| 🔬 方法/技术 | `method` | 具体技术方法、算法变体 | RLHF, LoRA, RAG |
| 📐 原理/定律 | `principle` | 理论基础、数学原理 | Scaling Law, Lyapunov稳定性 |
| 🔄 范式/框架 | `paradigm` | 研究范式、架构模式 | Agentic Protocol, 多Agent协作 |
| 📏 指标/评估 | `metric` | 评估指标、度量方法 | BLEU, 困惑度 |
| 🌊 现象/效应 | `phenomenon` | 观察到的现象 | 涌现能力, 幻觉问题 |
| 🎯 领域/方向 | `domain` | 研究领域、应用方向 | 自动驾驶, 具身智能 |

### 分类规则

1. **算法/架构归入实体**：Transformer, GRU, LSTM, MoE 等应标为 `entity.algorithm`，不要放入 concepts
2. **概念命名规范**：同一概念的中英文只保留一个规范名（优先英文缩写，如 RAG 而非"检索增强生成"）
3. **避免重复**：如果 GPT-4 已提取为 entity，不要再在 concepts 中出现
4. **使用 `aliases` 字段**记录同义词：如 RAG 页面的 `aliases: [检索增强生成]`

---

## ✍️ 页面规范

### 1️⃣ 文件命名规则

- **小写字母 + 中横线**: `transformer-architecture.md` ❌ `Transformer_Architecture.md`
- **无空格、无特殊字符**
- **语义化名称**: 反映页面核心内容
- **长度建议**: 3-5 个单词

### 2️⃣ Frontmatter 规范（必须）

每个 wiki 页面**必须**包含 YAML frontmatter：

```yaml
---
title: "页面标题"
type: concept | entity | comparison | source
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
confidence: high | medium | low  # 信息可信度
sources:
  - raw/articles/xxx.md
  - raw/papers/yyy.pdf
tags:
  - tag1
  - tag2
related:
  - [[相关概念1]]
  - [[相关概念2]]
status: draft | reviewed | archived
---
```

#### 字段说明：

| 字段 | 必填 | 说明 |
|------|------|------|
| title | ✅ | 显示标题，可包含中文 |
| type | ✅ | 页面类型：concept/entity/comparison/source |
| created | ✅ | 创建日期 |
| updated | ✅ | 最后更新日期 |
| confidence | ✅ | 可信度：high(确认)/medium(需验证)/low(存疑) |
| sources | ✅ | 引用的原始资料路径列表 |
| tags | ✅ | 标签数组，用于分类和搜索 |
| related | ✅ | 双向链接数组 |
| status | ✅ | 状态：draft(草稿)/reviewed(已审核)/archived(归档) |

### 3️⃣ 内容章节规范

#### 概念页模板 (`wiki/concepts/_template.md`)

```markdown
---
title: "[概念名称]"
type: concept
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
confidence: high
sources: []
tags: []
related: []
status: draft
---

# [概念名称]

## 定义
[一句话定义，清晰简洁]

## 核心原理
[详细解释工作原理、关键机制]

## 关键特性
- 特性 1
- 特性 2
- 特性 3

## 发展历程
[时间线或演进过程]

## 应用场景
- 场景 1
- 场景 2

## 与其他概念的关系
- **[[相关概念A]]**: [关系描述]
- **[[相关概念B]]**: [关系描述]

## 优缺点
### 优点
- ...

### 缺点
- ...

## 参考来源
- [来源1](raw/path/to/file)
- [来源2](raw/path/to/file)

---
*最后更新: YYYY-MM-DD*
```

#### 实体页模板 (`wiki/entities/_template.md`)

```markdown
---
title: "[实体名称]"
type: entity
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
confidence: high
sources: []
tags: [person/company/project/paper]
entity_type: person | organization | model | algorithm | dataset | venue | tool | project | hardware
related: []
status: draft
---

# [实体名称]

## 基本信息
- **类型**: 人物/组织/模型/算法/数据集/会议期刊/工具/项目/硬件
- **成立/出生日期**: [日期]
- **地点**: [地点]
- **官网/GitHub**: [链接]

## 简介
[2-3段详细简介]

## 主要贡献/成就
1. 贡献 1
2. 贡献 2
3. 贡献 3

## 相关概念
- **[[概念A]]**: [关联说明]
- **[[概念B]]**: [关联说明]

## 重要时间线
- **YYYY-MM**: [事件]
- **YYYY-MM**: [事件]

## 参考资料
- [来源1](raw/path/to/file)

---
*最后更新: YYYY-MM-DD*
```

#### 对比页模板 (`wiki/comparisons/_template.md`)

```markdown
---
title: "[对比主题]"
type: comparison
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
confidence: high
sources: []
tags: []
related: []
status: draft
---

# [对比主题]: A vs B vs C

## 对比维度总览

| 维度 | [[A]] | [[B]] | [[C]] |
|------|-------|-------|-------|
| 维度1 | ... | ... | ... |
| 维度2 | ... | ... | ... |
| 维度3 | ... | ... | ... |

## 详细分析

### 性能表现
[各方案的性能对比]

### 适用场景
- **A 适合**: ...
- **B 适合**: ...
- **C 适合**: ...

### 成本考量
[成本分析]

### 生态成熟度
[生态系统对比]

## 选择建议
[根据不同需求给出推荐]

## 总结
[一句话总结]

---
*最后更新: YYYY-MM-DD*
```

---

## 🔧 工作流规范

### 📥 Ingest（资料录入）

**触发条件**: 用户说 "Ingest raw/xxx.md" 或新增 raw 文件时

**执行步骤**:

1. **读取原始文件**
   ```bash
   读取 raw/articles/xxx.md 或 raw/papers/xxx.pdf
   ```

2. **生成摘要页**
   - 创建 `wiki/sources/xxx.md`
   - 包含：核心观点、关键数据、方法论、局限性
   - 提取所有实体和概念

3. **识别并处理实体**
   - 扫描出所有实体（人名、公司名、项目名、论文名）
   - 对每个实体：
     - 如果存在 → 更新页面，添加新信息
     - 如果不存在 → 创建新实体页（使用实体模板）

4. **识别并处理概念**
   - 扫描出所有专业术语、方法、原理
   - 对每个概念：
     - 如果存在 → 补充新的应用场景、案例
     - 如果不存在 → 创建新概念页（使用概念模板）

5. **添加双向链接**
   - 在所有相关页面添加 `[[link]]`
   - 更新 frontmatter 的 `related` 字段

6. **更新索引**
   - 更新 `wiki/index.md` 添加新条目
   - 记录到 `wiki/_log.md`

7. **更新元数据**
   - 更新 `raw/_meta.json`
   - 更新 `wiki/_graph.json`
   - 更新 `wiki/_dependencies.json`

**质量标准**:
- ✅ 摘要覆盖原文 80%+ 核心信息
- ✅ 所有专有名词都有对应页面
- ✅ 双向链接完整无遗漏
- ✅ frontmatter 格式正确

---

### 🔄 Update（知识维护）

**触发条件**:
- 新增 raw 文件后自动触发
- 用户说 "Update [[某个概念]]"
- 定期体检发现问题时

**执行逻辑**:

#### 级联更新机制

```
新增 raw/papers/new-paper.pdf
    ↓
1. 创建 wiki/sources/new-paper.md
    ↓
2. 识别涉及的概念: [MoE, Transformer, GPT-4]
    ↓
3. 对每个概念执行:
   ├─ 读取 wiki/concepts/moe.md
   ├─ 追加 new-paper 的发现
   ├─ 更新 sources 列表
   ├─ 添加 [[new-paper]] 链接
   └─ 标记 updated 时间
    ↓
4. 识别涉及的实体: [OpenAI, Researcher-X]
    ↓
5. 对每个实体执行类似更新
    ↓
6. 检查是否需要新建对比页
    ↓
7. 全局一致性检查
```

**更新策略**:
- **增量追加**: 在原有内容基础上补充，不删除旧信息
- **版本标记**: 重要变更在 _log.md 记录
- **冲突标注**: 发现矛盾时用 `> ⚠️ **冲突注意**: ...` 标注
- **过时标记**: 被新信息覆盖的内容用 `~~删除线~~` 标记

---

### 🔍 Query（智能查询）

**触发条件**: 用户提问时

**查询优先级**:

1. **先查 Wiki**（结构化知识）
   ```
   搜索 wiki/ 目录下相关页面
   优先匹配 title/tags/related
   ```

2. **必要时回查 Raw**（原始证据）
   ```
   当 wiki 信息不足或需要精确引用时
   读取对应的 raw/ 文件获取细节
   ```

**回答格式要求**:

```markdown
## 回答内容

[基于 wiki 结构化知识的回答]

### 详细依据
- 见 [[概念A]]: [简要引用]
- 见 [[实体B]]: [简要引用]

### 原始来源
- 来源1: [raw/path/to/file](具体段落或页码)
- 来源2: [raw/path/to/file](具体段落或页码)

---
*置信度: high/medium/low*
```

**特殊情况处理**:
- **信息缺失**: 明确告知 "当前知识库暂无此信息"，建议补充资料
- **矛盾信息**: 列出不同来源的冲突点，给出判断
- **低置信度**: 标注 confidence: low，建议人工审核

---

### 🏥 Health Check（系统体检）

**触发条件**:
- 用户说 "Health check" 或 "体检"
- 大规模更新后
- 定期（建议每周一次）

**检查项目清单**:

#### 1. 一致性检查 ⭐⭐⭐
- [ ] **矛盾检测**: 同一事实在不同页面描述不一致
  - 示例: A页说"GPT-4有1.8T参数"，B页说"1.7T参数"
  - 处理: 标注冲突，建议回查原始资料验证
  
- [ ] **过时检测**: 内容被新资料覆盖或推翻
  - 检查 updated 日期 vs sources 日期
  - 标记可能过时的内容

#### 2. 完整性检查 ⭐⭐
- [ ] **断链检测**: `[[link]]` 指向不存在的页面
  - 扫描所有 .md 文件中的 `[[]]` 链接
  - 列出失效链接
  
- [ ] **孤立页面检测**: 没有任何页面链接到的孤儿页
  - 分析 _graph.json 入度为0的节点
  - 判断是否应该被关联或合并

- [ ] **Frontmatter 缺失**: 缺少必要字段
  - 检查每个 .md 文件的 frontmatter
  - 补充缺失字段

#### 3. 质量检查 ⭐
- [ ] **重复内容检测**: 相似度过高的页面
  - 对比页面内容相似度
  - 建议合并重复项
  
- [ ] **标签规范化**: 标签命名不统一
  - 统一大小写、单复数、中英文
  - 建立标签词表

- [ ] **来源有效性**: sources 引用的 raw 文件存在性
  - 验证所有 source 路径有效

#### 4. 结构优化 💡
- [ ] **索引完整性**: index.md 是否包含所有页面
- [ ] **分类合理性**: 页面是否放在正确的目录
- [ ] **图谱健康度**: _graph.json 连通性分析

**输出格式**:

```markdown
# 健康检查报告

**检查时间**: YYYY-MM-DD HH:MM
**统计概览**:
- 总页面数: XX
- 问题数: XX (严重: X / 一般: X / 建议: X)

## 🚨 严重问题 (需立即修复)

### 1. [问题描述]
- **位置**: wiki/xxx.md
- **详情**: ...
- **建议修复**: ...

## ⚠️ 一般问题 (建议尽快处理)

### 1. [问题描述]
...

## 💡 优化建议 (可选改进)

### 1. [建议]
...

## 📊 统计数据
- 概念页: XX
- 实体页: XX
- 对比页: XX
- 来源页: XX
- 平均置信度: XX%
- 覆盖领域: XX 个

---
*下次检查建议时间: YYYY-MM-DD*
```

---

## 🎨 写作风格指南

### 语言要求
- **中文为主**: 使用简体中文
- **专业术语**: 首次出现时附英文原文，如：Transformer（变换器）
- **避免口语化**: 不用"我觉得"、"大概"等模糊表达
- **客观中立**: 呈现事实，区分事实与观点

### 格式要求
- **标题层级**: 最多 4 级（# ~ ####）
- **列表**: 优先使用有序列表（步骤）和无序列表（要点）
- **代码块**: 必须标注语言类型
- **强调**: 使用 **粗体** 强调关键词，不用斜体
- **链接**: 统一使用 `[[双向链接]]` 格式

### 内容深度
- **概念页**: 适合有技术背景的读者，深入但不晦涩
- **实体页**: 信息丰富但结构清晰，便于快速浏览
- **对比页**: 数据驱动，表格为主，辅以文字分析

---

## 📊 元数据管理

### raw/_meta.json 格式

```json
{
  "version": "1.0",
  "last_updated": "2026-04-15",
  "statistics": {
    "total_files": 42,
    "articles": 30,
    "papers": 10,
    "assets": 2
  },
  "files": [
    {
      "id": "article-001",
      "path": "raw/articles/llm-trends-2024.md",
      "filename": "llm-trends-2024.md",
      "type": "article",
      "size_bytes": 15234,
      "added_date": "2026-04-15",
      "source_url": "https://example.com/article",
      "title": "LLM Trends in 2024",
      "authors": ["Author Name"],
      "language": "zh-CN",
      "tags": ["LLM", "trends", "2024"],
      "processed": true,
      "wiki_source_page": "wiki/sources/llm-trends-2024.md",
      "extracted_concepts": ["transformer", "scaling-law"],
      "extracted_entities": ["OpenAI", "Google"]
    }
  ]
}
```

### wiki/_graph.json 格式

```json
{
  "nodes": [
    {
      "id": "transformer",
      "path": "wiki/concepts/transformer.md",
      "type": "concept",
      "label": "Transformer"
    }
  ],
  "edges": [
    {
      "source": "transformer",
      "target": "attention-mechanism",
      "relation": "uses",
      "weight": 1
    }
  ]
}
```

### wiki/_dependencies.json 格式

```json
{
  "wiki/concepts/moe.md": {
    "depends_on": [
      "wiki/sources/paper-moe-2024.md",
      "wiki/entities/deepmind.md"
    ],
    "dependents": [
      "wiki/comparisons/moe-vs-dense.md"
    ],
    "last_updated": "2026-04-15"
  }
}
```

---

## 🚫 禁止事项

1. **❌ 修改 raw/ 目录下的任何文件** - 原始资料不可变
2. **❌ 删除 wiki/ 页面内容** - 只能追加或标记过时
3. **❌ 创建无 source 的页面** - 每个页面必须有原始来源
4. **❌ 使用外部链接** - 所有资源本地化到 raw/assets/
5. **❌ 省略 frontmatter** - 即使是草稿也必须有完整元数据
6. **❌ 主观臆断** - 区分事实与推测，标注置信度
7. **❌ 忽略冲突** - 发现矛盾必须明确标注

---

## 📈 最佳实践

### 高效录入技巧
1. **批量处理**: 一次性放入多个 raw 文件，批量 ingest
2. **优先级排序**: 先录入高价值资料（论文 > 技术文章 > 博客）
3. **增量更新**: 新资料只触发相关页面更新，不全量重建

### 质量保证
1. **交叉验证**: 重要事实至少两个独立来源
2. **定期审查**: 每周运行 health check
3. **版本对比**: 利用 Git diff 追踪变化

### 知识组织
1. **粒度适中**: 一个概念一页，不要过于碎片化
2. **层次清晰**: 用子目录组织相关概念群
3. **适度冗余**: 关键信息可在多个页面适当重复

---

## 🆘 故障排除

### 常见问题

**Q: 新增 raw 文件后没有触发更新？**
A: 手动运行 `python scripts/ingest.py raw/filename.md`

**Q: 发现页面内容矛盾？**
A: 在两处都用 `> ⚠️ **冲突注意**` 标注，记录到 _log.md，建议用户审核

**Q: 双向链接失效？**
A: 运行 `python scripts/healthcheck.py --fix-links` 自动修复

**Q: 如何重建整个 wiki？**
A: 从 raw/ 重新 ingest 所有文件（保留 Git 历史即可回滚）

---

## 📝 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| 1.0.0 | 2026-04-15 | 初始版本，完成核心规范定义 |

---

*本 Schema 由 Human 定义，由 LLM 严格执行。如需修改规则，请通知 AI 并更新本文档。*
