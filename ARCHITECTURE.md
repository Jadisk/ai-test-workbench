# workbench 架构地图

> 给 AI 迭代用的稳定地图：文件职责、改动类型→最小读取集、事件绑定模板、Gradio DOM 坑。**只写不变的事实**，每轮改了什么看 `UI-CHANGES.md`（最新报告在顶部，历史章节在底部）。
>
> **坑清单维护规则**：不设定期巡检——坑的过期靠每轮实操自然暴露（如坑 4 即迭代中撞出后改写）。实操中发现条目与现实不符**立即改写**（标注「实测修正」+ 日期），坑被修复消除后删除或并入修复说明；「已证伪的假设」保留记录（避免后人重走排查弯路）；新坑按域归类（DOM/行为/frozen/观测）。

## 启动链路

```
launcher.py（exe/窗口入口，pywebview，窗口尺寸在 _open_window）
  └─ app.py（FastAPI + Gradio 挂载于 /；纯服务模式入口 python -m workbench.app）
       ├─ config.py（PROJECT_ROOT 锚定项目根、SKILL 注册表、prompt 构造、路径常量）
       ├─ jobs.py（JobManager：claude/pytest 任务互斥、事件流、日志落盘）
       ├─ claude_api.py / pytest_api.py（子进程调 claude CLI / pytest）
       └─ ui/__init__.py build_ui()（组装全部 UI）
```

## UI 文件地图

| 文件 | 职责 | 入口 |
|---|---|---|
| ui/__init__.py | **全部 CSS**（`_CSS`）、侧边栏、7 视图常驻 + `visible` 切换、跨视图事件链 | `build_ui()` |
| ui/chat.py | 聊天视图：chatbot/消息框/实时联想/SKILL 精简渲染 | `build_chat_panel(timer, active_job)` → `(panel, refs dict)`，refs 含 chatbot/status/session_state/msg |
| ui/views_gen.py | 测试点分析 / 用例生成 / 脚本生成 | `build_analysis_view` / `build_cases_view` / `build_scripts_view` |
| ui/views_ops.py | 脚本运行 / 结果报告 / 项目上下文 | `build_runner_view` / `build_reports_view` / `build_context_view` |
| ui/common.py | 公共设施：任务区、文件列表、读取预览、@ 联想 | `build_task_area` / `bind_task_area` / `list_choices` / `read_text` / `preview_xlsx` |

任务区模式：`area = build_task_area()`（返回 dict：job_id/status_md/progress_md/result_md/stop_btn），`bind_task_area(timer, area)` 接 Timer 轮询；启动回调返回 `(job_id, 状态文案)`。

## 改动类型 → 最小读取集

| 改动类型 | 必读 | 通常牵连 |
|---|---|---|
| 视图内布局 / 组件 / 文案 | 对应 views_*.py | ui/__init__.py（新增 CSS 类时） |
| 聊天页行为 | ui/chat.py | ui/__init__.py（CSS）、common.py（联想） |
| 跨视图联动 | ui/__init__.py + 源视图 + chat.py 的 refs | — |
| 上下文页配置展示 | views_ops.py | config.py + 被展示的源文件（如 src/corebrowser.py） |
| 任务行为 / 后端 | jobs.py / claude_api.py / pytest_api.py | 视图侧仅 on_start 的返回结构 |
| 窗口 / 启动 / 打包 | launcher.py | app.py、workbench.spec |

## 事件绑定模板（复用，别发明新形）

```python
# 视图内：选择/点击 → 更新（show_progress="hidden" 避免转圈遮罩）
comp.change(fn, inputs=[...], outputs=[...], show_progress="hidden")

# 跨视图联动（切视图成功后再灌内容，.success 链解耦）：
btn.click(_make_switch(idx), outputs=[*view_groups, *sidebar_buttons]).success(fn, inputs=..., outputs=...)

# 跨视图引用组件：通过 build_chat_panel 的 refs dict（含 msg），不要 import 别的视图内部组件
```

## Gradio 5.50 DOM / 行为坑（写 playwright 验证前必读）

1. **Dropdown 标题不是 `<label>` 元素**——按 label 定位下拉不可行；每个视图可见的 `.secondary-wrap` 唯一，直接点它。
2. Dropdown 的 input **没有 `type` attribute**，`input[type=text]` 选择器永远匹配 0 个。
3. **Dropdown 加载时自动预选第一项**：点击当前选中项不触发 change（不发 queue/join）；验证切换必须点非 selected 项。连带要求：依赖 change 回填的组件（如文件预览）初始 value 须对齐预选的第一项，否则打开页即空白。
4. **隐藏视图懒渲染**（实测修正，旧结论「7 视图 DOM 常驻」已过时）：初始只渲染可见视图（聊天），其余 6 视图的 DOM **不存在**；侧边栏点击触发 `visible=True` 事件后才挂载（约 1~2 秒），挂载后常驻。playwright 验证必须**先点侧边栏按钮、再 `wait_for_selector`**，对隐藏视图做 attached 等待永远超时。
5. **gr.Code 内容渲染在 CodeMirror**（`.cm-content`），不是 `pre code`；各组件标题/内容元素不一致（label/pre/textarea/cm-content 混用），断言按「叶子 block 的 innerText 匹配 + 内部多种内容元素兜底」最稳（叶子 block = 不含嵌套 `.block`）。
6. Accordion 折叠时内容 DOM 在但 offsetParent 为 null——验证前先展开。
7. **Group 真实 DOM 是 `.gr-group > .styler > 子组件`**：flex 布局必须作用于 `.styler`，作用于 `.gr-group` 不影响组件。
8. 组件的 height/overflow/flex-grow 是**内联样式**——CSS 覆盖不要硬对抗（`!important`），利用它（如 height 在 flex item 上恰作 flex-basis）。
9. **overflow 容器裁剪绝对定位弹层**：视图容器不要加 overflow 限高，否则 Dropdown 选项面板物理不可见（弹出来但看不到，表现为"下拉没反应"）。聊天视图可例外（页内只有内联组件无弹层）。
10. Python 侧 `from src.xxx import ...`（项目根的 src 包）在 exe frozen 下必炸（src 不在打包依赖，且顶层 import playwright）——读取项目文件配置用 `ast.parse` 静态解析，见 views_ops.py `_extract_browser_config`。
11. **gr.DataFrame 自带行号列**（约占 40px 宽，挤占业务列空间）；列宽过窄时表头中文会**竖排**（每字一行，窄列加 `min-width: 56px` 下限防竖排）；**无 `height` 参数**（固定高度用 CSS）；`max_height` 是滚动上限、内容不足时组件变矮；`column_widths` 总宽超过容器时会被**等比缩放回容器宽、不产生横向滚动**；传二维列表时**首行被当数据行，列名须拆到 `headers` 参数**（否则表头显示列序号 1..N）。默认 `table-layout: auto` 按内容量分配列宽（去掉强制宽度后即生效）。
12. 组件 `max-height` 类 CSS 是上限，**内容短时组件变矮**——需要"恒定高度占位"（如预览框、空列表占位）用 `height` / `min-height`（见 `.preview-tall` / `.cases-placeholder`）。
13. **windowed exe 下 claude 子进程可能零输出挂死**（2026-11-13 实证：claude.exe 活着、stdout/stderr 零字节、任务永远 running 面板「等待事件流」）。已证伪的假设——终端 / pythonw / `SetStdHandle(NULL)` 三种模拟均正常（claude 对无数据 stdin 有 3 秒兜底继续），cwd/认证/网络也正常，根因未锁定（疑 exe 引导层或安全软件对未签名 exe 子进程的干预）。**复现时的观测入口**：①任务日志尾部的「claude stderr（尾部）」（`jobs._run_claude` finally 落盘）②launcher 启动自检的 claude CLI 路径行。`ClaudeStream` 已用 `stdin=subprocess.DEVNULL` 兜底句柄继承（非确认修复，无害实践）。手动停止的终态是 `stopped`（中性「已停止」），收尾线程见到 stopped 不覆盖为 error。

## 验证惯例

- playwright headless msedge，viewport 对齐当前窗口默认尺寸（launcher.py `_open_window`）。
- 服务在验证脚本内以 **7861 端口**线程启动（避免与运行中的 7860 实例冲突）；`config.PORT = 7861` 必须在 `import workbench.app` 之前。
- 临时验证脚本放 `.tmp/`，成功后删除（**不保留上轮整脚本**——断言绑定当轮改动必过期；样板骨架在下方，每轮复制 + 写当轮断言）。
- 改动完成后更新 `UI-CHANGES.md`：本轮报告置顶 + 上轮收编历史章节（保留踩坑记录的引用价值）。

### 标准验证骨架（每轮复制此样板，只写当轮断言）

```python
# .tmp/verify_roundN.py —— 成功后删除
import sys, threading, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
import workbench.config as config
config.PORT = 7861                      # 必须在 import workbench.app 之前
from workbench.app import app
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=7861, log_level="warning"))
threading.Thread(target=server.run, daemon=True).start()
for _ in range(50):                     # 等端口就绪
    time.sleep(0.2)
    try: urllib.request.urlopen("http://127.0.0.1:7861/", timeout=1); break
    except Exception: pass

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 800})
    page.goto("http://127.0.0.1:7861/", wait_until="domcontentloaded")
    page.wait_for_selector(".sidebar button", timeout=20000)
    # 坑 4：隐藏视图初始 DOM 不存在，必须先点击切视图、再等元素挂载
    page.locator(".sidebar button", has_text="脚本生成").click()
    page.wait_for_selector("<当轮目标元素>", timeout=20000)
    # ……当轮断言（fail-fast：前序断言失败则跳过依赖它的后续断言）……
    page.screenshot(path="screenshots/debug/roundN.png")
    browser.close()
```

- 断言几何前先确认元素可见（视图已切换）；DataFrame 类断言注意 sticky 表头 + 数据两个 table（坑 11，th 按文本去重）。
- **诊断定序**（UI 行为与坑清单矛盾时）：第 1 轮脚本就「截图 + dump DOM」合并诊断 → 第 2 轮 `git stash` 对照实验（排除自己改坏 vs 环境行为）→ 再深挖环境。不要先改等待策略盲试。
