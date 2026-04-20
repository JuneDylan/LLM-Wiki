#!/usr/bin/env python3
"""
LLM Wiki - LLM 客户端
统一封装 Kimi / Qwen / OpenAI 的调用
"""

import os
import json
from typing import List, Dict, Optional

try:
    from openai import OpenAI
except ImportError:
    raise ImportError("请先安装 openai SDK: pip install openai")


class LLMClient:
    """
    通用 LLM 客户端
    
    支持的 provider:
      - kimi      -> Moonshot API
      - qwen      -> 阿里云 DashScope (兼容模式)
      - openai    -> OpenAI 官方
    """
    
    CONFIGS = {
        "kimi": {
            "base_url": "https://api.moonshot.cn/v1",
            "model": "moonshot-v1-8k",  # 可选: moonshot-v1-32k, moonshot-v1-128k
        },
        "qwen": {
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            # Qwen 兼容模式支持的模型名示例: qwen-plus, qwen-turbo, qwen-max
            "model": "qwen3.6-plus",
        },
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
        },
    }
    
    def __init__(self, provider: Optional[str] = None):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "qwen")).lower()
        config = self.CONFIGS.get(self.provider, self.CONFIGS["qwen"])
        
        api_key = os.getenv("LLM_API_KEY")
        if not api_key:
            env_var_map = {
                "kimi": "MOONSHOT_API_KEY",
                "qwen": "DASHSCOPE_API_KEY",
                "openai": "OPENAI_API_KEY",
            }
            api_key = os.getenv(env_var_map.get(self.provider, "LLM_API_KEY"))
        
        if not api_key:
            raise ValueError(
                f"使用 {self.provider} 需要提供 API Key。\n"
                f"请设置环境变量: LLM_API_KEY 或 {env_var_map.get(self.provider)}"
            )
        
        self.client = OpenAI(api_key=api_key, base_url=config["base_url"])
        self.model = os.getenv("LLM_MODEL") or config["model"]
    
    def chat(self, system_prompt: str, user_prompt: str, 
             temperature: float = 0.3, json_mode: bool = False) -> str:
        """
        发送聊天请求
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
    
    def extract_entities_and_concepts(self, content: str, filename: str) -> Dict[str, List[str]]:
        """
        智能提取实体和概念（细粒度分类版）
        返回: {"entities": [{name, type}, ...], "concepts": [{name, category}, ...]}
        """
        system_prompt = """你是一个知识库构建助手。请从用户提供的文章中精确提取关键信息，并进行细粒度分类。

## 实体分类体系 (entities)
每个实体必须标注类型：
- person: 人物（研究者、工程师、创始人）
- organization: 组织/公司（公司、研究机构、大学）
- model: 模型/产品（GPT-4, LLaMA 3, Claude, Gemini）
- algorithm: 算法/架构（Transformer, GRU, LSTM, MoE, Neural ODE）
- dataset: 数据集（BDD100K, nuScenes, ImageNet, COCO）
- venue: 学术会议/期刊（NeurIPS, CVPR, arXiv, Nature, TPAMI）
- tool: 工具/框架（PyTorch, ONNX, Zotero, LaTeX）
- project: 项目/系统（CARLA, SUMO, llama.cpp）
- hardware: 硬件/设备（Jetson Nano, DAVIS346）

## 概念分类体系 (concepts)
每个概念必须标注类别：
- method: 方法/技术（RLHF, LoRA, RAG, Few-shot, Chain-of-Thought）
- principle: 原理/定律（Scaling Law, Koopman算子, Lyapunov稳定性）
- paradigm: 范式/框架（Agentic Protocol, Context Engineering, 多Agent协作）
- metric: 指标/评估（BLEU, 困惑度, F1 Score）
- phenomenon: 现象/效应（涌现能力, 幻觉问题, 灾难性遗忘）
- domain: 领域/方向（自动驾驶, 具身智能, 数字孪生）

## 关键规则
1. 算法/架构（Transformer, GRU, LSTM, MoE）归入 entities.algorithm，不要放入 concepts
2. 同一概念的中英文只保留一个规范名（优先英文缩写，如 RAG 而非"检索增强生成"）
3. 不要重复提取：如果 GPT-4 已提取为 entity，不要再在 concepts 中出现
4. 保持原始大小写（如 GPT-4, LLaMA, MoE）
5. 只返回 JSON，不要任何解释

JSON 格式：
{
  "entities": [
    {"name": "OpenAI", "type": "organization"},
    {"name": "GPT-4", "type": "model"},
    {"name": "Transformer", "type": "algorithm"},
    {"name": "BDD100K", "type": "dataset"},
    {"name": "NeurIPS", "type": "venue"}
  ],
  "concepts": [
    {"name": "RLHF", "category": "method"},
    {"name": "Scaling Law", "category": "principle"},
    {"name": "多Agent协作", "category": "paradigm"},
    {"name": "自动驾驶", "category": "domain"}
  ]
}"""
        
        user_prompt = f"文件名: {filename}\n\n文章内容（前 8000 字符）:\n{content[:8000]}"
        
        try:
            result = self.chat(system_prompt, user_prompt, json_mode=True)
            data = json.loads(result)
            
            entities_raw = data.get("entities", [])
            concepts_raw = data.get("concepts", [])
            
            entities = []
            for e in entities_raw:
                if isinstance(e, dict):
                    entities.append(e)
                elif isinstance(e, str):
                    entities.append({"name": e, "type": "project"})
            
            concepts = []
            for c in concepts_raw:
                if isinstance(c, dict):
                    concepts.append(c)
                elif isinstance(c, str):
                    concepts.append({"name": c, "category": "method"})
            
            seen_entities = set()
            unique_entities = []
            for e in entities:
                key = e["name"].lower()
                if key not in seen_entities:
                    seen_entities.add(key)
                    unique_entities.append(e)
            
            seen_concepts = set()
            unique_concepts = []
            for c in concepts:
                key = c["name"].lower()
                if key not in seen_concepts:
                    seen_concepts.add(key)
                    unique_concepts.append(c)
            
            return {
                "entities": unique_entities,
                "concepts": unique_concepts,
            }
        except Exception as e:
            print(f"⚠️ LLM 提取失败，回退到规则提取: {e}")
            return {"entities": [], "concepts": []}
    
    def summarize_source(self, content: str, filename: str) -> Dict[str, str]:
        """
        为原始资料生成结构化摘要
        返回包含各章节内容的字典
        """
        system_prompt = """你是一个学术/技术文章摘要专家。
请阅读用户提供的文章，生成结构化的中文摘要。
只返回 JSON，不要任何解释。

JSON 格式：
{
  "core_points": "1. ...\\n2. ...\\n3. ...",
  "key_findings": "最重要的发现",
  "methodology": "研究方法",
  "data_results": "关键数据",
  "limitations": "局限性",
  "entities": "- [[实体1]]\\n- [[实体2]]",
  "concepts": "- [[概念1]]\\n- [[概念2]]",
  "quote": "> 重要段落引用"
}"""
        
        user_prompt = f"文件名: {filename}\n\n文章内容（前 12000 字符）:\n{content[:12000]}"
        
        try:
            result = self.chat(system_prompt, user_prompt, json_mode=True)
            return json.loads(result)
        except Exception as e:
            print(f"⚠️ LLM 摘要生成失败: {e}")
            return {}
    
    def analyze_dialogue(self, content: str, filename: str) -> Dict[str, any]:
        """
        分析 AI 对话记录，提取结构化知识
        返回包含主题、问题、实体、概念、结论的字典
        """
        system_prompt = """你是一个对话蒸馏专家。
请分析以下 AI 对话记录，将其转化为结构化知识。

要求：
1. topic: 用 3-8 个字概括对话主题
2. core_questions: 用户提出的核心问题列表（最多 5 个）
3. key_insights: 从回答中提取的关键洞察/知识点（最多 5 条）
4. conclusion: 对话的最终结论或解决方案（1-2 句话）
5. entities: 提到的工具、框架、公司、人名、项目名
6. concepts: 技术术语、方法、原理、架构
7. 保持原始大小写（如 GPT-4, LLaMA, MoE）
8. 只返回 JSON，不要任何解释

JSON 格式：
{
  "topic": "对话主题",
  "core_questions": ["问题1", "问题2"],
  "key_insights": ["洞察1", "洞察2"],
  "conclusion": "最终结论",
  "entities": ["OpenAI", "GPT-4"],
  "concepts": ["Transformer", "RLHF"]
}"""
        
        user_prompt = f"文件名: {filename}\n\n对话记录（前 12000 字符）:\n{content[:12000]}"
        
        try:
            result = self.chat(system_prompt, user_prompt, json_mode=True)
            data = json.loads(result)
            return {
                "topic": data.get("topic", filename),
                "core_questions": data.get("core_questions", []),
                "key_insights": data.get("key_insights", []),
                "conclusion": data.get("conclusion", ""),
                "entities": list(dict.fromkeys(data.get("entities", []))),
                "concepts": list(dict.fromkeys(data.get("concepts", []))),
            }
        except Exception as e:
            print(f"⚠️ LLM 对话分析失败: {e}")
            return {
                "topic": filename,
                "core_questions": [],
                "key_insights": [],
                "conclusion": "",
                "entities": [],
                "concepts": [],
            }


    def generate_stub_definition(self, name: str, category: str,
                                    context_snippets: str = "") -> Optional[str]:
        """
        为知识库 stub 页面生成一句话定义。
        
        参数:
            name: 实体/概念名称
            category: 类型或分类（如 "model", "method", "principle"）
            context_snippets: 从原始资料中提取的上下文片段（控制在 800 字符内）
        
        返回:
            1-2 句话的中文定义，失败时返回 None
        """
        system_prompt = """你是一个技术百科词条编辑助手。
请根据提供的技术术语和上下文，为其编写一句精准、专业的中文定义。

要求：
1. 只输出定义文本，不要任何解释、前缀或 JSON
2. 控制在 50-120 字
3. 必须包含该术语的核心功能/特性
4. 语言风格：客观、学术、简洁

示例：
- GPT-4: OpenAI 发布的大规模多模态语言模型，基于 Transformer 架构，支持文本与图像输入，具备高级推理和代码生成能力。
- LoRA: 一种参数高效微调方法，通过在预训练权重旁注入低秩矩阵来适配下游任务，显著降低显存占用和训练成本。"""

        user_prompt = f"""术语: {name}
分类: {category}

上下文片段:
{context_snippets[:800]}

请用 1-2 句话给出该术语的中文定义:"""

        try:
            result = self.chat(system_prompt, user_prompt, temperature=0.2)
            definition = result.strip().strip('"').strip("'")
            if len(definition) >= 15:
                return definition
            return None
        except Exception as e:
            print(f"   ⚠️ stub 定义生成失败 ({name}): {e}")
            return None


if __name__ == "__main__":
    # 简单测试
    import sys
    client = LLMClient()
    test = client.extract_entities_and_concepts(
        "OpenAI released GPT-4 with RLHF and MoE architecture.",
        "test.txt"
    )
    print(json.dumps(test, ensure_ascii=False, indent=2))
