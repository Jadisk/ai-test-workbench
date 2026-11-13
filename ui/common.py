# -*- coding: utf-8 -*-
"""UI 公共工具：文件列表、xlsx 解析/预览、@引用解析、任务轮询。"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import gradio as gr

from .. import config
from ..jobs import JobManager, get_job_manager, status_badge


def list_files(directory: Path, exts: tuple[str, ...]) -> list[str]:
    """目录下指定扩展名文件（新文件在前），返回绝对路径列表。"""
    if not directory.exists():
        return []
    files = [p for p in directory.iterdir() if p.suffix.lower() in exts and p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [str(p) for p in files]


def list_choices(directory: Path, exts: tuple[str, ...]) -> list[tuple[str, str]]:
    """目录文件 → 下拉选项 [(显示名, 绝对路径)]，新文件在前。"""
    return [(Path(p).name, p) for p in list_files(directory, exts)]


def dropdown_update(directory: Path, exts: tuple[str, ...]) -> gr.update:
    """产物下拉刷新（只更新 choices，不覆盖用户当前选择）。"""
    return gr.update(choices=list_choices(directory, exts))


def read_text(path: str | Path, max_chars: int = 80_000) -> str:
    """读取文本文件（utf-8 容错），超长截断。"""
    p = Path(path)
    if not p.exists():
        return f"（文件不存在：{p}）"
    text = p.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n…（内容过长已截断）"
    return text


def preview_xlsx(
    path: str, max_rows: int = 30, max_cols: int | None = None,
    cols: tuple[str, ...] | None = None,
) -> list[list]:
    """xlsx 首个 Sheet 前 N 行 → 二维列表（gr.DataFrame 直接可用）。

    cols：按首行表头名保留指定列，输出列序跟随 cols 给定顺序（一个未命中则不筛、返回全列）；
    max_cols：按位置裁剪前 N 列。cols 与 max_cols 同传时 cols 优先。
    """
    if not path:
        return [["（请先选择文件）"]]
    try:
        from openpyxl import load_workbook
        workbook = load_workbook(path, read_only=True, data_only=True)
        sheet = workbook[workbook.sheetnames[0]]
        rows: list[list] = []
        for row in sheet.iter_rows(values_only=True):
            rows.append(["" if cell is None else str(cell) for cell in row])
            if len(rows) >= max_rows + 1:
                break
        workbook.close()
        if not rows:
            return [["（空表格）"]]
        header = rows[0]
        body = rows[1:]
        if cols:
            # 按表头名取各列位置（保持 cols 顺序）；全部未命中则不筛列（非标准 Excel 显示原貌）
            index = [header.index(name) if name in header else -1 for name in cols]
            if any(i >= 0 for i in index):
                width = len(index)
                header = [header[i] if i >= 0 else "" for i in index]
                body = [[(r[i] if 0 <= i < len(r) else "") for i in index] for r in body]
                return [header] + [(r + [""] * width)[:width] for r in body]
        elif max_cols:
            header = header[:max_cols]
            body = [r[:max_cols] for r in body]
        width = len(header)
        return [header] + [(r + [""] * width)[:width] for r in body]
    except Exception as exc:
        return [[f"读取失败：{exc}"]]


def parse_excel_cases(path: str) -> list[dict]:
    """解析用例 Excel：遍历所有含「用例编号 + 自动化状态」列的 Sheet，提取用例信息。

    探索性 Charter Sheet（无自动化状态列）自动跳过。
    返回 [{"id", "name", "auto", "priority", "sheet"}]
    """
    from openpyxl import load_workbook
    workbook = load_workbook(path, read_only=True, data_only=True)
    cases: list[dict] = []
    for sheet_name in workbook.sheetnames:
        sheet = workbook[sheet_name]
        rows = sheet.iter_rows(values_only=True)
        header = [str(c).strip() if c is not None else "" for c in (next(rows, None) or [])]
        if "用例编号" not in header or "自动化状态" not in header:
            continue
        col = {name: header.index(name) for name in ("用例编号", "用例名称", "自动化状态", "优先级", "所属模块")}
        for row in rows:
            values = {k: (row[i] if i < len(row) else None) for k, i in col.items()}
            case_id = str(values["用例编号"] or "").strip()
            if not case_id:
                continue
            cases.append({
                "id": case_id,
                "name": str(values["用例名称"] or "").strip(),
                "auto": str(values["自动化状态"] or "").strip(),
                "priority": str(values["优先级"] or "").strip(),
                "module": str(values["所属模块"] or "").strip(),
                "sheet": sheet_name,
            })
    workbook.close()
    return cases


def generated_case_ids() -> set[str]:
    """扫描 tests/ 目录，返回已生成脚本的用例编号集合（test_{编号}.py）。"""
    ids: set[str] = set()
    if not config.DIR_TESTS.exists():
        return ids
    for p in config.DIR_TESTS.glob("test_*.py"):
        ids.add(p.stem[5:])  # 去掉 test_ 前缀
    return ids


def list_test_choices() -> list[tuple[str, str]]:
    """tests/ 下测试脚本下拉选项：仅 test_*.py（排除 conftest.py / __init__.py 等）。"""
    return [
        (Path(p).name, p) for p in list_files(config.DIR_TESTS, (".py",))
        if Path(p).name.startswith("test_")
    ]


# ---------------------------------------------------------------------------
# 聊天输入处理：/SKILL 命令 与 @文件引用
# ---------------------------------------------------------------------------
_REF_RE = re.compile(r"@([^\s@，。,；;：:]+)")


def parse_slash_command(text: str):
    """解析 /SKILL 命令。返回 (skill_key, 参数文本) 或 None；未知命令返回 ("__unknown__", 提示)。"""
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    parts = stripped[1:].split(None, 1)
    if not parts or parts[0] not in config.SKILLS:
        return ("__unknown__", stripped)
    return (parts[0], parts[1].strip() if len(parts) > 1 else "")


def resolve_refs(text: str) -> tuple[str, list[str]]:
    """解析消息中的 @文件引用：相对路径基于项目根，存在的路径展开为绝对路径清单附于消息尾部。"""
    refs: list[str] = []

    def _sub(match: re.Match) -> str:
        token = match.group(1)
        p = Path(token)
        if not p.is_absolute():
            p = config.PROJECT_ROOT / token
        if p.exists():
            refs.append(str(p.resolve()))
            return f"`{token}`"
        return match.group(0)  # 不存在的引用原样保留

    new_text = _REF_RE.sub(_sub, text)
    if refs:
        new_text += "\n\n[引用文件（绝对路径）]\n" + "\n".join(refs)
    return new_text, refs


def save_uploaded_images(paths: list[str], target_dir: Path) -> list[str]:
    """把 Gradio 缓存中的上传图片复制到目标目录（重名加时间戳），返回目标绝对路径列表。"""
    from datetime import datetime

    target_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for src in paths or []:
        src_path = Path(src)
        if not src_path.exists():
            continue
        dest = target_dir / src_path.name
        if dest.exists():
            stamp = datetime.now().strftime("%H%M%S")
            dest = target_dir / f"{src_path.stem}_{stamp}{src_path.suffix}"
        dest.write_bytes(src_path.read_bytes())
        saved.append(str(dest))
    return saved


def poll_job(job_id: str) -> dict:
    """查询任务状态（供轮询使用）。"""
    manager = get_job_manager()
    if not job_id:
        return {"status_md": "", "log": "", "done": False, "job": None}
    job = manager.get(job_id)
    if job is None:
        return {"status_md": "（任务记录不存在）", "log": "", "done": True, "job": None}
    return {
        "status_md": (
            f"**{job.title}** ｜ {status_badge(job.status)} ｜ "
            f"开始 {job.created_at} ｜ 结束 {job.finished_at or '—'}"
        ),
        "log": manager.log_tail(job_id),
        "done": job.status != "running",
        "job": job,
    }


def poll_status_md(job_id: str) -> str:
    """仅取任务状态 Markdown（停止按钮等轻量场景）。"""
    return poll_job(job_id)["status_md"]


def make_poll_outputs(job_id_state, status_md, log_component, extra_fn: Optional[callable] = None):
    """构造标准轮询回调（状态 + 日志 + 可选扩展输出）。

    extra_fn(job) 每次 tick 都会调用（job 可能为 None），返回单个 gr.update
    或多个值的元组（对应额外输出组件），保证输出数量与组件数一致。
    """
    def tick(job_id: str):
        info = poll_job(job_id)
        outputs = [info["status_md"], info["log"]]
        if extra_fn is not None:
            result = extra_fn(info["job"])
            if isinstance(result, tuple):
                outputs.extend(result)
            else:
                outputs.append(result)
        return tuple(outputs)

    return tick


def event_to_message(event: dict) -> Optional[dict]:
    """claude 任务事件 → 聊天消息（Claude Code CLI 风格：工具调用一行、输出分段）。"""
    kind = event.get("kind")
    if kind == "tool":
        detail = f"：{event['detail']}" if event.get("detail") else ""
        return {"role": "assistant", "content": f"[工具] {event.get('name')}{detail}"}
    if kind == "tool_error":
        return {"role": "assistant", "content": f"[被拒绝] {event.get('name')}：{event.get('detail')}"}
    if kind == "text":
        return {"role": "assistant", "content": event.get("text", "")}
    if kind == "result":
        return {"role": "assistant", "content": f"[任务输出]\n\n{event.get('text', '')}"}
    if kind == "stderr":
        return {"role": "assistant", "content": f"[stderr] {event.get('line', '')[:200]}"}
    return None  # init / exit 不渲染


# ---------------------------------------------------------------------------
# 页签内嵌任务区：状态行 + 精简过程 + 结果概览
# ---------------------------------------------------------------------------
def compact_progress_md(events: list[dict], recent: int = 5) -> str:
    """任务事件流 → 精简过程 Markdown（工具调用计数 + 最近 N 条摘要 + 出错项）。"""
    tools = [e for e in events if e.get("kind") == "tool"]
    errors = [e for e in events if e.get("kind") == "tool_error"]
    if not events:
        return "等待事件流…"
    head = f"已执行 {len(tools)} 次工具调用"
    if errors:
        head += f"，⚠ {len(errors)} 次执行出错"
    lines = [head]
    for e in tools[-recent:]:
        detail = f"：{e['detail']}" if e.get("detail") else ""
        lines.append(f"- {e.get('name')}{detail}")
    for e in errors[-3:]:
        lines.append(f"- ⚠ [{e.get('name')}] {e.get('detail')}")
    return "\n".join(lines)


def build_task_area() -> dict:
    """在当前 Gradio 上下文中创建任务区组件，返回组件引用（需 bind_task_area 绑定轮询）。"""
    with gr.Group(elem_classes=["task-area"]):
        gr.Markdown("#### 任务执行（过程与结果在本页签展示）")
        status_md = gr.Markdown("本页签暂无任务")
        progress_md = gr.Markdown("")
        result_md = gr.Markdown("", elem_classes=["task-result"])
        stop_btn = gr.Button("停止任务", variant="stop", size="sm")
        job_id = gr.State(None)
    return {"job_id": job_id, "status_md": status_md, "progress_md": progress_md,
            "result_md": result_md, "stop_btn": stop_btn}


def bind_task_area(timer: gr.Timer, area: dict) -> None:
    """绑定任务区轮询：每 tick 刷新状态/精简过程/结果概览；无本页签任务时提示全局运行中任务。"""
    def tick(job_id: str):
        info = poll_job(job_id)
        job = info["job"]
        if job is None:
            running = get_job_manager().running()
            hint = f" ｜ 全局运行中：{running[0].title}" if running else ""
            return f"本页签暂无任务{hint}", "", ""
        progress = compact_progress_md(job.events) if job.status == "running" else ""
        if job.status == "running":
            result = "（任务执行中，结束后在此展示结果概览）"
        elif job.status == "stopped":
            result = "（任务已手动停止，未产出结果）"
        else:
            result = job.result_text or "（无结果文本）"
        return info["status_md"], progress, result

    timer.tick(tick, inputs=[area["job_id"]],
               outputs=[area["status_md"], area["progress_md"], area["result_md"]],
               show_progress="hidden")
    area["stop_btn"].click(
        lambda jid: get_job_manager().stop(jid or ""),
        inputs=[area["job_id"]], outputs=[], show_progress="hidden",
    )


# ---------------------------------------------------------------------------
# 聊天输入实时联想：/ SKILL 命令 与 @ 文件引用
# ---------------------------------------------------------------------------
# @ 文件引用：token 前为行首或空白，且位于末行末尾（未输完）
_AT_RE = re.compile(r"(?:^|\s)@([^\s@，。,；;：:]*)$")
# / SKILL 命令：仅行首触发（参数输入后不再联想）
_SLASH_RE = re.compile(r"^/([^\s/]*)$")

# @ 候选文件来源：项目根全扫描（os.walk 剪枝排除依赖/构建/缓存目录）
_SUGGEST_EXCLUDE_DIRS = {
    "node_modules", ".venv", ".git", ".idea", ".pytest_cache", ".tmp",
    "__pycache__", "build", "dist", "data",
}
# 白名单扩展名（业务产物 + 常见文本配置，避免扫到二进制杂项）
_SUGGEST_EXTS = (".md", ".py", ".xlsx", ".png", ".jpg", ".json", ".txt",
                 ".ini", ".yaml", ".yml", ".toml", ".log", ".csv")
# 扫描结果缓存秒数：逐字符输入都触发联想，避免反复全盘 walk
_SUGGEST_TTL_SEC = 30.0
_cand_cache: dict = {"files": None, "ts": 0.0}


def _scan_project_files() -> list[str]:
    """项目根扫描（剪枝排除目录），返回白名单扩展名的绝对路径（新文件在前）。"""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(config.PROJECT_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SUGGEST_EXCLUDE_DIRS]
        for name in filenames:
            if Path(name).suffix.lower() in _SUGGEST_EXTS:
                out.append(os.path.join(dirpath, name))
    out.sort(key=lambda p: Path(p).stat().st_mtime, reverse=True)
    return out


def build_candidates() -> list[dict]:
    """构建联想候选：项目根文件（@相对路径）+ SKILL 命令。文件列表带 TTL 缓存。"""
    import time

    now = time.monotonic()
    if _cand_cache["files"] is None or now - _cand_cache["ts"] > _SUGGEST_TTL_SEC:
        _cand_cache["files"] = _scan_project_files()
        _cand_cache["ts"] = now
    cands: list[dict] = []
    for p in _cand_cache["files"]:
        rel = Path(p).resolve().relative_to(config.PROJECT_ROOT).as_posix()
        cands.append({"token": rel, "insert": f"@{rel} ", "kind": "file"})
    for key, info in config.SKILLS.items():
        cands.append({"token": key, "insert": f"/{key} ", "kind": "skill",
                      "label_extra": info["label"]})
    return cands


def detect_trigger(text: str) -> Optional[tuple[str, str]]:
    """检测末行末尾的联想触发。返回 ("@", query) / ("/", query) 或 None。"""
    if not text:
        return None
    last = text.splitlines()[-1]
    m = _AT_RE.search(last)
    if m:
        return ("@", m.group(1))
    m = _SLASH_RE.match(last)
    if m:
        return ("/", m.group(1))
    return None


def filter_candidates(kind: str, query: str, cands: list[dict], limit: int = 8) -> list[dict]:
    """按触发类型与输入过滤候选：/ 仅 SKILL，@ 仅文件。

    排序：token 前缀命中优先，其余保持池内顺序（文件已按 mtime 新→旧）。
    """
    q = query.lower()
    want = "skill" if kind == "/" else "file"
    pool = [c for c in cands if c["kind"] == want]
    matched = [(not c["token"].lower().startswith(q), c) for c in pool if q in c["token"].lower()]
    matched.sort(key=lambda pair: pair[0])  # 稳定排序，保持池内 mtime 顺序
    return [c for _, c in matched[:limit]]


def suggest_label(kind: str, cand: dict) -> str:
    """候选 → 展示文本。"""
    if kind == "/":
        extra = cand.get("label_extra", "")
        return f"/{cand['token']}　{extra}" if extra else f"/{cand['token']}"
    return f"@{cand['token']}"


def dataset_update(component, cands: list[dict], kind: str, visible: bool) -> gr.Dataset:
    """联想候选 → 新 Dataset 实例（Gradio 要求 Dataset 更新必须整体重建，不能 gr.update）。

    component 必须传入 Blocks 上下文中已初始化的组件实例：事件监听器执行期间
    新建组件会因 Gradio updateable 机制跳过父类 __init__（proxy_url 缺失报错）。
    """
    return gr.Dataset(
        components=[component],
        samples=[[suggest_label(kind, c)] for c in cands],
        label="候选（点击回填）",
        headers=["候选"],
        type="index",
        samples_per_page=8,
        visible=visible,
    )


def replace_trigger(text: str, insert: str) -> str:
    """把输入末尾的触发 token（@xx / /xx）替换为完整插入文本。"""
    lines = text.splitlines()
    last = lines[-1] if lines else ""
    for pattern in (_AT_RE, _SLASH_RE):
        m = pattern.search(last)
        if m:
            new_last = last[:m.start()] + insert
            return "\n".join(lines[:-1] + [new_last]) if lines else insert
    return text


__all__ = [
    "list_files", "list_choices", "dropdown_update", "read_text", "preview_xlsx",
    "parse_excel_cases", "generated_case_ids", "list_test_choices",
    "parse_slash_command", "resolve_refs", "save_uploaded_images",
    "poll_job", "poll_status_md", "make_poll_outputs", "event_to_message",
    "compact_progress_md", "build_task_area", "bind_task_area",
    "build_candidates", "detect_trigger", "filter_candidates", "dataset_update",
    "replace_trigger", "JobManager",
]
