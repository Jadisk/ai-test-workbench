# -*- coding: utf-8 -*-
"""统一后台任务管理：claude SKILL 任务与 pytest 任务。

设计要点：
- 本地 JSON 落盘（workbench/data/jobs/*.json），无数据库；日志实时写入 data/logs/{id}.log
- 同类任务互斥：claude 任务同时仅 1 个、pytest 任务同时仅 1 个（避免产物目录交叉污染）
- 工作台重启时将残留 running 状态标记为 interrupted（子进程已随退出死亡）
"""
from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import claude_api, config, pytest_api


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


class Job:
    """单个后台任务的运行状态（内存 + JSON 双份）。"""

    def __init__(self, kind: str, title: str, meta: Optional[dict] = None):
        self.id = f"job_{_ts()}_{uuid.uuid4().hex[:6]}"
        self.kind = kind              # claude | pytest
        self.title = title
        self.status = "running"       # running | done | error | stopped | interrupted
        self.created_at = _now()
        self.finished_at: Optional[str] = None
        self.exit_code: Optional[int] = None
        self.result_text: Optional[str] = None
        self.claude_session_id: Optional[str] = None
        self.meta: dict = meta or {}
        # 结构化事件流（仅内存，供聊天主面板渲染工具调用与输出；不落盘）
        self.events: list[dict] = []

    # -- 持久化 --------------------------------------------------------------
    @property
    def json_path(self) -> Path:
        return config.DIR_JOBS / f"{self.id}.json"

    @property
    def log_path(self) -> Path:
        return config.DIR_JOB_LOGS / f"{self.id}.log"

    def save(self) -> None:
        self.json_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "title": self.title,
            "status": self.status, "created_at": self.created_at,
            "finished_at": self.finished_at, "exit_code": self.exit_code,
            "result_text": self.result_text,
            "claude_session_id": self.claude_session_id,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        job = cls.__new__(cls)
        job.id = data["id"]
        job.kind = data.get("kind", "claude")
        job.title = data.get("title", "")
        job.status = data.get("status", "interrupted")
        job.created_at = data.get("created_at", "")
        job.finished_at = data.get("finished_at")
        job.exit_code = data.get("exit_code")
        job.result_text = data.get("result_text")
        job.claude_session_id = data.get("claude_session_id")
        job.meta = data.get("meta") or {}
        return job

    # -- 日志 ----------------------------------------------------------------
    def log(self, line: str) -> None:
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.now().strftime('%H:%M:%S')}] {line}\n")

    def log_event(self, event: dict) -> None:
        """将 claude 流事件写成可读日志行。"""
        kind = event.get("kind")
        if kind == "init":
            self.log(f"[init] 会话启动 model={event.get('model', '?')} session={event.get('session_id')}")
        elif kind == "tool":
            detail = f"：{event['detail']}" if event.get("detail") else ""
            self.log(f"[tool] {event.get('name')}{detail}")
        elif kind == "tool_error":
            self.log(f"[tool_error] {event.get('name')}：{event.get('detail')}")
        elif kind == "text":
            self.log("── assistant ──")
            for text_line in event.get("text", "").splitlines() or [""]:
                self.log(text_line)
        elif kind == "stderr":
            self.log(f"[stderr] {event.get('line', '')}")
        elif kind == "result":
            self.log(f"■ 结果 is_error={event.get('is_error')} cost={event.get('cost_usd')}")
            self.log(event.get("text", ""))


class JobManager:
    """进程级单例。启动 claude / pytest 任务并跟踪其生命周期。"""

    def __init__(self):
        config.DIR_JOBS.mkdir(parents=True, exist_ok=True)
        config.DIR_JOB_LOGS.mkdir(parents=True, exist_ok=True)
        config.DIR_REPORTS.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, Job] = {}
        self._procs: dict[str, object] = {}   # job_id → Popen / ClaudeStream（可 stop）
        self._locks = {"claude": threading.Lock(), "pytest": threading.Lock()}
        self._load_history()

    # -- 历史恢复 --------------------------------------------------------------
    def _load_history(self) -> None:
        for path in sorted(config.DIR_JOBS.glob("*.json")):
            try:
                job = Job.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, KeyError):
                continue
            if job.status == "running":
                job.status = "interrupted"   # 工作台重启，子进程已死
            self._jobs[job.id] = job

    # -- 查询 ------------------------------------------------------------------
    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list(self, kind: Optional[str] = None) -> list[Job]:
        jobs = [j for j in self._jobs.values() if kind is None or j.kind == kind]
        return sorted(jobs, key=lambda j: j.id, reverse=True)  # 新任务在前

    def running(self, kind: Optional[str] = None) -> list[Job]:
        return [j for j in self.list(kind) if j.status == "running"]

    def log_tail(self, job_id: str, lines: int = config.LOG_TAIL_LINES) -> str:
        job = self.get(job_id)
        if job is None or not job.log_path.exists():
            return ""
        text = job.log_path.read_text(encoding="utf-8", errors="replace")
        return "\n".join(text.splitlines()[-lines:])

    # -- 启动任务 --------------------------------------------------------------
    def start_claude(self, prompt: str, title: str, kind: str = "claude") -> Job:
        """启动一个 claude CLI 任务。kind 用于业务区分（claude / analysis / cases / scripts / skill）。"""
        if not self._locks["claude"].acquire(blocking=False):
            busy = self.running("claude")
            raise RuntimeError(f"已有 claude 任务在运行：{busy[0].title if busy else '未知'}，请先等待或停止")
        job = Job(kind=kind, title=title)
        self._register(job)
        threading.Thread(target=self._run_claude, args=(job, prompt), daemon=True).start()
        return job

    def start_pytest(self, targets: list[str], marker: str = "", headed: bool = False,
                     channel: str = "msedge") -> Job:
        """启动一个 pytest 任务（独立于 claude 任务的互斥锁）。"""
        if not self._locks["pytest"].acquire(blocking=False):
            busy = self.running("pytest")
            raise RuntimeError(f"已有 pytest 任务在运行：{busy[0].title if busy else '未知'}，请先等待或停止")
        junitxml = config.DIR_REPORTS / f"junit_{_ts()}_{uuid.uuid4().hex[:6]}.xml"
        job = Job(
            kind="pytest",
            title="pytest " + (" ".join(targets) if targets else "tests/"),
            meta={
                "targets": targets, "marker": marker, "headed": headed, "channel": channel,
                "junitxml": str(junitxml),
            },
        )
        self._register(job)
        threading.Thread(target=self._run_pytest, args=(job,), daemon=True).start()
        return job

    def _register(self, job: Job) -> None:
        self._jobs[job.id] = job
        job.save()

    # -- claude 任务线程 ---------------------------------------------------------
    def _run_claude(self, job: Job, prompt: str) -> None:
        stream = claude_api.ClaudeStream(prompt)
        self._procs[job.id] = stream
        try:
            job.log(f"启动 claude 任务：{job.title}")
            for event in stream:
                job.events.append(event)
                job.log_event(event)
                if event["kind"] == "result":
                    job.result_text = event.get("text") or ""
                    job.claude_session_id = event.get("session_id")
                    job.save()
            # Popen 的退出码属性是 returncode（不是 exitcode）
            job.exit_code = stream.proc.returncode if stream.proc else None
            if job.result_text is None:
                job.status = "error"
            elif job.exit_code not in (0, None):
                job.status = "error"
            else:
                job.status = "done"
            job.log(f"任务结束 status={job.status} exit={job.exit_code}")
        except Exception as exc:  # 防御：日志线程异常不应悬死任务状态
            job.status = "error"
            job.log(f"任务异常：{exc}")
        finally:
            job.finished_at = _now()
            job.save()
            self._procs.pop(job.id, None)
            self._locks["claude"].release()

    # -- pytest 任务线程 ----------------------------------------------------------
    def _run_pytest(self, job: Job) -> None:
        try:
            cmd = pytest_api.build_pytest_cmd(
                targets=job.meta["targets"],
                marker=job.meta.get("marker", ""),
                headed=job.meta.get("headed", False),
                channel=job.meta.get("channel", "msedge"),
                junitxml=Path(job.meta["junitxml"]),
            )
            job.log("启动 pytest：" + " ".join(cmd))
            proc_holder: dict = {}
            self._procs[job.id] = proc_holder

            def on_line(line: str) -> None:
                job.log(line)

            # 先起进程再循环读（run_pytest_stream 内部持有 proc，这里仅记录以便停止）
            job.exit_code = pytest_api.run_pytest_stream(cmd, on_line)
            proc_holder.clear()

            summary = pytest_api.parse_junitxml(Path(job.meta["junitxml"]))
            job.meta["summary"] = summary
            job.status = "done" if job.exit_code in (0, 1) else "error"
            # 退出码 0=全过 1=有用例失败（属正常完成）；2+=收集/中断错误
            job.log(
                f"任务结束 status={job.status} exit={job.exit_code} "
                f"通过 {summary['passed']} / 失败 {summary['failed']} / "
                f"错误 {summary['error']} / 跳过 {summary['skipped']}"
            )
        except Exception as exc:
            job.status = "error"
            job.log(f"任务异常：{exc}")
        finally:
            job.finished_at = _now()
            # 运行结果落盘 results/（项目约定目录）：完整输出 + 摘要 JSON
            try:
                config.DIR_RESULTS.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(job.log_path, config.DIR_RESULTS / f"{job.id}_pytest_console.log")
                summary_snapshot = job.meta.get("summary") or {}
                (config.DIR_RESULTS / f"{job.id}_pytest_summary.json").write_text(
                    json.dumps(
                        {"job": job.to_dict(), "summary": summary_snapshot},
                        ensure_ascii=False, indent=2,
                    ),
                    encoding="utf-8",
                )
            except OSError as exc:
                job.log(f"运行结果落盘 results/ 失败：{exc}")
            job.save()
            self._procs.pop(job.id, None)
            self._locks["pytest"].release()

    # -- 停止 -----------------------------------------------------------------
    def stop(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None or job.status != "running":
            return False
        holder = self._procs.get(job_id)
        if isinstance(holder, claude_api.ClaudeStream):
            holder.stop()
        elif isinstance(holder, dict) and "proc" in holder:
            claude_api.kill_process_tree(holder["proc"].pid)
        job.log("⚠ 收到停止指令")
        return True


# 模块级单例（Gradio 各 Tab 与 FastAPI 路由共用）
_manager: Optional[JobManager] = None
_manager_lock = threading.Lock()


def get_job_manager() -> JobManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = JobManager()
    return _manager


def format_summary_md(summary: dict) -> str:
    """junitxml 摘要 → 统计 Markdown。"""
    if not summary or not summary.get("total"):
        return "暂无结果数据"
    total = summary["total"]
    passed, failed = summary["passed"], summary["failed"]
    error, skipped = summary["error"], summary["skipped"]
    rate = f"{passed / total * 100:.0f}%" if total else "-"
    return (
        f"**总计 {total}** ｜ 通过 **{passed}** ｜ 失败 **{failed}** ｜ "
        f"错误 **{error}** ｜ 跳过 **{skipped}** ｜ "
        f"通过率 **{rate}** ｜ 耗时 **{summary.get('duration', 0)}s**"
    )


def status_badge(status: str) -> str:
    """任务状态 → 中文文案。"""
    mapping = {
        "running": "运行中",
        "done": "完成",
        "error": "出错",
        "stopped": "已停止",
        "interrupted": "已中断",
    }
    return mapping.get(status, status)


def utc_now_iso() -> str:
    """兼容保留：返回当前时间戳（ISO）。"""
    return time.strftime("%Y-%m-%dT%H:%M:%S")
