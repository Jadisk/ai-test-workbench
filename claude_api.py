# -*- coding: utf-8 -*-
"""claude CLI 封装：headless 调用 + stream-json 事件流解析。

模型调用复用现有 Claude Code CLI / GLM 配置：
- 子进程继承用户级 settings.json 的环境变量（ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN 等），
  本模块不读取、不落盘任何 token；
- 权限策略由 config.CLAUDE_PERMISSION_MODE 控制（默认 bypassPermissions，SKILL 任务全自动）。
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Iterator, Optional

from . import config


def build_claude_cmd(prompt: str, resume_session: Optional[str] = None) -> list[str]:
    """构建 claude headless 命令。

    stream-json 输出逐行 JSON 事件（init / assistant / result），支持 --resume 多轮会话。
    """
    cmd = [
        config.resolve_claude_exe(),
        "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",  # headless 下使用 stream-json 必须带 --verbose
        "--permission-mode", config.CLAUDE_PERMISSION_MODE,
    ]
    if resume_session:
        cmd += ["--resume", resume_session]
    return cmd


def kill_process_tree(pid: int) -> None:
    """Windows 下强杀整个进程树（claude CLI 可能是 cmd → node 的父子链）。"""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        import signal
        os.kill(pid, signal.SIGTERM)


def _tool_detail(block: dict) -> str:
    """从 tool_use 块提取一行可读摘要（文件路径 / 命令 / 目标等关键信息）。"""
    payload = block.get("input") or {}
    for key in ("file_path", "path", "command", "url", "pattern", "description", "prompt", "query"):
        value = payload.get(key)
        if value:
            text = str(value).replace("\n", " ")
            return text[:160] + ("…" if len(text) > 160 else "")
    return ""


def _tool_error_summary(block: dict, limit: int = 200) -> str:
    """从 tool_result 错误块提取摘要文本（content 可能是 str 或 text 块列表）。"""
    content = block.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "\n".join(
            part.get("text", "") for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    else:
        text = ""
    text = text.strip().replace("\n", " ")
    if not text:
        text = "（工具执行出错，无错误详情）"
    return text[:limit] + ("…" if len(text) > limit else "")


class ClaudeStream:
    """一次 claude -p 调用的事件流。

    用法::

        stream = ClaudeStream(prompt, resume="session-id")
        for ev in stream:            # 惰性启动子进程并逐事件迭代
            ...
        stream.stop()                # 可选：中途终止（聊天取消 / 停止按钮）

    事件形态（已归一化）::

        {"kind": "init",   "session_id": str, "model": str}
        {"kind": "text",   "text": str}                        # assistant 文本片段
        {"kind": "tool",   "name": str, "detail": str}         # 工具调用摘要
        {"kind": "tool_error", "name": str, "detail": str}     # 工具执行出错（权限拒绝等）
        {"kind": "result", "text": str, "session_id": str,
         "is_error": bool, "cost_usd": float | None}           # 最终结果
        {"kind": "exit",   "code": int | None}                 # 进程退出
        {"kind": "stderr", "line": str}                        # 非 JSON 输出（警告等）
    """

    def __init__(self, prompt: str, resume_session: Optional[str] = None):
        self.prompt = prompt
        self.resume_session = resume_session
        self.session_id: Optional[str] = None
        self.proc: Optional[subprocess.Popen] = None
        self._stderr: Optional[_DrainThread] = None  # stderr 排空线程（stderr_lines() 取排查内容）
        self._pending_tools: dict[str, str] = {}  # tool_use_id → 工具名（用于匹配 tool_result）

    def __iter__(self) -> Iterator[dict]:
        if self.proc is not None:
            raise RuntimeError("ClaudeStream 不可重复迭代，请重新创建实例")
        cmd = build_claude_cmd(self.prompt, self.resume_session)
        try:
            self.proc = subprocess.Popen(
                cmd,
                cwd=str(config.PROJECT_ROOT),
                stdin=subprocess.DEVNULL,  # 不继承父进程句柄：windowed exe 下继承到的可能是无效句柄
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,  # 由守护线程排空，避免管道塞满死锁
                text=True,
                encoding="utf-8",
                errors="replace",
                env=dict(os.environ),  # 继承用户级 GLM 配置
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
        except FileNotFoundError as exc:
            yield {"kind": "stderr", "line": f"启动 claude CLI 失败：{exc}"}
            yield {"kind": "exit", "code": -1}
            return

        stderr_thread = _DrainThread(self.proc.stderr)
        self._stderr = stderr_thread  # 暴露给 stderr_lines()：任务异常时落日志排查
        stderr_thread.start()
        try:
            yield from self._iter_events()
        finally:
            code = self.proc.wait()
            stderr_thread.join(timeout=2)
            yield {"kind": "exit", "code": code}

    def _iter_events(self) -> Iterator[dict]:
        assert self.proc and self.proc.stdout
        for raw_line in self.proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            if not line.startswith("{"):
                # stream-json 模式下的非 JSON 行（版本警告等），透传便于排查
                yield {"kind": "stderr", "line": line}
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                yield {"kind": "stderr", "line": line[:200]}
                continue

            ev_type = event.get("type")
            if ev_type == "system" and event.get("subtype") == "init":
                self.session_id = event.get("session_id") or self.session_id
                yield {
                    "kind": "init",
                    "session_id": self.session_id,
                    "model": event.get("model", ""),
                }
            elif ev_type == "assistant":
                for block in (event.get("message") or {}).get("content") or []:
                    btype = block.get("type")
                    if btype == "text" and (block.get("text") or "").strip():
                        yield {"kind": "text", "text": block["text"]}
                    elif btype == "tool_use":
                        self._pending_tools[block.get("id", "")] = block.get("name", "?")
                        yield {
                            "kind": "tool",
                            "name": block.get("name", "?"),
                            "detail": _tool_detail(block),
                        }
            elif ev_type == "user":
                # 工具执行结果：仅提取出错项（权限拒绝、文件不存在等），用于任务区/日志展示
                for block in (event.get("message") or {}).get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                        yield {
                            "kind": "tool_error",
                            "name": self._pending_tools.get(block.get("tool_use_id", ""), "?"),
                            "detail": _tool_error_summary(block),
                        }
            elif ev_type == "result":
                self.session_id = event.get("session_id") or self.session_id
                yield {
                    "kind": "result",
                    "text": event.get("result") or "",
                    "session_id": self.session_id,
                    "is_error": bool(event.get("is_error", False)),
                    "cost_usd": event.get("total_cost_usd"),
                }
                return  # result 是终止事件，后续交给 exit

    def stop(self) -> None:
        """终止子进程树（幂等）。"""
        proc = self.proc
        if proc is not None and proc.poll() is None:
            kill_process_tree(proc.pid)

    def stderr_lines(self) -> list[str]:
        """子进程 stderr 已收集的行（最多 50 行，任务结束/异常时落日志用于排查）。"""
        return list(self._stderr.lines) if self._stderr is not None else []


class _DrainThread:
    """排空 stderr 管道的守护线程（收集少量行用于错误排查）。"""

    def __init__(self, pipe):
        self.pipe = pipe
        self.lines: list[str] = []
        self.thread = None

    def start(self) -> None:
        import threading
        self.thread = threading.Thread(target=self._drain, daemon=True)
        self.thread.start()

    def _drain(self) -> None:
        try:
            for line in self.pipe:
                line = line.strip()
                if line and len(self.lines) < 50:
                    self.lines.append(line)
        except Exception:
            pass  # 进程退出导致的管道关闭属正常情况

    def join(self, timeout: float = 2.0) -> None:
        if self.thread is not None:
            self.thread.join(timeout=timeout)
