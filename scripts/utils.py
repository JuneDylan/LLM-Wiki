#!/usr/bin/env python3
"""
LLM Wiki - 公共工具函数库
提供文件操作、Markdown 解析、元数据管理等基础功能
"""

import os
import re
import json
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import hashlib

try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False


class WikiUtils:
    """Wiki 工具类：提供所有工作流共享的基础功能"""
    
    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.raw_dir = self.base_dir / "raw"
        self.wiki_dir = self.base_dir / "wiki"
        self.scripts_dir = self.base_dir / "scripts"
        
    def get_raw_path(self, filename: str) -> Path:
        """获取 raw 文件完整路径"""
        return self.raw_dir / filename
    
    def get_wiki_path(self, category: str, filename: str) -> Path:
        """获取 wiki 文件完整路径"""
        return self.wiki_dir / category / filename
    
    def read_file(self, filepath: Path) -> str:
        """安全读取文件"""
        if not filepath.exists():
            raise FileNotFoundError(f"文件不存在: {filepath}")
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    
    def read_pdf_text(self, filepath: Path) -> str:
        """从 PDF 文件中提取文本"""
        if not PDF_SUPPORT:
            raise RuntimeError(
                "PDF 支持需要 pdfplumber。请安装: pip install pdfplumber"
            )
        text_parts = []
        try:
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
        except Exception as e:
            raise RuntimeError(f"无法读取 PDF 文件 {filepath}: {e}")
        return "\n".join(text_parts)
    
    def write_file(self, filepath: Path, content: str):
        """安全写入文件（自动创建目录）"""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def parse_frontmatter(self, content: str) -> Tuple[Dict[str, Any], str]:
        """
        解析 Markdown 的 YAML frontmatter
        返回 (frontmatter_dict, body_content)
        """
        if not content.startswith('---'):
            return {}, content
        
        lines = content.split('\n')
        end_idx = None
        
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                end_idx = i
                break
        
        if end_idx is None:
            return {}, content
        
        fm_text = '\n'.join(lines[1:end_idx])
        body = '\n'.join(lines[end_idx+1:])
        
        try:
            frontmatter = yaml.safe_load(fm_text) or {}
        except yaml.YAMLError:
            frontmatter = {}
        
        return frontmatter, body
    
    def build_frontmatter(self, metadata: Dict[str, Any]) -> str:
        """
        从字典构建 YAML frontmatter 字符串
        """
        field_order = ['title', 'type', 'created', 'updated', 'confidence', 
                      'sources', 'tags', 'related', 'status']
        
        ordered = {}
        for key in field_order:
            if key in metadata:
                ordered[key] = metadata[key]
        
        for key, value in metadata.items():
            if key not in ordered:
                ordered[key] = value
        
        fm_text = yaml.dump(ordered, allow_unicode=True, sort_keys=False, default_flow_style=False)
        return '---\n' + fm_text + '---\n\n'
    
    def extract_wiki_links(self, content: str) -> List[str]:
        """
        提取 Markdown 中的双向链接 [[link]]
        返回链接目标列表
        """
        pattern = r'\[\[([^\]]+)\]\]'
        matches = re.findall(pattern, content)
        return list(set(matches))
    
    def generate_id(self, text: str) -> str:
        """生成唯一 ID（基于内容的 hash）"""
        try:
            return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()[:12]
        except TypeError:
            # 某些 Python 发行版不支持 usedforsecurity 参数
            return hashlib.md5(text.encode()).hexdigest()[:12]
    
    def slugify(self, text: str) -> str:
        """
        将文本转换为文件名安全的 slug 格式
        例: "Transformer Architecture" -> "transformer-architecture"
        """
        text = text.lower().strip()
        # 显式将路径分隔符替换为连字符，避免生成异常子目录
        text = re.sub(r'[\\/]', '-', text)
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[-\s]+', '-', text)
        return text.strip('-')
    
    def get_today(self) -> str:
        """获取今天的日期字符串 YYYY-MM-DD"""
        return datetime.now().strftime('%Y-%m-%d')
    
    def load_json(self, filepath: Path) -> Dict:
        """加载 JSON 文件"""
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def save_json(self, filepath: Path, data: Dict):
        """保存 JSON 文件（格式化输出）"""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def list_wiki_files(self, category: Optional[str] = None) -> List[Path]:
        """
        列出 wiki 目录下的所有 .md 文件
        category: 可选，指定子目录（concepts/entities/comparisons/sources）
        """
        if category:
            search_dir = self.wiki_dir / category
        else:
            search_dir = self.wiki_dir
        
        files = []
        if search_dir.exists():
            for f in search_dir.rglob('*.md'):
                if f.name.startswith('_'):  # 排除模板文件
                    continue
                files.append(f)
        return sorted(files)
    
    def list_raw_files(self) -> List[Path]:
        """列出 raw 目录下所有文件（递归）"""
        files = []
        if self.raw_dir.exists():
            for ext in ['*.md', '*.pdf', '*.txt']:
                files.extend(self.raw_dir.rglob(ext))
        return sorted(files)


class MetadataManager:
    """元数据管理器：管理 _meta.json, _graph.json, _dependencies.json"""
    
    def __init__(self, utils: WikiUtils):
        self.utils = utils
        self.meta_file = utils.raw_dir / "_meta.json"
        self.graph_file = utils.wiki_dir / "_graph.json"
        self.deps_file = utils.wiki_dir / "_dependencies.json"
    
    def add_raw_file(self, filepath: Path, metadata: Dict[str, Any]):
        """添加原始文件到元数据库"""
        meta_data = self.utils.load_json(self.meta_file)
        
        file_entry = {
            "id": self.utils.generate_id(str(filepath)),
            "path": str(filepath.relative_to(self.utils.base_dir)),
            "filename": filepath.name,
            "type": self._detect_file_type(filepath),
            "size_bytes": filepath.stat().st_size,
            "added_date": self.utils.get_today(),
            "source_url": metadata.get("source_url", ""),
            "title": metadata.get("title", filepath.stem),
            "authors": metadata.get("authors", []),
            "language": metadata.get("language", "zh-CN"),
            "tags": metadata.get("tags", []),
            "processed": False,
            "wiki_source_page": "",
            "extracted_concepts": [],
            "extracted_entities": []
        }
        
        meta_data.setdefault("files", []).append(file_entry)
        meta_data["version"] = "1.0"
        meta_data["last_updated"] = self.utils.get_today()
        
        self._update_statistics(meta_data)
        self.utils.save_json(self.meta_file, meta_data)
        
        return file_entry["id"]
    
    def mark_as_processed(self, file_id: str, wiki_source_page: str,
                         concepts: List[str], entities: List[str]):
        """标记原始文件已处理"""
        meta_data = self.utils.load_json(self.meta_file)
        
        for f in meta_data.get("files", []):
            if f["id"] == file_id:
                f["processed"] = True
                f["wiki_source_page"] = wiki_source_page
                f["extracted_concepts"] = concepts
                f["extracted_entities"] = entities
                break
        
        meta_data["last_updated"] = self.utils.get_today()
        self.utils.save_json(self.meta_file, meta_data)
    
    def add_graph_node(self, node_id: str, node_path: str, 
                       node_type: str, label: str):
        """添加知识图谱节点"""
        graph = self.utils.load_json(self.graph_file)
        
        graph.setdefault("nodes", [])
        
        existing = any(n["id"] == node_id for n in graph["nodes"])
        if not existing:
            graph["nodes"].append({
                "id": node_id,
                "path": node_path,
                "type": node_type,
                "label": label
            })
        
        self.utils.save_json(self.graph_file, graph)
    
    def add_graph_edge(self, source: str, target: str, 
                       relation: str = "related_to"):
        """添加知识图谱边（关系）"""
        graph = self.utils.load_json(self.graph_file)
        
        graph.setdefault("edges", [])
        
        edge_exists = any(
            e["source"] == source and e["target"] == target 
            for e in graph["edges"]
        )
        
        if not edge_exists:
            graph["edges"].append({
                "source": source,
                "target": target,
                "relation": relation,
                "weight": 1
            })
        
        self.utils.save_json(self.graph_file, graph)
    
    def update_dependencies(self, wiki_page: str, depends_on: List[str],
                           dependents: List[str]):
        """更新页面依赖关系"""
        deps = self.utils.load_json(self.deps_file)
        
        deps.setdefault(wiki_page, {
            "depends_on": [],
            "dependents": [],
            "last_updated": ""
        })
        
        # 增量追加，避免覆盖
        existing = deps[wiki_page]
        existing["depends_on"] = list(set(existing.get("depends_on", []) + depends_on))
        existing["dependents"] = list(set(existing.get("dependents", []) + dependents))
        existing["last_updated"] = self.utils.get_today()
        
        self.utils.save_json(self.deps_file, deps)
    
    def _detect_file_type(self, filepath: Path) -> str:
        """检测文件类型"""
        path_str = str(filepath).lower()
        if '/articles/' in path_str or '\\articles\\' in path_str:
            return "article"
        elif '/papers/' in path_str or '\\papers\\' in path_str:
            return "paper"
        elif '/assets/' in path_str or '\\assets\\' in path_str:
            return "asset"
        return "unknown"
    
    def _update_statistics(self, meta_data: Dict):
        """更新统计信息"""
        files = meta_data.get("files", [])
        meta_data["statistics"] = {
            "total_files": len(files),
            "articles": sum(1 for f in files if f["type"] == "article"),
            "papers": sum(1 for f in files if f["type"] == "paper"),
            "assets": sum(1 for f in files if f["type"] == "asset")
        }


class LogManager:
    """变更日志管理器"""
    
    def __init__(self, utils: WikiUtils):
        self.utils = utils
        self.log_file = utils.wiki_dir / "_log.md"
    
    def log_ingest(self, raw_file: str, summary: str,
                   created_pages: List[str], updated_pages: List[str]):
        """记录录入操作"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        entry = f"""## [{timestamp}] Ingest: {raw_file}

- **操作**: 录入原始资料
- **摘要**: {summary}
- **新建页面**: {len(created_pages)} 个
{chr(10).join(f'  - {p}' for p in created_pages) if created_pages else '  - 无'}
- **更新页面**: {len(updated_pages)} 个
{chr(10).join(f'  - {p}' for p in updated_pages) if updated_pages else '  - 无'}

---
"""
        self._append_log(entry)
    
    def log_update(self, page: str, change_type: str, details: str):
        """记录更新操作"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        entry = f"""## [{timestamp}] Update: {page}

- **类型**: {change_type}
- **详情**: {details}

---
"""
        self._append_log(entry)
    
    def log_health_check(self, issues_found: int, issues_fixed: int):
        """记录体检操作"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        entry = f"""## [{timestamp}] Health Check

- **发现问题**: {issues_found} 个
- **修复问题**: {issues_fixed} 个

---
"""
        self._append_log(entry)
    
    def _append_log(self, entry: str):
        """追加日志条目"""
        if self.log_file.exists():
            content = self.utils.read_file(self.log_file)
            content += entry
        else:
            content = f"# 变更日志\n\n{entry}"
        
        self.utils.write_file(self.log_file, content)


def create_template(utils: WikiUtils, template_type: str) -> str:
    """
    根据类型生成模板内容
    template_type: concept | entity | comparison | source
    """
    today = utils.get_today()
    
    templates = {
        "concept": f"""---
title: "[概念名称]"
type: concept
created: "{today}"
updated: "{today}"
confidence: high
sources: []
tags: []
related: []
status: draft
---

# [概念名称]

## 定义
[一句话定义，清晰简洁]

## 核心原理
[详细解释工作原理、关键机制]

## 关键特性
- 特性 1
- 特性 2
- 特性 3

## 发展历程
[时间线或演进过程]

## 应用场景
- 场景 1
- 场景 2

## 与其他概念的关系
- **[[相关概念A]]**: [关系描述]
- **[[相关概念B]]**: [关系描述]

## 优缺点
### 优点
- ...

### 缺点
- ...

## 参考来源
- [来源1](raw/path/to/file)

---
*最后更新: {today}*
""",

        "entity": f"""---
title: "[实体名称]"
type: entity
created: "{today}"
updated: "{today}"
confidence: high
sources: []
tags: [person/company/project/paper]
related: []
status: draft
---

# [实体名称]

## 基本信息
- **类型**: 人物/公司/项目/论文
- **成立/出生日期**: [日期]
- **地点**: [地点]
- **官网/GitHub**: [链接]

## 简介
[2-3段详细简介]

## 主要贡献/成就
1. 贡献 1
2. 贡献 2
3. 贡献 3

## 相关概念
- **[[概念A]]**: [关联说明]
- **[[概念B]]**: [关联说明]

## 重要时间线
- **YYYY-MM**: [事件]
- **YYYY-MM**: [事件]

## 参考资料
- [来源1](raw/path/to/file)

---
*最后更新: {today}*
""",

        "comparison": f"""---
title: "[对比主题]"
type: comparison
created: "{today}"
updated: "{today}"
confidence: high
sources: []
tags: []
related: []
status: draft
---

# [对比主题]: A vs B vs C

## 对比维度总览

| 维度 | [[A]] | [[B]] | [[C]] |
|------|-------|-------|-------|
| 维度1 | ... | ... | ... |
| 维度2 | ... | ... | ... |
| 维度3 | ... | ... | ... |

## 详细分析

### 性能表现
[各方案的性能对比]

### 适用场景
- **A 适合**: ...
- **B 适合**: ...
- **C 适合**: ...

### 成本考量
[成本分析]

### 生态成熟度
[生态系统对比]

## 选择建议
[根据不同需求给出推荐]

## 总结
[一句话总结]

---
*最后更新: {today}*
""",

        "source": f"""---
title: "[资料标题]"
type: source
created: "{today}"
updated: "{today}"
confidence: high
sources: ["raw/path/to/original/file"]
tags: []
related: []
status: draft
---

# [资料标题]: 摘要

## 基本信息
- **原文路径**: raw/path/to/file
- **作者**: [...]
- **发布日期**: [日期]
- **类型**: 论文/文章/报告
- **URL**: [链接]

## 核心观点
1. 观点 1
2. 观点 2
3. 观点 3

## 关键发现
[最重要的发现或结论]

## 方法论
[研究方法、实验设计等]

## 数据与结果
[重要数据、图表解读]

## 局限性
[研究的不足之处]

## 提取的实体
- [[实体1]]
- [[实体2]]

## 提取的概念
- [[概念1]]
- [[概念2]]

## 原文引用
> [重要段落直接引用]

---
*最后更新: {today}*
"""
    }
    
    return templates.get(template_type, "")


if __name__ == "__main__":
    print("LLM Wiki Utils - 工具函数库")
    print("使用方法: from utils import WikiUtils, MetadataManager, LogManager")
