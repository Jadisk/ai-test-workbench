# -*- coding: utf-8 -*-
"""pytest 子进程封装：命令构建、实时日志、junitxml 结果解析。

通过 subprocess 调用项目虚拟环境中的 pytest（CLAUDE.md 约定的运行方式），
附加 --junitxml 生成结构化报告，供「脚本运行 / 结果与报告」Tab 展示。
"""
from __future__ import annotations

import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, Optional

from . import config

# Windows 下子进程 stdout 重定向到管道时默认用本地编码（GBK），
# 必须强制 utf-8 + 无缓冲，否则中文断言消息乱码、日志迟迟不刷新。
_CHILD_ENV = {
    **os.environ,
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUNBUFFERED": "1",
}


def build_pytest_cmd(
    targets: list[str],
    marker: str = "",
    headed: bool = False,
    channel: str = "msedge",
    junitxml: Optional[Path] = None,
) -> list[str]:
    """构建 pytest 命令。

    - channel 默认 msedge（与 conftest.py / corebrowser.py 一致；chromium 需 ms-playwright 缓存）
    - -u 关闭输出缓冲，保证日志实时落盘
    """
    if junitxml is None:
        junitxml = config.DIR_REPORTS / "latest.xml"
    cmd = [
        str(config.PYTEST_PYTHON),
        "-u",
        "-m", "pytest",
        *targets,
        "-v",
        "--tb=short",
        f"--junitxml={junitxml}",
        f"--browser-channel={channel}",
    ]
    if marker:
        cmd.append(f"-m={marker}")
    if headed:
        cmd.append("--headed")
    return cmd


def run_pytest_stream(cmd: list[str], on_line: Optional[Callable[[str], None]] = None) -> int:
    """运行 pytest 子进程，逐行回调输出，返回退出码。

    调用方（JobManager）在 on_line 中写入任务日志；进程树的终止由 JobManager 负责。
    """
    proc = subprocess.Popen(
        cmd,
        cwd=str(config.PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_CHILD_ENV,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line.strip():
                if on_line:
                    on_line(line)
    finally:
        code = proc.wait()
    return code


def parse_junitxml(path: Path) -> dict:
    """解析 junitxml 为结果摘要。

    返回::

        {
          "total": int, "passed": int, "failed": int,
          "error": int, "skipped": int, "duration": float,
          "cases": [ {"nodeid": str, "status": str, "time": float, "message": str | None} ]
        }
    """
    summary = {
        "total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0,
        "duration": 0.0, "cases": [],
    }
    if not path.exists() or path.stat().st_size == 0:
        return summary
    try:
        root = ET.parse(str(path)).getroot()
    except ET.ParseError:
        return summary

    suite = root.find("testsuite")
    if suite is None:
        return summary
    summary["total"] = int(suite.get("tests", 0) or 0)
    summary["failed"] = int(suite.get("failures", 0) or 0)
    summary["error"] = int(suite.get("errors", 0) or 0)
    summary["skipped"] = int(suite.get("skipped", 0) or 0)
    summary["duration"] = round(float(suite.get("time", 0) or 0), 2)
    summary["passed"] = max(summary["total"] - summary["failed"] - summary["error"] - summary["skipped"], 0)

    for case in suite.iter("testcase"):
        classname = case.get("classname", "")
        name = case.get("name", "")
        # 还原为可读 nodeid：tests.test_X.test_y → tests/test_X.py::test_y
        nodeid = classname.replace(".", "/") + ".py::" + name if classname else name
        message = None
        if case.find("failure") is not None:
            status = "failed"
            message = (case.find("failure").get("message") or "").strip()
        elif case.find("error") is not None:
            status = "error"
            message = (case.find("error").get("message") or "").strip()
        elif case.find("skipped") is not None:
            status = "skipped"
            message = (case.find("skipped").get("message") or "").strip()
        else:
            status = "passed"
        summary["cases"].append({
            "nodeid": nodeid,
            "status": status,
            "time": round(float(case.get("time", 0) or 0), 3),
            "message": message[:300] if message else None,  # 截断，避免表格过宽
        })
    return summary
