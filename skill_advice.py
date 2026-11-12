# -*- coding: utf-8 -*-
"""SKILL 完善建议：本地解析测试点文档的「Skill 完善建议」章节 + 构造讨论 prompt。

测试点分析 SKILL 输出的文档末尾固定包含：

    ## Skill 完善建议 (Knowledge Gap Alert)
    ### 未知组件（如有）
    #### 1. 组件名
    - **视觉特征**：……
    - **建议优先级**：P2
    ### 未知页面/业务类型（如有）
    #### 1. 页面名
    - **建议优先级**：P0

本模块用正则按章节结构提取条目（不调模型），供「完善 SKILL」视图展示，
并以聊天讨论方式让模型基于建议给出 SKILL 完善方案。
"""
from __future__ import annotations

import re
from pathlib import Path

_SEC_RE = re.compile(r"^##\s*Skill\s*完善建议")            # 章节标题（容忍后缀 Knowledge Gap Alert）
_CAT_RE = re.compile(r"^###\s*(未知组件|未知页面[/／]?业务类型|未知页面)")
_ITEM_RE = re.compile(r"^####\s*\d*\s*[.、]?\s*(.+)$")
_BULLET_RE = re.compile(r"^-\s*\*\*(.+?)\*\*[：:]\s*(.*)$")
_PRI_RE = re.compile(r"\*\*建议优先级\*\*[：:]\s*(P\d)", re.I)

_DETAIL_MAX = 120  # 单条要点截断长度


def extract_suggestions(md_path: str | Path) -> list[dict]:
    """解析测试点文档「Skill 完善建议」章节。

    返回 [{"category": str, "name": str, "priority": str, "detail": str}]，
    未找到章节或无条目时返回 []。detail 为条目下除优先级外的要点拼接。
    """
    path = Path(md_path)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    suggestions: list[dict] = []
    in_section = False
    category = ""
    current: dict | None = None
    details: list[str] = []

    def _flush() -> None:
        nonlocal current, details
        if current is not None:
            current["detail"] = "；".join(details)[:_DETAIL_MAX * 2]
            suggestions.append(current)
        current, details = None, []

    for raw in lines:
        line = raw.strip()
        if not in_section:
            if _SEC_RE.match(line):
                in_section = True
            continue
        if line.startswith("## ") and not _SEC_RE.match(line):
            break  # 离开章节（下一个 ## 标题）
        cat = _CAT_RE.match(line)
        if cat:
            _flush()
            category = "未知组件" if cat.group(1).startswith("未知组件") else "未知页面"
            continue
        item = _ITEM_RE.match(line)
        if item:
            _flush()
            current = {"category": category, "name": item.group(1).strip(),
                       "priority": "", "detail": ""}
            continue
        if current is None:
            continue
        pri = _PRI_RE.search(line)
        if pri:
            current["priority"] = pri.group(1).upper()
            continue
        bullet = _BULLET_RE.match(line)
        if bullet and bullet.group(1) != "建议优先级" and bullet.group(2):
            text = bullet.group(2).strip()
            if text:
                details.append(f"{bullet.group(1)}：{text[:_DETAIL_MAX]}")
    _flush()
    return suggestions


def format_suggestions_md(suggestions: list[dict]) -> str:
    """建议列表 → Markdown 表格（视图展示用）。"""
    if not suggestions:
        return "该文档未包含 Skill 完善建议（或文档不含该章节）。"
    rows = ["| 分类 | 条目 | 优先级 | 要点 |", "|---|---|---|---|"]
    for s in suggestions:
        rows.append(
            f"| {s['category']} | {s['name']} | {s['priority'] or '—'} | {s['detail'] or '—'} |"
        )
    return "\n".join(rows)


def build_discussion_prompt(md_path: str | Path, suggestions: list[dict]) -> str:
    """构造「完善 SKILL」讨论 prompt：模型先读 SKILL 给方案，本轮不改文件。

    无建议条目时退化为通读引导——「进聊天」按钮在未提取建议时也能带入可直接发送的内容。
    """
    path = Path(md_path)
    if suggestions:
        items = "\n".join(
            f"- [{s['category']} ｜ {s['priority'] or '优先级未标'}] {s['name']}"
            + (f"（{s['detail']}）" if s["detail"] else "")
            for s in suggestions
        )
        suggest_block = f"提取到的建议条目：\n{items}\n\n"
    else:
        suggest_block = "该文档未提取到结构化建议条目，请通读全文找出可完善点。\n\n"
    return (
        "请基于测试点文档讨论完善对应的 SKILL 规范。\n\n"
        f"测试点文档（绝对路径）：{path.resolve()}\n"
        "请先读取该文档（重点关注「Skill 完善建议」章节）了解上下文。\n\n"
        f"{suggest_block}"
        "要求：\n"
        "1. 针对每个完善点，先读取 .claude/skills/web-test-analysis/SKILL.md（未知组件建议）"
        "或 .claude/skills/test-case-generation/SKILL.md（未知页面/场景建议），评估当前规范缺失点\n"
        "2. 给出具体完善方案：改哪个 SKILL.md 的哪个章节、补充什么内容（映射表条目/测试场景/决策规则等）\n"
        "3. 本轮仅讨论方案，不要修改任何文件；等我确认后再执行修改\n"
    )
