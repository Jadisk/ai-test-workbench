# -*- coding: utf-8 -*-
"""FastAPI JSON 路由：任务查询/停止、产物文件列表、项目上下文。

Gradio UI 直接同进程调用 Python 函数；本路由层供外部脚本 / 后续扩展使用。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from . import config
from .jobs import get_job_manager, status_badge

router = APIRouter(prefix="/api", tags=["workbench"])


@router.get("/jobs")
def list_jobs(kind: str | None = None):
    """任务列表（新任务在前）。kind 可选：claude | pytest。"""
    jobs = get_job_manager().list(kind)
    return [
        {**j.to_dict(), "status_badge": status_badge(j.status)}
        for j in jobs
    ]


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = get_job_manager().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    tail = get_job_manager().log_tail(job_id, lines=100)
    return {**job.to_dict(), "status_badge": status_badge(job.status), "log_tail": tail}


@router.post("/jobs/{job_id}/stop")
def stop_job(job_id: str):
    ok = get_job_manager().stop(job_id)
    if not ok:
        raise HTTPException(status_code=409, detail="任务不存在或已结束")
    return {"ok": True}


# 文件类目 → 目录 + 扩展名（kind 即 URL 路径段）
_FILE_KINDS: dict[str, tuple[Path, tuple[str, ...]]] = {
    "test-points": (config.DIR_TEST_POINTS, (".md",)),
    "test-cases": (config.DIR_TEST_CASES, (".xlsx",)),
    "tests": (config.DIR_TESTS, (".py",)),
    "pages": (config.DIR_PAGES, (".py",)),
    "results": (config.DIR_RESULTS, (".log",)),
    "failures": (config.DIR_SHOT_FAILURES, (".png", ".jpg")),
}


@router.get("/files/{kind}")
def list_files(kind: str):
    """列出某类产物文件（新文件在前），路径相对项目根。"""
    if kind not in _FILE_KINDS:
        raise HTTPException(status_code=404, detail=f"未知文件类目：{kind}")
    directory, exts = _FILE_KINDS[kind]
    if not directory.exists():
        return []
    files = [p for p in directory.iterdir() if p.suffix.lower() in exts and p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": p.name, "path": str(p.relative_to(config.PROJECT_ROOT))} for p in files]


@router.get("/context")
def project_context():
    """项目上下文摘要（CLAUDE.md 状态、目录存在性、任务统计）。"""
    manager = get_job_manager()
    jobs = manager.list()
    return {
        "project_root": str(config.PROJECT_ROOT),
        "claude_md_exists": config.FILE_CLAUDE_MD.exists(),
        "pytest_python_exists": config.PYTEST_PYTHON.exists(),
        "claude_exe": config.resolve_claude_exe(),
        "permission_mode": config.CLAUDE_PERMISSION_MODE,
        "dirs": {
            name: str(path) for name, path in {
                "test-points": config.DIR_TEST_POINTS,
                "test-cases": config.DIR_TEST_CASES,
                "tests": config.DIR_TESTS,
                "pages": config.DIR_PAGES,
                "results": config.DIR_RESULTS,
                "failures": config.DIR_SHOT_FAILURES,
            }.items()
        },
        "jobs_total": len(jobs),
        "jobs_running": len(manager.running()),
    }
