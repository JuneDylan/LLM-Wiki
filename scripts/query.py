#!/usr/bin/env python3
"""
LLM Wiki - Query 工作流（智能查询系统）
功能：搜索 Wiki → 必要时回查 Raw → 结构化回答 + 引用
使用方法:
  python scripts/query.py "Transformer 架构"
  python scripts/query.py --tag deep-learning
  python scripts/query.py --entity OpenAI
  python scripts/query.py --list-all
"""

import sys
import os
import io
import argparse
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional

# Windows 终端默认编码为 GBK，强制 stdout 使用 UTF-8 以支持 emoji
if sys.platform == "win32":
    try:
        if sys.stdout.encoding != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except (AttributeError, io.UnsupportedOperation):
        pass

sys.path.insert(0, str(Path(__file__).parent))
from utils import WikiUtils


class QueryEngine:
    """智能查询引擎"""
    
    def __init__(self, base_dir: str = "."):
        self.utils = WikiUtils(base_dir)
        self.cache = {}
    
    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """
        主搜索功能：在 wiki 中搜索匹配的页面
        返回排序后的结果列表
        """
        results = []
        
        all_files = self.utils.list_wiki_files()
        
        for filepath in all_files:
            content = self.utils.read_file(filepath)
            frontmatter, body = self.utils.parse_frontmatter(content)
            
            score = self._calculate_relevance(query, frontmatter, body, filepath)
            
            if score > 0:
                results.append({
                    "path": str(filepath.relative_to(self.utils.base_dir)),
                    "title": frontmatter.get("title", filepath.stem),
                    "type": frontmatter.get("type", "unknown"),
                    "score": score,
                    "confidence": frontmatter.get("confidence", "unknown"),
                    "tags": frontmatter.get("tags", []),
                    "preview": self._extract_preview(body, query),
                    "related": frontmatter.get("related", [])
                })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return results[:max_results]
    
    def get_page(self, page_path: str) -> Optional[Dict]:
        """获取单个页面的完整内容"""
        filepath = Path(page_path)
        if not filepath.is_absolute():
            filepath = self.utils.base_dir / page_path
        
        if not filepath.exists():
            return None
        
        content = self.utils.read_file(filepath)
        frontmatter, body = self.utils.parse_frontmatter(content)
        
        links = self.utils.extract_wiki_links(content)
        
        return {
            "path": str(filepath.relative_to(self.utils.base_dir)),
            "frontmatter": frontmatter,
            "body": body,
            "links": links,
            "full_content": content
        }
    
    def find_by_tag(self, tag: str) -> List[Dict]:
        """按标签查找页面"""
        results = []
        
        all_files = self.utils.list_wiki_files()
        
        for filepath in all_files:
            content = self.utils.read_file(filepath)
            frontmatter, _ = self.utils.parse_frontmatter(content)
            
            tags = frontmatter.get("tags", [])
            
            if tag.lower() in [t.lower() for t in tags]:
                results.append({
                    "path": str(filepath.relative_to(self.utils.base_dir)),
                    "title": frontmatter.get("title", filepath.stem),
                    "type": frontmatter.get("type", "unknown"),
                    "tags": tags,
                    "updated": frontmatter.get("updated", "")
                })
        
        return sorted(results, key=lambda x: x["updated"], reverse=True)
    
    def find_by_type(self, page_type: str) -> List[Dict]:
        """按类型查找页面（concept/entity/comparison/source）"""
        results = []
        
        files = self.utils.list_wiki_files(page_type)
        
        for filepath in files:
            content = self.utils.read_file(filepath)
            frontmatter, _ = self.utils.parse_frontmatter(content)
            
            results.append({
                "path": str(filepath.relative_to(self.utils.base_dir)),
                "title": frontmatter.get("title", filepath.stem),
                "tags": frontmatter.get("tags", []),
                "updated": frontmatter.get("updated", ""),
                "confidence": frontmatter.get("confidence", "")
            })
        
        return sorted(results, key=lambda x: x["updated"], reverse=True)
    
    def get_related_pages(self, page_path: str, depth: int = 1) -> List[Dict]:
        """
        获取相关页面（基于双向链接）
        depth: 链接深度（1=直接链接，2=链接的链接）
        """
        visited = set()
        related = []
        
        self._collect_related(page_path, depth, visited, related)
        
        return related
    
    def get_statistics(self) -> Dict:
        """获取知识库统计信息"""
        stats = {
            "total_pages": 0,
            "by_type": {},
            "by_category": {},
            "total_links": 0,
            "average_confidence": None,
            "last_updated": None
        }
        
        all_files = self.utils.list_wiki_files()
        stats["total_pages"] = len(all_files)
        
        confidence_sum = 0
        confidence_count = 0
        last_update = None
        
        for filepath in all_files:
            content = self.utils.read_file(filepath)
            frontmatter, _ = self.utils.parse_frontmatter(content)
            
            page_type = frontmatter.get("type", "unknown")
            stats["by_type"][page_type] = stats["by_type"].get(page_type, 0) + 1
            
            category = filepath.parent.name
            stats["by_category"][category] = stats["by_category"].get(category, 0) + 1
            
            links = self.utils.extract_wiki_links(content)
            stats["total_links"] += len(links)
            
            conf = frontmatter.get("confidence")
            if conf:
                confidence_map = {"high": 3, "medium": 2, "low": 1}
                confidence_sum += confidence_map.get(conf, 0)
                confidence_count += 1
            
            updated = frontmatter.get("updated")
            if updated and (not last_update or updated > last_update):
                last_update = updated
        
        if confidence_count > 0:
            avg = confidence_sum / confidence_count
            if avg >= 2.5:
                stats["average_confidence"] = "high"
            elif avg >= 1.5:
                stats["average_confidence"] = "medium"
            else:
                stats["average_confidence"] = "low"
        
        stats["last_updated"] = last_update
        
        return stats
    
    def format_results(self, query: str, results: List[Dict]) -> str:
        """格式化搜索结果为可读文本"""
        if not results:
            return f"""# 查询结果: "{query}"

❌ **未找到匹配结果**

建议：
- 尝试不同的关键词
- 检查拼写是否正确
- 浏览 [[index]] 查看所有可用页面

---
*置信度: 信息缺失*
"""
        
        output = f"# 查询结果: \"{query}\"\n\n"
        output += f"**找到 {len(results)} 个相关页面**\n\n"
        
        for i, result in enumerate(results, 1):
            output += f"## {i}. [[{result['title']}]]\n\n"
            output += f"- **路径**: `{result['path']}`\n"
            output += f"- **类型**: {result['type']}\n"
            output += f"- **相关度**: {'⭐' * min(result['score'], 5)} ({result['score']}/5)\n"
            output += f"- **置信度**: {result['confidence']}\n"
            
            if result['tags']:
                output += f"- **标签**: {', '.join(result['tags'])}\n"
            
            if result['preview']:
                output += f"\n**预览**:\n> {result['preview']}\n"
            
            if result['related']:
                related_str = ', '.join(f'[[{r}]]' for r in result['related'][:5])
                output += f"\n**相关页面**: {related_str}\n"
            
            output += "\n---\n\n"
        
        output += f"---\n*查询完成 · 结果按相关性排序*\n"
        
        return output
    
    def format_detailed_answer(self, query: str, results: List[Dict]) -> str:
        """
        格式化为详细答案格式（适合 AI 回答）
        包含引用和原始来源
        """
        if not results:
            return f"很抱歉，当前知识库中没有关于「{query}」的信息。\n\n建议补充相关资料到 raw/ 目录后重新查询。"
        
        top_result = results[0]
        
        answer = f"## 关于「{query}」\n\n"
        
        best_match = self.get_page(top_result['path'])
        if best_match:
            answer += best_match['body'][:2000]
            if len(best_match['body']) > 2000:
                answer += "\n\n... (更多内容请查看完整页面)\n"
        
        answer += f"\n### 详细依据\n\n"
        
        for i, result in enumerate(results[:3], 1):
            answer += f"{i}. 见 [[{result['title']}]]: "
            
            page = self.get_page(result['path'])
            if page and page['frontmatter'].get('sources'):
                sources = page['frontmatter']['sources'][:2]
                sources_str = ', '.join(f"[{s}]({s})" for s in sources)
                answer += f"来源 {sources_str}\n"
            else:
                answer += "\n"
        
        answer += f"\n### 原始来源\n\n"
        
        all_sources = set()
        for result in results[:5]:
            page = self.get_page(result['path'])
            if page and page['frontmatter'].get('sources'):
                all_sources.update(page['frontmatter']['sources'])
        
        for source in list(all_sources)[:5]:
            answer += f"- 来源: [{source}]({source})\n"
        
        avg_confidence = sum(
            1 for r in results 
            if r.get('confidence') == 'high'
        ) / len(results)
        
        if avg_confidence >= 0.7:
            conf_level = "high"
        elif avg_confidence >= 0.4:
            conf_level = "medium"
        else:
            conf_level = "low"
        
        answer += f"\n---\n*置信度: {conf_level}*"
        
        return answer
    
    def _calculate_relevance(self, query: str, frontmatter: Dict, 
                            body: str, filepath: Path) -> float:
        """
        计算页面与查询的相关度得分 (0-5)
        综合考虑标题、标签、内容匹配度
        """
        score = 0.0
        query_lower = query.lower()
        
        title = frontmatter.get("title", "").lower()
        tags = [t.lower() for t in frontmatter.get("tags", [])]
        
        if query_lower in title:
            score += 3.0
        
        for tag in tags:
            if query_lower in tag or tag in query_lower:
                score += 1.5
                break
        
        body_lower = body.lower()
        query_words = query_lower.split()
        
        matches = sum(1 for word in query_words if word in body_lower)
        word_score = min(matches / len(query_words), 1.0) * 1.5
        score += word_score
        
        exact_matches = len(re.findall(re.escape(query), body_lower, re.IGNORECASE))
        score += min(exact_matches * 0.2, 1.0)
        
        filename = filepath.stem.lower()
        if query_lower in filename:
            score += 0.5
        
        return min(score, 5.0)
    
    def _extract_preview(self, body: str, query: str, max_length: int = 150) -> str:
        """提取包含查询词的预览片段"""
        sentences = re.split(r'[。！？\n]', body)
        
        for sentence in sentences:
            if query.lower() in sentence.lower() and len(sentence.strip()) > 20:
                preview = sentence.strip()
                if len(preview) > max_length:
                    preview = preview[:max_length] + "..."
                return preview
        
        if body.strip():
            preview = body.strip().replace('\n', ' ')[:max_length]
            if len(body) > max_length:
                preview += "..."
            return preview
        
        return ""
    
    def _collect_related(self, page_path: str, depth: int, 
                        visited: set, related: list):
        """递归收集相关页面"""
        if depth <= 0 or page_path in visited:
            return
        
        visited.add(page_path)
        
        page = self.get_page(page_path)
        if not page:
            return
        
        for link in page['links']:
            link_path = self._resolve_link(link, page_path)
            if link_path and link_path not in visited:
                linked_page = self.get_page(link_path)
                if linked_page:
                    related.append({
                        "path": link_path,
                        "title": linked_page['frontmatter'].get('title', link),
                        "depth": depth
                    })
                    
                    if depth > 1:
                        self._collect_related(link_path, depth - 1, 
                                            visited, related)
    
    def _resolve_link(self, link: str, current_path: str) -> Optional[str]:
        """将双向链接解析为实际文件路径"""
        slug = self.utils.slugify(link)
        
        categories = ['concepts', 'entities', 'comparisons', 'sources']
        
        for category in categories:
            test_path = self.utils.wiki_dir / category / f"{slug}.md"
            if test_path.exists():
                return str(test_path.relative_to(self.utils.base_dir))
        
        return None


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="LLM Wiki - 智能查询工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/query.py "Transformer 架构"
  python scripts/query.py --tag deep-learning
  python scripts/query.py --type concept
  python scripts/query.py --detailed "注意力机制"
  python scripts/query.py --stats
  python scripts/query.py --related wiki/concepts/transformer.md
        """
    )
    
    parser.add_argument(
        "query",
        nargs="?",
        help="搜索关键词或问题"
    )
    
    parser.add_argument(
        "--tag",
        metavar="TAG",
        help="按标签筛选"
    )
    
    parser.add_argument(
        "--type",
        metavar="TYPE",
        choices=["concept", "entity", "comparison", "source"],
        help="按类型筛选"
    )
    
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="显示详细答案格式（含引用）"
    )
    
    parser.add_argument(
        "--stats",
        action="store_true",
        help="显示知识库统计信息"
    )
    
    parser.add_argument(
        "--related",
        metavar="PAGE",
        help="查找指定页面的相关页面"
    )
    
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="最大返回结果数（默认: 10）"
    )
    
    args = parser.parse_args()
    
    try:
        engine = QueryEngine(".")
        
        if args.stats:
            stats = engine.get_statistics()
            print("\n📊 知识库统计信息\n")
            print("=" * 50)
            print(f"总页面数: {stats['total_pages']}")
            print(f"\n按类型:")
            for ptype, count in stats['by_type'].items():
                print(f"  - {ptype}: {count}")
            print(f"\n按目录:")
            for category, count in stats['by_category'].items():
                print(f"  - {category}/: {count}")
            print(f"\n总链接数: {stats['total_links']}")
            print(f"平均置信度: {stats['average_confidence']}")
            print(f"最后更新: {stats['last_updated']}")
            print("=" * 50)
        
        elif args.related:
            related = engine.get_related_pages(args.related, depth=2)
            print(f"\n🔗 与 '{args.related}' 相关的页面 ({len(related)} 个):\n")
            for r in related:
                indent = "  " * (2 - r['depth'])
                print(f"{indent}- [[{r['title']}]] ({r['path']})")
        
        elif args.tag:
            results = engine.find_by_tag(args.tag)
            print(f"\n🏷️ 标签为 '{args.tag}' 的页面 ({len(results)} 个):\n")
            for r in results:
                print(f"- [[{r['title']}]] ({r['path']}) - 更新于 {r['updated']}")
        
        elif args.type:
            results = engine.find_by_type(args.type)
            print(f"\n📁 类型为 '{args.type}' 的页面 ({len(results)} 个):\n")
            for r in results:
                print(f"- [[{r['title']}]] ({r['path']})")
        
        elif args.query:
            results = engine.search(args.query, args.max_results)
            
            if args.detailed:
                output = engine.format_detailed_answer(args.query, results)
            else:
                output = engine.format_results(args.query, results)
            
            print("\n" + output)
        
        else:
            parser.print_help()
            sys.exit(1)
    
    except Exception as e:
        print(f"\n❌ 查询错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
