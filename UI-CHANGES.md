# 工作台 UI 迭代报告（第四轮 · 2026-11-12）

> 写给下一轮迭代的三条规则：①本文件**仅保留最近两轮**迭代详报，更早轮次删除——其中「仍有效」的遗留风险并入文末「历史遗留汇总」，其余不保留；通用坑与经验一律沉淀进 ARCHITECTURE.md 坑清单，不依赖本文件历史。②改动前先读 `ARCHITECTURE.md`（文件地图 + Gradio DOM 坑清单）。③迭代收尾顺序：更新本文件 → `git commit + push origin main` → **重新打包 exe**（pyinstaller，命令见 CLAUDE.md 工作台节）。回滚用 `git revert`（仓库在 `workbench/`）。

## 本轮改了什么

### 1. 用例生成页：预览加高至近满屏（views_gen.py + CSS）
预览组件（`preview-tall` 类）固定高度 **620px**（`height` 而非 `max-height`——后者是上限、内容短时组件变矮，见 ARCHITECTURE.md 坑 12）；右列 = 空状态任务区 74px + 预览 620px ≈ 694px ≈ 可视高 700。左列内容少被行内等高拉伸，下方自然留白。

### 2. 脚本生成页：解析前后左右列恒齐平（views_gen.py + CSS）
- **左列勾选列表占位**（`cases-placeholder` 类）：`min-height: 260px`（= 解析后网格限高），未解析时空列表保留高度；状态行初始改为提示文案「请先选择用例 Excel，点击「解析用例」后在此勾选」（解析后照旧被统计覆盖）。
- **右列 Excel 预览固定高 560px**（`.excel-preview` CSS）：未解析时右列底 759 vs 左列按钮底 737（左列被拉伸、留白 22px）；解析后左列长至 760 ≈ 759 齐平——两个状态都对齐，实测量化。

### 3. Excel 预览列宽放宽 + 横向滚动（views_gen.py + CSS）
- `column_widths` 百分比方案弃用——**实测 Gradio 5.50 的 column_widths 总宽超容器时会被等比缩放回容器宽**（864px→510px），永远不出横向滚动条（已录入 ARCHITECTURE.md 坑 11）。
- 改 CSS：`.excel-preview table { min-width: 860px }` + 容器 `overflow-x: auto`——表格恒 860px 宽，容器 ~510px，横向滚动时视口内 4~5 列同时可见，每列比均分方案宽 30~50%。

### 4. exe 重新打包
本轮起打包固化进收尾流程（此前仅 commit+push，exe 一直停留在初始提交前的旧代码）。dist 下 exe 现包含全部四轮改动。

## 涉及文件
| 文件 | 改动 |
|---|---|
| workbench/ui/views_gen.py | 用例生成预览 preview-tall 类；脚本生成 parse_status 初始提示、cases-placeholder 类、Excel 预览 excel-preview 类（去 column_widths） |
| workbench/ui/__init__.py | CSS：preview-tall 620 / cases-placeholder 占位 260 / excel-preview 高 560 + 表格 min-width 860 横滚 |
| workbench/ARCHITECTURE.md | 坑 11 扩充（无 height 参数、column_widths 缩放行为）、新增坑 12（max-height vs height 占位语义） |
| workbench/UI-CHANGES.md | 本报告（并按新规则压缩历史） |

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

## 上一轮概要（第三轮 · 提交 da6ff25 · 2026-11-12）
- 窗口默认 **1400×800**（更早 1432×913→1400×900 仅差 2%，用户实测无变化属预期，非 bug）。
- 测试点分析预览挪到右列任务区下方（与用例生成同模式），「完善 SKILL」Accordion 恢复单列。
- 两页文档预览限高 `preview-scroll`（400px 框内滚动，不撑长页面）。
- 脚本生成：解析/刷新按钮同尺寸；数量上限加宽（label 不换行）、显示全部变窄（换行）；Excel 预览裁剪前 7 列（`preview_xlsx` 加 `max_cols`）。
- 流程固化进 CLAUDE.md（迭代开始读上轮报告 / 结束更新文档并 push）。
验证 11 项全过；其「Excel 预览高度依赖内容超限」遗留已在本轮以固定 height 消除。

---

## 历史遗留汇总（第一、二轮中仍有效的项；其余内容已删，坑均在 ARCHITECTURE.md）
- 预填后「手动发送」的 submit 链路未自动实测（会真调 claude CLI）——窗口模式首次使用留意。
- `--chat-reserved: 160px`（聊天弹性布局预留高）按当前字体渲染校准，出现 ±几px 页面滚动时优先调它。
- Dropdown 自动预选后刷新列表，选中项与预览可能短暂不一致（影响小）。
- @ 联想候选 TTL 30 秒（common.py `_SUGGEST_TTL_SEC`）。
- 脚本生成「已生成禁勾」是提交时过滤而非 UI 置灰。
- tests/ 残留 `@pytest.mark.p3` 会打 unknown-marker warning（非工作台问题，未处理）。
- exe 打包后建议实测：窗口模式开窗 + 上下文页（ast 解析是为 frozen 场景修的）。
