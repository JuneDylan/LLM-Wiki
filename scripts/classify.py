#!/usr/bin/env python3
"""
LLM Wiki - 实体分类与概念归并工具
功能：
  1. 对现有 entities/ 下的页面进行细粒度分类
  2. 对 concepts/ 下的同义/重复概念进行归并
  3. 修复分类标签和 frontmatter
使用方法:
  python scripts/classify.py --classify-entities     # 对所有实体重新分类
  python scripts/classify.py --merge-concepts        # 归并同义概念
  python scripts/classify.py --fix-tags              # 修复所有页面的 tags
  python scripts/classify.py --all                   # 执行全部操作
"""

import sys
import os
import io
import re
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

if sys.platform == "win32":
    try:
        if sys.stdout.encoding != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except (AttributeError, io.UnsupportedOperation):
        pass

sys.path.insert(0, str(Path(__file__).parent))
from utils import WikiUtils, MetadataManager, LogManager

try:
    from llm_client import LLMClient
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False


# ================================================================
# 核心分类体系定义
# ================================================================

ENTITY_TYPES = {
    "person": {
        "label": "👤 人物",
        "description": "研究者、工程师、创始人等个人",
        "examples": ["Karpathy", "Hinton", "LeCun", "Vaswani"],
        "frontmatter_template": {
            "type": "entity",
            "entity_type": "person",
        }
    },
    "organization": {
        "label": "🏢 组织/公司",
        "description": "公司、研究机构、大学、实验室",
        "examples": ["OpenAI", "Google DeepMind", "Meta AI", "Microsoft Research"],
        "frontmatter_template": {
            "type": "entity",
            "entity_type": "organization",
        }
    },
    "model": {
        "label": "🤖 模型/产品",
        "description": "具体的 AI 模型或产品名称",
        "examples": ["GPT-4", "GPT-4o", "LLaMA 3", "Claude", "Gemini", "Mixtral"],
        "frontmatter_template": {
            "type": "entity",
            "entity_type": "model",
        }
    },
    "algorithm": {
        "label": "🧠 算法/架构",
        "description": "神经网络架构、算法、训练方法",
        "examples": ["Transformer", "GRU", "LSTM", "MoE", "JEPA", "Neural ODE"],
        "frontmatter_template": {
            "type": "entity",
            "entity_type": "algorithm",
        }
    },
    "dataset": {
        "label": "📊 数据集",
        "description": "公开数据集、基准测试集",
        "examples": ["BDD100K", "nuScenes", "NGSIM", "HighD", "ImageNet", "COCO"],
        "frontmatter_template": {
            "type": "entity",
            "entity_type": "dataset",
        }
    },
    "venue": {
        "label": "📚 学术会议/期刊",
        "description": "学术出版场所：会议、期刊、预印本平台",
        "examples": ["NeurIPS", "ICML", "CVPR", "ICCV", "arXiv", "Nature", "TPAMI"],
        "frontmatter_template": {
            "type": "entity",
            "entity_type": "venue",
        }
    },
    "tool": {
        "label": "🔧 工具/框架",
        "description": "软件工具、开发框架、平台",
        "examples": ["PyTorch", "ONNX", "Zotero", "Jupyter", "Git", "LaTeX"],
        "frontmatter_template": {
            "type": "entity",
            "entity_type": "tool",
        }
    },
    "project": {
        "label": "📦 项目/系统",
        "description": "开源项目、软件系统、平台",
        "examples": ["CARLA", "SUMO", "MMDetection3D", "llama.cpp"],
        "frontmatter_template": {
            "type": "entity",
            "entity_type": "project",
        }
    },
    "hardware": {
        "label": "🖥️ 硬件/设备",
        "description": "硬件设备、芯片、传感器",
        "examples": ["Jetson Nano", "NVIDIA H100", "DAVIS346"],
        "frontmatter_template": {
            "type": "entity",
            "entity_type": "hardware",
        }
    },
    "concept_as_entity": {
        "label": "⚠️ 应为概念",
        "description": "被错误归类为实体的概念，应迁移到 concepts/",
        "examples": [],
        "frontmatter_template": {
            "type": "concept",
        }
    },
}

CONCEPT_CATEGORIES = {
    "method": {
        "label": "🔬 方法/技术",
        "description": "具体的技术方法、算法变体",
        "examples": ["RLHF", "LoRA", "RAG", "Few-shot", "Chain-of-Thought"]
    },
    "principle": {
        "label": "📐 原理/定律",
        "description": "理论基础、数学原理、经验定律",
        "examples": ["Scaling Law", "Koopman算子", "Lyapunov稳定性"]
    },
    "paradigm": {
        "label": "🔄 范式/框架",
        "description": "研究范式、架构模式、工作流框架",
        "examples": ["Agentic Protocol", "Context Engineering", "多Agent协作"]
    },
    "metric": {
        "label": "📏 指标/评估",
        "description": "评估指标、度量方法",
        "examples": ["BLEU", "困惑度", "F1 Score"]
    },
    "phenomenon": {
        "label": "🌊 现象/效应",
        "description": "观察到的现象、涌现能力",
        "examples": ["涌现能力", "幻觉问题", "灾难性遗忘"]
    },
    "domain": {
        "label": "🎯 领域/方向",
        "description": "研究领域、应用方向",
        "examples": ["自动驾驶", "具身智能", "数字孪生"]
    },
}


class EntityClassifier:
    """实体分类器：对 entities/ 下的页面进行细粒度分类"""
    
    def __init__(self, base_dir: str = ".", use_llm: bool = False):
        self.utils = WikiUtils(base_dir)
        self.meta_mgr = MetadataManager(self.utils)
        self.log_mgr = LogManager(self.utils)
        self.llm = LLMClient() if LLM_AVAILABLE else None
        self.use_llm = use_llm
        
        self.classification_results = defaultdict(list)
    
    def classify_all_entities(self) -> Dict:
        """对所有实体页面进行分类"""
        print(f"\n{'='*70}")
        print("🏷️ 实体分类器")
        print(f"{'='*70}\n")
        
        entity_files = self.utils.list_wiki_files("entities")
        print(f"📋 扫描到 {len(entity_files)} 个实体页面\n")
        
        for filepath in entity_files:
            if filepath.name.startswith('_'):
                continue
            
            entity_type = self._classify_entity(filepath)
            self.classification_results[entity_type].append(
                str(filepath.relative_to(self.utils.base_dir))
            )
            
            self._update_entity_frontmatter(filepath, entity_type)
        
        self._print_classification_summary()
        
        return dict(self.classification_results)
    
    def _classify_entity(self, filepath: Path) -> str:
        """
        分类单个实体
        策略：先规则匹配，再 LLM 辅助
        """
        content = self.utils.read_file(filepath)
        frontmatter, body = self.utils.parse_frontmatter(content)
        
        title = frontmatter.get("title", filepath.stem)
        slug = filepath.stem.lower()
        tags = frontmatter.get("tags", [])
        related = frontmatter.get("related", [])
        
        all_text = f"{title} {slug}".lower()
        
        # 规则 1：学术会议/期刊
        venue_keywords = [
            'cvpr', 'iccv', 'eccv', 'neurips', 'icml', 'iclr', 'aaai',
            'nips', 'corl', 'rss', 'ral', 'icra', 'iros',
            'nature', 'science', 'cell', 'pnas', 'jmlr',
            'pubmed', 'physica', 'transportation-research',
            'accident-analysis', 'ieee-access', 'ieee-tits',
        ]
        venue_exact_slugs = [
            'arxiv', 'ieee', 'tpami', 'tits',
        ]
        for kw in venue_keywords:
            if kw in slug or kw in all_text:
                return "venue"
        if slug in venue_exact_slugs:
            return "venue"
        
        # 规则 2：数据集
        dataset_keywords = [
            'nuscenes', 'bdd100k', 'ngsim', 'highd', 'lyft', 'waymo',
            'kitti', 'coco', 'imagenet', 'nusc', 'dsec', 'mvsec',
            'us-101', 'i-80', 'opends', 'highd',
        ]
        for kw in dataset_keywords:
            if kw in slug:
                return "dataset"
        
        # 规则 3：算法/架构
        algorithm_keywords = [
            'transformer', 'lstm', 'gru', 'moe', 'jepa', 'tcn', 'lnn',
            'nsm', 'cfc', 'pinn', 'neural-ode', 'eventlnn', 'physicslnn',
            'swin-vit', 'yolov8', 'yolov10', 'aod-net', 'adaptivecliff',
            'fluidclaw', 'openclaw', 'bitnet', 'gptq', 'ncps',
        ]
        algorithm_exact_slugs = [
            'gru', 'lstm', 'tcn', 'lnn', 'nsm', 'cfc', 'pinn', 'moe',
            'jepa', 'transformer', 'bitnet', 'gptq', 'neural-ode',
            'koopman', 'ode',
        ]
        for kw in algorithm_keywords:
            if kw in slug:
                return "algorithm"
        if slug in algorithm_exact_slugs:
            return "algorithm"
        
        # 规则 4：模型/产品
        model_keywords = [
            'gpt-4', 'gpt-4o', 'gpt-3', 'llama', 'claude', 'gemini',
            'qwen', 'minicpm', 'sensevoice', 'voxcpm', 'mistral',
            'llama-3', 'llama.cpp', 'llamacpp',
        ]
        for kw in model_keywords:
            if kw in slug:
                return "model"
        
        # 规则 5：工具/框架
        tool_keywords = [
            'pytorch', 'onnx', 'jupyter', 'latex', 'zotero',
            'overleaf', 'mkdocs', 'vitepress', 'obsidian', 'logseq',
            'prisma', 'sqlite', 'sympy', 'pyyaml',
        ]
        tool_exact_slugs = [
            'git', 'r', 'github', 'vs-code',
        ]
        for kw in tool_keywords:
            if kw in slug:
                return "tool"
        if slug in tool_exact_slugs:
            return "tool"
        
        # 规则 6：项目/系统
        project_keywords = [
            'carla', 'sumo', 'lgsvl', 'mmdetection', 'firebase',
            'autoresearch', 'grobid', 'sciencebeam', 'paperpal',
            'piper', 'hermes', 'nuwa', 'mempalace', 'autora',
        ]
        for kw in project_keywords:
            if kw in slug:
                return "project"
        
        # 规则 7：硬件
        hardware_keywords = ['jetson', 'nano', 'h100', 'a100', 'gpu']
        for kw in hardware_keywords:
            if kw in slug:
                return "hardware"
        
        # 规则 8：人物（优先级提高，在工具/项目之前检测）
        person_keywords = [
            'karpathy', 'lecun', 'hinton', 'goodfellow', 'vaswani',
            'sutskever', 'bengio', 'schmidhuber', 'he', 'resnet',
        ]
        person_slugs = [
            'karpathy', 'lecun', 'hinton', 'goodfellow', 'vaswani',
            'sutskever', 'bengio', 'schmidhuber',
        ]
        for kw in person_keywords:
            if kw in slug:
                return "person"
        if slug in person_slugs:
            return "person"
        
        # 规则 9：组织
        org_keywords = [
            'openai', 'deepmind', 'google', 'meta', 'microsoft',
            'anthropic', 'nvidia', 'nsfc', 'epoch',
        ]
        for kw in org_keywords:
            if kw in slug:
                return "organization"
        
        # LLM 辅助分类（仅当规则无法匹配时）
        if self.llm and self.use_llm:
            return self._llm_classify(title, body[:2000])
        
        return "project"
    
    def _llm_classify(self, title: str, body: str) -> str:
        """使用 LLM 辅助分类"""
        type_list = ", ".join(
            f"{k}({v['description']})" for k, v in ENTITY_TYPES.items()
            if k != "concept_as_entity"
        )
        
        system_prompt = f"""你是一个知识分类专家。请判断以下实体属于哪种类型。

可选类型:
{type_list}

只返回类型名称（英文小写），不要任何解释。"""
        
        user_prompt = f"实体名称: {title}\n\n描述:\n{body[:1000]}"
        
        try:
            result = self.llm.chat(system_prompt, user_prompt, temperature=0.1)
            result = result.strip().lower()
            
            if result in ENTITY_TYPES:
                return result
        except Exception:
            pass
        
        return "project"
    
    def _update_entity_frontmatter(self, filepath: Path, entity_type: str):
        """更新实体的 frontmatter，添加 entity_type 字段"""
        content = self.utils.read_file(filepath)
        frontmatter, body = self.utils.parse_frontmatter(content)
        
        old_type = frontmatter.get("entity_type", "")
        if old_type == entity_type:
            return
        
        frontmatter["entity_type"] = entity_type
        
        if entity_type in ENTITY_TYPES:
            proper_tags = [entity_type]
            if "tags" in frontmatter:
                existing = frontmatter["tags"]
                cleaned = [t for t in existing if t not in ENTITY_TYPES and t != "person/company/project/paper"]
                frontmatter["tags"] = proper_tags + cleaned
            else:
                frontmatter["tags"] = proper_tags
        
        frontmatter["updated"] = self.utils.get_today()
        
        new_content = self.utils.build_frontmatter(frontmatter) + body
        self.utils.write_file(filepath, new_content)
    
    def _print_classification_summary(self):
        """打印分类统计"""
        print(f"\n{'='*70}")
        print("📊 实体分类统计")
        print(f"{'='*70}")
        
        for etype, paths in sorted(self.classification_results.items(),
                                    key=lambda x: len(x[1]), reverse=True):
            label = ENTITY_TYPES.get(etype, {}).get("label", etype)
            print(f"\n  {label} ({len(paths)} 个)")
            for p in paths[:5]:
                print(f"    - {p}")
            if len(paths) > 5:
                print(f"    ... 还有 {len(paths)-5} 个")
        
        total = sum(len(v) for v in self.classification_results.values())
        print(f"\n  总计: {total} 个实体已分类")
        print(f"{'='*70}\n")


class ConceptMerger:
    """概念归并器：检测和合并同义概念"""
    
    def __init__(self, base_dir: str = "."):
        self.utils = WikiUtils(base_dir)
        self.meta_mgr = MetadataManager(self.utils)
        self.log_mgr = LogManager(self.utils)
        self.llm = LLMClient() if LLM_AVAILABLE else None
        
        self.merge_groups = []
    
    def find_synonym_concepts(self) -> List[Dict]:
        """检测同义概念组"""
        print(f"\n{'='*70}")
        print("🔍 同义概念检测")
        print(f"{'='*70}\n")
        
        concept_files = self.utils.list_wiki_files("concepts")
        print(f"📋 扫描到 {len(concept_files)} 个概念页面\n")
        
        concepts_data = []
        for filepath in concept_files:
            content = self.utils.read_file(filepath)
            frontmatter, body = self.utils.parse_frontmatter(content)
            
            title = frontmatter.get("title", filepath.stem)
            slug = filepath.stem
            
            concepts_data.append({
                "path": filepath,
                "title": title,
                "slug": slug,
                "body": body,
                "frontmatter": frontmatter,
            })
        
        # 策略 1：标题规范化后匹配
        title_groups = defaultdict(list)
        for c in concepts_data:
            norm_title = self._normalize_concept_title(c["title"])
            title_groups[norm_title].append(c)
        
        # 策略 2：中英文对照匹配
        zh_en_map = self._build_zh_en_map(concepts_data)
        
        # 策略 3：LLM 语义匹配（对可疑对）
        synonym_groups = []
        
        for norm_title, group in title_groups.items():
            if len(group) > 1:
                synonym_groups.append({
                    "type": "title_variant",
                    "canonical": self._pick_canonical(group),
                    "members": group,
                    "reason": f"标题变体: {norm_title}",
                    "action": "merge"
                })
        
        for zh_name, en_entries in zh_en_map.items():
            if len(en_entries) > 1:
                existing_paths = set()
                for g in synonym_groups:
                    for m in g["members"]:
                        existing_paths.add(str(m["path"]))
                
                new_members = [e for e in en_entries if str(e["path"]) not in existing_paths]
                if len(new_members) > 1:
                    synonym_groups.append({
                        "type": "zh_en_duplicate",
                        "canonical": self._pick_canonical(new_members),
                        "members": new_members,
                        "reason": f"中英文重复: {zh_name}",
                        "action": "merge"
                    })
        
        self.merge_groups = synonym_groups
        
        print(f"   ✓ 发现 {len(synonym_groups)} 组同义概念\n")
        
        for i, group in enumerate(synonym_groups, 1):
            titles = [m["title"] for m in group["members"]]
            canonical = group["canonical"]["title"]
            print(f"   {i}. {group['reason']}")
            print(f"      成员: {', '.join(titles)}")
            print(f"      建议保留: {canonical}")
            print()
        
        return synonym_groups
    
    def merge_synonym_groups(self, groups: List[Dict] = None) -> Dict:
        """执行概念归并"""
        if groups is None:
            groups = self.merge_groups
        
        if not groups:
            print("没有需要归并的同义概念组")
            return {"merged": 0, "skipped": 0}
        
        print(f"\n{'='*70}")
        print("🔗 开始归并同义概念")
        print(f"{'='*70}\n")
        
        merged_count = 0
        skipped_count = 0
        
        for i, group in enumerate(groups, 1):
            canonical = group["canonical"]
            members = group["members"]
            
            print(f"[{i}/{len(groups)}] 归并: {group['reason']}")
            print(f"  保留: {canonical['title']} ({canonical['slug']})")
            
            for member in members:
                if member["path"] == canonical["path"]:
                    continue
                
                print(f"  合并: {member['title']} → {canonical['title']}")
                
                self._merge_concept_pair(canonical, member)
                merged_count += 1
            
            print()
        
        print(f"✅ 归并完成: 合并 {merged_count} 个, 跳过 {skipped_count} 个")
        
        return {"merged": merged_count, "skipped": skipped_count}
    
    def _merge_concept_pair(self, primary: Dict, secondary: Dict):
        """合并两个概念页面"""
        primary_path = primary["path"]
        secondary_path = secondary["path"]
        
        primary_content = self.utils.read_file(primary_path)
        primary_fm, primary_body = self.utils.parse_frontmatter(primary_content)
        
        secondary_content = self.utils.read_file(secondary_path)
        secondary_fm, secondary_body = self.utils.parse_frontmatter(secondary_content)
        
        # 合并 frontmatter
        primary_fm["sources"] = list(set(
            primary_fm.get("sources", []) + secondary_fm.get("sources", [])
        ))
        primary_fm["tags"] = list(set(
            primary_fm.get("tags", []) + secondary_fm.get("tags", [])
        ))
        primary_fm["related"] = list(set(
            primary_fm.get("related", []) + secondary_fm.get("related", [])
        ))
        
        if "aliases" not in primary_fm:
            primary_fm["aliases"] = []
        primary_fm["aliases"].append(secondary_fm.get("title", secondary["slug"]))
        primary_fm["aliases"] = list(set(primary_fm["aliases"]))
        
        primary_fm["updated"] = self.utils.get_today()
        
        # 合并正文（追加次页面的独有内容）
        merged_body = primary_body.rstrip()
        
        sec_title = secondary_fm.get("title", secondary["slug"])
        if secondary_body.strip() and secondary_body.strip() != primary_body.strip():
            merged_body += f"\n\n---\n\n## 来自 [[{sec_title}]] 的补充内容\n\n"
            merged_body += secondary_body.rstrip()
        
        new_content = self.utils.build_frontmatter(primary_fm) + merged_body
        self.utils.write_file(primary_path, new_content)
        
        # 次页面变为重定向
        redirect = self._create_concept_redirect(
            sec_title, primary_fm.get("title", primary["slug"]),
            secondary_fm.get("sources", [])
        )
        self.utils.write_file(secondary_path, redirect)
        
        # 更新引用
        self._update_concept_links(
            secondary["slug"], primary["slug"]
        )
    
    def _create_concept_redirect(self, old_title: str, new_title: str,
                                  sources: List[str]) -> str:
        """创建概念重定向页面"""
        today = self.utils.get_today()
        new_slug = self.utils.slugify(new_title)
        
        return f"""---
title: "{old_title}"
type: concept
created: "{today}"
updated: "{today}"
confidence: high
sources: {sources}
tags: [redirect]
related: ["[[{new_slug}]]"]
status: archived
aliases: []
---

# {old_title}

> ⚠️ **此概念已归并**
> 
> 本页面已归并至 [[{new_slug}]]，请点击链接查看完整内容。

---
*归并时间: {today}*
"""
    
    def _update_concept_links(self, old_slug: str, new_slug: str):
        """更新所有页面中的概念链接"""
        all_files = self.utils.list_wiki_files()
        updated = 0
        
        for filepath in all_files:
            content = self.utils.read_file(filepath)
            
            old_link = f"[[{old_slug}]]"
            new_link = f"[[{new_slug}]]"
            
            if old_link in content:
                content = content.replace(old_link, new_link)
                self.utils.write_file(filepath, content)
                updated += 1
        
        if updated > 0:
            print(f"    ✓ 已更新 {updated} 个页面中的链接")
    
    def _normalize_concept_title(self, title: str) -> str:
        """规范化概念标题，用于匹配同义词"""
        t = title.lower().strip()
        t = re.sub(r'[\(\)（）]', '', t)
        t = re.sub(r'[-_\s]+', '', t)
        
        zh_en_map = {
            '检索增强生成': 'rag',
            '液态神经网络': 'liquidneuralnetwork',
            '液态网络': 'liquidneuralnetwork',
            '元学习': 'metalearning',
            '零样本迁移': 'zeroshottransfer',
            '零样本适应': 'zeroshotadaptation',
            '知识蒸馏': 'knowledgedistillation',
            '最小可行产品': 'mvp',
            '连续时间建模': 'continuoustimemodeling',
            '连续时间动态系统': 'continuoustimedynamics',
            '连续时间动力学': 'continuoustimedynamics',
            '物理启发神经网络': 'physicsinformedneuralnetwork',
            '物理信息神经网络': 'physicsinformedneuralnetwork',
            '对抗性测试': 'adversarialtesting',
            '对抗性验证': 'adversarialverification',
            '多智能体编排': 'multiagentorchestration',
            '多agent编排': 'multiagentorchestration',
            '多agent协作': 'multiagentcollaboration',
            '多智能体协作': 'multiagentcollaboration',
            '上下文工程': 'contextengineering',
            '双向链接': 'bidirectionallink',
            '增量更新': 'incrementalupdate',
            '隐式神经场': 'implicitneuralfield',
            '数字孪生': 'digitaltwin',
            '认知架构提取': 'cognitivearchitectureextraction',
            '认知模式提取': 'cognitivepatternextraction',
            '对抗式prompt': 'adversarialprompt',
            '对话蒸馏': 'dialoguedistillation',
            '技能蒸馏': 'skilldistillation',
            '人格蒸馏': 'personalitydistillation',
            '学术写作技能蒸馏': 'academicwritingskilldistillation',
            '智能体技能蒸馏': 'agentskilldistillation',
            '分层渐进式蒸馏': 'progressivedistillation',
            '架构融合与人格蒸馏': 'architecturefusionpersonalitydistillation',
            '闭式解析解': 'closedformanalyticalsolution',
            '闭式解': 'closedformsolution',
            '雅可比矩阵分析': 'jacobianmatrixanalysis',
            '雅可比矩阵': 'jacobianmatrix',
            '稳定性理论': 'stabilitytheory',
            'lyapunov稳定性': 'lyapunovstability',
            '状态演化连续性': 'stateevolutioncontinuity',
            '隐状态动力学': 'hiddenstatedynamics',
            '在线适应': 'onlineadaptation',
            '域适应': 'domainadaptation',
            '反事实推理': 'counterfactualreasoning',
            '反事实生成': 'counterfactualgeneration',
            '贝叶斯优化': 'bayesianoptimization',
            '符号数值混合验证': 'symbolicnumerichybridverification',
            '物理一致性约束': 'physicalconsistencyconstraint',
            '物理信息验证层': 'physicsinformedverificationlayer',
            '异步事件流融合': 'asynchronouseventstreamfusion',
            '异步融合': 'asynchronousfusion',
            '非均匀采样鲁棒性': 'nonuniformsamplingrobustness',
            '预测性切换': 'predictiveswitching',
            '预测性失效检测': 'predictivefailuredetection',
            '不确定性量化': 'uncertaintyquantification',
            '视觉感知不确定性': 'visualperceptionuncertainty',
            '自适应时间常数': 'adaptivetimeconstant',
            '时间常数可视化': 'timeconstantvisualization',
            '长尾场景': 'longtailscenario',
            '长尾场景感知稳定性': 'longtailscenarioawarenessstability',
            '驾驶人格数字孪生': 'drivingpersonalitydigitaltwin',
            '人机共驾': 'humanmachinecoDriving',
            '事件相机': 'eventcamera',
            '六路并行采集': 'sixchannelparallelacquisition',
            '大气散射模型': 'atmosphericscatteringmodel',
            '离散映射': 'discretemapping',
            '柯氏复杂度': 'kolmogorovcomplexity',
            '模式挖掘': 'patternmining',
            '质量过滤': 'qualityfiltering',
            '风格距离度量': 'styledistancemetric',
            '引用语境': 'citationcontext',
            '心智模型': 'mentalmodel',
            '认知漂移': 'cognitivedrift',
            '认知负荷优化': 'cognitiveloadoptimization',
            '渐进式披露': 'progressivedisclosure',
            '声明式架构': 'declarativearchitecture',
            '文件驱动声明式架构': 'filedrivendeclarativearchitecture',
            '旧信息新信息流动': 'oldtonewinformationflow',
            '旧信息→新信息流动': 'oldtonewinformationflow',
            '可证伪科学过程': 'falsifiablescientificprocess',
            '闭环迭代': 'closedloopiteration',
            '闭环实证研究': 'closedloopempiricalresearch',
            '决策启发式': 'decisionheuristics',
            '成功原则': 'successprinciple',
            '故事张力诊断': 'storytensiondiagnosis',
            '修辞人格': 'rhetoricalpersona',
            '论证链提取': 'argumentchainextraction',
            '隐性知识显性化': 'tacitknowledgeexplicitation',
            '表达dna': 'expressiondna',
            '洋葱模型': 'onionmodel',
            '交叉质疑机制': 'crossquestioningmechanism',
            '交叉质疑委员会': 'crossquestioningcommittee',
            '三重验证': 'tripleverification',
            '幻觉涌现困境': 'hallucinationemergencedilemma',
            '基金选题分析': 'fundtopicselectionanalysis',
            '自动驾驶长尾感知选题': 'autonomousdrivinglongtailperceptiontopic',
            '大模型科研协作': 'llmscientificresearchcollaboration',
            '人机协作研究范式': 'humanmachinecollaborativeresearchparadigm',
            'subagent系统': 'subagentsystem',
            'state管理': 'statemanagement',
            '旧信息新信息流动': 'oldtonewinformationflow',
        }
        
        for zh, en in zh_en_map.items():
            if zh in t:
                return en
        
        return t
    
    def _build_zh_en_map(self, concepts_data: List[Dict]) -> Dict:
        """构建中英文对照映射"""
        zh_en_map = defaultdict(list)
        
        for c in concepts_data:
            title = c["title"]
            
            m = re.match(r'(.+?)[（(](.+?)[）)]', title)
            if m:
                zh_name = m.group(1).strip()
                en_name = m.group(2).strip()
                zh_en_map[zh_name].append(c)
            
            norm = self._normalize_concept_title(title)
            zh_en_map[norm].append(c)
        
        return zh_en_map
    
    def _pick_canonical(self, group: List[Dict]) -> Dict:
        """选择规范页面（保留哪个）"""
        scored = []
        for c in group:
            score = 0
            title = c["title"]
            body = c["body"]
            
            if re.match(r'^[a-zA-Z0-9\-]+$', c["slug"]):
                score += 10
            
            if len(body) > 100:
                score += 5
            
            if c["frontmatter"].get("sources"):
                score += 3
            
            if not re.search(r'[\(\)（）]', title):
                score += 2
            
            if re.match(r'^[A-Z][a-zA-Z0-9]+$', title):
                score += 2
            
            scored.append((score, c))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]


class TagFixer:
    """标签修复器：统一和规范化所有页面的标签"""
    
    def __init__(self, base_dir: str = "."):
        self.utils = WikiUtils(base_dir)
    
    def fix_all_tags(self) -> Dict:
        """修复所有页面的标签"""
        print(f"\n{'='*70}")
        print("🏷️ 标签修复器")
        print(f"{'='*70}\n")
        
        all_files = self.utils.list_wiki_files()
        
        fixed_count = 0
        tag_stats = defaultdict(int)
        
        for filepath in all_files:
            content = self.utils.read_file(filepath)
            frontmatter, body = self.utils.parse_frontmatter(content)
            
            if not frontmatter:
                continue
            
            old_tags = frontmatter.get("tags", [])
            new_tags = self._normalize_tags(old_tags, frontmatter, filepath)
            
            if new_tags != old_tags:
                frontmatter["tags"] = new_tags
                frontmatter["updated"] = self.utils.get_today()
                
                new_content = self.utils.build_frontmatter(frontmatter) + body
                self.utils.write_file(filepath, new_content)
                fixed_count += 1
            
            for tag in new_tags:
                tag_stats[tag] += 1
        
        print(f"   ✓ 修复了 {fixed_count} 个页面的标签")
        print(f"\n   📊 标签使用统计 (Top 20):")
        for tag, count in sorted(tag_stats.items(), key=lambda x: x[1], reverse=True)[:20]:
            print(f"     - {tag}: {count} 个页面")
        
        return {"fixed": fixed_count, "tag_stats": dict(tag_stats)}
    
    def _normalize_tags(self, tags: List[str], frontmatter: Dict,
                        filepath: Path) -> List[str]:
        """规范化标签列表"""
        new_tags = []
        
        for tag in tags:
            if tag == "person/company/project/paper":
                entity_type = frontmatter.get("entity_type", "")
                if entity_type and entity_type in ENTITY_TYPES:
                    new_tags.append(entity_type)
                else:
                    new_tags.append("unclassified")
            elif tag == "redirect":
                new_tags.append(tag)
            else:
                normalized = tag.lower().strip().replace(' ', '-')
                if normalized:
                    new_tags.append(normalized)
        
        page_type = frontmatter.get("type", "")
        if page_type == "entity":
            entity_type = frontmatter.get("entity_type", "")
            if entity_type and entity_type not in new_tags:
                new_tags.insert(0, entity_type)
        
        if page_type == "concept":
            concept_cat = frontmatter.get("concept_category", "")
            if concept_cat and concept_cat not in new_tags:
                new_tags.insert(0, concept_cat)
        
        return list(dict.fromkeys(new_tags))


def main():
    parser = argparse.ArgumentParser(
        description="LLM Wiki - 实体分类与概念归并工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/classify.py --classify-entities     # 对实体重新分类
  python scripts/classify.py --merge-concepts        # 检测并归并同义概念
  python scripts/classify.py --fix-tags              # 修复标签
  python scripts/classify.py --all                   # 执行全部
        """
    )
    
    parser.add_argument("--classify-entities", action="store_true",
                       help="对所有实体进行细粒度分类")
    parser.add_argument("--merge-concepts", action="store_true",
                       help="检测并归并同义概念")
    parser.add_argument("--fix-tags", action="store_true",
                       help="修复所有页面的标签")
    parser.add_argument("--all", action="store_true",
                       help="执行全部操作")
    parser.add_argument("--use-llm", action="store_true",
                       help="对规则无法分类的实体使用 LLM 辅助（较慢）")
    parser.add_argument("--yes", "-y", action="store_true",
                       help="自动确认所有操作，不询问")
    
    args = parser.parse_args()
    
    try:
        if args.all or args.classify_entities:
            classifier = EntityClassifier(".", use_llm=args.use_llm)
            classifier.classify_all_entities()
        
        if args.all or args.merge_concepts:
            merger = ConceptMerger(".")
            groups = merger.find_synonym_concepts()
            
            if groups:
                if args.yes:
                    merger.merge_synonym_groups(groups)
                else:
                    answer = input("\n是否执行归并？(y/N): ").strip().lower()
                    if answer == 'y':
                        merger.merge_synonym_groups(groups)
                    else:
                        print("跳过归并操作")
        
        if args.all or args.fix_tags:
            fixer = TagFixer(".")
            fixer.fix_all_tags()
        
        if not any([args.classify_entities, args.merge_concepts, 
                    args.fix_tags, args.all]):
            parser.print_help()
    
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
