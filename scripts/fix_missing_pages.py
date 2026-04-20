#!/usr/bin/env python3
"""
LLM Wiki - 缺失页面自动修复工具
功能：扫描所有断链，批量创建缺失的实体/概念 stub 页面
使用方法:
  python scripts/fix_missing_pages.py           # 创建所有缺失页面
  python scripts/fix_missing_pages.py --dry-run # 只预览，不创建
"""

import sys
import os
import io
import argparse
from pathlib import Path
from collections import defaultdict

# Windows 终端默认编码为 GBK，强制 stdout 使用 UTF-8 以支持 emoji
if sys.platform == "win32":
    try:
        if sys.stdout.encoding != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except (AttributeError, io.UnsupportedOperation):
        pass

sys.path.insert(0, str(Path(__file__).parent))
from utils import WikiUtils, create_template


def detect_link_category(link_text: str, all_files: list) -> str:
    """
    推断缺失链接应该属于哪个分类
    策略：
      1. 如果链接文本看起来像技术概念/方法 -> concepts
      2. 如果像产品/公司/人名/模型 -> entities
      3. 默认 -> concepts
    """
    text = link_text.lower()
    
    # 明显的实体特征
    entity_indicators = [
        '.cpp', '.py', '.js', '.go', '.rs',  # 工具/库
        'gpt-', 'llama', 'claude', 'gemini', 'qwen',  # 模型
        'openai', 'google', 'meta', 'anthropic', 'deepmind',
    ]
    
    # 明显的概念特征
    concept_indicators = [
        '量化', '微调', '蒸馏', '注意力', '嵌入', '优化',
        'transformer', 'attention', 'fine-tuning', 'quantization',
        'lora', 'rlhf', 'moe', 'rag', 'embedding',
    ]
    
    for indicator in entity_indicators:
        if indicator in text:
            return "entities"
    
    for indicator in concept_indicators:
        if indicator in text:
            return "concepts"
    
    # 启发式：如果包含人名大写、版本号、文件后缀 -> entity
    if any(c.isupper() for c in link_text[1:]) and len(link_text) > 3:
        # 但技术缩写通常也是大写，需要进一步判断
        pass
    
    # 默认放到 concepts（因为技术概念更多）
    return "concepts"


def main():
    parser = argparse.ArgumentParser(
        description="自动修复缺失的 wiki 页面",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true", help="只预览，不创建文件")
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print("🔧 缺失页面自动修复")
    print(f"{'='*60}\n")
    
    utils = WikiUtils(".")
    all_files = utils.list_wiki_files()
    
    # 收集所有有效页面
    valid_pages = {}
    for f in all_files:
        slug = utils.slugify(f.stem)
        valid_pages[slug] = f
    
    # 收集所有断链
    broken_links = defaultdict(list)  # link_text -> [source_files]
    
    for filepath in all_files:
        content = utils.read_file(filepath)
        links = utils.extract_wiki_links(content)
        for link in links:
            slug = utils.slugify(link)
            if slug not in valid_pages:
                broken_links[link].append(filepath)
    
    if not broken_links:
        print("✅ 没有发现断链，知识库非常健康！\n")
        sys.exit(0)
    
    print(f"📊 发现 {len(broken_links)} 个缺失页面（来自 {sum(len(v) for v in broken_links.values())} 处引用）\n")
    
    created_count = {"concepts": 0, "entities": 0}
    
    for link_text, sources in sorted(broken_links.items(), key=lambda x: -len(x[1])):
        slug = utils.slugify(link_text)
        category = detect_link_category(link_text, all_files)
        target_path = utils.get_wiki_path(category, f"{slug}.md")
        
        # 如果已存在（可能之前创建过），跳过
        if target_path.exists():
            continue
        
        ref_count = len(sources)
        print(f"  {'[预览]' if args.dry_run else ''} 创建: wiki/{category}/{slug}.md")
        print(f"      原名: [[{link_text}]] | 被引用: {ref_count} 次")
        
        if not args.dry_run:
            template_type = "concept" if category == "concepts" else "entity"
            template = create_template(utils, template_type)
            
            if category == "concepts":
                content = template.replace("[概念名称]", link_text)
                content = content.replace("[一句话定义，清晰简洁]",
                                         f"[{link_text}] 的定义（待补充）")
                content = content.replace("[详细解释工作原理、关键机制]",
                                         f"[{link_text}] 的核心原理（待补充）")
            else:
                content = template.replace("[实体名称]", link_text)
                content = content.replace("**类型**: 人物/公司/项目/论文",
                                         "**类型**: [自动检测]")
                content = content.replace("- **成立/出生日期**: [日期]",
                                         "- **来源**: 从对话记录中提取")
            
            utils.write_file(target_path, content)
        
        created_count[category] += 1
    
    print(f"\n{'='*60}")
    if args.dry_run:
        print("📋 预览模式完成，未创建任何文件")
    else:
        print(f"✅ 修复完成！")
    print(f"   创建概念页: {created_count['concepts']} 个")
    print(f"   创建实体页: {created_count['entities']} 个")
    print(f"{'='*60}\n")
    
    if not args.dry_run:
        print("💡 建议接下来运行:\n")
        print("   python scripts/healthcheck.py\n")


if __name__ == "__main__":
    main()
