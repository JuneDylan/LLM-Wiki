#!/usr/bin/env python3
"""
LLM Wiki - 去重检测与合并模块
功能：三层去重（Raw文件级 → Wiki页面级 → 内容级）+ 智能合并
使用方法:
  python scripts/dedup.py                     # 运行完整去重检测
  python scripts/dedup.py --raw              # 仅检测 Raw 层重复文件
  python scripts/dedup.py --wiki             # 仅检测 Wiki 层相似页面
  python scripts/dedup.py --content          # 仅检测内容重叠
  python scripts/dedup.py --merge page1 page2 # 合并两个页面
  python scripts/dedup.py --auto-merge 0.9   # 自动合并相似度>0.9的页面
"""

import sys
import os
import io
import re
import argparse
import hashlib
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


class DedupDetector:
    """三层去重检测器"""
    
    SIMILARITY_HIGH = 0.9
    SIMILARITY_MEDIUM = 0.7
    SIMILARITY_LOW = 0.5
    
    def __init__(self, base_dir: str = "."):
        self.utils = WikiUtils(base_dir)
        self.meta_mgr = MetadataManager(self.utils)
        self.log_mgr = LogManager(self.utils)
        self.llm = LLMClient() if LLM_AVAILABLE else None
        
        self.duplicates = {
            "raw_exact": [],
            "raw_similar": [],
            "wiki_similar": [],
            "content_overlap": [],
        }
    
    # ================================================================
    # 第一层：Raw 文件级去重
    # ================================================================
    
    def check_raw_duplicates(self) -> Dict:
        """
        检测 raw/ 目录下的重复文件
        1. 精确重复：文件内容完全相同（hash 一致）
        2. 相似文件：内容高度相似（可能是同一文章的不同版本/翻译）
        """
        print("\n📁 [第一层] 检测 Raw 文件重复...\n")
        
        raw_files = self.utils.list_raw_files()
        print(f"   扫描到 {len(raw_files)} 个原始文件\n")
        
        hash_map = defaultdict(list)
        for filepath in raw_files:
            content = self._safe_read(filepath)
            if content:
                file_hash = self._content_hash(content)
                hash_map[file_hash].append(filepath)
        
        exact_dupes = {h: paths for h, paths in hash_map.items() if len(paths) > 1}
        
        for file_hash, paths in exact_dupes.items():
            group = {
                "hash": file_hash,
                "files": [str(p.relative_to(self.utils.base_dir)) for p in paths],
                "similarity": 1.0,
                "action": "delete_copies",
                "recommendation": f"保留 {paths[0].name}，删除其余 {len(paths)-1} 个副本"
            }
            self.duplicates["raw_exact"].append(group)
        
        print(f"   ✓ 精确重复: {len(exact_dupes)} 组")
        
        similar_groups = self._find_similar_raw_files(raw_files)
        self.duplicates["raw_similar"] = similar_groups
        
        print(f"   ✓ 相似文件: {len(similar_groups)} 组")
        
        return {
            "exact_duplicates": len(exact_dupes),
            "similar_files": len(similar_groups),
            "details": self.duplicates["raw_exact"] + self.duplicates["raw_similar"]
        }
    
    def _content_hash(self, content: str) -> str:
        """计算内容哈希（归一化后）"""
        normalized = self._normalize_text(content)
        try:
            return hashlib.md5(normalized.encode(), usedforsecurity=False).hexdigest()
        except TypeError:
            return hashlib.md5(normalized.encode()).hexdigest()
    
    def _normalize_text(self, text: str) -> str:
        """文本归一化：去除空白、标点差异，用于比较"""
        text = text.lower()
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\s]', '', text)
        text = text.strip()
        return text
    
    def _safe_read(self, filepath: Path) -> str:
        """安全读取文件内容"""
        try:
            if filepath.suffix.lower() == '.pdf':
                return self.utils.read_pdf_text(filepath)
            return self.utils.read_file(filepath)
        except Exception:
            return ""
    
    def _find_similar_raw_files(self, files: List[Path], 
                                 threshold: float = 0.7) -> List[Dict]:
        """
        检测内容相似的 raw 文件
        使用 n-gram 指纹 + Jaccard 相似度，避免全文比较
        """
        similar_groups = []
        compared = set()
        
        fingerprints = {}
        for filepath in files:
            content = self._safe_read(filepath)
            if content:
                fingerprints[str(filepath)] = self._ngram_fingerprint(content, n=3)
        
        file_list = list(fingerprints.keys())
        
        for i in range(len(file_list)):
            for j in range(i + 1, len(file_list)):
                path_i = file_list[i]
                path_j = file_list[j]
                
                pair_key = tuple(sorted([path_i, path_j]))
                if pair_key in compared:
                    continue
                compared.add(pair_key)
                
                sim = self._jaccard_similarity(
                    fingerprints[path_i], 
                    fingerprints[path_j]
                )
                
                if sim >= threshold:
                    similar_groups.append({
                        "files": [
                            str(Path(path_i).relative_to(self.utils.base_dir)),
                            str(Path(path_j).relative_to(self.utils.base_dir))
                        ],
                        "similarity": round(sim, 3),
                        "action": "review_and_merge",
                        "recommendation": self._suggest_raw_action(sim)
                    })
        
        return similar_groups
    
    def _ngram_fingerprint(self, text: str, n: int = 3) -> set:
        """
        生成 n-gram 指纹集合
        用于快速比较文档相似度
        """
        normalized = self._normalize_text(text)
        words = normalized.split()
        
        if len(words) < n:
            return {normalized}
        
        ngrams = set()
        for i in range(len(words) - n + 1):
            ngram = ' '.join(words[i:i+n])
            ngrams.add(ngram)
        
        return ngrams
    
    def _jaccard_similarity(self, set_a: set, set_b: set) -> float:
        """计算 Jaccard 相似度"""
        if not set_a and not set_b:
            return 1.0
        if not set_a or not set_b:
            return 0.0
        
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        
        return intersection / union if union > 0 else 0.0
    
    def _suggest_raw_action(self, similarity: float) -> str:
        """根据相似度建议处理方式"""
        if similarity >= self.SIMILARITY_HIGH:
            return "高度相似，建议只保留一个版本，删除冗余副本"
        elif similarity >= self.SIMILARITY_MEDIUM:
            return "中度相似，可能是同一主题的不同文章，建议合并录入"
        else:
            return "低度相似，可能只是主题相关，建议分别录入但交叉引用"
    
    # ================================================================
    # 第二层：Wiki 页面级去重
    # ================================================================
    
    def check_wiki_duplicates(self) -> Dict:
        """
        检测 wiki/ 目录下的相似/重复页面
        1. 同名页面（slug 冲突）
        2. 语义相似页面（不同 slug 但内容高度重叠）
        3. 实体-概念混淆（同一主题被创建为不同类型）
        """
        print("\n📖 [第二层] 检测 Wiki 页面重复...\n")
        
        all_files = self.utils.list_wiki_files()
        print(f"   扫描到 {len(all_files)} 个 Wiki 页面\n")
        
        slug_map = defaultdict(list)
        for filepath in all_files:
            slug = filepath.stem.lower()
            slug_map[slug].append(filepath)
        
        slug_conflicts = {s: paths for s, paths in slug_map.items() if len(paths) > 1}
        if slug_conflicts:
            print(f"   ⚠️  发现 {len(slug_conflicts)} 组 slug 冲突")
        
        similar_pages = self._find_similar_wiki_pages(all_files)
        self.duplicates["wiki_similar"] = similar_pages
        
        print(f"   ✓ 相似页面: {len(similar_pages)} 组")
        
        cross_type = self._find_cross_type_duplicates(all_files)
        if cross_type:
            print(f"   ✓ 跨类型重复: {len(cross_type)} 组")
            similar_pages.extend(cross_type)
        
        return {
            "slug_conflicts": len(slug_conflicts),
            "similar_pages": len(similar_pages),
            "details": similar_pages
        }
    
    def _find_similar_wiki_pages(self, files: List[Path],
                                  threshold: float = 0.5) -> List[Dict]:
        """
        检测内容相似的 Wiki 页面
        策略：先按标题/标签快速筛选候选对，再计算内容相似度
        """
        similar_groups = []
        compared = set()
        
        page_data = []
        for filepath in files:
            content = self._safe_read(filepath)
            if not content:
                continue
            
            frontmatter, body = self.utils.parse_frontmatter(content)
            title = frontmatter.get("title", filepath.stem)
            tags = frontmatter.get("tags", [])
            page_type = frontmatter.get("type", "unknown")
            
            page_data.append({
                "path": filepath,
                "title": title,
                "tags": tags,
                "type": page_type,
                "body": body,
                "fingerprint": self._ngram_fingerprint(body, n=4),
                "title_words": set(self._normalize_text(title).split())
            })
        
        for i in range(len(page_data)):
            for j in range(i + 1, len(page_data)):
                pi = page_data[i]
                pj = page_data[j]
                
                pair_key = tuple(sorted([
                    str(pi["path"].relative_to(self.utils.base_dir)),
                    str(pj["path"].relative_to(self.utils.base_dir))
                ]))
                if pair_key in compared:
                    continue
                
                title_sim = self._jaccard_similarity(
                    pi["title_words"], pj["title_words"]
                )
                
                tag_overlap = len(set(pi["tags"]) & set(pj["tags"]))
                
                if title_sim < 0.2 and tag_overlap == 0:
                    continue
                
                compared.add(pair_key)
                
                content_sim = self._jaccard_similarity(
                    pi["fingerprint"], pj["fingerprint"]
                )
                
                combined_sim = (content_sim * 0.6) + (title_sim * 0.3) + (min(tag_overlap / 3, 1.0) * 0.1)
                
                if combined_sim >= threshold:
                    similar_groups.append({
                        "pages": [
                            {
                                "path": str(pi["path"].relative_to(self.utils.base_dir)),
                                "title": pi["title"],
                                "type": pi["type"]
                            },
                            {
                                "path": str(pj["path"].relative_to(self.utils.base_dir)),
                                "title": pj["title"],
                                "type": pj["type"]
                            }
                        ],
                        "similarity": round(combined_sim, 3),
                        "content_similarity": round(content_sim, 3),
                        "title_similarity": round(title_sim, 3),
                        "action": self._suggest_wiki_action(combined_sim),
                        "recommendation": self._generate_merge_recommendation(
                            pi, pj, combined_sim
                        )
                    })
        
        similar_groups.sort(key=lambda x: x["similarity"], reverse=True)
        return similar_groups
    
    def _find_cross_type_duplicates(self, files: List[Path]) -> List[Dict]:
        """检测跨类型重复：同一主题被创建为 concept 和 entity"""
        cross_type = []
        
        by_title = defaultdict(list)
        for filepath in files:
            content = self._safe_read(filepath)
            if not content:
                continue
            frontmatter, _ = self.utils.parse_frontmatter(content)
            title = frontmatter.get("title", "").lower()
            page_type = frontmatter.get("type", "")
            if title:
                by_title[title].append({
                    "path": str(filepath.relative_to(self.utils.base_dir)),
                    "type": page_type,
                    "title": frontmatter.get("title", filepath.stem)
                })
        
        for title, pages in by_title.items():
            if len(pages) > 1:
                types = set(p["type"] for p in pages)
                if len(types) > 1:
                    cross_type.append({
                        "pages": pages,
                        "similarity": 1.0,
                        "content_similarity": 1.0,
                        "title_similarity": 1.0,
                        "action": "merge_into_one",
                        "recommendation": (
                            f"标题 '{title}' 同时存在为 {', '.join(types)} 类型，"
                            f"建议合并为一个页面（选择最合适的类型）"
                        )
                    })
        
        return cross_type
    
    def _suggest_wiki_action(self, similarity: float) -> str:
        """根据相似度建议 Wiki 页面处理方式"""
        if similarity >= self.SIMILARITY_HIGH:
            return "auto_merge"
        elif similarity >= self.SIMILARITY_MEDIUM:
            return "review_and_merge"
        else:
            return "add_cross_reference"
    
    def _generate_merge_recommendation(self, page_a: Dict, page_b: Dict,
                                        similarity: float) -> str:
        """生成合并建议"""
        if similarity >= self.SIMILARITY_HIGH:
            return (
                f"高度重复：'{page_a['title']}' 和 '{page_b['title']}' "
                f"内容几乎相同，建议合并为一个页面"
            )
        elif similarity >= self.SIMILARITY_MEDIUM:
            return (
                f"中度相似：'{page_a['title']}' 和 '{page_b['title']}' "
                f"有较多重叠内容，建议合并或添加明确的 [[双向链接]] 区分"
            )
        else:
            return (
                f"低度相似：'{page_a['title']}' 和 '{page_b['title']}' "
                f"主题相关但内容不同，建议添加 [[双向链接]] 互相引用"
            )
    
    # ================================================================
    # 第三层：内容级去重
    # ================================================================
    
    def check_content_overlap(self) -> Dict:
        """
        检测 Wiki 页面间的内容重叠
        关注：同一段落/定义在多个页面重复出现
        """
        print("\n📄 [第三层] 检测内容重叠...\n")
        
        all_files = self.utils.list_wiki_files()
        
        paragraph_map = defaultdict(list)
        
        for filepath in all_files:
            content = self._safe_read(filepath)
            if not content:
                continue
            
            _, body = self.utils.parse_frontmatter(content)
            paragraphs = self._split_paragraphs(body)
            
            for para in paragraphs:
                if len(para) < 30:
                    continue
                
                para_norm = self._normalize_text(para)
                para_hash = hashlib.md5(para_norm.encode()).hexdigest()[:16]
                
                paragraph_map[para_hash].append({
                    "path": str(filepath.relative_to(self.utils.base_dir)),
                    "paragraph": para[:100] + "..." if len(para) > 100 else para,
                    "length": len(para)
                })
        
        overlapping = {
            h: entries for h, entries in paragraph_map.items() 
            if len(entries) > 1
        }
        
        overlap_groups = []
        for para_hash, entries in overlapping.items():
            paths = list(set(e["path"] for e in entries))
            if len(paths) > 1:
                overlap_groups.append({
                    "hash": para_hash,
                    "pages": paths,
                    "preview": entries[0]["paragraph"],
                    "length": entries[0]["length"],
                    "action": "extract_to_shared_section",
                    "recommendation": (
                        f"同一段内容在 {len(paths)} 个页面重复出现，"
                        f"建议提取到其中一个主页面，其他页面用 [[链接]] 引用"
                    )
                })
        
        self.duplicates["content_overlap"] = overlap_groups
        
        print(f"   ✓ 发现 {len(overlap_groups)} 组内容重叠")
        
        return {
            "overlap_count": len(overlap_groups),
            "details": overlap_groups
        }
    
    def _split_paragraphs(self, text: str) -> List[str]:
        """将文本按段落分割"""
        paragraphs = re.split(r'\n{2,}', text)
        return [p.strip() for p in paragraphs if p.strip() and not p.strip().startswith('#')]
    
    # ================================================================
    # 合并功能
    # ================================================================
    
    def merge_pages(self, primary_path: str, secondary_path: str,
                    strategy: str = "combine") -> Dict:
        """
        合并两个 Wiki 页面
        
        Args:
            primary_path: 主页面路径（保留此页面）
            secondary_path: 次页面路径（合并后标记为 archived）
            strategy: 合并策略
                - "combine": 合并所有内容到主页面
                - "keep_primary": 只保留主页面内容，次页面重定向
                - "llm_merge": 使用 LLM 智能合并（去重+补充）
        
        Returns:
            合并结果统计
        """
        print(f"\n🔗 合并页面:")
        print(f"   主页面: {primary_path}")
        print(f"   次页面: {secondary_path}")
        print(f"   策略: {strategy}\n")
        
        primary = self.utils.base_dir / primary_path
        secondary = self.utils.base_dir / secondary_path
        
        if not primary.exists() or not secondary.exists():
            raise FileNotFoundError("主页面或次页面不存在")
        
        primary_content = self.utils.read_file(primary)
        secondary_content = self.utils.read_file(secondary)
        
        primary_fm, primary_body = self.utils.parse_frontmatter(primary_content)
        secondary_fm, secondary_body = self.utils.parse_frontmatter(secondary_content)
        
        if strategy == "combine":
            merged_fm, merged_body = self._combine_merge(
                primary_fm, primary_body,
                secondary_fm, secondary_body,
                secondary_path
            )
        elif strategy == "keep_primary":
            merged_fm, merged_body = self._redirect_merge(
                primary_fm, primary_body,
                secondary_fm, secondary_path
            )
        elif strategy == "llm_merge":
            merged_fm, merged_body = self._llm_merge(
                primary_fm, primary_body,
                secondary_fm, secondary_body,
                secondary_path
            )
        else:
            raise ValueError(f"未知合并策略: {strategy}")
        
        merged_content = self.utils.build_frontmatter(merged_fm) + merged_body
        self.utils.write_file(primary, merged_content)
        
        redirect_content = self._create_redirect_page(
            secondary_fm.get("title", Path(secondary_path).stem),
            primary_path,
            secondary_fm.get("sources", [])
        )
        self.utils.write_file(secondary, redirect_content)
        
        self._update_links_after_merge(
            Path(secondary_path).stem,
            Path(primary_path).stem
        )
        
        self.log_mgr.log_update(
            primary_path,
            "merge",
            f"合并页面 {secondary_path} → {primary_path}（策略: {strategy}）"
        )
        
        print(f"   ✅ 合并完成")
        print(f"   主页面已更新: {primary_path}")
        print(f"   次页面已归档: {secondary_path}")
        
        return {
            "primary": primary_path,
            "secondary": secondary_path,
            "strategy": strategy,
            "status": "merged"
        }
    
    def _combine_merge(self, primary_fm: Dict, primary_body: str,
                       secondary_fm: Dict, secondary_body: str,
                       secondary_path: str) -> Tuple[Dict, str]:
        """合并策略：组合两个页面的内容"""
        merged_fm = dict(primary_fm)
        
        merged_fm["sources"] = list(set(
            primary_fm.get("sources", []) + secondary_fm.get("sources", [])
        ))
        merged_fm["tags"] = list(set(
            primary_fm.get("tags", []) + secondary_fm.get("tags", [])
        ))
        merged_fm["related"] = list(set(
            primary_fm.get("related", []) + secondary_fm.get("related", [])
        ))
        merged_fm["updated"] = self.utils.get_today()
        
        merged_body = primary_body.rstrip()
        
        secondary_title = secondary_fm.get("title", Path(secondary_path).stem)
        merged_body += f"\n\n---\n\n## 来自 [[{secondary_title}]] 的补充内容\n\n"
        merged_body += secondary_body.rstrip()
        
        return merged_fm, merged_body
    
    def _redirect_merge(self, primary_fm: Dict, primary_body: str,
                        secondary_fm: Dict, secondary_path: str) -> Tuple[Dict, str]:
        """合并策略：保留主页面，次页面重定向"""
        merged_fm = dict(primary_fm)
        merged_fm["sources"] = list(set(
            primary_fm.get("sources", []) + secondary_fm.get("sources", [])
        ))
        merged_fm["updated"] = self.utils.get_today()
        
        secondary_title = secondary_fm.get("title", Path(secondary_path).stem)
        merged_body = primary_body.rstrip()
        merged_body += f"\n\n> ℹ️ 已合并 [[{secondary_title}]] 的内容"
        
        return merged_fm, merged_body
    
    def _llm_merge(self, primary_fm: Dict, primary_body: str,
                   secondary_fm: Dict, secondary_body: str,
                   secondary_path: str) -> Tuple[Dict, str]:
        """合并策略：使用 LLM 智能合并（去重+补充）"""
        if not self.llm:
            print("   ⚠️ LLM 不可用，回退到 combine 策略")
            return self._combine_merge(
                primary_fm, primary_body,
                secondary_fm, secondary_body,
                secondary_path
            )
        
        merged_fm = dict(primary_fm)
        merged_fm["sources"] = list(set(
            primary_fm.get("sources", []) + secondary_fm.get("sources", [])
        ))
        merged_fm["tags"] = list(set(
            primary_fm.get("tags", []) + secondary_fm.get("tags", [])
        ))
        merged_fm["related"] = list(set(
            primary_fm.get("related", []) + secondary_fm.get("related", [])
        ))
        merged_fm["updated"] = self.utils.get_today()
        
        system_prompt = """你是一个知识库合并专家。
请将两个关于同一主题的 Wiki 页面合并为一个。
要求：
1. 去除重复内容
2. 保留两个页面的独有信息
3. 保持 Markdown 格式
4. 按标准章节组织（定义→核心内容→关系→引用）
5. 只输出合并后的 Markdown 正文（不含 frontmatter）"""
        
        user_prompt = f"""页面 A:
{primary_body}

页面 B:
{secondary_body}

请合并以上两个页面，去除重复，保留所有独有信息。"""
        
        try:
            merged_body = self.llm.chat(system_prompt, user_prompt, temperature=0.2)
            print("   ✓ LLM 合并成功")
        except Exception as e:
            print(f"   ⚠️ LLM 合并失败: {e}，回退到 combine 策略")
            return self._combine_merge(
                primary_fm, primary_body,
                secondary_fm, secondary_body,
                secondary_path
            )
        
        return merged_fm, merged_body
    
    def _create_redirect_page(self, old_title: str, target_path: str,
                              sources: List[str]) -> str:
        """创建重定向页面（替代被合并的次页面）"""
        target_slug = Path(target_path).stem
        today = self.utils.get_today()
        
        content = f"""---
title: "{old_title}"
type: entity
created: "{today}"
updated: "{today}"
confidence: high
sources: {sources}
tags: [redirect]
related: ["[[{target_slug}]]"]
status: archived
---

# {old_title}

> ⚠️ **此页面已合并**
> 
> 本页面内容已合并至 [[{target_slug}]]，请点击链接查看完整内容。

---
*合并时间: {today}*
"""
        return content
    
    def _update_links_after_merge(self, old_slug: str, new_slug: str):
        """合并后更新所有页面中的双向链接"""
        all_files = self.utils.list_wiki_files()
        updated_count = 0
        
        for filepath in all_files:
            content = self.utils.read_file(filepath)
            
            old_link = f"[[{old_slug}]]"
            new_link = f"[[{new_slug}]]"
            
            if old_link in content:
                content = content.replace(old_link, new_link)
                
                frontmatter, body = self.utils.parse_frontmatter(content)
                if "related" in frontmatter:
                    frontmatter["related"] = [
                        new_link if r == old_link else r 
                        for r in frontmatter["related"]
                    ]
                    frontmatter["updated"] = self.utils.get_today()
                    content = self.utils.build_frontmatter(frontmatter) + body
                
                self.utils.write_file(filepath, content)
                updated_count += 1
        
        if updated_count > 0:
            print(f"   ✓ 已更新 {updated_count} 个页面中的链接引用")
    
    # ================================================================
    # 录入前去重检查（供 ingest.py 调用）
    # ================================================================
    
    def check_before_ingest(self, raw_filepath: str) -> Dict:
        """
        录入前去重检查
        在 ingest 流程开始前调用，检测是否已有相似内容
        
        Returns:
            {
                "is_duplicate": bool,
                "similar_files": [...],
                "similar_pages": [...],
                "recommendation": str
            }
        """
        filepath = Path(raw_filepath)
        if not filepath.is_absolute():
            filepath = self.utils.base_dir / raw_filepath
        
        content = self._safe_read(filepath)
        if not content:
            return {
                "is_duplicate": False,
                "similar_files": [],
                "similar_pages": [],
                "recommendation": "无法读取文件内容，继续录入"
            }
        
        new_hash = self._content_hash(content)
        new_fingerprint = self._ngram_fingerprint(content, n=3)
        
        meta_data = self.utils.load_json(self.utils.raw_dir / "_meta.json")
        for f in meta_data.get("files", []):
            existing_path = self.utils.base_dir / f["path"]
            existing_content = self._safe_read(existing_path)
            if existing_content:
                existing_hash = self._content_hash(existing_content)
                if new_hash == existing_hash:
                    return {
                        "is_duplicate": True,
                        "duplicate_type": "exact",
                        "similar_files": [f["path"]],
                        "similar_pages": [],
                        "recommendation": f"与已录入文件 {f['path']} 完全相同，跳过录入"
                    }
        
        similar_pages = []
        all_files = self.utils.list_wiki_files("sources")
        for wiki_file in all_files:
            wiki_content = self._safe_read(wiki_file)
            if not wiki_content:
                continue
            _, wiki_body = self.utils.parse_frontmatter(wiki_content)
            wiki_fp = self._ngram_fingerprint(wiki_body, n=3)
            sim = self._jaccard_similarity(new_fingerprint, wiki_fp)
            
            if sim >= self.SIMILARITY_MEDIUM:
                similar_pages.append({
                    "path": str(wiki_file.relative_to(self.utils.base_dir)),
                    "similarity": round(sim, 3)
                })
        
        similar_pages.sort(key=lambda x: x["similarity"], reverse=True)
        
        if similar_pages and similar_pages[0]["similarity"] >= self.SIMILARITY_HIGH:
            return {
                "is_duplicate": True,
                "duplicate_type": "high_similarity",
                "similar_files": [],
                "similar_pages": similar_pages[:3],
                "recommendation": (
                    f"与已有摘要页高度相似（{similar_pages[0]['similarity']}），"
                    f"建议跳过或合并更新"
                )
            }
        
        if similar_pages:
            return {
                "is_duplicate": False,
                "duplicate_type": "partial_overlap",
                "similar_files": [],
                "similar_pages": similar_pages[:3],
                "recommendation": (
                    f"与 {len(similar_pages)} 个已有页面有部分重叠，"
                    f"建议录入后运行去重检查"
                )
            }
        
        return {
            "is_duplicate": False,
            "duplicate_type": "none",
            "similar_files": [],
            "similar_pages": [],
            "recommendation": "无重复，可以安全录入"
        }
    
    # ================================================================
    # 完整检测 + 报告
    # ================================================================
    
    def run_full_check(self) -> Dict:
        """运行完整的三层去重检测"""
        print(f"\n{'='*70}")
        print("🔍 LLM Wiki 去重检测")
        print(f"{'='*70}")
        print(f"⏰ 检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        raw_result = self.check_raw_duplicates()
        wiki_result = self.check_wiki_duplicates()
        content_result = self.check_content_overlap()
        
        report = self._generate_report(raw_result, wiki_result, content_result)
        
        return report
    
    def _generate_report(self, raw_result: Dict, wiki_result: Dict,
                         content_result: Dict) -> Dict:
        """生成去重检测报告"""
        total_issues = (
            raw_result.get("exact_duplicates", 0) +
            raw_result.get("similar_files", 0) +
            wiki_result.get("similar_pages", 0) +
            content_result.get("overlap_count", 0)
        )
        
        print(f"\n{'='*70}")
        print("📊 去重检测报告")
        print(f"{'='*70}")
        print(f"  📁 Raw 精确重复: {raw_result.get('exact_duplicates', 0)} 组")
        print(f"  📁 Raw 相似文件: {raw_result.get('similar_files', 0)} 组")
        print(f"  📖 Wiki 相似页面: {wiki_result.get('similar_pages', 0)} 组")
        print(f"  📄 内容重叠: {content_result.get('overlap_count', 0)} 组")
        print(f"  📊 总计: {total_issues} 组需处理")
        print(f"{'='*70}\n")
        
        if self.duplicates["raw_exact"]:
            print("🚨 Raw 精确重复文件:")
            for group in self.duplicates["raw_exact"]:
                print(f"   - {', '.join(group['files'])}")
                print(f"     → {group['recommendation']}")
            print()
        
        if self.duplicates["wiki_similar"]:
            print("⚠️ Wiki 相似页面 (Top 10):")
            for group in self.duplicates["wiki_similar"][:10]:
                pages = [p["title"] for p in group["pages"]]
                print(f"   - {' & '.join(pages)} (相似度: {group['similarity']})")
                print(f"     → {group['recommendation']}")
            print()
        
        if self.duplicates["content_overlap"]:
            print("📄 内容重叠 (Top 5):")
            for group in self.duplicates["content_overlap"][:5]:
                print(f"   - 重叠出现在: {', '.join(group['pages'])}")
                print(f"     预览: {group['preview'][:80]}...")
            print()
        
        report_path = self.utils.wiki_dir / "_dedup-report.md"
        self._save_report(report_path, total_issues)
        
        return {
            "total_issues": total_issues,
            "raw_exact": raw_result.get("exact_duplicates", 0),
            "raw_similar": raw_result.get("similar_files", 0),
            "wiki_similar": wiki_result.get("similar_pages", 0),
            "content_overlap": content_result.get("overlap_count", 0),
            "report_file": str(report_path)
        }
    
    def _save_report(self, report_path: Path, total_issues: int):
        """保存去重报告到文件"""
        today = self.utils.get_today()
        
        content = f"# 去重检测报告\n\n"
        content += f"**检测时间**: {today}\n"
        content += f"**总问题数**: {total_issues}\n\n"
        
        if self.duplicates["raw_exact"]:
            content += "## 🚨 Raw 精确重复\n\n"
            for group in self.duplicates["raw_exact"]:
                content += f"- 文件: {', '.join(group['files'])}\n"
                content += f"  → {group['recommendation']}\n\n"
        
        if self.duplicates["raw_similar"]:
            content += "## ⚠️ Raw 相似文件\n\n"
            for group in self.duplicates["raw_similar"]:
                content += f"- 文件: {', '.join(group['files'])} (相似度: {group['similarity']})\n"
                content += f"  → {group['recommendation']}\n\n"
        
        if self.duplicates["wiki_similar"]:
            content += "## ⚠️ Wiki 相似页面\n\n"
            for group in self.duplicates["wiki_similar"]:
                pages = [p["title"] for p in group["pages"]]
                content += f"- {' & '.join(pages)} (相似度: {group['similarity']})\n"
                content += f"  → {group['recommendation']}\n\n"
        
        if self.duplicates["content_overlap"]:
            content += "## 📄 内容重叠\n\n"
            for group in self.duplicates["content_overlap"]:
                content += f"- 页面: {', '.join(group['pages'])}\n"
                content += f"  → {group['recommendation']}\n\n"
        
        content += f"\n---\n*报告生成时间: {today}*\n"
        
        self.utils.write_file(report_path, content)
        print(f"💾 报告已保存至: {report_path}")


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="LLM Wiki - 去重检测与合并工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/dedup.py                          # 完整去重检测
  python scripts/dedup.py --raw                    # 仅检测 Raw 层
  python scripts/dedup.py --wiki                   # 仅检测 Wiki 层
  python scripts/dedup.py --content                # 仅检测内容重叠
  python scripts/dedup.py --merge wiki/concepts/a.md wiki/concepts/b.md
  python scripts/dedup.py --merge wiki/concepts/a.md wiki/concepts/b.md --strategy llm
  python scripts/dedup.py --check raw/articles/new.md  # 录入前检查
        """
    )
    
    parser.add_argument("--raw", action="store_true", help="仅检测 Raw 层重复文件")
    parser.add_argument("--wiki", action="store_true", help="仅检测 Wiki 层相似页面")
    parser.add_argument("--content", action="store_true", help="仅检测内容重叠")
    parser.add_argument("--merge", nargs=2, metavar=("PRIMARY", "SECONDARY"),
                       help="合并两个页面（主页面 次页面）")
    parser.add_argument("--strategy", choices=["combine", "keep_primary", "llm_merge"],
                       default="combine", help="合并策略（默认: combine）")
    parser.add_argument("--check", metavar="RAW_FILE",
                       help="录入前去重检查")
    
    args = parser.parse_args()
    
    try:
        detector = DedupDetector(".")
        
        if args.merge:
            result = detector.merge_pages(args.merge[0], args.merge[1], args.strategy)
            print(f"\n✅ 合并完成: {result}")
        
        elif args.check:
            result = detector.check_before_ingest(args.check)
            print(f"\n📋 录入前检查结果:")
            print(f"   是否重复: {'是' if result['is_duplicate'] else '否'}")
            print(f"   重复类型: {result['duplicate_type']}")
            print(f"   建议: {result['recommendation']}")
            
            if result["similar_files"]:
                print(f"\n   相似文件:")
                for f in result["similar_files"]:
                    print(f"   - {f}")
            
            if result["similar_pages"]:
                print(f"\n   相似页面:")
                for p in result["similar_pages"]:
                    print(f"   - {p['path']} (相似度: {p['similarity']})")
            
            if result["is_duplicate"]:
                sys.exit(1)
        
        elif args.raw:
            detector.check_raw_duplicates()
        
        elif args.wiki:
            detector.check_wiki_duplicates()
        
        elif args.content:
            detector.check_content_overlap()
        
        else:
            detector.run_full_check()
    
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
