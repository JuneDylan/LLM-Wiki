---
title: "Embedding（嵌入）"
type: concept
created: "2026-04-20"
updated: "2026-04-20"
confidence: high
sources: ["raw/dialogues/demo-rag-intro.md"]
tags: [method]
related: [RAG, 向量数据库, 语义搜索]
status: draft
---

# Embedding（嵌入）

## 定义
Embedding 是将离散对象（如词语、句子、图像）映射到连续低维向量空间的技术。在文本领域，语义相近的句子在向量空间中的距离也更近，这使得计算机可以通过向量运算来理解和比较文本的语义关系。

## 核心原理
现代文本 embedding 基于 Transformer 编码器架构：

1. **输入编码**：文本经过 tokenization 转为模型可理解的 token 序列
2. **上下文编码**：Transformer 层通过自注意力机制捕捉词与词之间的上下文关系
3. **池化输出**：将最后一层的 hidden states 通过 mean pooling 或取 [CLS] token 的方式压缩为固定维度的向量

关键特性：
- **语义相似性**：向量空间的距离对应语义相似度（通常用余弦相似度度量）
- **线性语义关系**：向量运算可以捕捉类比关系，如 `king - man + woman ≈ queen`
- **跨模态对齐**：CLIP 等模型可以将文本和图像映射到同一向量空间

## 关键特性
- **维度**：常见 384d（轻量）、768d（BERT-base）、1024d（BERT-large）、3072d（OpenAI text-embedding-3-large）
- **上下文敏感**：同一词语在不同句子中会产生不同的向量（区别于静态词向量 Word2Vec）
- **多语言支持**：mBERT、LaBSE、BGE-M3 等模型支持跨语言语义对齐

## 应用场景
- **语义搜索**：用向量相似度替代关键词匹配，支持同义词和近义表达
- **RAG 检索**：将文档片段和问题编码为向量，通过最近邻搜索召回相关内容
- **文本聚类**：K-Means / HDBSCAN 在向量空间对文档进行主题聚类
- **推荐系统**：将用户行为和物品内容编码为向量，计算相似度进行推荐

## 与其他概念的关系
- **[[RAG]]**: Embedding 是 RAG 检索阶段的核心技术基础
- **[[向量数据库]]**: 专门优化了高维向量存储和 ANN 查询的数据库系统
- **[[Transformer]]**: 当前主流 embedding 模型的基础架构

## 常见模型
| 模型 | 维度 | 特点 | 适用场景 |
|------|------|------|----------|
| text-embedding-3-small | 1536 | OpenAI 出品，性价比极高 | 通用英文场景 |
| text-embedding-3-large | 3072 | 多语言支持好，精度最高 | 高质量多语言需求 |
| BGE-M3 | 1024 | 开源、多语言、支持稀疏向量 | 中英混合、本地部署 |
| nomic-embed-text | 768 | 开源、上下文窗口 8192 | 本地轻量部署 |
| M3E | 768 | 中文社区常用开源模型 | 纯中文场景 |

## 参考来源
- [demo-rag-intro.md](raw/dialogues/demo-rag-intro.md)
