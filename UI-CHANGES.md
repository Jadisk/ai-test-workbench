# 工作台 UI 迭代报告（第四轮 · 2026-11-12）

> 写给下一轮迭代：本轮改动全景、涉及文件、验证结论、遗留风险。每轮报告置顶、上轮收编历史章节；回滚用 `git revert`（仓库在 `workbench/`）。改动前先读 `ARCHITECTURE.md`（文件地图 + Gradio DOM 坑清单）。

## 本轮改了什么

### 1. 用例生成页：预览加高至近满屏（views_gen.py + CSS）
预览组件（`preview-tall` 类）固定高度 **620px**（`height` 而非 `max-height`——后者是上限、内容短时组件变矮，见 ARCHITECTURE.md 坑 12）；右列 = 空状态任务区 74px + 预览 620px ≈ 694px ≈ 可视高 700。左列内容少被行内等高拉伸，下方自然留白。

### 2. 脚本生成页：解析前后左右列恒齐平（views_gen.py + CSS）
- **左列勾选列表占位**（`cases-placeholder` 类）：`min-height: 260px`（= 解析后网格限高），未解析时空列表保留高度；状态行初始改为提示文案「请先选择用例 Excel，点击「解析用例」后在此勾选」（解析后照旧被统计覆盖）。
- **右列 Excel 预览固定高 560px**（`.excel-preview` CSS）：未解析时右列底 759 vs 左列按钮底 737（左列被拉伸、留白 22px）；解析后左列长至 760 ≈ 759 齐平——两个状态都对齐，实测量化。

### 3. Excel 预览列宽放宽 + 横向滚动（views_gen.py + CSS）
- `column_widths` 百分比方案弃用——**实测 Gradio 5.50 的 column_widths 总宽超容器时会被等比缩放回容器宽**（864px→510px），永远不出横向滚动条（已录入 ARCHITECTURE.md 坑 11）。
- 改 CSS：`.excel-preview table { min-width: 860px }` + 容器 `overflow-x: auto`——表格恒 860px 宽，容器 ~510px，横向滚动时视口内 4~5 列同时可见（用户要求 4~7 列），每列比均分方案宽 30~50%。

## 涉及文件
| 文件 | 改动 |
|---|---|
| workbench/ui/views_gen.py | 用例生成预览 preview-tall 类；脚本生成 parse_status 初始提示、cases-placeholder 类、Excel 预览 excel-preview 类（去 column_widths） |
| workbench/ui/__init__.py | CSS：preview-tall 620 / cases-placeholder 占位 260 / excel-preview 高 560 + 表格 min-width 860 横滚 |
| workbench/ARCHITECTURE.md | 坑 11 扩充（无 height 参数、column_widths 缩放行为）、新增坑 12（max-height vs height 占位语义） |
| workbench/UI-CHANGES.md | 本报告 |

launcher.py / chat.py / views_ops.py / common.py / skill_advice.py 及后端未动。

## 验证结论（playwright headless msedge，1400×800 视口，9 项断言全过 + 截图目测）
- 聊天页 800 高无滚动（回归）；用例生成预览 620 固定高生效、右列 694px ≈ 可视高。
- 脚本生成未解析：提示文案在、勾选列表占位 260px、右列不塌（759 ≥ 按钮 737，留白 22px 属确认过的方案）。
- 真解析流程（点解析按钮，本地 openpyxl）：状态行统计更新、解析后左右下边界 760 vs 759（差 1px）、Excel 预览横向滚动可用（scrollWidth 860 > clientWidth 510）。
- 截图目测：Excel 列宽舒展（步骤/结果列内容完整横排）、整体布局协调。

## 遗留风险 / 下一轮注意
1. **Excel 预览表格固定 860px 宽**：列宽由浏览器表格布局按内容分配（已去 column_widths），超长内容列会更宽——若观感不佳可改回比例列宽 + min-width 组合。
2. 用例生成左列下方留白（左列内容仅 4 个组件）——确认过的方案，若想填充可加说明块。
3. 1400×800 窗口下脚本生成解析后内容底 ~800+，页面轻微滚动（自然滚动模式，正常）。

---

## 历史：2026-11-12 第三轮（提交 da6ff25）

### 改了什么
1. **窗口默认大小 1400×800**：上轮 1400×900 与更早 1432×913 仅差 32×13px（约 2%），用户实测「看不出变化」属预期非 bug；本轮按确认改 1400×800。聊天弹性布局自适应无需动。
2. **测试点分析预览挪位**：从「完善 SKILL」Accordion 双列右列挪到右列任务区下方（与用例生成同模式），Accordion 恢复单列竖排。
3. **两页预览限高**（`preview-scroll` 类，400px 框内滚动）：此前 `lines=18` 内容长会撑高组件拉长页面。
4. **脚本生成微调**：刷新按钮去 `size="sm"` 与解析用例同尺寸（40px）；第三行数量上限 `scale 1→2`（label 不换行）、显示全部 `scale 2→1`（换行）；Excel 预览裁剪前 7 列（`preview_xlsx` 加 `max_cols`）；`column_widths` 百分比防表头竖排（本轮弃用，见上）；预览 `max_height 320→220` 与左列未解析态对齐（本轮改 560 固定高，见上）。
5. **流程固化**（CLAUDE.md）：迭代开始先读 UI-CHANGES.md 顶部最新报告、结束后更新该文档并 commit + push——无需用户重复要求。（ARCHITECTURE.md 坑清单加第 11 条 DataFrame）

### 验证（当时 1400×800，11 项断言全过）
800 高聊天无滚动、预览初始内容+切换更新、限高生效、预览与任务区同列、按钮同高、Excel 预览有内容、cases-list 单列、上下文页无报错；预览下边界 458 vs 按钮 455（差 3px，当时未解析态）。

### 遗留（本轮处置随文标注）
1. Excel 预览高度对齐依赖内容超限——本轮改固定 height 560，消除。
2. 1400×800 在 1366×768 屏超屏钳制——仍有效。
3. exe 未重新打包——仍有效。

---

## 历史：2026-11-12 第二轮（提交 ea02134）

> 「进聊天预填」与三视图预览在本轮引入；Gradio Dropdown 自动预选第一项的坑在本轮发现并已录入 ARCHITECTURE.md 第 3 条。

### 改了什么
1. **窗口默认大小 1400×900**（后改 1400×800）。
2. **聊天视图弹性填满窗口**：弃用 `.chat-resize` 拖动机制；flex 作用于 Group 内层 `.styler`；`--chat-reserved: 160px` 实测校准；消息框 lines 2→5、max_lines=12。聊天视图是唯一锁高视图。
3. **三个生成视图补文件预览**：测试点分析/用例生成（gr.Code markdown）、脚本生成（gr.DataFrame）。**坑：Dropdown 加载时自动预选第一项**，change 只在 value 真变化时触发——预览初始 value 须对齐预选第一项。
4. **「进聊天讨论方案」改预填消息栏**：discuss_prefill 同步预填（保留附件），不自动发送；无建议预填基础引导（修复「只跳转」）；`build_chat_panel` 返回 dict 加 `"msg"`；运行中任务守卫删除。
5. **脚本生成三行重排**（本轮又微调宽度）。
6. **脚本运行 cases-list 类**（与 cases-grid 拆分）：一行一个、长名换行、限高 400、无横向滚动。
7. **提示文案清理**：去括号说明，保留 chromium 缺失 info。
8. **上下文页报错修复**：动态 import src.corebrowser 在 exe frozen 下必炸 → ast 静态解析三常量（ARCHITECTURE.md 坑 10）。
9. **CLAUDE.md 改 gr.Code**（复制按钮、可全选）。

### 验证（当时 1400×900，25 项断言全过）
聊天无滚动、联想可见、弹层可见、预览初始+切换、预填两分支、cases-list、上下文页、文案清理。

### 遗留（处置随文标注）
1. 预填后手动发送 submit 链路未自动实测——仍有效。
2. `--chat-reserved` 字体渲染 ±几px——仍有效。
3. Dropdown 预选后刷新列表短暂不一致——仍有效。
4. exe 未重新打包——仍有效。

---

## 历史：2026-11-12 第一轮（无 git 时代，改动在初始提交 3a691f1 内）

> 坑记录均已录入 ARCHITECTURE.md（Dropdown 无 type 属性、overflow 裁剪弹层等）。

### 改了什么
1. **恢复页面整体滚动**：根因 `.view-scroll` overflow 裁剪 Dropdown 弹层（「下拉没反应」）；删限高，局部滚动保留（shot-scroll/cases-grid/advice-table/task-result）。
2. **聊天页精简**：删新会话/滑块；@ 联想扩为项目根全扫描（30s TTL）+ `/` SKILL 联想。
3. **测试点分析**：修复 shots_radio change 未绑预览的真 bug；完善 SKILL 改 Accordion。
4. **脚本生成**：两排排版 + 已生成提交时强制过滤。
5. **脚本运行**：marker p0–p2；文件选择改 CheckboxGroup。
6. **结果报告**：区块顺序 历史运行→运行结果文件→失败截图。
7. **上下文页**：CLAUDE.md 默认折叠。
8. **服务常驻**：窗口关闭服务不退出（WORKBENCH_KEEP_ALIVE=0 可关）、「退出服务」按钮、app.py 自建 uvicorn.Server。

### 遗留（处置情况）
1/2. chat-resize 双滚动条/不持久化 → 第二轮弃用消除。
3. 候选 TTL 30s——仍有效。4. 已生成禁勾是提交时过滤——仍有效。
5. Gradio DOM 坑——已录入 ARCHITECTURE.md。
6. exe 未重新打包——仍有效。7. p3 marker 残留 warning（非工作台，未处理）。
