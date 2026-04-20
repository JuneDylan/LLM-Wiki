#!/usr/bin/env python3
"""
LLM Wiki - Update 工作流（知识维护和级联更新）
功能：检测变更 → 级联更新相关页面 → 维护一致性 → 记录日志
使用方法: 
  python scripts/update.py --all              # 更新所有页面
  python scripts/update.py wiki/concepts/xxx.md  # 更新指定页面
  python scripts/update.py --cascade raw/articles/yyy.md  # 级联更新
"""

import sys
import os
import io
import argparse
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
from utils import WikiUtils, MetadataManager, LogManager


class UpdateWorkflow:
    """知识更新工作流"""
    
    def __init__(self, base_dir: str = "."):
        self.utils = WikiUtils(base_dir)
        self.meta_mgr = MetadataManager(self.utils)
        self.log_mgr = LogManager(self.utils)
    
    def update_all(self) -> dict:
        """
        全量更新：扫描所有 wiki 页面，根据依赖关系进行增量更新
        """
        print(f"\n{'='*60}")
        print("🔄 开始全量更新...")
        print(f"{'='*60}\n")
        
        result = {
            "updated_pages": [],
            "skipped_pages": [],
            "errors": [],
            "statistics": {
                "concepts_checked": 0,
                "entities_checked": 0,
                "sources_checked": 0,
                "comparisons_checked": 0
            }
        }
        
        try:
            # 1. 加载依赖关系图
            deps = self.utils.load_json(self.utils.wiki_dir / "_dependencies.json")
            print(f"📊 已加载 {len(deps)} 个页面的依赖关系\n")
            
            # 2. 按类别更新
            categories = ["concepts", "entities", "comparisons", "sources"]
            
            for category in categories:
                files = self.utils.list_wiki_files(category)
                result["statistics"][f"{category}_checked"] = len(files)
                
                for filepath in files:
                    try:
                        updated = self._update_single_page(filepath, deps)
                        if updated:
                            result["updated_pages"].append(str(filepath.relative_to(self.utils.base_dir)))
                    except Exception as e:
                        result["errors"].append(f"{filepath}: {e}")
                        result["skipped_pages"].append(str(filepath.relative_to(self.utils.base_dir)))
            
            # 3. 更新索引
            print("\n📑 [最后步骤] 更新主页索引...")
            self._update_index()
            print("   ✓ 索引已更新")
            
            # 4. 记录日志
            self.log_mgr.log_update(
                "ALL_PAGES",
                "full_update",
                f"全量更新完成: 更新 {len(result['updated_pages'])} 页, "
                f"跳过 {len(result['skipped_pages'])} 页"
            )
            
            # 输出统计
            print(f"\n{'='*60}")
            print("✅ 更新完成！统计信息:")
            print(f"{'='*60}")
            print(f"  📝 更新页面: {len(result['updated_pages'])} 个")
            print(f"  ⏭️  跳过页面: {len(result['skipped_pages'])} 个")
            print(f"  ❌ 错误数: {len(result['errors'])} 个")
            print(f"\n  📊 分类统计:")
            for key, value in result["statistics"].items():
                print(f"    - {key}: {value}")
            print(f"{'='*60}\n")
            
        except Exception as e:
            result["errors"].append(str(e))
            print(f"\n❌ 更新失败: {e}")
            raise
        
        return result
    
    def update_page(self, page_path: str) -> dict:
        """
        更新单个指定页面及其相关页面
        """
        print(f"\n{'='*60}")
        print(f"🔄 开始更新: {page_path}")
        print(f"{'='*60}\n")
        
        filepath = Path(page_path)
        if not filepath.is_absolute():
            filepath = self.utils.base_dir / page_path
        
        if not filepath.exists():
            raise FileNotFoundError(f"页面不存在: {filepath}")
        
        result = {
            "target_page": page_path,
            "updated_pages": [],
            "cascaded_updates": [],
            "errors": []
        }
        
        try:
            deps = self.utils.load_json(self.utils.wiki_dir / "_dependencies.json")
            
            # 更新目标页面
            print("📝 [1/2] 更新目标页面...")
            updated = self._update_single_page(filepath, deps)
            if updated:
                result["updated_pages"].append(page_path)
            
            # 级联更新相关页面
            print("\n🔗 [2/2] 级联更新相关页面...")
            cascaded = self._cascade_update(filepath, deps)
            result["cascaded_updates"] = cascaded
            
            # 记录日志
            self.log_mgr.log_update(
                page_path,
                "single_update",
                f"更新页面及 {len(cascaded)} 个关联页面"
            )
            
            print(f"\n✅ 更新完成！")
            print(f"  目标页面: {'已更新' if updated else '无需更新'}")
            print(f"  级联更新: {len(cascaded)} 个页面")
            
        except Exception as e:
            result["errors"].append(str(e))
            print(f"\n❌ 更新失败: {e}")
            raise
        
        return result
    
    def cascade_from_raw(self, raw_file: str) -> dict:
        """
        从原始资料触发级联更新
        用于：新增或修改 raw 文件后，重新处理所有相关 wiki 页面
        """
        print(f"\n{'='*60}")
        print(f"🔗 从原始资料触发级联更新: {raw_file}")
        print(f"{'='*60}\n")
        
        filepath = Path(raw_file)
        if not filepath.is_absolute():
            raw_str = str(raw_file).replace('\\', '/')
            if raw_str.startswith('raw/'):
                filepath = self.utils.base_dir / raw_file
            else:
                filepath = self.utils.get_raw_path(raw_file)
        
        result = {
            "raw_file": raw_file,
            "affected_pages": [],
            "updates_performed": [],
            "errors": []
        }
        
        try:
            meta_data = self.utils.load_json(self.utils.raw_dir / "_meta.json")
            
            file_entry = None
            for f in meta_data.get("files", []):
                if f["path"] == str(filepath.relative_to(self.utils.base_dir)):
                    file_entry = f
                    break
            
            if not file_entry:
                print(f"⚠️  文件尚未被录入，请先运行 ingest")
                return result
            
            concepts = file_entry.get("extracted_concepts", [])
            entities = file_entry.get("extracted_entities", [])
            
            print(f"📋 关联概念 ({len(concepts)}): {', '.join(concepts)}")
            print(f"📋 关联实体 ({len(entities)}): {', '.join(entities)}\n")
            
            all_affected = []
            
            # 更新 source 页面
            source_page = file_entry.get("wiki_source_page")
            if source_page:
                source_path = self.utils.base_dir / source_page
                if source_path.exists():
                    self._refresh_source_page(source_path, filepath)
                    all_affected.append(source_page)
                    result["updates_performed"].append(f"刷新摘要页: {source_page}")
            
            # 更新概念页
            for concept in concepts:
                slug = self.utils.slugify(concept)
                concept_path = self.utils.get_wiki_path("concepts", f"{slug}.md")
                if concept_path.exists():
                    self._add_raw_reference(concept_path, filepath)
                    all_affected.append(f"wiki/concepts/{slug}.md")
                    result["updates_performed"].append(f"更新概念页: {concept}")
            
            # 更新实体页
            for entity in entities:
                slug = self.utils.slugify(entity)
                entity_path = self.utils.get_wiki_path("entities", f"{slug}.md")
                if entity_path.exists():
                    self._add_raw_reference(entity_path, filepath)
                    all_affected.append(f"wiki/entities/{slug}.md")
                    result["updates_performed"].append(f"更新实体页: {entity}")
            
            result["affected_pages"] = all_affected
            
            self.log_mgr.log_update(
                raw_file,
                "cascade_update",
                f"从原始资料触发，影响 {len(all_affected)} 个页面"
            )
            
            print(f"\n✅ 级联更新完成！")
            print(f"  影响页面: {len(all_affected)} 个")
            for update in result["updates_performed"]:
                print(f"  ✓ {update}")
            
        except Exception as e:
            result["errors"].append(str(e))
            print(f"\n❌ 级联更新失败: {e}")
            raise
        
        return result
    
    def _update_single_page(self, filepath: Path, deps: dict) -> bool:
        """
        更新单个页面
        返回 True 表示有实际更新，False 表示无变化
        """
        relative_path = str(filepath.relative_to(self.utils.base_dir))
        print(f"   检查: {filepath.name}", end="")
        
        content = self.utils.read_file(filepath)
        frontmatter, body = self.utils.parse_frontmatter(content)
        
        needs_update = False
        today = self.utils.get_today()
        
        page_deps = deps.get(relative_path, {})
        depends_on = page_deps.get("depends_on", [])
        
        for dep in depends_on:
            dep_path = self.utils.base_dir / dep
            if dep_path.exists():
                dep_content = self.utils.read_file(dep_path)
                dep_fm, _ = self.utils.parse_frontmatter(dep_content)
                
                dep_updated = dep_fm.get("updated", "")
                
                if dep_updated > frontmatter.get("updated", ""):
                    needs_update = True
                    break
        
        if needs_update:
            frontmatter["updated"] = today
            
            new_content = self.utils.build_frontmatter(frontmatter) + body
            self.utils.write_file(filepath, new_content)
            
            print(" → ✅ 已更新")
            return True
        else:
            print(" → ✓ 无需更新")
            return False
    
    def _cascade_update(self, target_path: Path, deps: dict) -> list:
        """
        级联更新：找到所有依赖目标页面的页面并更新
        """
        target_relative = str(target_path.relative_to(self.utils.base_dir))
        cascaded = []
        
        for page_path, page_deps in deps.items():
            dependents = page_deps.get("dependents", [])
            
            if target_relative in dependents or any(
                target_relative in dep for dep in dependents
            ):
                dep_path = self.utils.base_dir / page_path
                if dep_path.exists() and dep_path != target_path:
                    updated = self._update_single_page(dep_path, deps)
                    if updated:
                        cascaded.append(page_path)
        
        return cascaded
    
    def _refresh_source_page(self, source_path: Path, raw_path: Path):
        """刷新 source 页面的内容"""
        content = self.utils.read_file(raw_path)
        frontmatter, body = self.utils.parse_frontmatter(content)
        
        existing = self.utils.read_file(source_path)
        existing_fm, existing_body = self.utils.parse_frontmatter(existing)
        
        existing_fm["updated"] = self.utils.get_today()
        
        new_content = self.utils.build_frontmatter(existing_fm) + existing_body
        self.utils.write_file(source_path, new_content)
    
    def _add_raw_reference(self, page_path: Path, raw_path: Path):
        """在页面中添加新的原始资料引用"""
        content = self.utils.read_file(page_path)
        frontmatter, body = self.utils.parse_frontmatter(content)
        
        raw_rel = raw_path.relative_to(self.utils.base_dir).as_posix()
        
        if "sources" in frontmatter:
            if raw_rel not in frontmatter["sources"]:
                frontmatter["sources"].append(raw_rel)
                frontmatter["updated"] = self.utils.get_today()
                
                ref_text = f"- [{raw_path.name}]({raw_rel})"
                
                if "## 参考来源" in body and ref_text not in body:
                    body = body.replace("## 参考来源", "## 参考来源\n" + ref_text)
                elif "## 参考资料" in body and ref_text not in body:
                    body = body.replace("## 参考资料", "## 参考资料\n" + ref_text)
                
                new_content = self.utils.build_frontmatter(frontmatter) + body
                self.utils.write_file(page_path, new_content)
    
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
        index_content = f"""# LLM Wiki 知识库

> **最后更新**: {today}
> **总页面数**: {sum(len(files) for _, files in categories.values())}

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
    parser = argparse.ArgumentParser(
        description="LLM Wiki - 知识更新工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/update.py --all                           # 全量更新
  python scripts/update.py wiki/concepts/transformer.md    # 更新单页
  python scripts/update.py --cascade raw/articles/new.md   # 级联更新
        """
    )
    
    parser.add_argument(
        "target",
        nargs="?",
        help="要更新的目标（页面路径或 --all）"
    )
    
    parser.add_argument(
        "--all",
        action="store_true",
        help="更新所有页面"
    )
    
    parser.add_argument(
        "--cascade",
        metavar="RAW_FILE",
        help="从原始资料触发级联更新"
    )
    
    args = parser.parse_args()
    
    try:
        workflow = UpdateWorkflow(".")
        
        if args.all:
            result = workflow.update_all()
        elif args.cascade:
            result = workflow.cascade_from_raw(args.cascade)
        elif args.target:
            result = workflow.update_page(args.target)
        else:
            parser.print_help()
            sys.exit(1)
        
        if result.get("errors"):
            print(f"\n⚠️  警告: {len(result['errors'])} 个错误")
            sys.exit(1)
    
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
