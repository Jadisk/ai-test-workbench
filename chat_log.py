# -*- coding: utf-8 -*-
"""聊天消息轻量落盘：聊天面板的普通消息不走 JobManager（无任务日志），
出问题（如权限拒绝、模型异常回复）时无从排查——本模块把每轮对话摘要
追加写入 data/logs/chat_YYYYMMDD.log，与任务日志同目录。
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from . import config

_lock = threading.Lock()
_MAX_CHARS = 2000  # 单条文本截断长度


def log_turn(role: str, text: str, session_id: str | None = None, extra: str = "") -> None:
    """追加一轮对话摘要。任何 IO 异常静默吞掉（日志不应影响对话）。"""
    try:
        log_dir = Path(config.DIR_JOB_LOGS)
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"chat_{datetime.now().strftime('%Y%m%d')}.log"
        text = (text or "").strip()
        if len(text) > _MAX_CHARS:
            text = text[:_MAX_CHARS] + "…（截断）"
        parts = [
            f"[{datetime.now().strftime('%H:%M:%S')}] [{role}]"
            + (f" session={session_id}" if session_id else ""),
            text,
        ]
        if extra:
            parts.append(f"（{extra}）")
        with _lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(parts) + "\n\n")
    except OSError:
        pass
