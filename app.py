# -*- coding: utf-8 -*-
"""工作台入口：FastAPI（JSON API）+ Gradio（UI 挂载于 /）。

启动::

    .venv\\Scripts\\activate
    python -m workbench.app

浏览器打开 http://127.0.0.1:7860
"""
from __future__ import annotations

import gradio as gr
import uvicorn
from fastapi import FastAPI

from . import config
from .api import router
from .ui import build_ui


def create_app() -> FastAPI:
    """构建 ASGI 应用：/api/* JSON 路由在前，Gradio UI 挂载于 /。"""
    app = FastAPI(title="B站 AI 测试工程化工作台")
    app.include_router(router)                                  # JSON API
    app = gr.mount_gradio_app(app, build_ui(), path="/")        # Web UI
    return app


app = create_app()

# uvicorn.Server 运行时引用：launcher / 纯服务模式启动后注入，
# 供「退出服务」按钮优雅停机（should_exit → server.run 返回 → 进程收尾）
uvicorn_server: uvicorn.Server | None = None


def stop_server() -> bool:
    """优雅停止 uvicorn 服务。返回是否有可停的实例。"""
    if uvicorn_server is None:
        return False
    uvicorn_server.should_exit = True
    return True


def run_server() -> None:
    """自建 Server 对象启动（替代 uvicorn.run），使退出按钮在纯服务模式同样生效。"""
    global uvicorn_server
    server = uvicorn.Server(uvicorn.Config(app, host=config.HOST, port=config.PORT))
    uvicorn_server = server
    server.run()


if __name__ == "__main__":
    # Windows GBK 控制台打印兜底：避免 emoji/中文导致 UnicodeEncodeError 中断启动
    try:
        print(f"工作台启动中：http://{config.HOST}:{config.PORT}")
    except UnicodeEncodeError:
        print(f"Workbench starting at http://{config.HOST}:{config.PORT}")
    run_server()
