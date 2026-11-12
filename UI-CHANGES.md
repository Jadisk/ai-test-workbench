# 工作台 UI 迭代报告（第三轮 · 2026-11-12）

> 写给下一轮迭代：本轮改动全景、涉及文件、验证结论、遗留风险。每轮报告置顶、上轮收编历史章节；回滚用 `git revert`（仓库在 `workbench/`）。改动前先读 `ARCHITECTURE.md`（文件地图 + Gradio DOM 坑清单）。

## 本轮改了什么

### 1. 窗口默认大小 1400×800（launcher.py:189-190）
上一轮改的 1400×900 与更早的 1432×913 仅差 32×13px（约 2%），用户实测「看不出变化」——属预期现象非 bug（尺寸需求本身接近）。本轮按用户确认改为 **1400×800**。聊天弹性布局自适应（`--chat-reserved` 与窗口高度无关，无需动），800 高实测无页面滚动、chatbot 442px。

### 2. 测试点分析：预览挪位 + 两页预览限高（views_gen.py + CSS）
- 预览从「完善 SKILL」Accordion 的双列右列**挪到右列任务区下方**，与用例生成完全同模式（右列 = 任务执行区 + 文档预览）；Accordion 恢复单列竖排（下拉 → 三按钮 → 建议表）。
- 两页预览加 `preview-scroll` 类：`max-height: 400px + overflow-y: auto`——内容长时**框内滚动**、不撑长页面（此前 `lines=18` 撑高组件、页面被拉长）。预览内无弹层，overflow 安全。

### 3. 脚本生成微调（views_gen.py）
- 「刷新」按钮去 `size="sm"`，与「解析用例」同尺寸（实测均 40px 高）。
- 第三行宽度重分配：数量上限 `scale 1→2`（label「数量上限（留空或 0 = 不限）」不换行）、显示全部 `scale 2→1`（label 换行）。
- **Excel 预览裁剪前 7 列**：`preview_xlsx` 加 `max_cols` 参数（common.py），change 回调改 `lambda p: preview_xlsx(p, max_cols=7)`——默认宽度下 12 列太挤（每列 ~55px、表头竖排），7 列均分变宽。
- **列宽分配**：`column_widths=["11%","12%","13%","14%","15%","17%","18%"]`——Gradio DataFrame 表头在窄列下中文会竖排（每字一行），按比例分配后窄列 ≥ 两字宽（编号列两行横排、步骤/结果列单行）。
- **预览高度与左列对齐**：`max_height 320→220`，实测预览下边界 458 vs「生成自动化脚本」按钮下边界 455（差 3px，肉眼齐平）。

### 4. 流程固化（CLAUDE.md）
工作台节新增**迭代流程**条目：开始前先读 UI-CHANGES.md 顶部最新报告；结束后更新该文档并 commit + push——均无需用户在要求中重复。（ARCHITECTURE.md 坑清单同步新增第 11 条：DataFrame 行号列/竖排/max_height 语义）

## 涉及文件
| 文件 | 改动 |
|---|---|
| workbench/launcher.py | 窗口 1400×800 |
| workbench/ui/common.py | `preview_xlsx` 加 `max_cols` 参数 |
| workbench/ui/views_gen.py | 测试点分析预览挪位+Accordion 单列、两页预览 preview-scroll、脚本生成按钮/Row3/Excel 预览（7 列+列宽+高度对齐） |
| workbench/ui/__init__.py | CSS 加 `.preview-scroll` |
| workbench/CLAUDE.md（项目根） | 迭代流程固化 |
| workbench/ARCHITECTURE.md | 坑清单第 11 条（DataFrame） |
| workbench/UI-CHANGES.md | 本报告 |

后端 jobs.py / claude_api.py / api.py / pytest_api.py / config.py / chat.py / views_ops.py / skill_advice.py 未动。

## 验证结论（playwright headless msedge，1400×800 视口，11 项断言全过 + 截图目测）
- 800 高窗口：聊天页 `scrollHeight==innerHeight==800`、chatbot 442px（弹性自适应生效）。
- 测试点分析：预览初始有内容（751 字符）、`preview-scroll` max-height 400px + overflow-y auto 生效、预览与任务区同列。
- 预填链路、cases-list 单列、上下文页无报错——均无回归。
- 脚本生成（截图目测 + 量化）：解析/刷新同高 40px；数量上限 label 单行、显示全部换行；Excel 预览 7 列、表头横排不竖排；预览下边界 458 vs 生成按钮下边界 455（差 3px）。

## 遗留风险 / 下一轮注意
1. **Excel 预览高度对齐依赖「内容超过 max_height」**：`max_height` 是滚动上限，用例 Excel 行数少（≤5 行）时预览组件变矮、与左列下边界不再齐平。标准 12 列用例 Excel 通常几十行，实际影响小；要根治需 flex 布局让 DataFrame 填满剩余空间（Gradio 组件结构限制，成本高未做）。
2. **窗口 1400×800 在 1366×768 屏会超屏钳制**（高度 800 > 768），弹性布局可正常降级。
3. exe 未重新打包（本轮未动 launcher 以外的前轮遗留项），下次打包后建议实测窗口模式。

---

## 历史：2026-11-12 第二轮（提交 ea02134）

> 「进聊天预填」与三视图预览均在本轮引入；Gradio Dropdown 自动预选第一项的坑在本轮发现并已录入 ARCHITECTURE.md 第 3 条。

### 改了什么
1. **窗口默认大小 1400×900**（launcher.py，原 1432×913；本轮已改 1400×800）。
2. **聊天视图弹性填满窗口**：弃用 `.chat-resize`（CSS resize 拖动）机制——flex 弹性下拖动值会被 free-space 分配覆盖；DOM 对策是 flex 作用于 Group 内层 `.styler`（`.gr-group > .styler > 组件`），chatbot 内联 `height:340` 恰作 flex-basis；`--chat-reserved: 160px`（头部+页脚+padding，实测校准）；消息框 lines 2→5、max_lines=12。聊天视图是唯一锁高视图（页内无 Dropdown 弹层）。
3. **三个生成视图补文件预览**：测试点分析（完善 SKILL 区双列右列 gr.Code）、用例生成（任务区下方 gr.Code）、脚本生成（任务区下方 gr.DataFrame + preview_xlsx 前 30 行）。**重要坑：Gradio 5.50 Dropdown 加载时自动预选第一项**，change 只在 value 真变化时触发——预览初始 value 必须对齐预选第一项，否则打开页即空白。
4. **「进聊天讨论方案」改预填消息栏**：原 discuss_fn 生成器直接 stream_chat 自动开聊、未提取建议时只切视图不带内容（用户遇到的「只跳转」）；改为 discuss_prefill 同步函数预填 `build_discussion_prompt` 产物进消息栏（保留已贴附件），不自动发送；无建议时预填基础引导。链路 `btn.click(_make_switch(0)).success(fn, inputs=[advice_dd, advice_state, chat_refs["msg"]], outputs=[msg, status])`；`build_chat_panel` 返回 dict 加 `"msg"`；运行中任务守卫删除。
5. **脚本生成三行重排**：Row1=[Excel 独占]、Row2=[解析,刷新]、Row3=[数量上限,显示全部]（本轮又微调宽度）。
6. **脚本运行列表 cases-list 类**（与 cases-grid 拆分）：一行一个、长名换行（overflow-wrap:anywhere + min-width:0）、限高 400、无横向滚动；label 清理。
7. **提示文案清理**：去括号说明（新文件在前/默认最新在前/仅 test_*.py/解析后勾选用例），保留 chromium 缺失 info。
8. **上下文页报错修复**：`_browser_config_md` 动态 import src.corebrowser 在 exe frozen 下必炸（src 不可导入 + playwright 未打包）→ 改 ast.parse + literal_eval 静态提取三常量（已录入 ARCHITECTURE.md 第 10 条）。
9. **CLAUDE.md 改 gr.Code**（自带复制按钮、可全选）。

### 验证（当时 1400×900 视口，25 项断言全过）
聊天页无滚动/chatbot 542、联想候选可见、弹层物理可见、预览初始+切换更新、预填两分支实测、cases-list 单列无横滚、上下文页无报错行、文案清理四项。

### 遗留（本轮处置随文标注）
1. 预填后手动发送的 submit 链路未自动实测（会真调 claude CLI）——仍有效，窗口模式首次使用留意。
2. `--chat-reserved` 按字体渲染 ±几px——仍有效（本轮 800 高实测无滚动）。
3. Dropdown 预选后刷新列表选中项与预览短暂不一致——仍有效（影响小）。
4. exe 未重新打包——仍有效。
5. 1400×900 在 1366×768 屏超屏——本轮改 800 高后仍超（800>768），见上文。

---

## 历史：2026-11-12 第一轮（无 git 时代，改动在初始提交 3a691f1 内，无独立 diff）

> 「无版本控制」背景已过时；坑记录仍有效，均已录入 ARCHITECTURE.md（Dropdown 无 type 属性、overflow 裁剪弹层等）。

### 改了什么
1. **恢复页面整体滚动**：根因是 `.view-scroll { max-height + overflow-y }` 裁剪 Dropdown 弹层（「下拉没反应」）；删限高规则，页面回归自然滚动，局部滚动保留（shot-scroll/cases-grid/advice-table/task-result）。
2. **聊天页精简**：删新会话按钮与高度滑块；状态行初始空；@ 联想候选扩为项目根全扫描（30s TTL 缓存）+ `/` SKILL 联想（Dataset 点击回填，无键盘导航）。
3. **测试点分析**：修复 shots_radio change 从未绑定预览的真 bug；完善 SKILL 改 Accordion。
4. **脚本生成**：两排排版 + 已生成用例提交时强制过滤（CheckboxGroup 无单条禁勾能力）。
5. **脚本运行**：marker p0–p2（对齐 pytest.ini）；文件选择 Dropdown→CheckboxGroup（默认全不选）。
6. **结果报告**：区块顺序 历史运行→运行结果文件→失败截图。
7. **上下文页**：CLAUDE.md Accordion 默认折叠。
8. **服务常驻**：窗口关闭服务不退出（WORKBENCH_KEEP_ALIVE=0 可关）；「退出服务」按钮优雅停机；app.py 改自建 uvicorn.Server 使纯服务模式同样可停。二次打开约 1 秒。

### 遗留（处置情况）
1/2. chat-resize 双滚动条/拖动不持久化 → 第二轮弃用该机制，消除。
3. 候选 TTL 30s——仍有效（common.py `_SUGGEST_TTL_SEC`）。
4. 已生成禁勾是提交时过滤非 UI 置灰——仍有效。
5. Gradio DOM 坑（Dropdown 无 type 属性、隐藏视图 .first 命中）——已录入 ARCHITECTURE.md 第 1/2/4 条。
6. exe 未重新打包——仍有效。
7. pytest.ini 无 p3 marker，tests/ 残留 @pytest.mark.p3 会打 warning（不属于工作台，未处理）。
