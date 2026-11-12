# 工作台 UI 迭代报告（2026-11-12）

> 写给下一轮迭代：本轮改动全景、涉及文件、验证结论、遗留风险。改动前项目**无版本控制**，回滚只能靠本文件描述逆向。

## 本轮改了什么

### 1. 全局：恢复页面整体滚动（修三大"看不到"问题的根因）
- **根因**：上一版给每个视图容器加了 `.view-scroll { max-height + overflow-y: auto }`。CSS 的 overflow 容器会**裁剪内部绝对定位弹层**——Gradio Dropdown 的选项面板被裁掉，表现为「测试点文档列表无法看到」「结果报告页选择历史运行下拉没反应」（数据一直在，选项面板弹出来但物理不可见）；`max-height` 限高同时造成"页面太紧凑、有遮挡"。
- **改动**：删 `.view-scroll` 限高规则与全部视图上的 `elem_classes=["view-scroll"]` 引用；页面回归自然滚动。局部滚动保留：截图列表（`.shot-scroll`）、用例/文件勾选网格（`.cases-grid` 两列限高）、任务结果区（`.task-result`）、完善建议（`.advice-table`）。

### 2. 聊天页（ui/chat.py）
- 删「新会话」按钮、删「对话区高度」滑块；对话区高度默认 **340px**，CSS `resize: vertical`（`.chat-resize`）拖动调整（拖动值不持久化，刷新回到 340）。
- 右侧初始提示文字清空；状态行保留**任务进度/会话信息**功能（初始为空、有任务时显示进度）。
- 联想候选（`/` SKILL、`@` 文件）：保留 Dataset + 点击回填（用户选了"简化版"，**未做键盘 ↑↓/Tab**）；CSS `.suggest-panel` 做近似 CLI 风格（等宽字体、hover 蓝底）。
- **@ 候选来源从 4 个固定目录扩为项目根全扫描**（ui/common.py）：os.walk 剪枝排除 `node_modules/.venv/.git/.idea/.pytest_cache/.tmp/__pycache__/build/dist/data`，扩展名白名单（md/py/xlsx/png/jpg/json/txt/ini/yaml/yml/toml/log/csv），mtime 新→旧，**30 秒 TTL 缓存**（`_cand_cache`，逐字符输入触发联想不能每次全盘 walk）。token 为项目根相对路径，`resolve_refs` 原逻辑天然兼容（未改）。

### 3. 测试点分析（ui/views_gen.py）
- **修复真 bug**：`shots_radio` 的 change 从未绑定预览组件，补绑后选中即预览。
- 「完善 SKILL」区块由 Group 改 Accordion（默认展开）。

### 4. 脚本生成（ui/views_gen.py）
- 排版：第一排 Excel 下拉+解析按钮；第二排 数量上限+展示全部+刷新。
- 勾选策略：展示全部时未标记自动化的可勾；**已生成用例提交时强制过滤**并在状态行提示"N 条已生成"（CheckboxGroup 无单条禁勾能力，用提交校验实现；全勾已生成时报"不可重复生成"不启动任务）。

### 5. 脚本运行（ui/views_ops.py）
- marker choices 由 `["", "p0".."p3"]` 改 `["", "p0", "p1", "p2"]`（对齐 pytest.ini 现状）。
- 文件选择 Dropdown→CheckboxGroup（两列限高网格 `cases-grid`、`show_select_all`，默认全不选）；`on_start` 的 targets 逻辑未变（CheckboxGroup 值同样是路径列表）。

### 6. 结果报告（ui/views_ops.py）
- 区块顺序改为：历史运行 → 运行结果文件 → 失败截图（Gallery 挪到最末）。

### 7. 项目上下文（ui/views_ops.py）
- CLAUDE.md Accordion 改默认折叠（`open=False`）。

### 8. 启动加速：服务常驻（launcher.py / app.py / ui/__init__.py）
- 实测启动 4~5s：`import gradio` 3~4s + `build_ui()` 1s + webview ~1s。gradio 导入是框架开销无法根治 → 改打"二次打开秒开"：
- **窗口关闭后服务不再退出**（默认常驻，`WORKBENCH_KEEP_ALIVE=0` 可关闭）：launcher 保活循环 `while server_thread.is_alive()`；再开 launcher 走已有"端口占用→复用开窗"分支，约 1 秒。
- **退出入口**：侧边栏底部「退出服务」按钮（`_quit_service`）→ `app.stop_server()`（`uvicorn_server.should_exit=True`）+ destroy webview 窗口 → launcher 保活循环见线程结束 → 进程收尾。
- `app.py` 的纯服务模式由 `uvicorn.run()` 改为自建 `uvicorn.Server`（`run_server()`），使退出按钮在纯服务模式同样生效。
- 用户侧另建议：Defender 排除项目目录（系统级，用户自行执行）。

## 涉及文件
| 文件 | 改动 |
|---|---|
| workbench/ui/__init__.py | CSS 重写（删 view-scroll、加 chat-resize/suggest-panel/quit-btn）、侧边栏加退出按钮、`_quit_service` |
| workbench/ui/chat.py | 删新会话/滑块、状态行改初始空、chatbot 340+chat-resize、Dataset 加 suggest-panel |
| workbench/ui/common.py | @ 候选项目根全扫描（`_scan_project_files` + TTL 缓存），删 `_SUGGEST_SOURCES` |
| workbench/ui/views_gen.py | 预览绑定补缺、完善 SKILL Accordion、脚本生成两排排版、已生成过滤 |
| workbench/ui/views_ops.py | marker p0-p2、文件 CheckboxGroup、结果页区块重排、CLAUDE.md 折叠 |
| workbench/launcher.py | `_start_server_thread` 返回 (server, thread) 并注入 app 模块、关窗常驻分支、docstring 更新 |
| workbench/app.py | `uvicorn_server` 模块引用、`stop_server()`、`run_server()`（替代 uvicorn.run） |
| workbench/UI-CHANGES.md | 本报告 |

后端 jobs.py / claude_api.py / api.py / pytest_api.py / config.py **未动**。

## 验证结论（playwright headless msedge 实测）
- 全过：页面滚动、聊天页精简（无新会话/滑块、340px）、@ 联想出项目根候选（@CLA → CLAUDE.md）、/ 联想 SKILL、图片预览渲染、完善 SKILL Accordion、脚本生成两排排版、marker=p0-p2（弹层物理可见）、文件多选框默认不选、结果页区块顺序与历史运行下拉 6 条选项可见、CLAUDE.md 折叠、launcher 常驻冒烟（注入引用→退出回调→线程优雅退出）。
- 截图留档 `screenshots/debug/workbench/验证-*.png`。

## 遗留风险 / 下一轮注意
1. **`.chat-resize` 的 `overflow: auto` 可能在 chatbot 内部出现双滚动条**（headless 截图未见，但真实窗口多分辨率未试）；若出现，改为外层包容器做 resize。
2. **拖动调高的值不持久化**（纯 CSS resize，刷新回 340）。如需持久化要走 JS 回写 + gr.State，本轮按简化版约定未做。
3. **候选 TTL 缓存 30s**：新建文件最多延迟 30s 才进 @ 候选；如嫌慢可调 `_SUGGEST_TTL_SEC`（common.py）。
4. **已生成禁勾是提交时过滤**而非 UI 置灰，用户勾了已生成用例要到点"生成"才看到提示——若要 UI 级禁勾需自绘 HTML 候选项（同键盘补全一起升级时做）。
5. **排查 Gradio DOM 的坑（本轮耗时最长）**：Gradio 5.50 的 Dropdown input **没有 `type` attribute**，`input[type=text]` 选择器永远匹配 0 个；要按 `i.type === 'text'`（property）或父级 `.secondary-wrap` 定位。且 7 个视图 DOM 常驻（隐藏视图 display:none），playwright `.first` 会命中隐藏组件导致 click 超时，务必加可见性过滤。
6. **exe 模式（PyInstaller）未重新打包验证**：launcher/app 改动涉及 frozen 路径（`_ensure_streams` 在 gradio 导入前执行的前提未破坏，app.py 顶部仍 `import gradio`，逻辑不变），但 dist 下旧 exe 不含新代码；下次打包后建议跑一次窗口模式 + 退出按钮。
7. pytest.ini 已无 p3 marker，tests/ 里若有 `@pytest.mark.p3` 残留会打 unknown-marker warning（不属于工作台，未处理）。
8. 项目**无 git**，本轮无备份点；下一轮如要大改 UI，建议先 `git init` 或把 workbench/ui 复制到 .tmp/backup/。
