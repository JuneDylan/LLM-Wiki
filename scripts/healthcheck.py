#!/usr/bin/env python3
"""
LLM Wiki - Health Check 工作流（系统体检）
功能：一致性检查 → 完整性检查 → 质量检查 → 生成报告
使用方法:
  python scripts/healthcheck.py                    # 运行完整体检
  python scripts/healthcheck.py --fix-links        # 自动修复断链
  python scripts/healthcheck.py --category concepts # 检查特定分类
"""

import sys
import os
import io
import re
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple
from collections import defaultdict

# Windows 终端默认编码为 GBK，强制 stdout 使用 UTF-8 以支持 emoji
if sys.platform == "win32":
    try:
        if sys.stdout.encoding != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except (AttributeError, io.UnsupportedOperation):
        pass

sys.path.insert(0, str(Path(__file__).parent))
from utils import WikiUtils, MetadataManager, LogManager
from query import QueryEngine

try:
    from dedup import DedupDetector
    DEDUP_AVAILABLE = True
except ImportError:
    DEDUP_AVAILABLE = False


class HealthChecker:
    """知识库健康检查器"""
    
    def __init__(self, base_dir: str = "."):
        self.utils = WikiUtils(base_dir)
        self.meta_mgr = MetadataManager(self.utils)
        self.log_mgr = LogManager(self.utils)
        
        self.issues = {
            "critical": [],    # 严重问题（需立即修复）
            "warning": [],     # 一般问题（建议尽快处理）
            "info": []         # 优化建议（可选改进）
        }
        
        self.stats = {
            "total_pages": 0,
            "issues_found": 0,
            "issues_fixed": 0,
            "by_category": defaultdict(int)
        }
    
    def run_full_check(self) -> Dict:
        """运行完整的健康检查"""
        print(f"\n{'='*70}")
        print("🏥 LLM Wiki 健康检查")
        print(f"{'='*70}")
        print(f"⏰ 检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        print("📋 检查项目清单:\n")
        print("  ✅ [1/9] Frontmatter 完整性检查")
        print("  ✅ [2/9] 断链检测")
        print("  ✅ [3/9] 孤立页面检测")
        print("  ✅ [4/9] 来源有效性验证")
        print("  ✅ [5/9] 标签规范化检查")
        print("  ✅ [6/9] 内容质量评估")
        print("  ✅ [7/9] 索引完整性检查")
        print("  ✅ [8/9] 知识图谱一致性")
        print("  ✅ [9/9] 重复内容检测\n")
        
        try:
            all_files = self.utils.list_wiki_files()
            self.stats["total_pages"] = len(all_files)
            
            print("=" * 70)
            print("🔍 开始检查...\n")
            
            self._check_frontmatter(all_files)
            self._check_broken_links(all_files)
            self._check_orphan_pages(all_files)
            self._check_source_validity(all_files)
            self._check_tag_normalization(all_files)
            self._check_content_quality(all_files)
            self._check_index_completeness(all_files)
            self._check_graph_consistency()
            self._check_duplicates(all_files)
            
            report = self._generate_report()
            
            self.log_mgr.log_health_check(
                len(self.issues["critical"]) + 
                len(self.issues["warning"]) + 
                len(self.issues["info"]),
                self.stats["issues_fixed"]
            )
            
            return report
            
        except Exception as e:
            print(f"\n❌ 体检过程出错: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def fix_broken_links(self) -> int:
        """自动修复断链"""
        print("\n🔧 自动修复断链...\n")
        
        all_files = self.utils.list_wiki_files()
        fixed_count = 0
        
        valid_pages = set()
        for f in all_files:
            valid_pages.add(f.stem.lower().replace(' ', '-'))
        
        for filepath in all_files:
            content = self.utils.read_file(filepath)
            links = self.utils.extract_wiki_links(content)
            
            needs_fix = False
            fixed_content = content
            
            for link in links:
                slug = self.utils.slugify(link)
                
                if slug not in valid_pages:
                    similar = self._find_similar_page(slug, valid_pages)
                    
                    if similar:
                        print(f"   修复: {filepath.name} 中的 [[{link}]] → [[{similar}]]")
                        fixed_content = fixed_content.replace(
                            f'[[{link}]]', 
                            f'[[{similar}]]'
                        )
                        needs_fix = True
                        fixed_count += 1
            
            if needs_fix:
                frontmatter, body = self.utils.parse_frontmatter(fixed_content)
                frontmatter["updated"] = self.utils.get_today()
                new_content = self.utils.build_frontmatter(frontmatter) + body
                self.utils.write_file(filepath, new_content)
        
        print(f"\n✅ 已修复 {fixed_count} 个断链\n")
        return fixed_count
    
    def _check_frontmatter(self, files: List[Path]):
        """检查 1: Frontmatter 完整性"""
        print("📝 [1/8] 检查 Frontmatter 完整性...")
        
        required_fields = {
            "title": str,
            "type": str,
            "created": str,
            "updated": str,
            "confidence": str,
            "sources": list,
            "tags": list,
            "related": list,
            "status": str
        }
        
        valid_types = ["concept", "entity", "comparison", "source"]
        valid_confidence = ["high", "medium", "low"]
        valid_status = ["draft", "reviewed", "archived"]
        
        count = 0
        for filepath in files:
            if filepath.name == 'index.md':
                continue
            
            content = self.utils.read_file(filepath)
            frontmatter, body = self.utils.parse_frontmatter(content)
            
            if not frontmatter:
                self._add_issue("critical", filepath, 
                              "missing_frontmatter",
                              "缺少 YAML frontmatter")
                continue
            
            for field, expected_type in required_fields.items():
                if field not in frontmatter:
                    self._add_issue("warning", filepath,
                                  f"missing_field_{field}",
                                  f"缺少必要字段: {field}")
                elif not isinstance(frontmatter[field], expected_type):
                    self._add_issue("warning", filepath,
                                  f"invalid_field_type_{field}",
                                  f"字段 '{field}' 类型错误: 期望 {expected_type.__name__}")
            
            if frontmatter.get("type") and frontmatter["type"] not in valid_types:
                self._add_issue("warning", filepath,
                              "invalid_type",
                              f"无效的页面类型: {frontmatter['type']}")
            
            if frontmatter.get("confidence") and frontmatter["confidence"] not in valid_confidence:
                self._add_issue("warning", filepath,
                              "invalid_confidence",
                              f"无效的置信度: {frontmatter['confidence']}")
            
            if frontmatter.get("status") and frontmatter["status"] not in valid_status:
                self._add_issue("warning", filepath,
                              "invalid_status",
                              f"无效的状态: {frontmatter['status']}")
            
            count += 1
        
        print(f"   ✓ 检查了 {count} 个页面")
    
    def _check_broken_links(self, files: List[Path]):
        """检查 2: 断链检测"""
        print("🔗 [2/8] 检测断链...")
        
        valid_pages = set()
        page_map = {}
        
        for f in files:
            slug = f.stem.lower().replace(' ', '-')
            valid_pages.add(slug)
            page_map[slug] = f
        
        broken_count = 0
        
        for filepath in files:
            content = self.utils.read_file(filepath)
            links = self.utils.extract_wiki_links(content)
            
            for link in links:
                slug = self.utils.slugify(link)
                
                if slug not in valid_pages:
                    self._add_issue("critical", filepath,
                                  "broken_link",
                                  f"断链: [[{link}]] 指向不存在的页面")
                    broken_count += 1
        
        print(f"   ✓ 发现 {broken_count} 个断链")
    
    def _check_orphan_pages(self, files: List[Path]):
        """检查 3: 孤立页面检测"""
        print("🏝️ [3/8] 检测孤立页面...")
        
        linked_pages = set()
        
        for filepath in files:
            content = self.utils.read_file(filepath)
            links = self.utils.extract_wiki_links(content)
            
            for link in links:
                slug = self.utils.slugify(link)
                linked_pages.add(slug)
        
        orphan_count = 0
        
        for filepath in files:
            slug = self.utils.slugify(filepath.stem)
            
            if slug not in linked_pages:
                is_index = filepath.name == "index.md"
                is_log = filepath.name.startswith("_log")
                is_template = filepath.name.startswith("_template")
                
                # source 页面作为知识根节点，不被链接是正常设计
                is_source = filepath.parent.name == 'sources'
                
                if not is_index and not is_log and not is_template and not is_source:
                    orphan_count += 1
                    
                    backlinks = sum(
                        1 for f in files 
                        if f != filepath and slug in {
                            self.utils.slugify(link)
                            for link in self.utils.extract_wiki_links(self.utils.read_file(f))
                        }
                    )
                    
                    if backlinks == 0:
                        self._add_issue("info", filepath,
                                       "orphan_page",
                                       "孤立页面: 没有其他页面链接到此页面")
                    else:
                        self._add_issue("info", filepath,
                                       "low_connectivity",
                                       f"低连接度: 只有 {backlinks} 个反向链接")
        
        print(f"   ✓ 发现 {orphan_count} 个潜在孤立页面")
    
    def _check_source_validity(self, files: List[Path]):
        """检查 4: 来源有效性验证"""
        print("📎 [4/8] 验证来源有效性...")
        
        invalid_count = 0
        
        for filepath in files:
            content = self.utils.read_file(filepath)
            frontmatter, _ = self.utils.parse_frontmatter(content)
            
            sources = frontmatter.get("sources", [])
            
            for source in sources:
                source_path = self.utils.base_dir / source
                
                if not source_path.exists():
                    self._add_issue("critical", filepath,
                                  "invalid_source",
                                  f"无效来源: {source} (文件不存在)")
                    invalid_count += 1
        
        print(f"   ✓ 发现 {invalid_count} 个无效来源引用")
    
    def _check_tag_normalization(self, files: List[Path]):
        """检查 5: 标签规范化"""
        print("🏷️ [5/8] 检查标签规范化...")
        
        tag_usage = defaultdict(int)
        tag_variants = defaultdict(set)
        
        for filepath in files:
            content = self.utils.read_file(filepath)
            frontmatter, _ = self.utils.parse_frontmatter(content)
            
            tags = frontmatter.get("tags", [])
            
            for tag in tags:
                tag_usage[tag] += 1
                
                normalized = tag.lower().replace('-', ' ').replace('_', ' ')
                tag_variants[normalized].add(tag)
        
        variant_count = 0
        
        for normalized, variants in tag_variants.items():
            if len(variants) > 1:
                variant_count += 1
                self._add_issue("info", None,
                              "tag_inconsistency",
                              f"标签不一致: '{', '.join(variants)}' 应统一为 '{normalized}'")
        
        print(f"   ✓ 发现 {variant_count} 组不一致标签")
    
    def _check_content_quality(self, files: List[Path]):
        """检查 6: 内容质量评估"""
        print("⭐ [6/8] 评估内容质量...")
        
        quality_issues = 0
        
        for filepath in files:
            content = self.utils.read_file(filepath)
            _, body = self.utils.parse_frontmatter(content)
            
            word_count = len(body.split())
            
            if word_count < 50:
                quality_issues += 1
                self._add_issue("warning", filepath,
                              "thin_content",
                              f"内容过少: 仅 {word_count} 词（建议至少 100 词）")
            
            if body.count('#') < 2:
                quality_issues += 1
                self._add_issue("info", filepath,
                              "poor_structure",
                              "结构不佳: 缺少足够的章节标题")
            
            if '## 定义' not in body and '## 基本信息' not in body:
                if filepath.parent.name in ['concepts', 'entities']:
                    quality_issues += 1
                    self._add_issue("info", filepath,
                                  "missing_standard_section",
                                  "缺少标准章节（定义或基本信息）")
        
        print(f"   ✓ 发现 {quality_issues} 个质量问题")
    
    def _check_index_completeness(self, files: List[Path]):
        """检查 7: 索引完整性"""
        print("📑 [7/8] 检查索引完整性...")
        
        index_path = self.utils.wiki_dir / "index.md"
        
        if not index_path.exists():
            self._add_issue("critical", None,
                          "missing_index",
                          "主页索引文件不存在: wiki/index.md")
            print("   ⚠️  索引文件不存在")
            return
        
        index_content = self.utils.read_file(index_path)
        
        # index.md 设计上每个分类最多只显示 20 个页面，
        # 因此不应该将"未全部列出"视为不完整。
        # 这里只检查 index.md 是否包含每个分类的条目即可。
        categories_in_index = {
            '💡 概念': 'concepts',
            '👤 实体': 'entities',
            '⚖️ 对比': 'comparisons',
            '📄 资料': 'sources'
        }
        
        missing_categories = []
        for label, category in categories_in_index.items():
            if label not in index_content:
                missing_categories.append(category)
        
        if missing_categories:
            self._add_issue("warning", None,
                          "incomplete_index",
                          f"索引缺少分类: {', '.join(missing_categories)}")
        
        print(f"   ✓ 索引包含 {4 - len(missing_categories)}/4 个主要分类")
    
    def _check_graph_consistency(self):
        """检查 8: 知识图谱一致性"""
        print("🕸️ [8/9] 检查知识图谱一致性...")
        
        graph_file = self.utils.wiki_dir / "_graph.json"
        
        if not graph_file.exists():
            self._add_issue("info", None,
                          "missing_graph",
                          "知识图谱文件不存在: wiki/_graph.json")
            print("   ⚠️  知识图谱文件不存在")
            return
        
        graph = self.utils.load_json(graph_file)
        
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        
        node_ids = {node["id"] for node in nodes}
        
        issues = 0
        
        for edge in edges:
            if edge["source"] not in node_ids:
                issues += 1
                self._add_issue("warning", None,
                              "graph_edge_invalid_source",
                              f"图谱边源节点不存在: {edge['source']}")
            
            if edge["target"] not in node_ids:
                issues += 1
                self._add_issue("warning", None,
                              "graph_edge_invalid_target",
                              f"图谱边目标节点不存在: {edge['target']}")
        
        print(f"   ✓ 图谱包含 {len(nodes)} 节点, {len(edges)} 边, {issues} 个一致性问题")
    
    def _check_duplicates(self, files: List[Path]):
        """检查 9: 重复内容检测"""
        print("🔍 [9/9] 检测重复内容...")
        
        if not DEDUP_AVAILABLE:
            print("   ⚠️  去重模块不可用，跳过（需要 dedup.py）")
            return
        
        try:
            detector = DedupDetector(str(self.utils.base_dir))
            
            dup_count = 0
            
            title_map = defaultdict(list)
            for filepath in files:
                content = self.utils.read_file(filepath)
                frontmatter, _ = self.utils.parse_frontmatter(content)
                title = frontmatter.get("title", "").lower().strip()
                if title:
                    title_map[title].append(filepath)
            
            for title, paths in title_map.items():
                if len(paths) > 1:
                    dup_count += 1
                    path_names = [str(p.relative_to(self.utils.base_dir)) for p in paths]
                    self._add_issue("warning", paths[0],
                                  "duplicate_title",
                                  f"标题重复 '{title}': {', '.join(path_names)}")
            
            body_map = defaultdict(list)
            for filepath in files:
                content = self.utils.read_file(filepath)
                _, body = self.utils.parse_frontmatter(content)
                normalized = re.sub(r'\s+', ' ', body.lower().strip())
                if len(normalized) > 100:
                    body_hash = hashlib.md5(normalized.encode()).hexdigest()[:12]
                    body_map[body_hash].append(filepath)
            
            for body_hash, paths in body_map.items():
                if len(paths) > 1:
                    dup_count += 1
                    path_names = [str(p.relative_to(self.utils.base_dir)) for p in paths]
                    self._add_issue("critical", paths[0],
                                  "duplicate_content",
                                  f"内容完全相同: {', '.join(path_names)}")
            
            if dup_count == 0 and len(files) > 1:
                fingerprints = {}
                for filepath in files:
                    content = self.utils.read_file(filepath)
                    _, body = self.utils.parse_frontmatter(content)
                    if len(body) > 100:
                        fp = detector._ngram_fingerprint(body, n=4)
                        fingerprints[str(filepath)] = fp
                
                fp_list = list(fingerprints.items())
                for i in range(len(fp_list)):
                    for j in range(i + 1, len(fp_list)):
                        path_i, fp_i = fp_list[i]
                        path_j, fp_j = fp_list[j]
                        sim = detector._jaccard_similarity(fp_i, fp_j)
                        
                        if sim >= 0.7:
                            dup_count += 1
                            self._add_issue("warning", None,
                                          "similar_content",
                                          f"内容高度相似 ({sim:.0%}): {path_i} & {path_j}")
            
            print(f"   ✓ 发现 {dup_count} 组重复/相似内容")
            
        except Exception as e:
            print(f"   ⚠️  去重检查出错: {e}")
    
    def _add_issue(self, severity: str, filepath: Path, 
                   issue_type: str, message: str):
        """添加问题记录"""
        location = str(filepath.relative_to(self.utils.base_dir)) if filepath else "system"
        
        self.issues[severity].append({
            "location": location,
            "type": issue_type,
            "message": message,
            "detected_at": self.utils.get_today()
        })
        
        self.stats["issues_found"] += 1
    
    def _find_similar_page(self, target_slug: str, 
                          valid_pages: set) -> str:
        """查找相似的页面名称（用于修复建议）"""
        best_match = None
        best_score = 0
        
        for valid in valid_pages:
            score = self._similarity_score(target_slug, valid)
            
            if score > best_score and score >= 0.6:
                best_score = score
                best_match = valid
        
        return best_match
    
    def _similarity_score(self, s1: str, s2: str) -> float:
        """计算两个字符串的相似度 (0-1)"""
        if s1 == s2:
            return 1.0
        
        if s1 in s2 or s2 in s1:
            return 0.8
        
        words1 = set(s1.replace('-', ' ').split())
        words2 = set(s2.replace('-', ' ').split())
        
        intersection = words1 & words2
        union = words1 | words2
        
        if not union:
            return 0.0
        
        jaccard = len(intersection) / len(union)
        
        edit_dist = self._levenshtein_distance(s1, s2)
        max_len = max(len(s1), len(s2))
        edit_similarity = 1 - (edit_dist / max_len) if max_len > 0 else 0
        
        return (jaccard * 0.5) + (edit_similarity * 0.5)
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """计算编辑距离"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                
                current_row.append(min(insertions, deletions, substitutions))
            
            previous_row = current_row
        
        return previous_row[-1]
    
    def _generate_report(self) -> Dict:
        """生成健康检查报告"""
        total_issues = (
            len(self.issues["critical"]) +
            len(self.issues["warning"]) +
            len(self.issues["info"])
        )
        
        report_text = f"""
# 健康检查报告

**检查时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**统计概览**:
- 总页面数: {self.stats['total_pages']}
- 问题总数: {total_issues}
  - 🚨 严重: {len(self.issues['critical'])} 个
  - ⚠️ 一般: {len(self.issues['warning'])} 个
  - 💡 建议: {len(self.issues['info'])} 个

"""
        
        if self.issues["critical"]:
            report_text += """## 🚨 严重问题 (需立即修复)

"""
            for i, issue in enumerate(self.issues["critical"], 1):
                report_text += f"""### {i}. [{issue['type']}] {issue['location']}

- **详情**: {issue['message']}
- **建议**: 请立即检查并修复此问题

"""
        
        if self.issues["warning"]:
            report_text += """## ⚠️ 一般问题 (建议尽快处理)

"""
            for i, issue in enumerate(self.issues["warning"], 1):
                report_text += f"""### {i}. [{issue['type']}] {issue['location']}

- **详情**: {issue['message']}

"""
        
        if self.issues["info"]:
            report_text += """## 💡 优化建议 (可选改进)

"""
            for i, issue in enumerate(self.issues["info"], 1):
                report_text += f"""### {i}. [{issue['type']}]

- **详情**: {issue['message']}

"""
        
        stats = QueryEngine(".").get_statistics()
        
        report_text += f"""---

## 📊 统计数据

| 指标 | 数值 |
|------|------|
| 总页面数 | {self.stats['total_pages']} |
| 严重问题 | {len(self.issues['critical'])} |
| 一般问题 | {len(self.issues['warning'])} |
| 优化建议 | {len(self.issues['info'])} |
| 健康评分 | {self._calculate_health_score()}/100 |

---
*下次检查建议时间: 1 周后*
*使用 `python scripts/healthcheck.py --fix-links` 可自动修复部分问题*
"""
        
        print(report_text)
        
        report_path = self.utils.wiki_dir / "_health-report.md"
        self.utils.write_file(report_path, report_text)
        print(f"\n💾 报告已保存至: {report_path}\n")
        
        return {
            "total_pages": self.stats["total_pages"],
            "total_issues": total_issues,
            "critical": len(self.issues["critical"]),
            "warning": len(self.issues["warning"]),
            "info": len(self.issues["info"]),
            "health_score": self._calculate_health_score(),
            "report_file": str(report_path)
        }
    
    def _calculate_health_score(self) -> int:
        """
        计算健康评分 (0-100)
        基于问题数量和严重程度加权
        """
        if self.stats["total_pages"] == 0:
            return 100
        
        critical_weight = 10
        warning_weight = 3
        info_weight = 1
        
        weighted_sum = (
            len(self.issues["critical"]) * critical_weight +
            len(self.issues["warning"]) * warning_weight +
            len(self.issues["info"]) * info_weight
        )
        
        max_possible = self.stats["total_pages"] * 2
        
        score = max(0, 100 - (weighted_sum / max_possible * 100))
        
        return round(score)


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="LLM Wiki - 健康检查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/healthcheck.py                  # 完整体检
  python scripts/healthcheck.py --fix-links      # 自动修复断链
  python scripts/healthcheck.py --quiet          # 静默模式（仅显示摘要）
        """
    )
    
    parser.add_argument(
        "--fix-links",
        action="store_true",
        help="自动修复断链"
    )
    
    parser.add_argument(
        "--category",
        metavar="CATEGORY",
        choices=["concepts", "entities", "comparisons", "sources"],
        help="只检查指定分类"
    )
    
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="静默模式，仅输出摘要"
    )
    
    args = parser.parse_args()
    
    try:
        checker = HealthChecker(".")
        
        if args.fix_links:
            fixed = checker.fix_broken_links()
            print(f"\n✅ 修复完成！共修复 {fixed} 个断链\n")
        else:
            result = checker.run_full_check()
            
            if not args.quiet:
                print(f"\n{'='*70}")
                print("📊 体检总结")
                print(f"{'='*70}")
                print(f"  总页面数: {result['total_pages']}")
                print(f"  问题总数: {result['total_issues']}")
                print(f"  └─ 🚨 严重: {result['critical']}")
                print(f"  └─ ⚠️ 一般: {result['warning']}")
                print(f"  └─ 💡 建议: {result['info']}")
                print(f"  健康评分: {result['health_score']}/100")
                print(f"  报告文件: {result['report_file']}")
                print(f"{'='*70}\n")
            
            sys.exit(1 if result['critical'] > 0 else 0)
    
    except Exception as e:
        print(f"\n❌ 体检失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
