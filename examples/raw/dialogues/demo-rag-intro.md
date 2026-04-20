## 用户
什么是 RAG（检索增强生成）？它和直接用大模型有什么区别？

## 助手
RAG（Retrieval-Augmented Generation）是一种将外部知识检索与 LLM 生成能力结合的技术架构。

核心区别：
1. **纯 LLM**：只能依赖预训练参数中的知识，存在知识截止（knowledge cutoff）和幻觉问题
2. **RAG**：在生成前先检索相关文档，把检索结果作为上下文（context）喂给 LLM，让模型基于事实生成回答

典型流程：
```python
# 1. 用户提问
query = "2024年诺贝尔物理学奖得主是谁？"

# 2. 检索阶段
retrieved_docs = vector_db.similarity_search(query, k=3)

# 3. 增强阶段
context = "\n".join([doc.page_content for doc in retrieved_docs])
prompt = f"基于以下资料回答问题：\n{context}\n\n问题：{query}"

# 4. 生成阶段
answer = llm.generate(prompt)
```

## 用户
RAG 里的 "检索" 具体是怎么实现的？用的什么数据库？

## 助手
检索的核心是**向量相似度搜索**，步骤如下：

1. **切分（Chunking）**：把长文档切成小段（通常 200-500 token）
2. **嵌入（Embedding）**：用 embedding 模型（如 OpenAI text-embedding-3、BGE、M3E）把文本段转为高维向量
3. **存储**：存入向量数据库（ChromaDB、Milvus、Pinecone、Weaviate、pgvector）
4. **查询**：用户问题也转为向量，做最近邻搜索（ANN），召回最相关的 k 个片段

常见向量数据库对比：
- **ChromaDB**：轻量、本地优先，适合个人项目
- **Milvus**：企业级、分布式，适合海量数据
- **Pinecone**：全托管 SaaS，免运维
- **pgvector**：PostgreSQL 扩展，适合已有 PG 基础设施的团队

## 用户
RAG 有什么局限？什么场景不适合？

## 助手
主要局限：

1. **检索质量决定上限**：如果召回的文档不相关，LLM 会被误导（Garbage In, Garbage Out）
2. **多跳推理弱**：需要跨多个文档推理的问题（如"A 公司和 B 公司共同的供应商是谁？"），单次检索难以解决
3. **长上下文瓶颈**：检索到的文档太长会挤占生成 token，太短可能丢失关键信息
4. **实时性**：向量索引更新有延迟，不适合股价、天气等实时数据

不适合的场景：
- 需要严格数学证明（应让 LLM 用工具如 Wolfram）
- 强实时性（如交易决策）
- 涉及个人隐私且不能出域的数据（虽然本地 RAG 可以部分解决）

## 用户
如果我想在个人笔记里用 RAG，最轻量的方案是什么？

## 助手
最轻量的个人 RAG 方案：

**技术栈**：
- 文档：Markdown 笔记（Obsidian / Logseq 导出）
- 嵌入：Ollama 本地跑 `nomic-embed-text` 或 `bge-m3`（免费、不出域）
- 向量库：ChromaDB（pip install 即可）
- LLM：Ollama 本地跑 Qwen / Llama 3
- 框架：LangChain 或 LlamaIndex（快速搭建）

**最小可行代码**：
```python
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama

# 1. 加载笔记
loader = DirectoryLoader("notes/", glob="**/*.md")
docs = loader.load()

# 2. 切分并嵌入
vectorstore = Chroma.from_documents(
    docs,
    embedding=OllamaEmbeddings(model="nomic-embed-text"),
    persist_directory="./chroma_db"
)

# 3. 查询
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
qa_chain = RetrievalQA.from_chain_type(
    llm=Ollama(model="qwen:14b"),
    retriever=retriever
)

result = qa_chain.invoke("我在哪篇笔记里写过 RAG 的局限？")
print(result)
```

核心建议：**先跑通，再优化**。不要一上来就纠结完美的 chunk size 和重排序（rerank），先用起来，根据实际 bad case 迭代。
