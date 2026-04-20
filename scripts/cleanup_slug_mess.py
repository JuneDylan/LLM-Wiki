#!/usr/bin/env python3
"""
清理由不一致 slug 生成导致的错误子目录文件
"""
import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import WikiUtils

utils = WikiUtils(".")
wiki = utils.wiki_dir

moved = 0
removed_empty = 0

for category in ["concepts", "entities", "sources"]:
    cat_dir = wiki / category
    if not cat_dir.exists():
        continue
    
    # 查找该类别下所有深度>1的 .md 文件
    for f in cat_dir.rglob("*.md"):
        rel_parts = f.relative_to(cat_dir).parts
        if len(rel_parts) > 1:
            # 这是错误子目录中的文件
            # 将子目录路径拼接成新的文件名（用 - 替换 /）
            new_name = "-".join(rel_parts)
            target = cat_dir / new_name
            
            print(f"发现异常路径: {f.relative_to(utils.base_dir)}")
            if target.exists():
                print(f"  目标 {target.relative_to(utils.base_dir)} 已存在，删除异常文件")
                f.unlink()
            else:
                print(f"  移动至: {target.relative_to(utils.base_dir)}")
                shutil.move(str(f), str(target))
                moved += 1
    
    # 清理空目录
    for subdir in sorted(cat_dir.rglob("*"), reverse=True):
        if subdir.is_dir() and not any(subdir.iterdir()):
            print(f"  删除空目录: {subdir.relative_to(utils.base_dir)}")
            subdir.rmdir()
            removed_empty += 1

print(f"\n清理完成: 移动 {moved} 个文件，删除 {removed_empty} 个空目录")
