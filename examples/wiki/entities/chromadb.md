---
title: "ChromaDB"
type: entity
created: "2026-04-20"
updated: "2026-04-20"
confidence: high
sources: ["raw/dialogues/demo-rag-intro.md"]
tags: [tool, project]
related: [向量数据库, RAG, LangChain, LlamaIndex, Milvus, Pinecone]
status: draft
---

# ChromaDB

## 基本信息
- **类型**: 开源向量数据库
- **开发团队**: Chroma 团队
- **首次发布**: 2023年
- **许可证**: Apache-2.0
- **官网**: https://www.trychroma.com
- **GitHub**: https://github.com/chroma-core/chroma

## 简介
ChromaDB 是一个专为 AI 应用设计的开源向量数据库，以"AI 原生"和开发者体验为核心卖点。它支持嵌入式运行（in-memory 或持久化到本地磁盘），也可以通过 Docker 部署为独立服务。因其极简的 API 设计和 Python 优先的 SDK，成为个人项目和小型团队构建 RAG 应用的首选向量库。

## 核心特性
- **多模态支持**: 原生支持文本、图像、音频的向量存储和查询
- **多种运行模式**: 
  - `EphemeralClient`：纯内存，适合测试
  - `PersistentClient`：持久化到本地文件，适合个人项目
  - `HttpClient`：连接远程 Chroma 服务，适合生产部署
- **内置嵌入**: 可自动调用 embedding 模型（OpenAI、HuggingFace、ONNX Runtime），无需手动处理
- **元数据过滤**: 支持在向量搜索基础上叠加 WHERE 条件过滤（如 `{"source": "arxiv"}`）
- **距离度量**: 支持 cosine（默认）、l2、inner product 等多种相似度算法

## 典型用法
```python
import chromadb

# 本地持久化模式
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection("notes")

# 添加文档
collection.add(
    documents=["RAG 是一种检索增强生成技术", "Embedding 将文本映射到向量空间"],
    metadatas=[{"source": "demo"}, {"source": "demo"}],
    ids=["doc1", "doc2"]
)

# 查询
results = collection.query(
    query_texts=["什么是检索增强？"],
    n_results=2
)
```

## 优缺点
### 优点
- 安装极简单：`pip install chromadb`，一行代码运行
- Python API 直观，与 LangChain、LlamaIndex 集成无缝
- 开源免费，数据完全本地可控
- 社区活跃，文档完善

### 缺点
- 单机架构，不适合海量数据（亿级向量）或高并发场景
- 分布式能力较弱（相比 Milvus / Weaviate）
- 纯 Python 实现，性能不如基于 C++/Rust 的竞品

## 与其他实体的关系
- **[[LangChain]]**: 深度集成，是 LangChain 默认推荐的向量存储之一
- **[[LlamaIndex]]**: 官方支持 ChromaDB 作为向量索引后端
- **[[Milvus]]**: 更企业级的向量数据库选择，适合从 ChromaDB 迁移的扩展路径
- **[[Pinecone]]**: 托管 SaaS 竞品，免运维但需付费

## 适用场景
- 个人知识库 RAG（千级到十万级文档）
- 原型验证和 MVP 开发
- 中小型团队的内部文档问答系统
- 需要数据不出域的本地/私有化部署场景

## 参考来源
- [demo-rag-intro.md](raw/dialogues/demo-rag-intro.md)
