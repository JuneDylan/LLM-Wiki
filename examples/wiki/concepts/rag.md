---
title: "RAG（检索增强生成）"
type: concept
created: "2026-04-20"
updated: "2026-04-20"
confidence: high
sources: ["raw/dialogues/demo-rag-intro.md"]
tags: [method]
related: [Embedding, 向量数据库, 幻觉问题, 多跳推理, 重排序]
status: draft
---

# RAG（检索增强生成）

## 定义
RAG（Retrieval-Augmented Generation）是一种将外部知识检索与大语言模型生成能力结合的技术范式。它在生成回答前，先从知识库中检索相关文档片段，将这些片段作为上下文注入 prompt，从而让模型基于事实而非纯参数记忆进行生成。

## 核心原理
RAG 的核心流程分为三个阶段：

1. **索引（Indexing）**：原始文档经过切分（Chunking）、嵌入（Embedding）后存入向量数据库
2. **检索（Retrieval）**：用户查询被编码为向量，通过近似最近邻搜索（ANN）召回 top-k 相关片段
3. **生成（Generation）**：将检索到的片段与原始问题拼接为增强 prompt，送入 LLM 生成最终回答

这一架构本质上是用检索模块替代了传统 fine-tuning 中"把知识写入模型参数"的思路，实现了知识的动态更新和来源可追溯。

## 关键特性
- **知识动态更新**：无需重新训练模型，更新向量库即可反映最新信息
- **可溯源性**：每个回答都可以追溯到具体的参考文档片段
- **幻觉抑制**：模型生成被约束在检索到的上下文范围内，大幅降低虚构事实的概率
- **成本可控**：相比全量 fine-tuning，RAG 的部署和迭代成本显著更低

## 应用场景
- 企业知识库问答（基于内部文档的客服/助手）
- 个人笔记智能检索（Obsidian / Notion + 本地向量库）
- 学术论文辅助阅读（基于论文集合的专题问答）
- 法律法规查询（需要严格来源引用的场景）

## 与其他概念的关系
- **[[Embedding]]**: RAG 的检索依赖 embedding 模型将文本映射到语义空间
- **[[向量数据库]]**: 存储和检索 embedding 的基础设施
- **[[Fine-tuning]]**: 与 RAG 互补的知识注入方式；RAG 适合频繁更新的知识，fine-tuning 适合固化行为模式
- **[[多跳推理]]**: RAG 的单次检索难以解决需要跨文档推理的复杂问题，需结合 Agent 或图检索增强

## 优缺点
### 优点
- 部署快、成本低、知识更新灵活
- 天然支持来源引用，适合高可信场景
- 与现有 LLM API 兼容，无需模型改动

### 缺点
- 检索质量是天花板，bad retrieval 会导致错误放大
- 长文档的切分策略（chunk size / overlap）需要大量调优
- 跨文档的关联推理能力弱于参数化知识

## 参考来源
- [demo-rag-intro.md](raw/dialogues/demo-rag-intro.md)
