# -*- coding: utf-8 -*-
"""工作台全局配置：路径常量、SKILL 注册表、prompt 模板、命令构建。

所有路径锚定项目根目录（workbench/ 的上一级），保证从任意工作目录启动均可用。
产物目录约定与 CLAUDE.md / 各 SKILL.md 保持一致，不新增第四套目录体系。
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 项目根目录与产物目录
# ---------------------------------------------------------------------------
# 开发模式：workbench/config.py 的上一级；exe 模式（PyInstaller frozen）：
# 优先环境变量 WORKBENCH_PROJECT_ROOT，否则从 exe 所在目录向上查找
# 含 CLAUDE.md / pytest.ini 的祖先目录（兼容 exe 放在项目根或其子目录）。
def _find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "CLAUDE.md").exists() or (candidate / "pytest.ini").exists():
            return candidate
    return start


if getattr(sys, "frozen", False):
    _ROOT_ENV = os.environ.get("WORKBENCH_PROJECT_ROOT", "").strip()
    if _ROOT_ENV:
        PROJECT_ROOT = Path(_ROOT_ENV)
    else:
        PROJECT_ROOT = _find_project_root(Path(sys.executable).resolve().parent)
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

DIR_TEST_POINTS = PROJECT_ROOT / "test-points"          # 测试点文档 *.md
DIR_TEST_CASES = PROJECT_ROOT / "test-cases"            # 测试用例 *.xlsx
DIR_TESTS = PROJECT_ROOT / "tests"                      # pytest 用例脚本
DIR_PAGES = PROJECT_ROOT / "pages"                      # POM 页面对象
DIR_SCREENSHOTS = PROJECT_ROOT / "screenshots"
DIR_SHOT_TEST_POINTS = DIR_SCREENSHOTS / "test-points"  # 测试点分析输入截图
DIR_SHOT_FAILURES = DIR_SCREENSHOTS / "failures"        # 失败自动截图（conftest 管理）
DIR_SHOT_SCRIPT_OUTPUT = DIR_SCREENSHOTS / "script-output"
DIR_RESULTS = PROJECT_ROOT / "results"                  # 失败用例 console/network 日志
DIR_TMP = PROJECT_ROOT / ".tmp" / "workbench"           # 工作台专用临时目录
DIR_CHAT_UPLOADS = DIR_TMP / "chat-uploads"             # 聊天面板附件

FILE_CLAUDE_MD = PROJECT_ROOT / "CLAUDE.md"

# ---------------------------------------------------------------------------
# 工作台自身数据目录（任务记录 / 日志 / junit 报告，本地 JSON 文件存储，无数据库）
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent / "data"
DIR_JOBS = DATA_DIR / "jobs"
DIR_JOB_LOGS = DATA_DIR / "logs"
DIR_REPORTS = DATA_DIR / "reports"

# ---------------------------------------------------------------------------
# 可执行命令
# ---------------------------------------------------------------------------
# pytest 使用项目虚拟环境解释器
PYTEST_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"


def resolve_claude_exe() -> str:
    """解析 claude CLI 可执行文件路径。

    优先级：环境变量 WORKBENCH_CLAUDE_CMD 显式覆盖 > CLAUDE_CODE_EXECPATH
    （Claude Code 自身维护的安装路径，直连 exe 避免 cmd 中间层）> PATH 中的 claude。
    """
    override = os.environ.get("WORKBENCH_CLAUDE_CMD", "").strip()
    if override:
        return override
    from_env = os.environ.get("CLAUDE_CODE_EXECPATH", "").strip()
    if from_env and Path(from_env).exists():
        return from_env
    found = shutil.which("claude")
    if found:
        return found
    raise FileNotFoundError(
        "未找到 claude CLI：请确认已安装 Claude Code，"
        "或设置环境变量 WORKBENCH_CLAUDE_CMD 指向可执行文件"
    )


# claude headless 模式的权限策略（用户已确认：SKILL 任务全自动执行）
CLAUDE_PERMISSION_MODE = os.environ.get("WORKBENCH_PERMISSION_MODE", "bypassPermissions")

# Web 服务绑定
HOST = os.environ.get("WORKBENCH_HOST", "127.0.0.1")
PORT = int(os.environ.get("WORKBENCH_PORT", "7860"))

# 轮询间隔（秒）：任务状态 + 日志刷新
POLL_INTERVAL_SEC = 2.0

# 日志区最多回显的行数
LOG_TAIL_LINES = 200

# ---------------------------------------------------------------------------
# SKILL 注册表（与 .claude/skills/ 一一对应）
# ---------------------------------------------------------------------------
SKILLS: dict[str, dict[str, str]] = {
    "web-test-analysis": {
        "label": "截图分析测试点",
        "skill_md": ".claude/skills/web-test-analysis/SKILL.md",
        "desc": "基于页面截图分析 UI 结构，输出 test-points/*.md",
        "param_hint": "示例：分析 bilibili 首页截图，重点关注顶部导航",
    },
    "test-case-generation": {
        "label": "测试点转用例 Excel",
        "skill_md": ".claude/skills/test-case-generation/SKILL.md",
        "desc": "基于 test-points/*.md 生成 test-cases/*.xlsx",
        "param_hint": "示例：基于 test-points/homepage_20261010_v4.md 生成，接口维度排除",
    },
    "script-func": {
        "label": "FUNC 用例 → 自动化脚本",
        "skill_md": ".claude/skills/script-func/SKILL.md",
        "desc": "基于 test-cases/*.xlsx 的 FUNC 用例生成 tests/test_*.py",
        "param_hint": "示例：基于 test-cases/homepage_20261102_v4.xlsx，用例编号 HOME_FUNC_001",
    },
    "script-ui": {
        "label": "UI 用例 → 自动化脚本",
        "skill_md": ".claude/skills/script-ui/SKILL.md",
        "desc": "基于 test-cases/*.xlsx 的 UI 用例生成 tests/test_*.py",
        "param_hint": "示例：基于 test-cases/homepage_20261102_v4.xlsx，用例编号 HOME_UI_001",
    },
    "py-browser-lite": {
        "label": "轻量浏览器脚本",
        "skill_md": ".claude/skills/py-browser-lite/SKILL.md",
        "desc": "单文件浏览器自动化脚本，输出到 scripts/",
        "param_hint": "示例：抓取 bilibili 热门榜标题，保存截图到 screenshots/debug/",
    },
}


# ---------------------------------------------------------------------------
# Prompt 模板
# ---------------------------------------------------------------------------
_TAIL = (
    "\n\n当前以 bypassPermissions 全自动权限运行，工作目录即项目根，"
    "可直接使用 Write/Edit/Bash 等工具落盘文件，无需请求授权。"
    "\n完成后，在回复末尾单独一行用【产物】前缀列出本次新生成的文件路径。"
)


def build_skill_prompt(skill_key: str, task_desc: str) -> str:
    """SKILL 快捷调用：要求模型读取对应 SKILL.md 并严格按规范执行。"""
    info = SKILLS[skill_key]
    return (
        f"请读取 {info['skill_md']} 并严格按其中规范执行本次任务。\n\n"
        f"任务：{task_desc or info['desc']}" + _TAIL
    )


def build_analysis_prompt(screenshot: str, note: str = "") -> str:
    """测试点分析：web-test-analysis SKILL，显式指定本次分析的截图（单张）。"""
    return (
        "请读取 .claude/skills/web-test-analysis/SKILL.md 并严格按其中规范执行测试点分析。\n\n"
        f"本次分析的截图（绝对路径）：{Path(screenshot).resolve()}\n\n"
        f"补充说明：{note.strip() or '无'}\n\n"
        "输出必须落到 test-points/ 目录，命名遵循 SKILL 规范（页面标识_日期_版本号）。" + _TAIL
    )


def build_cases_prompt(point_md: str, note: str = "") -> str:
    """用例生成：test-case-generation SKILL。"""
    return (
        "请读取 .claude/skills/test-case-generation/SKILL.md 并严格按其中规范执行测试用例生成。\n\n"
        f"输入的测试点文档（绝对路径）：{Path(point_md).resolve()}\n\n"
        f"补充说明：{note.strip() or '无'}\n\n"
        "输出必须落到 test-cases/ 目录，命名遵循 SKILL 规范。" + _TAIL
    )


def build_script_prompt(xlsx: str, case_ids: str, limit: int = 0) -> str:
    """脚本生成：按用例编号前缀路由（FUNC → script-func / UI → script-ui），混合任务一并说明。

    case_ids 为逗号分隔编号或 ALL（全量模式）；limit 为可选数量上限（0 = 不限）。
    """
    xlsx_path = Path(xlsx).resolve()
    ids_line = "ALL（全量模式：自动选取全部可自动化且未生成的用例）" if case_ids.strip().upper() == "ALL" else case_ids.strip()
    prompt = (
        "请执行自动化脚本生成，按用例编号前缀分别遵循对应 SKILL 规范：\n"
        "- FUNC 前缀用例：读取 .claude/skills/script-func/SKILL.md 并严格按其中规范执行\n"
        "- UI 前缀用例：读取 .claude/skills/script-ui/SKILL.md 并严格按其中规范执行\n\n"
        f"测试用例 Excel（绝对路径）：{xlsx_path}\n"
        f"本次要实现的用例编号：{ids_line}\n"
    )
    if limit and limit > 0:
        prompt += f"数量上限：本次最多生成 {limit} 个脚本（按顺序取前 {limit} 条，跳过已生成的不计数）\n"
    prompt += (
        "\n严格遵循 SKILL 的选择器现场核验、POM 更新、试运行修正流程；"
        "试运行完整输出落盘 results/。" + _TAIL
    )
    return prompt
