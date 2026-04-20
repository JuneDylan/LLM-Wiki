#!/usr/bin/env python3
"""
LLM Wiki - 批量录入脚本
功能：自动扫描 raw/ 目录，批量处理所有未录入的 .md 文件
支持：普通文章 (articles/)、对话记录 (dialogues/)
使用方法:
  python scripts/batch_ingest.py                    # 处理所有新文件
  python scripts/batch_ingest.py --force            # 强制重新处理所有文件
  python scripts/batch_ingest.py --type dialogue    # 只处理对话记录
  python scripts/batch_ingest.py --type article     # 只处理普通文章
"""

import sys
import os
import io
import argparse
from pathlib import Path

# Windows 终端默认编码为 GBK，强制 stdout 使用 UTF-8 以支持 emoji
if sys.platform == "win32":
    try:
        if sys.stdout.encoding != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except (AttributeError, io.UnsupportedOperation):
        pass

sys.path.insert(0, str(Path(__file__).parent))
from utils import WikiUtils, MetadataManager
from ingest import IngestWorkflow
from ingest_dialogue import DialogueIngestWorkflow


def get_processed_files(meta_mgr: MetadataManager) -> set:
    """获取已经录入过的文件路径集合"""
    meta_data = meta_mgr.utils.load_json(meta_mgr.meta_file)
    processed = set()
    for f in meta_data.get("files", []):
        if f.get("processed"):
            processed.add(f["path"].replace("\\", "/"))
    return processed


def collect_files(utils: WikiUtils, file_type: str = None) -> list:
    """
    收集待处理的 .md 文件
    file_type: dialogue | article | None(全部)
    """
    files = []
    raw_dir = utils.raw_dir
    
    if not raw_dir.exists():
        return files
    
    # 对话记录
    if file_type in (None, "dialogue"):
        dialogues_dir = raw_dir / "dialogues"
        if dialogues_dir.exists():
            files.extend(sorted(dialogues_dir.rglob("*.md")))
    
    # 普通文章
    if file_type in (None, "article"):
        articles_dir = raw_dir / "articles"
        if articles_dir.exists():
            files.extend(sorted(articles_dir.rglob("*.md")))
    
    return files


def detect_file_type(filepath: Path) -> str:
    """根据路径判断文件类型"""
    path_str = str(filepath).lower().replace("\\", "/")
    if "/dialogues/" in path_str:
        return "dialogue"
    elif "/articles/" in path_str:
        return "article"
    return "article"  # 默认按文章处理


def main():
    parser = argparse.ArgumentParser(
        description="LLM Wiki - 批量录入工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/batch_ingest.py              # 增量录入所有新文件
  python scripts/batch_ingest.py --force      # 全量重新录入
  python scripts/batch_ingest.py --type dialogue
        """
    )
    parser.add_argument("--force", action="store_true", help="强制重新处理所有文件")
    parser.add_argument("--type", choices=["article", "dialogue"], help="只处理特定类型")
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print("📦 LLM Wiki 批量录入")
    print(f"{'='*60}\n")
    
    utils = WikiUtils(".")
    meta_mgr = MetadataManager(utils)
    
    # 获取已处理文件列表
    processed = set() if args.force else get_processed_files(meta_mgr)
    
    # 收集待处理文件
    all_files = collect_files(utils, args.type)
    
    if not all_files:
        print("⚠️  未找到任何 .md 文件")
        print(f"   请确保文件放在以下目录之一:")
        print(f"   - raw/articles/    (普通文章)")
        print(f"   - raw/dialogues/   (对话记录)")
        sys.exit(0)
    
    # 过滤已处理的文件
    to_process = []
    skipped = []
    
    for f in all_files:
        rel_path = f.relative_to(utils.base_dir).as_posix()
        if rel_path in processed:
            skipped.append(rel_path)
        else:
            to_process.append(f)
    
    print(f"📊 扫描结果:")
    print(f"   发现文件: {len(all_files)} 个")
    print(f"   待处理:   {len(to_process)} 个")
    print(f"   已跳过:   {len(skipped)} 个 (已录入)")
    if args.force:
        print(f"   模式:     强制重新处理所有文件")
    print()
    
    if not to_process and not args.force:
        print("✅ 所有文件都已录入完毕，无需处理\n")
        sys.exit(0)
    
    # 准备处理器
    article_workflow = IngestWorkflow(".")
    dialogue_workflow = DialogueIngestWorkflow(".")
    
    results = {
        "success": [],
        "failed": [],
        "skipped": skipped,
    }
    
    target_files = all_files if args.force else to_process
    
    for i, filepath in enumerate(target_files, 1):
        rel_path = filepath.relative_to(utils.base_dir).as_posix()
        file_type = detect_file_type(filepath)
        
        print(f"\n{'─'*60}")
        print(f"[{i}/{len(target_files)}] 处理: {rel_path} ({file_type})")
        print(f"{'─'*60}")
        
        try:
            if file_type == "dialogue":
                result = dialogue_workflow.ingest_file(str(filepath))
            else:
                result = article_workflow.ingest_file(str(filepath))
            
            if result.get("errors"):
                results["failed"].append({"file": rel_path, "errors": result["errors"]})
            else:
                results["success"].append(rel_path)
                
        except Exception as e:
            results["failed"].append({"file": rel_path, "errors": [str(e)]})
            print(f"❌ 处理失败: {e}")
    
    # 批量更新索引（避免每个文件重复更新）
    print(f"\n{'='*60}")
    print("📑 批量更新索引...")
    print(f"{'='*60}")
    article_workflow._update_index()
    print("   ✓ 索引已更新")
    
    # 输出统计
    print(f"\n{'='*60}")
    print("📊 批量处理报告")
    print(f"{'='*60}")
    print(f"  ✅ 成功:   {len(results['success'])} 个")
    print(f"  ❌ 失败:   {len(results['failed'])} 个")
    print(f"  ⏭️  跳过:   {len(results['skipped'])} 个")
    print(f"{'='*60}\n")
    
    # 如果有失败，打印详情
    if results["failed"]:
        print("🚨 失败详情:")
        for item in results["failed"]:
            print(f"   - {item['file']}")
            for err in item["errors"]:
                print(f"     错误: {err}")
        print()
        sys.exit(1)
    
    print("🎉 批量处理全部完成！建议运行一次体检:\n")
    print("   python scripts/healthcheck.py\n")


if __name__ == "__main__":
    main()
