# 工作台 UI 迭代报告（第二轮 · 2026-11-12）

> 写给下一轮迭代：本轮改动全景、涉及文件、验证结论、遗留风险。本轮起项目有版本控制（`workbench/` 仓库），回滚可 `git revert`，本文件聚焦「为什么这么改」与踩坑记录。

## 本轮改了什么

### 1. 窗口默认大小 1400×900（launcher.py:189-190）
原 1432×913。仅改默认值，min_size (1024,680) 不变；小于 1400 宽的屏幕由 pywebview 钳制，CSS 弹性布局自适应。

### 2. 聊天视图弹性填满窗口（ui/chat.py + ui/__init__.py CSS）
- **弃用 `.chat-resize`（CSS resize 拖动调高）机制**：对话区改为 flex 弹性占满后，用户拖出的高度会被 free-space 分配立刻覆盖，resize 手柄形同虚设；弹性填满收益严格更大。`chat-resize` 类与 CSS 规则一并删除。
- **DOM 对策（Gradio 5.50 实测结构）**：Group 的子组件全部在内层 `div.styler` 里，flex 必须作用于 `.styler` 而非 `.gr-group`。规则：
  ```css
  :root { --chat-reserved: 160px; }   /* 头部+页脚+容器 padding，playwright 实测校准 */
  .chat-view { height: calc(100vh - var(--chat-reserved)); }
  .chat-view .styler { display: flex; flex-direction: column; height: 100%; }
  .chat-view .chat-fill { flex: 1 1 auto; min-height: 160px; }
  ```
- chatbot 的内联 `height:340` 恰好充当 flex-basis，无需 `!important` 对抗内联样式；内层 `.bubble-wrap` 自带 overflow-y:auto，滚动正常。`chat-view` 类挂在聊天视图 Group 上（chat.py `build_chat_panel`）。
- 消息输入框 `lines=2→5`、新增 `max_lines=12`（容纳预填的长讨论 prompt）。
- 聊天视图是唯一锁高视图（页内无 Dropdown 弹层，不受「overflow 裁剪弹层」问题影响）；其余 6 视图维持页面自然滚动。

### 3. 三个生成视图补「文件预览」（ui/views_gen.py）
- 测试点分析（完善 SKILL 区改双列，右列 `gr.Code` markdown 预览）、用例生成（任务区下方 `gr.Code`）、脚本生成（任务区下方 `gr.DataFrame` + 复用 `common.preview_xlsx` 前 30 行）。
- **重要踩坑：Gradio 5.50 的 Dropdown 加载时自动预选第一项**（input 初始即有值、选项带 selected 标记），而 change 只在 value 变化时触发——若预览初始值为空，用户打开页面就看到「已选中文件但预览空白」。修复：三个预览组件的初始 value 直接读当前选中（第一项）文件，与预选状态对齐。
- 预览选 `gr.Code(language="markdown")` 而非 Markdown 渲染：核对内容为目的（保留原文格式、自带复制按钮）、与 CLAUDE.md 预览模式统一。注意 gr.Code 内容渲染在 CodeMirror（`.cm-content`），不是 `pre code`——playwright 断言时按此定位。

### 4. 「进聊天讨论方案」改为预填消息栏（views_gen.py + chat.py + __init__.py）
- 原行为：`discuss_fn` 生成器直接 `stream_chat` 自动开聊；**未提取建议时校验失败只切视图不带任何内容**（用户遇到的「只跳转」现象即此）。
- 新行为：`discuss_prefill` 同步函数把 `skill_advice.build_discussion_prompt` 产物预填进消息栏（`gr.update(value={"text":…, "files":…})`，保留用户已贴附件），不自动发送；有建议提示「核对补充后手动发送」，无建议预填基础引导（可直接发送）。
- 链路：`btn.click(_make_switch(0)).success(adv["fn"], inputs=[advice_dd, advice_state, chat_refs["msg"]], outputs=[msg, status])`——chatbot/active_job/session_state 不再参与，「运行中任务守卫」随之删除（真冲突由发送时 claude_api 报错兜住）。
- 前置改造：`build_chat_panel` 返回 dict 增加 `"msg"`；`build_discussion_prompt`（skill_advice.py）空建议分支输出通读引导而非空 items 段。

### 5. 脚本生成三行重排（views_gen.py）
Row1=[Excel 下拉独占]、Row2=[解析用例, 刷新]、Row3=[数量上限, 显示全部]。组件对象与事件绑定未动。

### 6. 脚本运行列表优化（views_ops.py + CSS）
- 文件选择列表新类 `cases-list`（与脚本生成的 `cases-grid` 拆分，互不影响）：一行一个（`grid-template-columns: minmax(0,1fr)`）、长文件名自动换行（`overflow-wrap:anywhere` + 链路 `min-width:0` 防撑开）、`max-height: 400px`、`overflow-x:hidden`——无横向滚动、无省略号（CheckboxGroup 无悬浮 title 能力，放弃「省略+悬浮」方案）。
- label 清理：「选择测试文件（仅 test_*.py，默认全不选）」→「选择测试文件」，「默认全不选」语义挪入视图头部说明句。

### 7. 提示文案清理（views_gen.py / views_ops.py）
去掉括号类操作说明：截图「（新文件在前）」、测试点文档「（默认最新在前）」、脚本生成标题「解析后勾选用例（默认仅计划自动化且未生成）」、脚本运行 label 括号。**保留**浏览器渠道的 chromium 缺失 info（环境约束提示，删了会不知道为何选不了）。

### 8. 上下文页「实际生效值」报错修复（views_ops.py）
- **根因**：`_browser_config_md` 动态 `from src.corebrowser import …`，而 corebrowser.py 顶层 `import playwright`；exe frozen 模式下 `src` 不是可导入包且 playwright 未打包 → `ModuleNotFoundError` → 渲染「读取 src/corebrowser.py 失败：…」一行报错（venv 命令行模式正常，故仅 exe 用户可见）。
- **修复**：改为读 `src/corebrowser.py` 文本 + `ast.parse` + `ast.literal_eval` 静态提取 `DEFAULT_BROWSER_CHANNEL / BROWSER_ARGS / CONTEXT_CONFIG`（均为纯字面量），不执行 import，frozen 安全；文件缺失/语法错/非字面量各自兜底。展示文案不变。

### 9. CLAUDE.md 改 gr.Code 展示（views_ops.py）
原 gr.Markdown 改 `gr.Code(language="markdown", wrap_lines=True, lines=22)`：自带复制按钮、整文件可全选，满足「命令可选中复制」诉求。仍在折叠 Accordion 内。

## 涉及文件
| 文件 | 改动 |
|---|---|
| workbench/launcher.py | 窗口 1400×900 |
| workbench/ui/__init__.py | CSS：删 chat-resize、加 chat-view/chat-fill/cases-list；预填链路改写（.success outputs→msg/status）；docstring |
| workbench/ui/chat.py | chat-view/chat-fill 类、msg lines=5/max_lines=12、返回 dict 暴露 msg、docstring |
| workbench/ui/views_gen.py | 三预览（含初始值对齐预选）、完善 SKILL 双列、discuss_prefill、三行重排、文案清理 |
| workbench/ui/views_ops.py | cases-list 类、label 清理、_browser_config_md 改 ast 静态解析、CLAUDE.md 改 Code |
| workbench/skill_advice.py | build_discussion_prompt 空建议分支 |
| workbench/UI-CHANGES.md | 本报告（上一轮收编为文末历史章节） |

后端 jobs.py / claude_api.py / api.py / pytest_api.py / config.py 未动。

## 验证结论（playwright headless msedge，1400×900 视口，25 项断言全过）
- 聊天页 `scrollHeight==innerHeight==900`（无页面滚动）、chatbot offsetHeight 542（弹性生效）、styler flex 化；`@CLA` 联想候选可见（flex 化后未被裁剪）。
- 其余视图保留自然滚动；测试点分析 Dropdown 选项面板物理可见（弹层回归）。
- 预览三视图：初始内容对齐预选、切换文档后预览更新（change 路径实测）、Excel DataFrame 有内容；cases-grid 仍两列（零回归）。
- 预填两分支：有建议→「已填入讨论内容（消息栏），请核对补充后手动发送」；无建议→「已填入基础引导（可直接发送）」；两分支均不自动发送（聊天流 message-row=0）。
- cases-list 单列、无横向滚动、限高 400。
- 上下文页含 msedge 与启动参数、无「读取失败」行；CLAUDE.md Code 组件内容+复制按钮均在。
- 文案清理四项字样均不在页面文本中。
- **验证脚本的 Gradio 定位经验**：Dropdown 标题不是 `<label>` 元素（按 label 定位不可行，每页可见 `.secondary-wrap` 唯一直接点）；切换选项必须点非 selected 项否则 change 不触发；组件标题/内容元素跨组件不一致（label/pre/textarea/cm-content 混用），断言按「叶子 block 的 innerText 匹配 + 内部多种内容元素兜底」最稳。

## 遗留风险 / 下一轮注意
1. **预填后「手动发送」的 submit 链路未自动实测**（会真调 claude CLI）；submit 绑定未动（chat.py:162-167 原样），风险低，窗口模式首次使用时留意。
2. **`--chat-reserved: 160px` 按 1400×900 + 当前字体校准**：Windows 缩放/字体渲染差异可能造成 ±几px 页面滚动；若出现滚动优先调此变量。
3. **Dropdown 自动预选第一项是 Gradio 5.50 行为**：各视图打开即有「当前选中文件」；刷新列表后 choices 变化时选中项与预览可能短暂不一致，未做联动刷新（实测影响小）。
4. **exe 未重新打包**：launcher/app 本轮未动，但 views_ops ast 解析正是为 exe 修复；下次打包后建议实测窗口模式 + 上下文页。
5. 窗口 1400×900 在 1366×768 屏会超屏钳制（弹性布局可正常降级）。

---

## 历史：2026-11-12 上一轮（无 git 时代，改动在初始提交 3a691f1 内，无独立 diff）

> 本节为上一轮原始报告收编，其中「项目无版本控制」背景已过时（现已 git init，仓库在 workbench/）。「遗留风险」第 1/5 条（chat-resize 双滚动条、Gradio Dropdown 无 type 属性与隐藏视图 .first 命中坑）仍是有效的踩坑记录；本轮已按第 1 条预期把 chat-resize 整体弃用。

### 上一轮改了什么

#### 1. 全局：恢复页面整体滚动（修三大"看不到"问题的根因）
- **根因**：更早版本给每个视图容器加了 `.view-scroll { max-height + overflow-y: auto }`。CSS 的 overflow 容器会**裁剪内部绝对定位弹层**——Gradio Dropdown 的选项面板被裁掉，表现为「测试点文档列表无法看到」「结果报告页选择历史运行下拉没反应」（数据一直在，选项面板弹出来但物理不可见）；`max-height` 限高同时造成"页面太紧凑、有遮挡"。
- **改动**：删 `.view-scroll` 限高规则与全部视图上的 `elem_classes=["view-scroll"]` 引用；页面回归自然滚动。局部滚动保留：截图列表（`.shot-scroll`）、用例/文件勾选网格（`.cases-grid` 两列限高）、任务结果区（`.task-result`）、完善建议（`.advice-table`）。

#### 2. 聊天页（ui/chat.py）
- 删「新会话」按钮、删「对话区高度」滑块；对话区高度默认 **340px**，CSS `resize: vertical`（`.chat-resize`）拖动调整（拖动值不持久化，刷新回到 340）。**（本轮已弃用该机制，见上文第 2 条）**
- 右侧初始提示文字清空；状态行保留**任务进度/会话信息**功能（初始为空、有任务时显示进度）。
- 联想候选（`/` SKILL、`@` 文件）：保留 Dataset + 点击回填（用户选了"简化版"，**未做键盘 ↑↓/Tab**）；CSS `.suggest-panel` 做近似 CLI 风格（等宽字体、hover 蓝底）。
- **@ 候选来源从 4 个固定目录扩为项目根全扫描**（ui/common.py）：os.walk 剪枝排除 `node_modules/.venv/.git/.idea/.pytest_cache/.tmp/__pycache__/build/dist/data`，扩展名白名单（md/py/xlsx/png/jpg/json/txt/ini/yaml/yml/toml/log/csv），mtime 新→旧，**30 秒 TTL 缓存**（`_cand_cache`）。token 为项目根相对路径，`resolve_refs` 原逻辑天然兼容（未改）。

#### 3. 测试点分析（ui/views_gen.py）
- **修复真 bug**：`shots_radio` 的 change 从未绑定预览组件，补绑后选中即预览。
- 「完善 SKILL」区块由 Group 改 Accordion（默认展开）。

#### 4. 脚本生成（ui/views_gen.py）
- 排版：第一排 Excel 下拉+解析按钮；第二排 数量上限+展示全部+刷新。**（本轮重排为三行，见上文第 5 条）**
- 勾选策略：展示全部时未标记自动化的可勾；**已生成用例提交时强制过滤**并在状态行提示"N 条已生成"（CheckboxGroup 无单条禁勾能力，用提交校验实现；全勾已生成时报"不可重复生成"不启动任务）。

#### 5. 脚本运行（ui/views_ops.py）
- marker choices 由 `["", "p0".."p3"]` 改 `["", "p0", "p1", "p2"]`（对齐 pytest.ini 现状）。
- 文件选择 Dropdown→CheckboxGroup（两列限高网格、`show_select_all`，默认全不选）；`on_start` 的 targets 逻辑未变。**（本轮拆分 cases-list 类并重排展示，见上文第 6 条）**

#### 6. 结果报告（ui/views_ops.py）
- 区块顺序改为：历史运行 → 运行结果文件 → 失败截图（Gallery 挪到最末）。

#### 7. 项目上下文（ui/views_ops.py）
- CLAUDE.md Accordion 改默认折叠（`open=False`）。

#### 8. 启动加速：服务常驻（launcher.py / app.py / ui/__init__.py）
- 实测启动 4~5s：`import gradio` 3~4s + `build_ui()` 1s + webview ~1s。gradio 导入是框架开销无法根治 → 改打"二次打开秒开"：
- **窗口关闭后服务不再退出**（默认常驻，`WORKBENCH_KEEP_ALIVE=0` 可关闭）：launcher 保活循环 `while server_thread.is_alive()`；再开 launcher 走已有"端口占用→复用开窗"分支，约 1 秒。
- **退出入口**：侧边栏底部「退出服务」按钮（`_quit_service`）→ `app.stop_server()`（`uvicorn_server.should_exit=True`）+ destroy webview 窗口 → launcher 保活循环见线程结束 → 进程收尾。
- `app.py` 的纯服务模式由 `uvicorn.run()` 改为自建 `uvicorn.Server`（`run_server()`），使退出按钮在纯服务模式同样生效。
- 用户侧另建议：Defender 排除项目目录（系统级，用户自行执行）。

### 上一轮遗留风险（本轮处置情况随文标注）
1. ~~`.chat-resize` 的 `overflow: auto` 可能在 chatbot 内部出现双滚动条~~ → 本轮弃用该机制，风险消除。
2. **拖动调高的值不持久化** → 机制已弃用，弹性行为无此问题。
3. **候选 TTL 缓存 30s**：新建文件最多延迟 30s 才进 @ 候选（common.py `_SUGGEST_TTL_SEC`）——仍有效。
4. **已生成禁勾是提交时过滤**而非 UI 置灰——仍有效。
5. **排查 Gradio DOM 的坑（上轮耗时最长）**：Gradio 5.50 的 Dropdown input **没有 `type` attribute**，`input[type=text]` 选择器永远匹配 0 个；要按 `i.type === 'text'`（property）或父级 `.secondary-wrap` 定位。且 7 个视图 DOM 常驻（隐藏视图 display:none），playwright `.first` 会命中隐藏组件导致 click 超时，务必加可见性过滤。——本轮验证再次印证，并新增：Dropdown 标题非 `<label>` 元素、加载时自动预选第一项。
6. **exe 模式（PyInstaller）未重新打包验证**——仍有效，本轮 ast 修复待打包实测。
7. pytest.ini 已无 p3 marker，tests/ 里若有 `@pytest.mark.p3` 残留会打 unknown-marker warning（不属于工作台，未处理）。
