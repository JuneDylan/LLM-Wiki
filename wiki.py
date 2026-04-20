#!/usr/bin/env python3
"""
LLM Wiki - 统一命令行入口

将分散的 scripts/ 脚本封装为统一 CLI，降低使用门槛。

用法:
  python wiki.py ingest                  # 增量录入新文件
  python wiki.py ingest --force          # 全量重新录入
  python wiki.py health                  # 运行体检
  python wiki.py health --fix-links      # 体检并自动修复断链
  python wiki.py query "Transformer"     # 搜索知识库
  python wiki.py fix                     # 修复缺失页面
  python wiki.py update --all            # 更新索引
  python wiki.py rebuild                 # 一键全量重建（备份→清空→重新录入→修复→体检）
"""

import sys
import os
import shutil
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

# Windows 终端默认编码为 GBK，强制 stdout 使用 UTF-8 以支持 emoji
if sys.platform == "win32":
    import io
    try:
        if sys.stdout.encoding != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except (AttributeError, io.UnsupportedOperation):
        pass


PROJECT_ROOT = Path(__file__).parent.resolve()
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def run_script(script_name: str, args: list) -> int:
    """运行指定脚本并传递参数"""
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        print(f"❌ 脚本不存在: {script_path}")
        return 1
    
    cmd = [sys.executable, str(script_path)] + args
    print(f"▶  {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return result.returncode


def cmd_ingest(args):
    """录入命令"""
    extra = []
    if args.force:
        extra.append("--force")
    if args.type:
        extra.extend(["--type", args.type])
    return run_script("batch_ingest.py", extra)


def cmd_health(args):
    """体检命令"""
    extra = []
    if args.fix_links:
        extra.append("--fix-links")
    if args.quiet:
        extra.append("--quiet")
    return run_script("healthcheck.py", extra)


def cmd_query(args):
    """查询命令"""
    extra = []
    if args.keyword:
        extra.append(args.keyword)
    if args.tag:
        extra.extend(["--tag", args.tag])
    if args.entity:
        extra.extend(["--entity", args.entity])
    if args.list_all:
        extra.append("--list-all")
    return run_script("query.py", extra)


def cmd_fix(args):
    """修复命令"""
    extra = []
    if args.dry_run:
        extra.append("--dry-run")
    return run_script("fix_missing_pages.py", extra)


def cmd_update(args):
    """更新命令"""
    extra = []
    if args.page:
        extra.append(args.page)
    if args.all:
        extra.append("--all")
    if args.cascade:
        extra.extend(["--cascade", args.cascade])
    return run_script("update.py", extra)


def cmd_rebuild(args):
    """
    一键全量重建：
    1. 备份当前 wiki
    2. 清空 wiki 内容页
    3. 重置 _meta.json processed 标记
    4. 全量重新录入
    5. 修复缺失页面
    6. 运行体检
    """
    if not args.yes:
        confirm = input("⚠️  这将备份并清空当前 wiki，然后全量重建。确认吗？ [y/N] ")
        if confirm.lower() not in ("y", "yes"):
            print("已取消")
            return 0

    backup_name = f"wiki-backup-{datetime.now().strftime('%Y%m%d-%H%M')}"
    backup_path = PROJECT_ROOT / backup_name
    wiki_dir = PROJECT_ROOT / "wiki"
    meta_file = PROJECT_ROOT / "raw" / "_meta.json"

    # 1. 备份
    if wiki_dir.exists():
        print(f"\n📦 备份 wiki/ → {backup_name}/ ...")
        shutil.copytree(wiki_dir, backup_path, ignore=shutil.ignore_patterns("*.tmp"))
        print(f"   ✓ 备份完成")

    # 2. 清空 wiki 内容（保留目录结构）
    print("\n🧹 清空 wiki 内容页...")
    for subdir in ["sources", "concepts", "entities", "comparisons"]:
        d = wiki_dir / subdir
        if d.exists():
            for f in d.glob("*.md"):
                f.unlink()
            print(f"   ✓ 清空 wiki/{subdir}/")
    
    # 保留 index.md, _log.md 等元文件
    for keep in ["index.md", "_log.md", "_graph.json", "_dependencies.json"]:
        keep_path = wiki_dir / keep
        if not keep_path.exists():
            keep_path.write_text("", encoding="utf-8")

    # 3. 重置 processed 标记（可选：更安全的方式是清空 processed）
    if meta_file.exists():
        print("\n📝 重置录入标记...")
        import json
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            for f in meta.get("files", []):
                f["processed"] = False
                f["wiki_source_page"] = ""
            meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            print("   ✓ 已重置")
        except Exception as e:
            print(f"   ⚠️ 重置 meta 失败: {e}")

    # 4. 全量重新录入
    print("\n" + "=" * 60)
    print("🚀 开始全量重新录入")
    print("=" * 60)
    ret = run_script("batch_ingest.py", ["--force"])
    if ret != 0:
        print("\n❌ 录入阶段失败，停止重建")
        return ret

    # 5. 修复缺失页面
    print("\n" + "=" * 60)
    print("🔧 修复缺失页面")
    print("=" * 60)
    ret = run_script("fix_missing_pages.py", [])
    if ret != 0:
        print("\n⚠️ 修复阶段出错（非致命）")

    # 6. 体检
    print("\n" + "=" * 60)
    print("🏥 运行健康检查")
    print("=" * 60)
    ret = run_script("healthcheck.py", [])

    print(f"\n{'=' * 60}")
    print(f"🎉 重建完成！备份保存在: {backup_name}/")
    print(f"{'=' * 60}\n")
    return ret


def main():
    parser = argparse.ArgumentParser(
        prog="wiki.py",
        description="LLM Wiki - 本地 LLM 驱动的知识库编译器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
快速开始:
  1. 配置环境变量:  export LLM_PROVIDER=qwen; export LLM_API_KEY=xxx
  2. 放入资料:       cp my-dialogue.md raw/dialogues/
  3. 一键录入:       python wiki.py ingest
  4. 查看体检:       python wiki.py health

更多文档见: README.md / CLAUDE.md
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # ingest
    p = subparsers.add_parser("ingest", help="批量录入 raw 文件到 wiki")
    p.add_argument("--force", action="store_true", help="强制重新处理所有文件")
    p.add_argument("--type", choices=["article", "dialogue"], help="只处理特定类型")
    
    # health
    p = subparsers.add_parser("health", help="运行知识库健康检查")
    p.add_argument("--fix-links", action="store_true", help="自动修复断链")
    p.add_argument("--quiet", action="store_true", help="静默模式，仅输出摘要")
    
    # query
    p = subparsers.add_parser("query", help="查询知识库内容")
    p.add_argument("keyword", nargs="?", help="搜索关键词")
    p.add_argument("--tag", help="按标签筛选")
    p.add_argument("--entity", help="按实体筛选")
    p.add_argument("--list-all", action="store_true", help="列出所有页面")
    
    # fix
    p = subparsers.add_parser("fix", help="修复缺失的 wiki 页面（断链自动补齐）")
    p.add_argument("--dry-run", action="store_true", help="只预览，不创建文件")
    
    # update
    p = subparsers.add_parser("update", help="更新知识库索引和依赖关系")
    p.add_argument("page", nargs="?", help="指定要更新的 wiki 页面路径")
    p.add_argument("--all", action="store_true", help="更新所有页面")
    p.add_argument("--cascade", metavar="RAW_FILE", help="从指定 raw 文件级联更新")
    
    # rebuild
    p = subparsers.add_parser("rebuild", help="一键全量重建（备份→清空→重新录入→修复→体检）")
    p.add_argument("--yes", "-y", action="store_true", help="跳过确认提示")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    handlers = {
        "ingest": cmd_ingest,
        "health": cmd_health,
        "query": cmd_query,
        "fix": cmd_fix,
        "update": cmd_update,
        "rebuild": cmd_rebuild,
    }
    
    ret = handlers[args.command](args)
    sys.exit(ret)


if __name__ == "__main__":
    main()
