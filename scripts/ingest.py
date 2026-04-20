#!/usr/bin/env python3
"""
LLM Wiki - Ingest 工作流（资料录入）
功能：读取原始资料 → 生成摘要 → 提取实体/概念 → 创建/更新页面 → 添加链接
使用方法: python scripts/ingest.py raw/articles/filename.md
"""

import sys
import os
import io
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

try:
    from dedup import DedupDetector
    DEDUP_AVAILABLE = True
except ImportError:
    DEDUP_AVAILABLE = False


class IngestWorkflow:
    """资料录入工作流"""
    
    def __init__(self, base_dir: str = "."):
        self.utils = WikiUtils(base_dir)
        self.meta_mgr = MetadataManager(self.utils)
        self.log_mgr = LogManager(self.utils)
        self.llm = LLMClient()
        
    def ingest_file(self, raw_filepath: str) -> dict:
        """
        执行完整的录入流程
        返回操作结果统计
        """
        print(f"\n{'='*60}")
        print(f"📥 开始录入: {raw_filepath}")
        print(f"{'='*60}\n")
        
        filepath = Path(raw_filepath)
        if not filepath.is_absolute():
            raw_str = str(raw_filepath).replace('\\', '/')
            if raw_str.startswith('raw/'):
                filepath = self.utils.base_dir / raw_filepath
            else:
                filepath = self.utils.get_raw_path(raw_filepath)
        
        if not filepath.exists():
            raise FileNotFoundError(f"原始文件不存在: {filepath}")
        
        # 录入前去重检查
        if DEDUP_AVAILABLE:
            print("🔍 [步骤 0/8] 录入前去重检查...")
            detector = DedupDetector(str(self.utils.base_dir))
            dedup_result = detector.check_before_ingest(str(filepath))
            
            if dedup_result["is_duplicate"]:
                print(f"   ⚠️  检测到重复内容！")
                print(f"   类型: {dedup_result['duplicate_type']}")
                print(f"   建议: {dedup_result['recommendation']}")
                
                if dedup_result["similar_files"]:
                    for f in dedup_result["similar_files"]:
                        print(f"   - 相同文件: {f}")
                if dedup_result["similar_pages"]:
                    for p in dedup_result["similar_pages"]:
                        print(f"   - 相似页面: {p['path']} (相似度: {p['similarity']})")
                
                print(f"\n   ❌ 跳过录入（如需强制录入，请使用 --force 参数）\n")
                return {
                    "raw_file": str(filepath),
                    "source_page": None,
                    "created_concepts": [],
                    "created_entities": [],
                    "updated_pages": [],
                    "errors": [],
                    "skipped_reason": f"重复内容: {dedup_result['recommendation']}"
                }
            else:
                if dedup_result["similar_pages"]:
                    print(f"   ⚠️  发现 {len(dedup_result['similar_pages'])} 个部分相似页面:")
                    for p in dedup_result["similar_pages"]:
                        print(f"   - {p['path']} (相似度: {p['similarity']})")
                    print(f"   建议: {dedup_result['recommendation']}")
                else:
                    print(f"   ✓ 无重复，可以安全录入")
        else:
            print("ℹ️  去重模块不可用，跳过录入前检查")
        
        result = {
            "raw_file": str(filepath),
            "source_page": None,
            "created_concepts": [],
            "created_entities": [],
            "updated_pages": [],
            "errors": []
        }
        
        try:
            # 步骤 1: 读取原始文件
            print("📖 [步骤 1/8] 读取原始文件...")
            if filepath.suffix.lower() == '.pdf':
                content = self.utils.read_pdf_text(filepath)
                print(f"   ✓ 已提取 PDF 文本，共 {len(content)} 字符")
            else:
                content = self.utils.read_file(filepath)
                print(f"   ✓ 文件大小: {len(content)} 字符")
            
            # 步骤 2: 生成摘要页
            print("\n📝 [步骤 2/8] 生成摘要页...")
            source_page = self._create_source_page(filepath, content)
            result["source_page"] = source_page
            print(f"   ✓ 摘要页已创建: {source_page}")
            
            # 步骤 3: 分析并提取实体和概念
            print("\n🔍 [步骤 3/8] 分析内容，提取实体和概念...")
            entities, concepts = self._extract_entities_and_concepts(content, filepath.name)
            
            entity_names = [e["name"] if isinstance(e, dict) else e for e in entities]
            concept_names = [c["name"] if isinstance(c, dict) else c for c in concepts]
            print(f"   ✓ 发现实体: {len(entity_names)} 个 - {entity_names}")
            print(f"   ✓ 发现概念: {len(concept_names)} 个 - {concept_names}")
            
            # 步骤 4: 创建或更新实体页
            print("\n👤 [步骤 4/8] 处理实体页...")
            for entity in entities:
                if isinstance(entity, dict):
                    entity_name = entity["name"]
                    entity_type = entity.get("type", "")
                else:
                    entity_name = entity
                    entity_type = ""
                entity_page = self._process_entity(entity_name, filepath, content, entity_type)
                if entity_page:
                    if entity_page["created"]:
                        result["created_entities"].append(entity_page["path"])
                    else:
                        result["updated_pages"].append(entity_page["path"])
            
            # 步骤 5: 创建或更新概念页
            print("\n💡 [步骤 5/8] 处理概念页...")
            for concept in concepts:
                if isinstance(concept, dict):
                    concept_name = concept["name"]
                    concept_cat = concept.get("category", "")
                else:
                    concept_name = concept
                    concept_cat = ""
                concept_page = self._process_concept(concept_name, filepath, content, concept_cat)
                if concept_page:
                    if concept_page["created"]:
                        result["created_concepts"].append(concept_page["path"])
                    else:
                        result["updated_pages"].append(concept_page["path"])
            
            # 步骤 6: 填充 source 页面占位符并添加交叉链接
            print("\n🔗 [步骤 6/8] 填充摘要页占位符并添加交叉链接...")
            self._finalize_source_page(entity_names, concept_names, filepath)
            self._add_cross_links(entity_names, concept_names, filepath)
            print("   ✓ 摘要页已完善，交叉链接已添加")
            
            # 步骤 7: 更新知识图谱和依赖关系
            print("\n🕸️ [步骤 7/8] 更新知识图谱...")
            self._update_graph_and_dependencies(source_page, 
                                                result["created_concepts"],
                                                result["created_entities"],
                                                result["updated_pages"])
            print("   ✓ 知识图谱已更新")
            
            # 步骤 8: 记录日志和更新元数据
            print("\n📊 [步骤 8/8] 记录日志和元数据...")
            file_id = self.meta_mgr.add_raw_file(filepath, {
                "title": filepath.stem,
                "tags": concept_names + entity_names
            })
            self.meta_mgr.mark_as_processed(
                file_id, 
                source_page,
                concepts,
                entities
            )
            
            self.log_mgr.log_ingest(
                raw_filepath,
                f"处理文件 {filepath.name}，提取 {len(concepts)} 个概念、{len(entities)} 个实体",
                result["created_concepts"] + result["created_entities"],
                result["updated_pages"]
            )
            print("   ✓ 日志和元数据已更新")
            
            # 步骤 9: 更新主页索引
            print("\n📑 [最后步骤] 更新主页索引...")
            self._update_index()
            print("   ✓ 索引已更新")
            
            # 输出统计信息
            print(f"\n{'='*60}")
            print("✅ 录入完成！统计信息:")
            print(f"{'='*60}")
            print(f"  📄 原始文件: {filepath.name}")
            print(f"  📝 摘要页: {source_page}")
            print(f"  💡 新建概念: {len(result['created_concepts'])} 个")
            print(f"  👤 新建实体: {len(result['created_entities'])} 个")
            print(f"  🔄 更新页面: {len(result['updated_pages'])} 个")
            print(f"{'='*60}\n")
            
        except Exception as e:
            result["errors"].append(str(e))
            print(f"\n❌ 录入失败: {e}")
            raise
        
        return result
    
    def _create_source_page(self, filepath: Path, content: str) -> str:
        """创建资料摘要页 (wiki/sources/)，优先使用 LLM 生成内容"""
        filename = filepath.stem
        slug = self.utils.slugify(filename)
        source_path = self.utils.get_wiki_path("sources", f"{slug}.md")
        
        today = self.utils.get_today()
        summary = self.llm.summarize_source(content, filename)
        
        # 如果 LLM 调用失败，回退到基础模板
        if not summary:
            template = create_template(self.utils, "source")
            source_content = template.replace("[资料标题]", filename)
            source_content = source_content.replace("raw/path/to/original/file",
                                                   filepath.relative_to(self.utils.base_dir).as_posix())
            source_content = source_content.replace("[日期]", today)
            self.utils.write_file(source_path, source_content)
            return str(source_path.relative_to(self.utils.base_dir))
        
        # 使用 LLM 结果填充模板
        template = create_template(self.utils, "source")
        source_content = template.replace("[资料标题]", filename)
        source_content = source_content.replace("raw/path/to/original/file",
                                               filepath.relative_to(self.utils.base_dir).as_posix())
        source_content = source_content.replace("[日期]", today)
        
        # 预定义默认值（避免 f-string 表达式中出现反斜杠）
        _default_core_points = "1. ...\n2. ...\n3. ..."
        _default_todo = "[待补充]"
        _default_pending = "- （待补充）"
        _default_quote = "> [待补充]"
        
        replacements = {
            "## 核心观点\n1. 观点 1\n2. 观点 2\n3. 观点 3\n": f"## 核心观点\n{summary.get('core_points', _default_core_points)}\n",
            "## 关键发现\n[最重要的发现或结论]\n": f"## 关键发现\n{summary.get('key_findings', _default_todo)}\n",
            "## 方法论\n[研究方法、实验设计等]\n": f"## 方法论\n{summary.get('methodology', _default_todo)}\n",
            "## 数据与结果\n[重要数据、图表解读]\n": f"## 数据与结果\n{summary.get('data_results', _default_todo)}\n",
            "## 局限性\n[研究的不足之处]\n": f"## 局限性\n{summary.get('limitations', _default_todo)}\n",
            "## 提取的实体\n- [[实体1]]\n- [[实体2]]\n": f"## 提取的实体\n{summary.get('entities', _default_pending)}\n",
            "## 提取的概念\n- [[概念1]]\n- [[概念2]]\n": f"## 提取的概念\n{summary.get('concepts', _default_pending)}\n",
            "## 原文引用\n> [重要段落直接引用]\n": f"## 原文引用\n{summary.get('quote', _default_quote)}\n",
        }
        
        for old, new in replacements.items():
            if old in source_content:
                source_content = source_content.replace(old, new)
        
        self.utils.write_file(source_path, source_content)
        return str(source_path.relative_to(self.utils.base_dir))
    
    def _extract_entities_and_concepts(self, content: str, filename: str) -> tuple:
        """调用 LLM 智能提取实体和概念，失败时回退到规则提取"""
        result = self.llm.extract_entities_and_concepts(content, filename)
        
        # 如果 LLM 成功返回，直接使用
        if result["entities"] or result["concepts"]:
            return result["entities"], result["concepts"]
        
        # 回退到规则提取
        entities, concepts = [], []
        import re
        
        entity_patterns = [
            r'\b(OpenAI|Google|DeepMind|Meta|Anthropic|Microsoft|NVIDIA)\b',
            r'\b(GPT-4|GPT-3|BERT|T5|LLaMA|Claude|Gemini)\b',
            r'\b(Karpathy|LeCun|Hinton|Goodfellow|Vaswani|Sutskever)\b'
        ]
        
        concept_patterns = [
            r'\b(Transformer|Attention|Fine-tuning|RLHF|LoRA|MoE)\b',
            r'\b(Large Language Model|Neural Network|Deep Learning|Machine Learning)\b',
            r'\b(Tokenization|Embedding|Vector Database|RAG)\b',
            r'\b(Scaling Law|Emergent Ability|Chain-of-Thought|Prompt Engineering)\b'
        ]
        
        for pattern in entity_patterns:
            matches = re.findall(pattern, content)
            entities.extend(matches)
        
        for pattern in concept_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            concepts.extend(matches)
        
        entities = list(dict.fromkeys(entities))
        concepts = list(dict.fromkeys(concepts))
        
        return entities, concepts
    
    def _extract_context_snippet(self, content: str, keyword: str,
                                   window: int = 300) -> str:
        """从原始内容中提取关键词周围的上下文片段"""
        idx = content.lower().find(keyword.lower())
        if idx == -1:
            return content[:800]
        start = max(0, idx - window)
        end = min(len(content), idx + len(keyword) + window)
        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        return snippet
    
    def _process_entity(self, entity_name: str, source_file: Path, 
                       content: str, entity_type: str = "") -> dict:
        """处理单个实体：创建或更新实体页"""
        slug = self.utils.slugify(entity_name)
        entity_path = self.utils.get_wiki_path("entities", f"{slug}.md")
        created = False
        
        if not entity_path.exists():
            template = create_template(self.utils, "entity")
            today = self.utils.get_today()
            
            entity_content = template.replace("[实体名称]", entity_name)
            
            type_label = entity_type if entity_type else "[自动检测]"
            entity_content = entity_content.replace("**类型**: 人物/公司/项目/论文",
                                                   f"**类型**: {type_label}")
            entity_content = entity_content.replace("- **成立/出生日期**: [日期]",
                                                   "- **来源**: 首次出现于 " + source_file.name)
            
            # 尝试用 LLM 生成一句话定义
            snippet = self._extract_context_snippet(content, entity_name)
            definition = self.llm.generate_stub_definition(entity_name, entity_type or "entity", snippet)
            if definition:
                entity_content = entity_content.replace("[一句话描述该实体是什么，解决什么问题]", definition)
                print(f"   ✨ 已生成定义: {entity_name}")
            else:
                entity_content = entity_content.replace("[一句话描述该实体是什么，解决什么问题]",
                                                       f"{entity_name}（定义待补充）")
            
            frontmatter, body = self.utils.parse_frontmatter(entity_content)
            if entity_type:
                frontmatter["entity_type"] = entity_type
                frontmatter["tags"] = [entity_type]
            entity_content = self.utils.build_frontmatter(frontmatter) + body
            
            self.utils.write_file(entity_path, entity_content)
            created = True
            
            self.meta_mgr.add_graph_node(slug, 
                                        f"wiki/entities/{slug}.md",
                                        "entity", 
                                        entity_name)
        else:
            existing_content = self.utils.read_file(entity_path)
            new_source_ref = f"- [{source_file.name}](raw/{source_file.parent.name}/{source_file.name})"
            
            if "## 参考资料" in existing_content and new_source_ref not in existing_content:
                updated = existing_content.replace("## 参考资料", 
                                                  "## 参考资料\n" + new_source_ref)
                frontmatter, body = self.utils.parse_frontmatter(updated)
                
                if "sources" in frontmatter:
                    source_rel = f"raw/{source_file.parent.name}/{source_file.name}"
                    if source_rel not in frontmatter.get("sources", []):
                        frontmatter["sources"].append(source_rel)
                        frontmatter["updated"] = self.utils.get_today()
                        
                        updated = self.utils.build_frontmatter(frontmatter) + body
                        self.utils.write_file(entity_path, updated)
        
        relative_path = str(entity_path.relative_to(self.utils.base_dir))
        source_slug = self.utils.slugify(Path(source_file).stem)
        self.meta_mgr.add_graph_edge(slug, source_slug, "extracted_from")
        
        return {"path": relative_path, "created": created}
    
    def _process_concept(self, concept_name: str, source_file: Path,
                        content: str, concept_category: str = "") -> dict:
        """处理单个概念：创建或更新概念页"""
        slug = self.utils.slugify(concept_name)
        concept_path = self.utils.get_wiki_path("concepts", f"{slug}.md")
        created = False
        
        if not concept_path.exists():
            template = create_template(self.utils, "concept")
            today = self.utils.get_today()
            
            concept_content = template.replace("[概念名称]", concept_name)
            
            # 尝试用 LLM 生成一句话定义
            snippet = self._extract_context_snippet(content, concept_name)
            definition = self.llm.generate_stub_definition(concept_name, concept_category or "concept", snippet)
            if definition:
                concept_content = concept_content.replace("[一句话定义，清晰简洁]", definition)
                print(f"   ✨ 已生成定义: {concept_name}")
            else:
                concept_content = concept_content.replace("[一句话定义，清晰简洁]",
                                                         f"{concept_name} 的定义（待补充）")
            
            concept_content = concept_content.replace("[详细解释工作原理、关键机制]",
                                                     f"[{concept_name}] 的核心原理（待补充）")
            
            frontmatter, body = self.utils.parse_frontmatter(concept_content)
            if concept_category:
                frontmatter["concept_category"] = concept_category
                frontmatter["tags"] = [concept_category]
            concept_content = self.utils.build_frontmatter(frontmatter) + body
            
            self.utils.write_file(concept_path, concept_content)
            created = True
            
            self.meta_mgr.add_graph_node(slug,
                                        f"wiki/concepts/{slug}.md",
                                        "concept",
                                        concept_name)
        else:
            existing_content = self.utils.read_file(concept_path)
            new_source_ref = f"- [{source_file.name}](raw/{source_file.parent.name}/{source_file.name})"
            
            if "## 参考来源" in existing_content and new_source_ref not in existing_content:
                updated = existing_content.replace("## 参考来源",
                                                  "## 参考来源\n" + new_source_ref)
                frontmatter, body = self.utils.parse_frontmatter(updated)
                
                if "sources" in frontmatter:
                    source_rel = f"raw/{source_file.parent.name}/{source_file.name}"
                    if source_rel not in frontmatter.get("sources", []):
                        frontmatter["sources"].append(source_rel)
                        frontmatter["updated"] = self.utils.get_today()
                        
                        updated = self.utils.build_frontmatter(frontmatter) + body
                        self.utils.write_file(concept_path, updated)
        
        relative_path = str(concept_path.relative_to(self.utils.base_dir))
        source_slug = self.utils.slugify(Path(source_file).stem)
        self.meta_mgr.add_graph_edge(slug, source_slug, "mentioned_in")
        
        return {"path": relative_path, "created": created}
    
    def _finalize_source_page(self, entities: list, concepts: list, source_file: Path):
        """用实际提取的实体和概念替换 source 页面中的占位符"""
        slug = self.utils.slugify(source_file.stem)
        source_path = self.utils.get_wiki_path("sources", f"{slug}.md")
        if not source_path.exists():
            return
        
        content = self.utils.read_file(source_path)
        
        # 替换实体占位符
        entity_placeholder = '## 提取的实体\n- [[实体1]]\n- [[实体2]]'
        if entity_placeholder in content:
            if entities:
                entity_links = '\n'.join(f'- [[{e}]]' for e in entities)
            else:
                entity_links = '- （待补充）'
            content = content.replace(entity_placeholder, f'## 提取的实体\n{entity_links}')
        
        # 替换概念占位符
        concept_placeholder = '## 提取的概念\n- [[概念1]]\n- [[概念2]]'
        if concept_placeholder in content:
            if concepts:
                concept_links = '\n'.join(f'- [[{c}]]' for c in concepts)
            else:
                concept_links = '- （待补充）'
            content = content.replace(concept_placeholder, f'## 提取的概念\n{concept_links}')
        
        # 同步更新 frontmatter 的 related 字段
        frontmatter, body = self.utils.parse_frontmatter(content)
        frontmatter.setdefault('related', [])
        for item in entities + concepts:
            if item not in frontmatter['related']:
                frontmatter['related'].append(item)
        content = self.utils.build_frontmatter(frontmatter) + body
        
        self.utils.write_file(source_path, content)
    
    def _add_cross_links(self, entities: list, concepts: list, source_file: Path):
        """为新创建的实体页和概念页添加交叉链接，替换模板占位符"""
        if not entities or not concepts:
            return
        
        for entity in entities:
            slug = self.utils.slugify(entity)
            entity_path = self.utils.get_wiki_path("entities", f"{slug}.md")
            if not entity_path.exists():
                continue
            
            content = self.utils.read_file(entity_path)
            # 如果还是模板占位符，替换为实际概念链接
            placeholder = '## 相关概念\n- **[[概念A]]**: [关联说明]\n- **[[概念B]]**: [关联说明]'
            if placeholder in content:
                concept_links = '\n'.join(
                    f'- **[[{c}]]**: 在 {source_file.name} 中提及'
                    for c in concepts
                )
                content = content.replace(placeholder, f'## 相关概念\n{concept_links}')
                
                # 同步更新 frontmatter 的 related 字段
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
            if placeholder in content:
                entity_links = '\n'.join(
                    f'- **[[{e}]]**: 在 {source_file.name} 中提及'
                    for e in entities
                )
                content = content.replace(placeholder, f'## 与其他概念的关系\n{entity_links}')
                
                # 同步更新 frontmatter 的 related 字段
                frontmatter, body = self.utils.parse_frontmatter(content)
                frontmatter.setdefault('related', [])
                for e in entities:
                    if e not in frontmatter['related']:
                        frontmatter['related'].append(e)
                content = self.utils.build_frontmatter(frontmatter) + body
                self.utils.write_file(concept_path, content)
    
    def _update_graph_and_dependencies(self, source_page: str,
                                      created_concepts: list,
                                      created_entities: list,
                                      updated_pages: list):
        """更新知识图谱和依赖关系"""
        # 为 source 页面注册图谱节点
        source_relative = source_page.replace('\\', '/')
        source_slug = Path(source_relative).stem
        self.meta_mgr.add_graph_node(
            source_slug,
            source_relative,
            "source",
            source_slug.replace('-', ' ').title()
        )
        
        all_related = created_concepts + created_entities + updated_pages
        
        self.meta_mgr.update_dependencies(
            source_page,
            depends_on=[],  # source 页面不依赖其他 wiki 页面
            dependents=all_related
        )
        
        for page in all_related:
            self.meta_mgr.update_dependencies(
                page,
                depends_on=[source_page],
                dependents=[]
            )
            
            # 在实体/概念和 source 之间添加图谱边（如果尚未存在）
            page_slug = Path(page).stem
            self.meta_mgr.add_graph_edge(page_slug, source_slug, "derived_from")
    
    def _update_index(self):
        """更新主页索引 index.md"""
        index_path = self.utils.wiki_dir / "index.md"
        
        categories = {
            "concepts": ("💡 概念", []),
            "entities": ("👤 实体", []),
            "comparisons": ("⚖️ 对比", []),
            "sources": ("📄 资料", [])
        }
        
        for category, (title, _) in categories.items():
            files = self.utils.list_wiki_files(category)
            categories[category] = (title, files)
        
        today = self.utils.get_today()
        total_pages = sum(len(files) for _, files in categories.values())
        
        index_content = f"""# LLM Wiki 知识库

> **最后更新**: {today}
> **总页面数**: {total_pages}

## 🗂️ 目录

"""
        
        for category, (title, files) in categories.items():
            index_content += f"### {title} ({len(files)} 个)\n\n"
            
            if files:
                for f in sorted(files)[:20]:  # 最多显示 20 个
                    fm, _ = self.utils.parse_frontmatter(self.utils.read_file(f))
                    name = fm.get("title", f.stem)
                    rel_path = f.relative_to(self.utils.base_dir).as_posix()
                    
                    index_content += f"- [[{name}]] ({rel_path})\n"
                
                if len(files) > 20:
                    index_content += f"- ... 还有 {len(files) - 20} 个\n"
            else:
                index_content += "- （暂无）\n"
            
            index_content += "\n"
        
        index_content += f"""---

## 📊 统计信息

| 类别 | 数量 |
|------|------|
| 概念 | {len(categories['concepts'][1])} |
| 实体 | {len(categories['entities'][1])} |
| 对比 | {len(categories['comparisons'][1])} |
| 资料 | {len(categories['sources'][1])} |

## 🔍 快速导航

- [CLAUDE.md](CLAUDE.md): 本知识库的构建规则
- [变更日志](wiki/_log.md): 最近的更新记录

---
*由 LLM 自动维护 · 最后更新: {today}*
"""
        
        self.utils.write_file(index_path, index_content)


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("""
📚 LLM Wiki - 资料录入工具

使用方法:
  python scripts/ingest.py <raw文件路径>
  
示例:
  python scripts/ingest.py raw/articles/llm-trends.md
  python scripts/ingest.py papers/attention-is-all-you-need.pdf
  
支持格式:
  - Markdown (.md)
  - PDF (.pdf)
  - 文本文件 (.txt)
""")
        sys.exit(1)
    
    raw_file = sys.argv[1]
    
    try:
        workflow = IngestWorkflow(".")
        result = workflow.ingest_file(raw_file)
        
        if result["errors"]:
            print(f"\n⚠️  警告: {len(result['errors'])} 个错误")
            for error in result["errors"]:
                print(f"  - {error}")
            sys.exit(1)
        
    except FileNotFoundError as e:
        print(f"\n❌ 错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
