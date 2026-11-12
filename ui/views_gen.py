# -*- coding: utf-8 -*-
"""生成类功能视图：测试点分析 / 用例生成 / 脚本生成。

统一模式：视图收集参数 → 构造 prompt → JobManager 启动 claude 任务 →
任务在本页签内嵌任务区展示（状态 + 精简过程 + 结果概览），不切换视图。
"""
from __future__ import annotations

import gradio as gr

from .. import config, skill_advice
from ..jobs import get_job_manager
from .common import (
    bind_task_area,
    build_task_area,
    generated_case_ids,
    list_choices,
    parse_excel_cases,
)


# ---------------------------------------------------------------------------
# 测试点分析视图
# ---------------------------------------------------------------------------
def build_analysis_view(timer: gr.Timer) -> dict:
    """构建测试点分析视图：单选截图 + 内嵌任务区 + 完善 SKILL 区。"""
    with gr.Group(visible=False) as view:
        gr.Markdown(
            "### 测试点分析　选择 `screenshots/test-points/` 中的截图（单选），"
            "输出测试点文档到 `test-points/`。"
        )
        with gr.Row():
            with gr.Column(scale=1):
                btn_refresh = gr.Button("刷新截图列表", size="sm")
                shots_radio = gr.Radio(
                    label="选择截图（新文件在前）",
                    choices=list_choices(config.DIR_SHOT_TEST_POINTS, (".png", ".jpg")),
                    interactive=True,
                    elem_classes=["shot-scroll"],
                )
                shot_preview = gr.Image(label="截图预览", interactive=False, height=220)
                note = gr.Textbox(label="补充说明（可选）", lines=2, placeholder="如：重点关注顶部导航与弹窗")
                btn_start = gr.Button("开始分析", variant="primary")
            with gr.Column(scale=1):
                area = build_task_area()
        bind_task_area(timer, area)

        btn_refresh.click(
            lambda: gr.update(choices=list_choices(config.DIR_SHOT_TEST_POINTS, (".png", ".jpg"))),
            outputs=[shots_radio],
        )

        # 选中截图 → 预览（此前缺失该绑定，预览一直是空图）
        shots_radio.change(
            lambda p: p or None, inputs=[shots_radio], outputs=[shot_preview],
            show_progress="hidden",
        )

        def start_fn(shots, note_text):
            if not shots:
                return None, "请先选择一张截图"
            try:
                prompt = config.build_analysis_prompt(shots, note_text or "")
                job = get_job_manager().start_claude(prompt, title="测试点分析", kind="analysis")
            except RuntimeError as exc:
                return None, f"启动失败：{exc}"
            return job.id, f"**{job.title}** 已启动，过程与结果在本页签右侧展示"

        btn_start.click(
            start_fn, inputs=[shots_radio, note],
            outputs=[area["job_id"], area["status_md"]], show_progress="hidden",
        )

        # ---------------- 完善 SKILL（基于测试点文档中的完善建议） ----------------
        with gr.Accordion("完善 SKILL（提取文档完善建议 → 进聊天讨论方案）", open=True):
            gr.Markdown(
                "提取文档「Skill 完善建议」章节的未知组件/未知场景，"
                "进聊天讨论完善方案（先出方案，确认后改 `.claude/skills/*.md`）。"
            )
            advice_dd = gr.Dropdown(
                label="测试点文档（默认最新在前）",
                choices=list_choices(config.DIR_TEST_POINTS, (".md",)),
                interactive=True,
            )
            with gr.Row():
                btn_advice_refresh = gr.Button("刷新文档列表", size="sm")
                btn_extract = gr.Button("提取完善建议", size="sm", variant="secondary")
                btn_discuss = gr.Button("进聊天讨论方案", size="sm", variant="primary")
            advice_md = gr.Markdown("", elem_classes=["advice-table"])
            advice_state = gr.State([])

        btn_advice_refresh.click(
            lambda: gr.update(choices=list_choices(config.DIR_TEST_POINTS, (".md",))),
            outputs=[advice_dd],
        )

        def on_extract(md_path):
            if not md_path:
                return "请先选择测试点文档", []
            suggestions = skill_advice.extract_suggestions(md_path)
            return skill_advice.format_suggestions_md(suggestions), suggestions

        btn_extract.click(
            on_extract, inputs=[advice_dd], outputs=[advice_md, advice_state],
            show_progress="hidden",
        )

        def discuss_fn(md_path, suggestions, history, session_id):
            """进聊天讨论方案：切视图由 __init__ 的按钮链处理，本函数负责流式对话。"""
            if not suggestions:
                yield history, gr.update(), session_id, "请先提取完善建议（当前文档无可讨论条目）"
                return
            running = get_job_manager().running("claude")
            if running:
                yield history, gr.update(), session_id, \
                    f"已有 claude 任务在运行（{running[0].title}），请等待完成或停止后再讨论"
                return
            from .chat import stream_chat  # 延迟导入避免循环依赖
            prompt = skill_advice.build_discussion_prompt(md_path, suggestions)
            yield from stream_chat(prompt, "（完善 SKILL 方案讨论）", history, session_id)

        return {
            "view": view, "task": area,
            "advice": {"btn": btn_discuss, "inputs": [advice_dd, advice_state], "fn": discuss_fn},
        }


# ---------------------------------------------------------------------------
# 用例生成视图
# ---------------------------------------------------------------------------
def build_cases_view(timer: gr.Timer) -> dict:
    with gr.Group(visible=False) as view:
        gr.Markdown(
            "### 用例生成　选择 `test-points/` 测试点文档（最新在前），"
            "生成标准 12 列用例 Excel 到 `test-cases/`。"
        )
        with gr.Row():
            with gr.Column(scale=1):
                btn_refresh = gr.Button("刷新文档列表", size="sm")
                point_md = gr.Dropdown(
                    label="测试点文档",
                    choices=list_choices(config.DIR_TEST_POINTS, (".md",)),
                    interactive=True,
                )
                note = gr.Textbox(
                    label="补充说明（可选）", lines=2,
                    placeholder="如：无接口文档，接口测试维度整体排除",
                )
                btn_start = gr.Button("生成用例 Excel", variant="primary")
            with gr.Column(scale=1):
                area = build_task_area()
        bind_task_area(timer, area)

        btn_refresh.click(
            lambda: gr.update(choices=list_choices(config.DIR_TEST_POINTS, (".md",))),
            outputs=[point_md],
        )

        def start_fn(point, note_text):
            if not point:
                return None, "请先选择测试点文档"
            try:
                prompt = config.build_cases_prompt(point, note_text or "")
                job = get_job_manager().start_claude(prompt, title="用例生成", kind="cases")
            except RuntimeError as exc:
                return None, f"启动失败：{exc}"
            return job.id, f"**{job.title}** 已启动，过程与结果在本页签右侧展示"

        btn_start.click(
            start_fn, inputs=[point_md, note],
            outputs=[area["job_id"], area["status_md"]], show_progress="hidden",
        )

        return {"view": view, "task": area}


# ---------------------------------------------------------------------------
# 脚本生成视图
# ---------------------------------------------------------------------------
def build_scripts_view(timer: gr.Timer) -> dict:
    with gr.Group(visible=False) as view:
        gr.Markdown(
            "### 脚本生成　选择用例 Excel 解析后勾选用例（默认仅计划自动化且未生成），"
            "按编号前缀路由 script-func / script-ui 生成 pytest 脚本。"
        )
        with gr.Row():
            with gr.Column(scale=1):
                with gr.Row():                      # 第一排：文件选择 + 解析
                    xlsx_dd = gr.Dropdown(
                        label="测试用例 Excel",
                        choices=list_choices(config.DIR_TEST_CASES, (".xlsx",)),
                        interactive=True, scale=4,
                    )
                    btn_parse = gr.Button("解析用例", variant="secondary", scale=1)
                parse_status = gr.Markdown("")
                with gr.Row():                      # 第二排：数量上限 + 展示全部 + 刷新
                    limit_num = gr.Number(
                        label="数量上限（留空或 0 = 不限）", value=None, precision=0,
                        minimum=0, maximum=200, scale=1,
                    )
                    show_all_cb = gr.Checkbox(
                        label="显示全部用例（含未标记自动化 / 已生成）", value=False, scale=2,
                    )
                    btn_refresh = gr.Button("刷新", size="sm", scale=1)
                cases_check = gr.CheckboxGroup(
                    label="勾选要生成的用例（编号 ｜ 自动化状态 ｜ 名称）",
                    choices=[], interactive=True,
                    show_select_all=True,           # 原生全选/清空
                    elem_classes=["cases-grid"],    # 两列 + 限高滚动（CSS）
                )
                btn_gen = gr.Button("生成自动化脚本", variant="primary")
            with gr.Column(scale=1):
                area = build_task_area()
        bind_task_area(timer, area)

        btn_refresh.click(
            lambda: gr.update(choices=list_choices(config.DIR_TEST_CASES, (".xlsx",))),
            outputs=[xlsx_dd],
        )

        cases_state = gr.State([])          # 全量解析结果
        generated_state = gr.State(set())   # 已生成编号集合

        def _visible_cases(cases: list, generated: set, show_all: bool) -> list:
            """展示过滤：默认仅计划自动化；显示全部时含已生成（标注，避免误重复生成）。"""
            if show_all:
                return cases
            return [c for c in cases if c["auto"] == "计划自动化"]

        def _choices_of(cases: list, generated: set, show_all: bool) -> list[tuple[str, str]]:
            choices = []
            for case in _visible_cases(cases, generated, show_all):
                is_generated = case["id"] in generated
                label = (
                    f"{case['id']} ｜ {case['auto'] or '未标记'}"
                    + ("（已生成）" if is_generated else "")
                    + f" ｜ {case['name'][:26]}"
                )
                choices.append((label, case["id"]))
            return choices

        def on_parse(xlsx_path, show_all):
            """解析 Excel：全量用例清单 + 默认勾选（可自动化且未生成）。"""
            if not xlsx_path:
                return gr.update(), "请先选择测试用例 Excel", [], set()
            try:
                cases = parse_excel_cases(xlsx_path)
            except Exception as exc:
                return gr.update(), f"解析失败：{exc}", [], set()
            generated = generated_case_ids()
            autoable = [c for c in cases if c["auto"] == "计划自动化"]
            default_selected = [c["id"] for c in autoable if c["id"] not in generated]
            summary = (
                f"共解析 {len(cases)} 条用例；可自动化 {len(autoable)} 条；"
                f"已生成脚本 {len([c for c in cases if c['id'] in generated])} 条；"
                f"默认勾选 {len(default_selected)} 条（可自动化且未生成）"
            )
            update = gr.update(
                choices=_choices_of(cases, generated, show_all), value=default_selected,
            )
            return update, summary, cases, generated

        btn_parse.click(
            on_parse, inputs=[xlsx_dd, show_all_cb],
            outputs=[cases_check, parse_status, cases_state, generated_state],
        )

        def on_toggle_show_all(show_all, cases, generated, current_selected):
            """切换显示范围：保留勾选中仍在可见集合内的编号。"""
            cases = cases or []
            generated = generated or set()
            visible_ids = {c["id"] for c in _visible_cases(cases, generated, show_all)}
            keep = [cid for cid in (current_selected or []) if cid in visible_ids]
            return gr.update(choices=_choices_of(cases, generated, show_all), value=keep)

        show_all_cb.change(
            on_toggle_show_all,
            inputs=[show_all_cb, cases_state, generated_state, cases_check],
            outputs=[cases_check], show_progress="hidden",
        )

        def start_fn(xlsx_path, selected_ids, limit, generated):
            """提交生成：已生成的用例强制过滤（展示全部时可见但不可重复生成）。"""
            if not xlsx_path:
                return None, "请先选择测试用例 Excel"
            if not selected_ids:
                return None, "请先解析用例并勾选要生成的编号（勾选为空：无可生成用例）"
            generated = generated or set()
            skipped = [cid for cid in selected_ids if cid in generated]
            selected = [cid for cid in selected_ids if cid not in generated]
            if not selected:
                return None, "勾选的用例均已生成脚本（不可重复生成）；如需重新生成请先删除 tests/ 对应脚本"
            ids = ", ".join(selected)
            prompt = config.build_script_prompt(xlsx_path, ids, int(limit or 0))
            title = "脚本生成 " + (selected[0] + (f" 等{len(selected)}条" if len(selected) > 1 else ""))
            try:
                job = get_job_manager().start_claude(prompt, title=title, kind="scripts")
            except RuntimeError as exc:
                return None, f"启动失败：{exc}"
            note = f"（已跳过 {len(skipped)} 条已生成用例）" if skipped else ""
            return job.id, f"**{job.title}** 已启动{note}，过程与结果在本页签右侧展示"

        btn_gen.click(
            start_fn, inputs=[xlsx_dd, cases_check, limit_num, generated_state],
            outputs=[area["job_id"], area["status_md"]], show_progress="hidden",
        )

        return {"view": view, "task": area}
