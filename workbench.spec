# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置：测试工程化工作台（onedir 模式，启动快）
#
# 打包命令（项目根目录执行）：
#   .venv/Scripts/pyinstaller workbench/workbench.spec --noconfirm --distpath workbench/dist --workpath workbench/build
#
# 产物：workbench/dist/工作台/ 目录，双击其中的 测试工作台.exe 启动。
# exe 可放在项目根目录或其子目录运行（自动向上查找项目根）；也可用
# 环境变量 WORKBENCH_PROJECT_ROOT 显式指定。

import os

from PyInstaller.utils.hooks import collect_all

# spec 文件位于 workbench/ 下；项目根为其上一级
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = []
binaries = []
hiddenimports = []

# Gradio 及其关联包带大量静态资源/子模块，必须 collect_all
for package in [
    "gradio",
    "gradio_client",
    "safehttpx",
    "groovy",
    "orjson",
    "uvicorn",
    "fastapi",
    "openpyxl",
]:
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        "workbench",
        "workbench.app",
        "workbench.config",
        "workbench.jobs",
        "workbench.claude_api",
        "workbench.pytest_api",
        "workbench.api",
        "workbench.skill_advice",
        "workbench.chat_log",
        "workbench.ui",
        "workbench.ui.chat",
        "workbench.ui.common",
        "workbench.ui.views_gen",
        "workbench.ui.views_ops",
        # pywebview 原生窗口（Windows 端 Edge WebView2 后端）
        "webview",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "clr_loader",
        "pythonnet",
        # 函数内 import，hook 静态分析兜底
        "src.corebrowser",
        "src.pom_base",
        "src",
    ],
    # 排除与工作台无关的重依赖，显著瘦身（pytest/playwright 等仍由项目 .venv 运行）
    excludes=[
        "playwright", "pytest", "pytest_asyncio", "pytest_playwright",
        "anthropic", "openai", "xmind", "locust", "weasyprint",
        "faker", "loguru", "black", "flake8", "mypy",
        "IPython", "jupyter", "tkinter", "matplotlib",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="测试工作台",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # 不弹控制台窗口（双击 exe 仅弹工作台窗口）；启动/报错日志见 data/logs/launcher.log
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="测试工作台",
)
