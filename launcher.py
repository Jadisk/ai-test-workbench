# -*- coding: utf-8 -*-
"""窗口模式入口：exe 打包用，开发模式亦可直接运行（python workbench/launcher.py）。

双击 exe 的完整流程：
  1. 检测端口是否已有工作台实例监听：有则不开新服务，窗口直接复用现有实例（秒开）
  2. 无实例时在后台线程启动 uvicorn 服务（Server 对象 + should_exit 优雅停止）
  3. pywebview 打开独立原生窗口（Windows 端为 Edge WebView2 内核）加载页面
  4. 窗口关闭 → 服务默认常驻后台（WORKBENCH_KEEP_ALIVE=0 可关闭），下次打开秒开；
     彻底退出用页面侧边栏「退出服务」按钮（优雅停机 + 进程收尾）

纯服务模式（不开窗口）：python -m workbench.app；或设置环境变量 WORKBENCH_WINDOW=0。
"""
from __future__ import annotations

import logging
import multiprocessing
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

# 直接以脚本方式运行（python workbench/launcher.py）时，把项目根加入 sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_LAUNCHER_LOG = "launcher.log"


def _log_to_file(message: str) -> None:
    """写入 launcher 文件日志（exe windowed 模式无控制台，启动过程要可追溯）。"""
    try:
        from workbench import config
        log_dir = Path(config.DIR_JOB_LOGS)
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / _LAUNCHER_LOG).open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass  # 日志失败不影响启动流程


def _ensure_streams() -> None:
    """windowed exe（console=False）下 sys.stdout/stderr 为 None，部分库会因此崩溃
    （如 uvicorn 的 DefaultFormatter 初始化调用 sys.stdout.isatty()）。
    重定向到 launcher 日志文件（普通文件 isatty()=False；注意不能用 nul 设备，
    其 isatty() 在 Windows 上返回 True 会被误判为终端），须在 uvicorn/gradio 导入前执行。"""
    if sys.stdout is None or sys.stderr is None:
        try:
            from workbench import config
            log_dir = Path(config.DIR_JOB_LOGS)
            log_dir.mkdir(parents=True, exist_ok=True)
            stream = open(log_dir / _LAUNCHER_LOG, "a", encoding="utf-8", buffering=1)
        except Exception:
            stream = open(os.devnull, "w", encoding="utf-8")
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream


def _setup_file_logging() -> None:
    """exe（windowed）模式下把 root logger 重定向到文件（uvicorn/gradio 报错可见）。"""
    if not getattr(sys, "frozen", False):
        return
    try:
        from workbench import config
        log_dir = Path(config.DIR_JOB_LOGS)
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_dir / _LAUNCHER_LOG, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        logging.basicConfig(level=logging.INFO, handlers=[handler])
    except Exception:
        pass


def _print(message: str) -> None:
    """Windows GBK 控制台打印兜底；windowed 模式 print 静默，靠文件日志留痕。"""
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", "replace").decode("ascii"))
    _log_to_file(message)


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) == 0


def _wait_ready(url: str, timeout: float = 15.0) -> bool:
    """轮询服务直到可访问（pywebview 窗口加载前确保后端就绪）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.4)
    return False


def _start_server_thread(host: str, port: int):
    import uvicorn

    from workbench import app as app_module

    # log_config=None：禁用 uvicorn 自身的 dictConfig（其 DefaultFormatter 会调用
    # sys.stdout.isatty()，windowed exe 下 stdout 为 None 直接崩溃），
    # uvicorn 日志改为沿 root logger 落入 launcher.log
    server_config = uvicorn.Config(app=app_module.app, host=host, port=port,
                                   log_level="info", log_config=None)
    server = uvicorn.Server(server_config)
    app_module.uvicorn_server = server  # 注入引用：供「退出服务」按钮优雅停机
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server, thread


def main() -> None:
    multiprocessing.freeze_support()  # frozen 多进程兜底
    _ensure_streams()                 # windowed 模式 stdout/stderr 为 None 的兜底（须最先）
    _setup_file_logging()             # exe windowed 模式：日志重定向到文件

    from workbench import config

    host, port = config.HOST, config.PORT
    url = f"http://{host}:{port}/"

    window_enabled = os.environ.get("WORKBENCH_WINDOW", "1") != "0"

    server = None
    server_thread = None
    if _port_in_use(host, port):
        _print(f"检测到 {url} 已有工作台实例在运行，窗口将直接复用它（不再启动新服务）")
    elif window_enabled:
        server, server_thread = _start_server_thread(host, port)
        _print(f"服务启动中：{url}（项目根 {config.PROJECT_ROOT}）")
        if not _wait_ready(url):
            _print("服务启动超时，请查看上方日志排查；窗口将仍尝试打开页面")

    if window_enabled:
        _open_window(server, server_thread, url)
    else:
        # 纯服务模式（WORKBENCH_WINDOW=0）：等价于 python -m workbench.app
        if server is None:
            server, server_thread = _start_server_thread(host, port)
            _print(f"服务启动中：{url}（项目根 {config.PROJECT_ROOT}）")
            _wait_ready(url)
        _print("纯服务模式运行中（Ctrl+C 退出）")
        try:
            while server_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    if server is not None:
        # 窗口模式默认常驻（WORKBENCH_KEEP_ALIVE=0 关闭）：关窗后服务留在后台，
        # 再次打开直接复用（约 1 秒）；彻底退出用页面「退出服务」按钮。
        keep_alive = window_enabled and os.environ.get("WORKBENCH_KEEP_ALIVE", "1") == "1"
        if keep_alive:
            _print("窗口已关闭，服务保持后台运行（再次打开秒开）；"
                   "彻底退出请用页面侧边栏「退出服务」按钮")
            try:
                while server_thread.is_alive():
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        else:
            server.should_exit = True  # 优雅停止服务线程，进程随之退出


def _open_window(server, server_thread, url: str) -> None:
    """打开 pywebview 原生窗口（阻塞至窗口关闭）。WebView2 缺失时退化为提示。"""
    try:
        import webview
    except ImportError:
        _print("未安装 pywebview，无法打开窗口；请改用浏览器访问 " + url)
        return

    _print("正在打开应用窗口…")
    webview.create_window(
        "B站 AI 测试工程化工作台",
        url,
        width=1400,
        height=800,
        min_size=(1024, 680),
    )
    try:
        # GUI 必须占据主线程；关闭窗口后 start() 返回
        webview.start()
    except Exception as exc:
        _print(f"打开应用窗口失败（{exc}）。请改用浏览器访问：{url}")
        _print("若窗口模式持续不可用，可设置环境变量 WORKBENCH_WINDOW=0 以纯服务模式运行。")
        if server is not None:
            _print(f"服务保持运行中：{url}（Ctrl+C 或页面「退出服务」退出）")
            try:
                while server_thread.is_alive():
                    time.sleep(1)
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
