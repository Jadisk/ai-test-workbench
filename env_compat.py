# -*- coding: utf-8 -*-
"""启动期环境兼容处理。"""
from __future__ import annotations

import os


def normalize_no_proxy() -> None:
    """去掉 NO_PROXY 中 IPv6 条目的方括号，避免 httpx 将 ``[::1]`` 误解析为端口。

    httpx 在构造环境代理匹配规则时接受 ``::1``，但不接受带方括号的 ``[::1]``。
    仅规范化 NO_PROXY/no_proxy，不改动其它代理变量或条目的语义。
    """
    for key in ("NO_PROXY", "no_proxy"):
        raw = os.environ.get(key)
        if raw is None:
            continue
        entries = [item.strip() for item in raw.split(",") if item.strip()]
        normalized = [
            item[1:-1] if item.startswith("[") and item.endswith("]") else item
            for item in entries
        ]
        os.environ[key] = ",".join(normalized)
