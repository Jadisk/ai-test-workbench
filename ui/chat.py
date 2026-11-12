# -*- coding: utf-8 -*-
"""主面板（聊天中心）：

- 默认即聊天：调起 claude CLI 多轮流式对话（可附截图、@ 引用文件、/ 与 @ 实时联想）
- / 命令快捷发起 SKILL 任务：聊天流精简展示（不刷工具调用，进度走状态行，完成输出概览）
- stream_chat 为公共生成器，供外部视图（完善 SKILL 讨论）自动发起多轮会话
"""
from __future__ import annotations

import gradio as gr

from .. import chat_log, claude_api, config
from ..jobs import get_job_manager, status_badge
from .common import (
    build_candidates,
    dataset_update,
    detect_trigger,
    event_to_message,
    filter_candidates,
    parse_slash_command,
    replace_trigger,
    resolve_refs,
    save_uploaded_images,
)

CHAT_HEIGHT_DEFAULT = 340


def _session_info_md(session_id: str | None) -> str:
    """会话状态行：仅在已建立多轮会话时显示（初始提示文字按需求去掉）。"""
    if session_id:
        return f"当前会话：{session_id}（多轮连续）"
    return ""


def stream_chat(prompt: str, display_text: str, history: list, session_id: str | None):
    """公共流式聊天生成器：yield (history, active_job_update, session_id, status_md)。

    普通消息与视图联动（完善 SKILL 讨论）共用；工具调用以状态行呈现，不刷进聊天流。
    """
    chat_log.log_turn("user", prompt, session_id)
    history = list(history) + [{"role": "user", "content": display_text}]
    stream = claude_api.ClaudeStream(prompt, resume_session=session_id)
    reply = ""
    history.append({"role": "assistant", "content": ""})
    tool_note = ""
    try:
        for event in stream:
            if event["kind"] == "text":
                reply += event["text"]
                history[-1] = {"role": "assistant", "content": reply or "…"}
                yield history, gr.update(), session_id, tool_note
            elif event["kind"] == "tool":
                detail = f"：{event['detail']}" if event.get("detail") else ""
                tool_note = f"正在调用 {event['name']}{detail}"
                yield history, gr.update(value=None), session_id, tool_note
            elif event["kind"] == "tool_error":
                tool_note = f"⚠ {event.get('name')} 执行出错：{event.get('detail')}"
                yield history, gr.update(value=None), session_id, tool_note
            elif event["kind"] == "result":
                if event.get("text"):
                    reply = event["text"]
                    history[-1] = {"role": "assistant", "content": reply}
                session_id = event.get("session_id") or session_id
                cost = event.get("cost_usd")
                cost_note = f" ｜ 成本 ${cost:.4f}" if isinstance(cost, (int, float)) else ""
                tool_note = ""
                yield history, gr.update(value=None), session_id, f"本轮完成{cost_note}"
            elif event["kind"] == "stderr":
                tool_note = f"{event['line'][:160]}"
                yield history, gr.update(value=None), session_id, tool_note
    finally:
        stream.stop()  # 页面取消/异常时终止进程；正常结束时进程已退出，无副作用

    chat_log.log_turn("assistant", reply, session_id)
    yield history, gr.update(value=None), session_id, _session_info_md(session_id)


def build_chat_panel(timer: gr.Timer, active_job: gr.State) -> tuple[gr.Group, dict]:
    """构建聊天主面板，返回 (面板 Group, 组件引用) 供侧边栏切换与外部联动。"""
    with gr.Group() as panel:
        session_state = gr.State(None)
        cursor_state = gr.State(0)  # 任务事件渲染游标（持久）
        chatbot = gr.Chatbot(
            type="messages",
            height=CHAT_HEIGHT_DEFAULT,
            label="对话",
            show_copy_button=True,
            elem_classes=["chat-resize"],   # CSS resize: vertical 拖动调高
        )
        status = gr.Markdown("", container=True)  # 任务进度/会话状态（初始为空）
        msg = gr.MultimodalTextbox(
            file_types=["image"],
            placeholder="输入消息，可附截图；@文件路径 引用文件（如 @test-points/xxx.md）；/命令 调用 SKILL",
            label="消息",
            lines=2,
        )
        # 实时联想候选区（/ SKILL 命令、@ 文件引用；点击回填输入框）
        # suggest_component 在 Blocks 上下文中创建（初始化完整），事件回调中复用（勿新建）
        suggest_component = gr.Textbox(visible=False)
        suggestions = gr.Dataset(
            components=[suggest_component],
            samples=[],
            label="候选（点击回填）",
            headers=["候选"],
            type="index",
            samples_per_page=8,
            visible=False,
            container=False,
            elem_classes=["suggest-panel"],  # CLI 风格 CSS
        )
        cand_state = gr.State([])   # 当前展示的候选列表
        cand_kind = gr.State("@")   # 当前触发类型（@ 文件 / / 命令）

        # ---------------------------------------------------------------
        # 发送消息：/ 命令 → SKILL 后台任务；普通消息 → 流式聊天
        # ---------------------------------------------------------------
        def on_submit(payload: dict, history: list, session_id: str | None):
            text = (payload.get("text") or "").strip()
            attachments = save_uploaded_images(payload.get("files") or [], config.DIR_CHAT_UPLOADS)
            if not text and not attachments:
                yield history, gr.update(), session_id, "请输入消息或附上截图"
                return

            # 附件以绝对路径提供给模型
            prompt = text
            if attachments:
                file_lines = "\n".join(f"- {p}" for p in attachments)
                prompt = (prompt + "\n\n" if prompt else "") + f"[附件文件]\n{file_lines}"

            # / 命令分流：SKILL 任务走 JobManager（聊天流精简渲染）
            command = parse_slash_command(text)
            if command is not None:
                key, arg = command
                if key == "__unknown__":
                    known = "、".join(f"/{k}" for k in config.SKILLS)
                    yield history, gr.update(), session_id, f"未知命令，可用：{known}"
                    return
                task_prompt = config.build_skill_prompt(key, arg)
                if attachments:
                    task_prompt += "\n\n[附件文件]\n" + "\n".join(attachments)
                try:
                    job = get_job_manager().start_claude(
                        task_prompt, title=f"SKILL·{config.SKILLS[key]['label']}", kind="skill",
                    )
                except RuntimeError as exc:
                    yield history, gr.update(), session_id, f"启动失败：{exc}"
                    return
                history = list(history) + [{"role": "user", "content": text}]
                chat_log.log_turn("user", text, session_id, extra=f"SKILL 任务 {job.id}")
                yield history, job.id, session_id, f"任务已启动：{job.title}（进度见状态行，完成后输出概览）"
                return

            # 普通消息：@ 引用解析 + 多轮流式对话
            display_text = text if text else "（附件）"
            if prompt.strip():
                prompt, refs = resolve_refs(prompt)
                if refs:
                    display_text = text + "\n\n" + "\n".join(f"[引用] {r}" for r in refs)
            yield from stream_chat(prompt, display_text, history, session_id)

        msg.submit(
            on_submit,
            inputs=[msg, chatbot, session_state],
            outputs=[chatbot, active_job, session_state, status],
            show_progress="hidden",
        )
        # 发送后隐藏联想候选（与主流程解耦，避免各分支重复输出）
        msg.submit(
            lambda: gr.update(visible=False),
            inputs=[], outputs=[suggestions], show_progress="hidden", queue=False,
        )

        # ---------------------------------------------------------------
        # 输入实时联想：末尾 @token → 文件候选；行首 /token → SKILL 候选
        # ---------------------------------------------------------------
        def on_input_suggest(payload: dict):
            text = (payload or {}).get("text") or ""
            trig = detect_trigger(text)
            if trig is None:
                return dataset_update(suggest_component, [], "@", False), [], "@"
            kind, query = trig
            cands = filter_candidates(kind, query, build_candidates())
            if not cands:
                return dataset_update(suggest_component, [], kind, False), [], kind
            return dataset_update(suggest_component, cands, kind, True), cands, kind

        # MultimodalTextbox 文本输入只触发 change 事件（input 事件仅文件上传时 dispatch）
        msg.change(
            on_input_suggest,
            inputs=[msg], outputs=[suggestions, cand_state, cand_kind],
            show_progress="hidden", queue=False,
        )

        def pick_suggest(evt: gr.SelectData, payload: dict, cands: list, kind: str):
            idx = evt.index
            if not cands or idx is None or idx >= len(cands):
                return gr.update(), gr.update(visible=False)
            text = (payload or {}).get("text") or ""
            files = (payload or {}).get("files") or []
            new_text = replace_trigger(text, cands[idx]["insert"])
            return (
                gr.update(value={"text": new_text, "files": files}),
                gr.update(visible=False),
            )

        suggestions.select(
            pick_suggest,
            inputs=[msg, cand_state, cand_kind], outputs=[msg, suggestions],
            show_progress="hidden",
        )

        # ---------------------------------------------------------------
        # SKILL 任务精简渲染：工具调用不进聊天流，状态行显示进度，完成输出概览
        # ---------------------------------------------------------------
        def render_task_events(job_id: str, history: list, cursor: int):
            if not job_id:
                return gr.update(), cursor, gr.update(), gr.update()
            job = get_job_manager().get(job_id)
            if job is None:
                return gr.update(), cursor, None, "（任务记录不存在）"
            events = job.events
            new_messages = []
            for ev in events[cursor:]:
                if ev.get("kind") in ("tool", "stderr", "init", "exit"):
                    continue  # 精简模式：过程细节不刷聊天流
                message = event_to_message(ev)
                if message:
                    new_messages.append(message)
            if new_messages:
                history = list(history) + new_messages
            tools = sum(1 for e in events if e.get("kind") == "tool")
            errors = sum(1 for e in events if e.get("kind") == "tool_error")
            note = f"已执行 {tools} 次工具调用" + (f"，⚠ {errors} 次执行出错" if errors else "")
            if job.status != "running":
                return history, len(events), None, f"任务结束（{status_badge(job.status)}）：{job.title} ｜ {note}"
            return history, len(events), gr.update(), f"任务进行中：{job.title} ｜ {note}"

        timer.tick(
            render_task_events,
            inputs=[active_job, chatbot, cursor_state],
            outputs=[chatbot, cursor_state, active_job, status],
            show_progress="hidden",
        )

    return panel, {"chatbot": chatbot, "status": status, "session_state": session_state}
