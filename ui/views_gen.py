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
    preview_xlsx,
    read_text,
)


# ---------------------------------------------------------------------------
# 测试点分析视图
# ---------------------------------------------------------------------------
def build_analysis_view(timer: gr.Timer) -> dict:
    """构建测试点分析视图：单选截图 + 内嵌任务区（含文档预览） + 完善 SKILL 区。"""
    _advice_files = list_choices(config.DIR_TEST_POINTS, (".md",))
    with gr.Group(visible=False) as view:
        gr.Markdown(
            "### 测试点分析　选择 `screenshots/test-points/` 中的截图（单选），"
            "输出测试点文档到 `test-points/`。"
        )
        with gr.Row():
            with gr.Column(scale=1):
                btn_refresh = gr.Button("刷新截图列表", size="sm")
                shots_radio = gr.Radio(
                    label="选择截图",
                    choices=list_choices(config.DIR_SHOT_TEST_POINTS, (".png", ".jpg")),
                    interactive=True,
                    elem_classes=["shot-scroll"],
                )
                shot_preview = gr.Image(label="截图预览", interactive=False, height=220)
                note = gr.Textbox(label="补充说明（可选）", lines=2, placeholder="如：重点关注顶部导航与弹窗")
                btn_start = gr.Button("开始分析", variant="primary")
            with gr.Column(scale=1):
                area = build_task_area()
                # 与用例生成同模式：任务区下方 + 限高框内滚动；初始值对齐 Dropdown 自动预选
                advice_preview = gr.Code(
                    value=read_text(_advice_files[0][1]) if _advice_files else "",
                    label="文档内容预览", language="markdown",
                    interactive=False, wrap_lines=True,
                    elem_classes=["preview-scroll"],
                )
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
                label="测试点文档",
                choices=_advice_files,
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

        # 选中测试点文档 → 右列预览原文
        advice_dd.change(
            lambda p: read_text(p) if p else "", inputs=[advice_dd],
            outputs=[advice_preview], show_progress="hidden",
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

        def discuss_prefill(md_path, suggestions, msg_value):
            """进聊天讨论方案：切视图由 __init__ 的按钮链处理，本函数把讨论 prompt 预填进消息栏（不自动发送）。"""
            prompt = skill_advice.build_discussion_prompt(md_path, suggestions or [])
            files = (msg_value or {}).get("files") or []   # 保留用户已贴的附件
            if suggestions:
                hint = "已填入讨论内容（消息栏），请核对补充后手动发送"
            else:
                hint = "该文档未提取到完善建议，已填入基础引导（可直接发送）"
            return gr.update(value={"text": prompt, "files": files}), hint

        return {
            "view": view, "task": area,
            "advice": {"btn": btn_discuss, "inputs": [advice_dd, advice_state], "fn": discuss_prefill},
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
                # 预览加高（preview-tall 覆盖到 480）：右列总高≈可视界面高，与脚本生成页一致；
                # 限高框内滚动；初始值对齐 Dropdown 的自动预选（第一项）
                _point_files = list_choices(config.DIR_TEST_POINTS, (".md",))
                point_preview = gr.Code(
                    value=read_text(_point_files[0][1]) if _point_files else "",
                    label="文档内容预览", language="markdown",
                    interactive=False, wrap_lines=True,
                    elem_classes=["preview-scroll", "preview-tall"],
                )
        bind_task_area(timer, area)

        btn_refresh.click(
            lambda: gr.update(choices=list_choices(config.DIR_TEST_POINTS, (".md",))),
            outputs=[point_md],
        )

        # 选中测试点文档 → 右列预览原文（任务区下方，状态行不被推下去）
        point_md.change(
            lambda p: read_text(p) if p else "", inputs=[point_md],
            outputs=[point_preview], show_progress="hidden",
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
            "### 脚本生成　选择用例 Excel，按编号前缀路由 script-func / script-ui 生成 pytest 脚本。"
        )
        with gr.Row():
            with gr.Column(scale=1):
                xlsx_dd = gr.Dropdown(                      # 第一行：文件选择独占
                    label="测试用例 Excel",
                    choices=list_choices(config.DIR_TEST_CASES, (".xlsx",)),
                    interactive=True,
                )
                with gr.Row():                      # 第二行：解析 + 刷新（同尺寸）
                    btn_parse = gr.Button("解析用例", variant="secondary")
                    btn_refresh = gr.Button("刷新")
                parse_status = gr.Markdown("请先选择用例 Excel，点击「解析用例」后在此勾选")
                with gr.Row():                      # 第三行：数量上限（宽，label 不换行）+ 显示全部（窄，label 换行）
                    limit_num = gr.Number(
                        label="数量上限（留空或 0 = 不限）", value=None, precision=0,
                        minimum=0, maximum=200, scale=2,
                    )
                    show_all_cb = gr.Checkbox(
                        label="显示全部用例（含未标记自动化 / 已生成）", value=False, scale=1,
                    )
                cases_check = gr.CheckboxGroup(
                    label="勾选要生成的用例（编号 ｜ 自动化状态 ｜ 名称）",
                    choices=[], interactive=True,
                    show_select_all=True,           # 原生全选/清空
                    elem_classes=["cases-grid", "cases-placeholder"],  # 两列限高滚动；未解析时保留占位高度（CSS）
                )
                btn_gen = gr.Button("生成自动化脚本", variant="primary")
            with gr.Column(scale=1):
                area = build_task_area()
                # 预览只保留 4 个关键列（编号/优先级/步骤/预期结果）——容器 ~510px 内 7 列必横滚截断，
                # 4 列按内容分配列宽可完整展示；高度与左列「解析后」对齐（实测校准），未解析时由左列占位高度保持齐平
                # gr.DataFrame 传二维列表时首行会被当数据行，列名须拆到 headers 参数（否则表头显示列序号）
                _xlsx_files = list_choices(config.DIR_TEST_CASES, (".xlsx",))
                _data = preview_xlsx(
                    _xlsx_files[0][1], cols=("用例编号", "优先级", "测试步骤", "预期结果"),
                ) if _xlsx_files else [["（暂无用例 Excel）"]]
                _has_header = len(_data) > 1
                xlsx_preview = gr.DataFrame(
                    value=_data[1:] if _has_header else _data,
                    headers=_data[0] if _has_header else None,
                    label="Excel 内容预览（前 30 行 ｜ 编号 / 优先级 / 测试步骤 / 预期结果）", interactive=False,
                    wrap=True, elem_classes=["excel-preview"],   # 固定高度（Gradio 无 height 参数，CSS 控制）；列宽自适应容器
                )
        bind_task_area(timer, area)

        # 选中用例 Excel → 右列预览前 30 行 × 4 关键列（preview_xlsx 自带空路径兜底）
        def _preview_update(p):
            data = preview_xlsx(p, cols=("用例编号", "优先级", "测试步骤", "预期结果"))
            if len(data) > 1:
                return gr.update(value=data[1:], headers=data[0])
            return gr.update(value=data)          # 占位/异常单行：无列名

        xlsx_dd.change(
            _preview_update, inputs=[xlsx_dd], outputs=[xlsx_preview],
            show_progress="hidden",
        )

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
