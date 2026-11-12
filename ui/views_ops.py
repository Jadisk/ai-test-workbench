# -*- coding: utf-8 -*-
"""运维类功能视图：脚本运行 / 结果报告 / 项目上下文。"""
from __future__ import annotations

import ast
from pathlib import Path

import gradio as gr

from .. import config
from ..jobs import format_summary_md, get_job_manager
from ..pytest_api import parse_junitxml
from .common import list_choices, list_files, list_test_choices, read_text


# ---------------------------------------------------------------------------
# 脚本运行视图
# ---------------------------------------------------------------------------
def build_runner_view(timer: gr.Timer) -> gr.Group:
    with gr.Group(visible=False) as view:
        gr.Markdown(
            "### 脚本运行\n\n"
            "通过 subprocess 调用项目虚拟环境 pytest（默认 msedge 无头）。"
            "失败用例自动截图至 `screenshots/failures/`，运行结果落盘 `results/`。"
            "测试文件默认全不选，勾选后仅运行所选。"
        )
        with gr.Row():
            with gr.Column(scale=1):
                run_all = gr.Checkbox(label="全量运行 tests/", value=False)
                test_files = gr.CheckboxGroup(
                    label="选择测试文件",
                    choices=list_test_choices(),
                    value=[],
                    interactive=True,
                    show_select_all=True,
                    elem_classes=["cases-list"],    # 一行一个 + 长名换行 + 限高滚动（与脚本生成的 cases-grid 区分）
                )
                marker_dd = gr.Dropdown(
                    label="优先级过滤（-m）", choices=["", "p0", "p1", "p2"],
                    value="", interactive=True,
                )
                channel_dd = gr.Dropdown(
                    label="浏览器渠道", choices=["msedge", "chromium"], value="msedge",
                    info="chromium 需 ms-playwright 缓存（当前缺失，默认 msedge）",
                )
                headed_cb = gr.Checkbox(label="有头模式（--headed，调试用）", value=False)
                btn = gr.Button("运行 pytest", variant="primary")
                btn_stop = gr.Button("停止", variant="stop")
                job_id = gr.State(None)
            with gr.Column(scale=2):
                status = gr.Markdown("")
                summary_md = gr.Markdown("暂无结果数据")
                log = gr.Code(label="实时日志", lines=16, language=None)
                cases_df = gr.DataFrame(
                    label="用例结果", interactive=False, wrap=True, max_height=420,
                )

        def on_start(run_all_flag, files, marker, channel, headed):
            targets = ["tests/"] if run_all_flag else list(files or [])
            if not targets:
                return None, "请勾选全量运行或选择至少一个测试文件"
            try:
                job = get_job_manager().start_pytest(
                    targets=targets, marker=marker or "", headed=headed, channel=channel or "msedge",
                )
            except RuntimeError as exc:
                return None, f"启动失败：{exc}"
            return job.id, f"已启动：{job.title}（任务 {job.id}）"

        btn.click(on_start, inputs=[run_all, test_files, marker_dd, channel_dd, headed_cb],
                  outputs=[job_id, status])

        def on_stop(job_id_value: str):
            get_job_manager().stop(job_id_value or "")

        btn_stop.click(on_stop, inputs=[job_id], outputs=[], show_progress="hidden")

        def refresh_summary(job):
            summary = (job.meta.get("summary") if job else None) or {}
            return format_summary_md(summary), _cases_table(summary)

        from .common import make_poll_outputs
        tick = make_poll_outputs(job_id, status, log, extra_fn=refresh_summary)
        timer.tick(tick, inputs=[job_id], outputs=[status, log, summary_md, cases_df],
                   show_progress="hidden")
        return view


def _cases_table(summary: dict) -> list[list]:
    """junitxml 摘要 → 用例表格（gr.DataFrame）。"""
    if not summary or not summary.get("cases"):
        return [["（暂无用例数据）"]]
    rows = [["用例", "状态", "耗时(s)", "失败信息"]]
    for case in summary["cases"]:
        label = {"passed": "通过", "failed": "失败", "error": "错误", "skipped": "跳过"}.get(
            case["status"], case["status"]
        )
        rows.append([case["nodeid"], label, case["time"], case.get("message") or ""])
    return rows


# ---------------------------------------------------------------------------
# 结果报告视图
# ---------------------------------------------------------------------------
def build_reports_view(timer: gr.Timer) -> gr.Group:
    with gr.Group(visible=False) as view:
        gr.Markdown(
            "### 结果报告\n\n"
            "回看历史 pytest 运行（junitxml 解析 + `results/` 落盘文件），"
            "浏览失败截图与运行日志。实时执行请用「脚本运行」。"
        )
        with gr.Accordion("历史 pytest 运行", open=True):
            with gr.Row():
                btn_refresh = gr.Button("刷新列表", scale=1)
                job_dd = gr.Dropdown(
                    label="选择历史运行", choices=_pytest_job_choices(),
                    interactive=True, scale=3,
                )
            summary_md = gr.Markdown("暂无数据")
            cases_df = gr.DataFrame(label="用例结果", interactive=False, wrap=True, max_height=320)
            job_log = gr.Code(label="该次运行日志", lines=16, language=None)

        def on_load(job_id_value: str):
            manager = get_job_manager()
            job = manager.get(job_id_value or "")
            if job is None:
                return "任务不存在", [["（无数据）"]], ""
            summary = job.meta.get("summary")
            if not summary and job.meta.get("junitxml"):
                summary = parse_junitxml(Path(job.meta["junitxml"]))
            status_line = f"**{job.title}** ｜ 状态：{job.status} ｜ {job.created_at}"
            return (f"{status_line}\n\n{format_summary_md(summary or {})}",
                    _cases_table(summary or {}), manager.log_tail(job_id_value))

        job_dd.change(on_load, inputs=[job_dd], outputs=[summary_md, cases_df, job_log])
        btn_refresh.click(lambda: gr.update(choices=_pytest_job_choices()), outputs=[job_dd])

        # 区块顺序（常用度优先）：历史运行 → 运行结果文件 → 失败截图
        gr.Markdown("### 运行结果文件（results/，pytest 运行与 SKILL 试运行落盘）")
        with gr.Row():
            btn_results_refresh = gr.Button("刷新", scale=1)
            results_dd = gr.Dropdown(
                label="文件", choices=list_choices(config.DIR_RESULTS, (".log", ".json")),
                interactive=True, scale=3,
            )
        results_preview = gr.Code(label="文件内容", lines=16, language=None)

        results_dd.change(
            lambda p: read_text(p) if p else "", inputs=[results_dd], outputs=[results_preview],
        )
        btn_results_refresh.click(
            lambda: gr.update(choices=list_choices(config.DIR_RESULTS, (".log", ".json"))),
            outputs=[results_dd],
        )

        gr.Markdown("### 失败截图（screenshots/failures/，conftest 自动保存）")
        gr.Gallery(value=_failures_gallery(), columns=4, height=320, interactive=False)
        return view


def _pytest_job_choices() -> list[tuple[str, str]]:
    """历史 pytest 任务下拉选项 [(显示, job_id)]。"""
    return [
        (f"{job.created_at} ｜ {job.title} ｜ {job.status}", job.id)
        for job in get_job_manager().list(kind="pytest")
    ]


def _failures_gallery() -> list[tuple[str, str]]:
    """失败截图画廊（最新 20 张）。"""
    return [
        (path, Path(path).name)
        for path in list_files(config.DIR_SHOT_FAILURES, (".png", ".jpg"))[:20]
    ]


# ---------------------------------------------------------------------------
# 项目上下文视图
# ---------------------------------------------------------------------------
def build_context_view(timer: gr.Timer) -> gr.Group:
    with gr.Group(visible=False) as view:
        gr.Markdown(
            f"### 项目上下文\n\n"
            f"项目根目录：`{config.PROJECT_ROOT}` ｜ "
            f"claude CLI 权限：`{config.CLAUDE_PERMISSION_MODE}` ｜ "
            f"pytest 解释器：`{config.PYTEST_PYTHON}`"
        )
        gr.Markdown("#### 浏览器配置（src/corebrowser.py，实际生效值）")
        gr.Markdown(_browser_config_md())
        with gr.Accordion("CLAUDE.md（项目规范，含目录结构与约定）", open=False):
            gr.Code(
                value=read_text(config.FILE_CLAUDE_MD),
                label="CLAUDE.md 原文（可全选复制）",
                language="markdown", interactive=False, lines=22, wrap_lines=True,
            )
        return view


_BROWSER_CONFIG_KEYS = {
    "DEFAULT_BROWSER_CHANNEL": "channel",
    "BROWSER_ARGS": "args",
    "CONTEXT_CONFIG": "context",
}


def _extract_browser_config() -> dict | None:
    """ast 静态解析 src/corebrowser.py 顶层字面量赋值（不执行 import）。

    exe frozen 模式下 src 不是可导入包且 playwright 未打包，动态 import 必失败
    （此前「实际生效值」下方的一行报错即来源于此）；三个目标常量均为纯字面量
    （str / list[str] / 含嵌套 dict），literal_eval 安全。
    """
    path = config.PROJECT_ROOT / "src" / "corebrowser.py"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError, ValueError):
        return None
    out: dict = {"channel": None, "args": [], "context": {}}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value_node = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value_node = node.target, node.value
        else:
            continue
        if not isinstance(target, ast.Name) or value_node is None:
            continue
        key = _BROWSER_CONFIG_KEYS.get(target.id)
        if key is None:
            continue
        try:
            out[key] = ast.literal_eval(value_node)
        except (ValueError, TypeError, MemoryError):
            continue  # 非字面量（拼接/调用）→ 保留默认值，不中断渲染
    return out


def _browser_config_md() -> str:
    """浏览器配置实际生效值：ast 静态解析 src/corebrowser.py（frozen 安全）。"""
    cfg = _extract_browser_config()
    if cfg is None:
        return "（读取 src/corebrowser.py 失败：文件不存在或语法错误）"
    args = "\n".join(f"  - `{a}`" for a in cfg["args"])
    context = cfg["context"] or {}
    viewport = context.get("viewport", {})
    return (
        f"**浏览器渠道**：`{cfg['channel']}`（系统自带 Edge）\n\n"
        f"**viewport**：`{viewport.get('width')}×{viewport.get('height')}` ｜ "
        f"**locale**：`{context.get('locale')}` ｜ "
        f"**时区**：`{context.get('timezone_id')}`\n\n"
        f"**启动参数（BROWSER_ARGS）**：\n{args}\n\n"
        f"**反检测**：`ANTI_DETECTION_SCRIPT`（conftest autouse 注入）"
    )
