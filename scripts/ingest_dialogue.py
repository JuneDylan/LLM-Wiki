#!/usr/bin/env python3
"""
LLM Wiki - Dialogue Distill 工作流（对话记录蒸馏）
功能：读取 AI 对话记录 → 提取核心问题/结论/代码 → 生成知识页
使用方法: python scripts/ingest_dialogue.py raw/dialogues/kimi-xxx.md

支持的对话格式:
  - 豆包 / Kimi 导出的 Markdown
  - 通用 Q&A markdown（带 ## 用户/助手 或 **User**/**Assistant** 标记）
"""

import sys
import os
import io
import re
from pathlib import Path
from datetime import datetime

# Windows 终端默认编码为 GBK，强制 stdout 使用 UTF-8 以支持 emoji
if sys.platform == "win32":
    try:
        if sys.stdout.encoding != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except (AttributeError, io.UnsupportedOperation):
        pass

sys.path.insert(0, str(Path(__file__).parent))
from utils import WikiUtils, MetadataManager, LogManager, create_template
from llm_client import LLMClient


class DialogueIngestWorkflow:
    """对话记录蒸馏工作流"""
    
    def __init__(self, base_dir: str = "."):
        self.utils = WikiUtils(base_dir)
        self.meta_mgr = MetadataManager(self.utils)
        self.log_mgr = LogManager(self.utils)
        self.llm = LLMClient()
    
    def ingest_file(self, raw_filepath: str) -> dict:
        print(f"\n{'='*60}")
        print(f"🗣️ 开始蒸馏对话记录: {raw_filepath}")
        print(f"{'='*60}\n")
        
        filepath = Path(raw_filepath)
        if not filepath.is_absolute():
            raw_str = str(raw_filepath).replace('\\', '/')
            if raw_str.startswith('raw/'):
                filepath = self.utils.base_dir / raw_filepath
            else:
                filepath = self.utils.get_raw_path(raw_filepath)
        
        if not filepath.exists():
            raise FileNotFoundError(f"文件不存在: {filepath}")
        
        result = {
            "raw_file": str(filepath),
            "source_page": None,
            "created_concepts": [],
            "created_entities": [],
            "updated_pages": [],
            "errors": []
        }
        
        try:
            # 步骤 1: 读取并解析对话
            print("📖 [步骤 1/7] 读取对话记录...")
            raw_content = self.utils.read_file(filepath)
            dialogue = self._parse_dialogue(raw_content)
            print(f"   ✓ 识别到 {len(dialogue['turns'])} 轮对话，{len(dialogue['code_blocks'])} 个代码块")
            
            # 步骤 2: LLM 分析对话，提取结构化知识
            print("\n🧠 [步骤 2/7] AI 正在分析对话内容...")
            analysis = self.llm.analyze_dialogue(raw_content, filepath.stem)
            print(f"   ✓ 主题: {analysis.get('topic', '未知')}")
            print(f"   ✓ 提取实体: {len(analysis.get('entities', []))} 个")
            print(f"   ✓ 提取概念: {len(analysis.get('concepts', []))} 个")
            print(f"   ✓ 核心问题: {len(analysis.get('core_questions', []))} 个")
            
            # 步骤 3: 生成对话摘要页
            print("\n📝 [步骤 3/7] 生成对话知识页...")
            source_page = self._create_dialogue_source_page(
                filepath, dialogue, analysis
            )
            result["source_page"] = source_page
            print(f"   ✓ 知识页已创建: {source_page}")
            
            # 步骤 4-5: 处理实体和概念
            entities = analysis.get("entities", [])
            concepts = analysis.get("concepts", [])
            
            print("\n👤 [步骤 4/7] 处理实体页...")
            for entity in entities:
                entity_page = self._process_entity(entity, filepath, analysis)
                if entity_page:
                    if entity_page["created"]:
                        result["created_entities"].append(entity_page["path"])
                    else:
                        result["updated_pages"].append(entity_page["path"])
            
            print("\n💡 [步骤 5/7] 处理概念页...")
            for concept in concepts:
                concept_page = self._process_concept(concept, filepath, analysis)
                if concept_page:
                    if concept_page["created"]:
                        result["created_concepts"].append(concept_page["path"])
                    else:
                        result["updated_pages"].append(concept_page["path"])
            
            # 步骤 6: 添加交叉链接
            print("\n🔗 [步骤 6/7] 添加交叉链接...")
            self._add_cross_links(entities, concepts, filepath)
            print("   ✓ 交叉链接已添加")
            
            # 步骤 7: 更新图谱、元数据和索引
            print("\n🕸️ [步骤 7/7] 更新知识图谱与索引...")
            self._update_graph_and_dependencies(
                source_page,
                result["created_concepts"],
                result["created_entities"],
                result["updated_pages"]
            )
            
            file_id = self.meta_mgr.add_raw_file(filepath, {
                "title": analysis.get("topic", filepath.stem),
                "tags": concepts + entities
            })
            self.meta_mgr.mark_as_processed(
                file_id, source_page, concepts, entities
            )
            
            self.log_mgr.log_ingest(
                raw_filepath,
                f"蒸馏对话 {filepath.name}，主题: {analysis.get('topic', '未知')}，"
                f"提取 {len(concepts)} 个概念、{len(entities)} 个实体",
                result["created_concepts"] + result["created_entities"],
                result["updated_pages"]
            )
            
            self._update_index()
            print("   ✓ 索引已更新")
            
            # 输出统计
            print(f"\n{'='*60}")
            print("✅ 蒸馏完成！统计信息:")
            print(f"{'='*60}")
            print(f"  🗣️  对话文件: {filepath.name}")
            print(f"  📝 知识页: {source_page}")
            print(f"  💡 新建概念: {len(result['created_concepts'])} 个")
            print(f"  👤 新建实体: {len(result['created_entities'])} 个")
            print(f"  🔄 更新页面: {len(result['updated_pages'])} 个")
            print(f"{'='*60}\n")
            
        except Exception as e:
            result["errors"].append(str(e))
            print(f"\n❌ 蒸馏失败: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        return result
    
    def _parse_dialogue(self, content: str) -> dict:
        """解析对话记录，提取问答对和代码块"""
        dialogue = {"turns": [], "code_blocks": []}
        
        # 提取所有代码块
        code_pattern = r'```(\w+)?\n(.*?)```'
        for match in re.finditer(code_pattern, content, re.DOTALL):
            lang = match.group(1) or "text"
            code = match.group(2).strip()
            if len(code) > 30:  # 过滤太短的代码块
                dialogue["code_blocks"].append({"lang": lang, "code": code})
        
        # 尝试识别问答对
        # 模式 1: 豆包/Kimi 常见的 ## 用户 / ## 助手
        pattern1 = r'(?:^|\n)##\s*(?:用户|我|User)\s*\n(.*?)(?=\n##\s*(?:助手|AI|Assistant)|\Z)'
        pattern2 = r'(?:^|\n)##\s*(?:助手|AI|Assistant)\s*\n(.*?)(?=\n##\s*(?:用户|我|User)|\Z)'
        
        users1 = re.findall(pattern1, content, re.DOTALL)
        assistants1 = re.findall(pattern2, content, re.DOTALL)
        
        # 模式 2: **用户**: / **助手**:
        pattern3 = r'(?:^|\n)\*\*(?:用户|我|User)\*\*[:：]\s*\n?(.*?)(?=\n\*\*(?:助手|AI|Assistant)\*\*[:：]|\Z)'
        pattern4 = r'(?:^|\n)\*\*(?:助手|AI|Assistant)\*\*[:：]\s*\n?(.*?)(?=\n\*\*(?:用户|我|User)\*\*[:：]|\Z)'
        
        users2 = re.findall(pattern3, content, re.DOTALL)
        assistants2 = re.findall(pattern4, content, re.DOTALL)
        
        # 模式 3: 简单的时间线格式（带时间戳）
        pattern5 = r'(?:^|\n)\d{2}:\d{2}(?::\d{2})?\s*\n?(?:我|用户)[：:]\s*(.*?)(?=\n\d{2}:\d{2}(?::\d{2})?\s*\n?(?:AI|助手)[：:]|\Z)'
        pattern6 = r'(?:^|\n)\d{2}:\d{2}(?::\d{2})?\s*\n?(?:AI|助手)[：:]\s*(.*?)(?=\n\d{2}:\d{2}(?::\d{2})?\s*\n?(?:我|用户)[：:]|\Z)'
        
        users3 = re.findall(pattern5, content, re.DOTALL)
        assistants3 = re.findall(pattern6, content, re.DOTALL)
        
        # 选择匹配最多的模式
        candidates = [
            (users1, assistants1),
            (users2, assistants2),
            (users3, assistants3),
        ]
        best = max(candidates, key=lambda x: len(x[0]) + len(x[1]))
        
        user_turns, assistant_turns = best
        max_turns = max(len(user_turns), len(assistant_turns))
        
        for i in range(max_turns):
            if i < len(user_turns):
                dialogue["turns"].append({
                    "role": "user",
                    "content": user_turns[i].strip()
                })
            if i < len(assistant_turns):
                dialogue["turns"].append({
                    "role": "assistant",
                    "content": assistant_turns[i].strip()
                })
        
        return dialogue
    
    def _create_dialogue_source_page(self, filepath: Path, dialogue: dict, analysis: dict) -> str:
        """创建对话摘要页"""
        filename = filepath.stem
        slug = self.utils.slugify(filename)
        source_path = self.utils.get_wiki_path("sources", f"{slug}.md")
        today = self.utils.get_today()
        
        topic = analysis.get("topic", filename)
        # 安全转义：避免 topic 中的特殊字符破坏 frontmatter 和 Markdown 标题
        safe_topic = topic.replace('"', '\\"').replace('\n', ' ').replace('#', '')
        core_questions = analysis.get("core_questions", [])
        key_insights = analysis.get("key_insights", [])
        conclusion = analysis.get("conclusion", "")
        entities = analysis.get("entities", [])
        concepts = analysis.get("concepts", [])
        
        # 构建核心问题部分
        questions_md = "\n".join(f"{i+1}. {q}" for i, q in enumerate(core_questions)) if core_questions else "1. （待补充）"
        
        # 构建关键洞察
        insights_md = "\n".join(f"- {insight}" for insight in key_insights) if key_insights else "- （待补充）"
        
        # 构建代码片段部分
        code_md = ""
        if dialogue["code_blocks"]:
            for i, cb in enumerate(dialogue["code_blocks"][:5], 1):
                code_md += f"\n### 代码片段 {i} ({cb['lang']})\n\n```{cb['lang']}\n{cb['code'][:500]}\n```\n"
                if len(cb['code']) > 500:
                    code_md += "\n*... 代码过长，已截断*\n"
        else:
            code_md = "\n（无代码片段）\n"
        
        # 构建实体/概念链接
        entity_links = "\n".join(f"- [[{e}]]" for e in entities) if entities else "- （待补充）"
        concept_links = "\n".join(f"- [[{c}]]" for c in concepts) if concepts else "- （待补充）"
        
        # 保留关键问答对（最多 3 轮）
        qa_md = ""
        qa_count = 0
        for turn in dialogue["turns"]:
            if turn["role"] == "user" and qa_count < 3:
                user_q = turn["content"][:200]
                if len(turn["content"]) > 200:
                    user_q += "..."
                qa_md += f"\n**问**: {user_q}\n\n"
                qa_count += 1
            elif turn["role"] == "assistant" and qa_md.endswith("**问**:") == False:
                assistant_a = turn["content"][:300]
                if len(turn["content"]) > 300:
                    assistant_a += "..."
                qa_md += f"**答**: {assistant_a}\n\n---\n"
        
        source_content = f"""---
title: "{safe_topic}"
type: source
created: "{today}"
updated: "{today}"
confidence: high
sources: ["{filepath.relative_to(self.utils.base_dir).as_posix()}"]
tags: []
related: []
status: draft
---

# {safe_topic}: 对话蒸馏

## 对话概览
- **原始文件**: {filename}
- **轮数**: {len([t for t in dialogue['turns'] if t['role'] == 'user'])} 问 / {len([t for t in dialogue['turns'] if t['role'] == 'assistant'])} 答
- **代码片段**: {len(dialogue['code_blocks'])} 个

## 核心问题
{questions_md}

## 关键洞察
{insights_md}

## 最终结论
{conclusion if conclusion else '[待补充]'}

## 涉及实体
{entity_links}

## 涉及概念
{concept_links}

## 代码片段
{code_md}

## 关键问答记录
{qa_md if qa_md else '[简要记录省略]'}

---
*最后更新: {today}*
*来源: AI 对话记录蒸馏*
"""
        
        self.utils.write_file(source_path, source_content)
        return str(source_path.relative_to(self.utils.base_dir))
    
    def _process_entity(self, entity_name: str, source_file: Path, analysis: dict) -> dict:
        """处理单个实体"""
        slug = self.utils.slugify(entity_name)
        entity_path = self.utils.get_wiki_path("entities", f"{slug}.md")
        created = not entity_path.exists()
        
        if created:
            template = create_template(self.utils, "entity")
            entity_content = template.replace("[实体名称]", entity_name)
            entity_content = entity_content.replace("**类型**: 人物/公司/项目/论文",
                                                   "**类型**: [自动检测]")
            entity_content = entity_content.replace("- **成立/出生日期**: [日期]",
                                                   "- **来源**: 来自对话记录 " + source_file.name)
            self.utils.write_file(entity_path, entity_content)
            self.meta_mgr.add_graph_node(slug, f"wiki/entities/{slug}.md", "entity", entity_name)
        
        relative_path = str(entity_path.relative_to(self.utils.base_dir))
        source_slug = self.utils.slugify(Path(source_file).stem)
        self.meta_mgr.add_graph_edge(slug, source_slug, "extracted_from")
        
        return {"path": relative_path, "created": created}
    
    def _process_concept(self, concept_name: str, source_file: Path, analysis: dict) -> dict:
        """处理单个概念"""
        slug = self.utils.slugify(concept_name)
        concept_path = self.utils.get_wiki_path("concepts", f"{slug}.md")
        created = not concept_path.exists()
        
        if created:
            template = create_template(self.utils, "concept")
            concept_content = template.replace("[概念名称]", concept_name)
            concept_content = concept_content.replace("[一句话定义，清晰简洁]",
                                                     f"[{concept_name}] 的定义（待补充）")
            concept_content = concept_content.replace("[详细解释工作原理、关键机制]",
                                                     f"[{concept_name}] 的核心原理（待补充）")
            self.utils.write_file(concept_path, concept_content)
            self.meta_mgr.add_graph_node(slug, f"wiki/concepts/{slug}.md", "concept", concept_name)
        
        relative_path = str(concept_path.relative_to(self.utils.base_dir))
        source_slug = self.utils.slugify(Path(source_file).stem)
        self.meta_mgr.add_graph_edge(slug, source_slug, "mentioned_in")
        
        return {"path": relative_path, "created": created}
    
    def _add_cross_links(self, entities: list, concepts: list, source_file: Path):
        """为新页面添加交叉链接"""
        for entity in entities:
            slug = self.utils.slugify(entity)
            entity_path = self.utils.get_wiki_path("entities", f"{slug}.md")
            if not entity_path.exists():
                continue
            content = self.utils.read_file(entity_path)
            placeholder = '## 相关概念\n- **[[概念A]]**: [关联说明]\n- **[[概念B]]**: [关联说明]'
            if placeholder in content and concepts:
                concept_links = '\n'.join(f'- **[[{c}]]**: 在对话 {source_file.name} 中提及' for c in concepts)
                content = content.replace(placeholder, f'## 相关概念\n{concept_links}')
                frontmatter, body = self.utils.parse_frontmatter(content)
                frontmatter.setdefault('related', [])
                for c in concepts:
                    if c not in frontmatter['related']:
                        frontmatter['related'].append(c)
                content = self.utils.build_frontmatter(frontmatter) + body
                self.utils.write_file(entity_path, content)
        
        for concept in concepts:
            slug = self.utils.slugify(concept)
            concept_path = self.utils.get_wiki_path("concepts", f"{slug}.md")
            if not concept_path.exists():
                continue
            content = self.utils.read_file(concept_path)
            placeholder = '## 与其他概念的关系\n- **[[相关概念A]]**: [关系描述]\n- **[[相关概念B]]**: [关系描述]'
            if placeholder in content and entities:
                entity_links = '\n'.join(f'- **[[{e}]]**: 在对话 {source_file.name} 中提及' for e in entities)
                content = content.replace(placeholder, f'## 与其他概念的关系\n{entity_links}')
                frontmatter, body = self.utils.parse_frontmatter(content)
                frontmatter.setdefault('related', [])
                for e in entities:
                    if e not in frontmatter['related']:
                        frontmatter['related'].append(e)
                content = self.utils.build_frontmatter(frontmatter) + body
                self.utils.write_file(concept_path, content)
    
    def _update_graph_and_dependencies(self, source_page: str, created_concepts: list,
                                      created_entities: list, updated_pages: list):
        """更新知识图谱和依赖关系"""
        source_relative = source_page.replace('\\', '/')
        source_slug = Path(source_relative).stem
        self.meta_mgr.add_graph_node(source_slug, source_relative, "source", source_slug.replace('-', ' ').title())
        
        all_related = created_concepts + created_entities + updated_pages
        self.meta_mgr.update_dependencies(source_page, depends_on=[], dependents=all_related)
        
        for page in all_related:
            self.meta_mgr.update_dependencies(page, depends_on=[source_page], dependents=[])
            page_slug = Path(page).stem
            self.meta_mgr.add_graph_edge(page_slug, source_slug, "derived_from")
    
    def _update_index(self):
        """更新主页索引"""
        from ingest import IngestWorkflow
        IngestWorkflow(self.utils.base_dir)._update_index()


def main():
    if len(sys.argv) < 2:
        print("""
🗣️ LLM Wiki - 对话记录蒸馏工具

使用方法:
  python scripts/ingest_dialogue.py <对话记录路径>
  
示例:
  python scripts/ingest_dialogue.py raw/dialogues/kimi-transformer.md
  python scripts/ingest_dialogue.py raw/dialogues/doubao-python.md
""")
        sys.exit(1)
    
    raw_file = sys.argv[1]
    
    try:
        workflow = DialogueIngestWorkflow(".")
        result = workflow.ingest_file(raw_file)
        
        if result["errors"]:
            print(f"\n⚠️ 警告: {len(result['errors'])} 个错误")
            for error in result["errors"]:
                print(f"  - {error}")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
