# -*- coding: utf-8 -*-
"""Gradio UI 组装：单主面板（聊天中心）+ 侧边栏功能按钮视图切换。

生成类视图（测试点分析/用例生成/脚本生成）的任务在本页签内嵌任务区展示，
启动按钮由各视图自行绑定，不再切回聊天；唯一跨视图联动是「完善 SKILL」
（切到聊天视图并把讨论 prompt 预填进消息栏，以 .success 链解耦）。
"""
from __future__ import annotations

import gradio as gr

from .. import config
from ..jobs import get_job_manager
from . import chat, views_gen, views_ops

_CSS = """
#workbench-header { text-align: center; padding: 4px 0 0; }
#workbench-header h1 { margin-bottom: 2px; font-size: 22px; }
.sidebar .btn { justify-content: flex-start; }
.sidebar .quit-btn { margin-top: 24px; }
/* 页面整体滚动：视图容器不再限高（overflow 会裁剪 Dropdown 弹层，导致"下拉没反应"），
   只有明确的长列表区域保留局部滚动；聊天视图例外——弹性填满窗口（页内无 Dropdown 弹层） */
.shot-scroll .wrap { max-height: 240px; overflow-y: auto; }
.cases-grid .wrap { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); max-height: 260px; overflow-y: auto; align-content: start; gap: 6px 14px; }
.advice-table { max-height: 180px; overflow-y: auto; }
.task-result { max-height: 340px; overflow-y: auto; }
/* 聊天视图弹性填满：Gradio Group 真实 DOM 为 .gr-group > .styler > 组件，flex 须作用于 .styler；
   chatbot 的内联 height:340 恰作 flex-basis，flex-grow 占满剩余空间、flex-shrink 允许收缩 */
:root { --chat-reserved: 160px; }  /* 头部+页脚+容器 padding 预留高度，playwright 实测校准 */
.chat-view { height: calc(100vh - var(--chat-reserved)); }
.chat-view .styler { display: flex; flex-direction: column; height: 100%; }
.chat-view .chat-fill { flex: 1 1 auto; min-height: 160px; }
/* 脚本运行页测试文件列表：一行一个、长名换行、不出横向滚动（minmax(0,1fr)+min-width:0 防长名撑开） */
.cases-list .wrap { display: grid; grid-template-columns: minmax(0, 1fr); max-height: 400px; overflow-y: auto; overflow-x: hidden; align-content: start; gap: 6px 0; }
.cases-list .wrap label, .cases-list .wrap label .wrap-inner, .cases-list .wrap label .label-text { min-width: 0; }
.cases-list .wrap label .label-text { white-space: normal; overflow-wrap: anywhere; }
/* 联想候选：CLI 风格（等宽、左对齐、hover 高亮成整行蓝底） */
.suggest-panel button { font-family: Consolas, "Courier New", monospace; text-align: left; justify-content: flex-start; }
.suggest-panel button:hover { background: #e3e7fd; }
"""

# 侧边栏按钮定义：(按钮文字, 视图序号)
_SIDEBAR = [
    ("聊天", 0), ("测试点分析", 1), ("用例生成", 2), ("脚本生成", 3),
    ("脚本运行", 4), ("结果报告", 5), ("项目上下文", 6),
]


def _quit_service() -> None:
    """退出服务：优雅停 uvicorn + 关闭 webview 窗口（launcher 保活循环随之收尾进程）。"""
    from .. import app as app_module  # 延迟导入：app 模块导入本模块，避免循环依赖
    app_module.stop_server()
    try:
        import webview
        for window in webview.windows:
            window.destroy()
    except Exception:
        pass  # 纯服务/浏览器模式无窗口可关，停服务即可


def build_ui() -> gr.Blocks:
    # 提前初始化 JobManager（建数据目录、恢复历史任务）
    get_job_manager()

    with gr.Blocks(title="B站 AI 测试工程化工作台", theme=gr.themes.Soft(), css=_CSS) as demo:
        with gr.Column(elem_id="workbench-header"):
            gr.Markdown(
                "# B站 AI 测试工程化工作台\n"
                "截图 → 测试点 → 用例 → 脚本 → 运行报告（claude CLI + GLM，"
                f"权限 {config.CLAUDE_PERMISSION_MODE}）"
            )

        active_job = gr.State(None)  # 当前聊天流中渲染的 SKILL 任务 id（仅聊天 /命令）
        timer = gr.Timer(config.POLL_INTERVAL_SEC)

        with gr.Row(equal_height=False):
            # ---------------- 侧边栏：功能按钮 ----------------
            with gr.Column(scale=0, min_width=180, elem_classes="sidebar"):
                sidebar_buttons = [gr.Button(text, variant="primary" if i == 0 else "secondary")
                                   for i, (text, _idx) in enumerate(_SIDEBAR)]
                # 服务常驻模式的唯一优雅退出入口（停 uvicorn + 关窗口 → launcher 收尾进程）
                btn_quit = gr.Button("退出服务", variant="stop", size="sm",
                                     elem_classes=["quit-btn"])
                btn_quit.click(_quit_service, inputs=[], outputs=[],
                               show_progress="hidden")

            # ---------------- 主区：7 个视图（聊天默认可见） ----------------
            with gr.Column(scale=7):
                view_chat, chat_refs = chat.build_chat_panel(timer, active_job)
                analysis = views_gen.build_analysis_view(timer)
                cases = views_gen.build_cases_view(timer)
                scripts = views_gen.build_scripts_view(timer)
                view_runner = views_ops.build_runner_view(timer)
                view_reports = views_ops.build_reports_view(timer)
                view_context = views_ops.build_context_view(timer)

        view_groups = [view_chat, analysis["view"], cases["view"], scripts["view"],
                       view_runner, view_reports, view_context]

        # ---------------- 侧边栏切换视图（含按钮高亮联动） ----------------
        def _make_switch(idx: int):
            def _switch():
                views = [gr.update(visible=i == idx) for i in range(len(view_groups))]
                buttons = [gr.update(variant="primary" if i == idx else "secondary")
                           for i in range(len(view_groups))]
                return views + buttons
            return _switch

        for button, (_text, idx) in zip(sidebar_buttons, _SIDEBAR):
            button.click(_make_switch(idx), inputs=[],
                         outputs=[*view_groups, *sidebar_buttons],
                         show_progress="hidden")

        # ---------------- 完善 SKILL：切到聊天后把讨论 prompt 预填进消息栏 ----------------
        adv = analysis["advice"]
        adv["btn"].click(
            _make_switch(0), inputs=[],
            outputs=[*view_groups, *sidebar_buttons], show_progress="hidden",
        ).success(
            adv["fn"],
            inputs=[*adv["inputs"], chat_refs["msg"]],
            outputs=[chat_refs["msg"], chat_refs["status"]],
            show_progress="hidden",
        )

    return demo
