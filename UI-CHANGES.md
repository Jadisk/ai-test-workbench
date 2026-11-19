# 工作台迭代报告（第七轮 · 修复 · 2026-11-19）

> 写给下一轮迭代的三条规则：①本文件记录**工作台全部迭代**（UI 与业务修复），仅保留最近两轮详报，更早轮次删除——「仍有效」的遗留并入文末「历史遗留汇总」，其余不保留；通用坑与经验一律沉淀进 ARCHITECTURE.md 坑清单。②改动前先读 `ARCHITECTURE.md`（文件地图 + 坑清单）。③迭代收尾顺序：更新本文件 → `git commit + push origin main` → **重新打包 exe**（命令见 CLAUDE.md）。回滚用 `git revert`（仓库在 `workbench/`）。

## 本轮改了什么（背景：输入内容多时发送/贴文件按钮被顶出视口）

用户报告：聊天页消息内容较多时，发送和贴文件按钮被顶掉，消息无法发出。根因有两个（坑 14）：

1. 输入框 textarea 的前端 autoresize 按内容持续改写**内联 height**（封顶 max_lines=12，约 255px），聊天弹性布局余量不足时把组件底部的按钮行顶出视口；
2. 弹性布局下让位本应由 chatbot 吸收，但 styler 的 flex item 实为输入框外层的 `.form` 包装——form 被压缩时内容按自然高度从 form 里溢出画到容器外，按钮反而被顶开。

### 修复（仅 CSS，`ui/__init__.py` 聊天视图规则）

- `.chat-view textarea { max-height: min(220px, calc(100vh - 420px)) }`：max-height 与内联 height 独立生效（实际渲染高取 min，无需 !important），大窗口 220px 封顶、小视口连续收紧；超限后 textarea 自身滚动（autoresize action 恒设 overflowY:scroll）。
- `.chat-view .form { flex-shrink: 0 }`：输入框不参与 flex 收缩，空间不足时让位全部由 chatbot 吸收（min-height 160 兜底）。

## 涉及文件
| 文件 | 改动 |
|---|---|
| workbench/ui/__init__.py | 聊天视图 CSS：textarea 限高 + .form flex-shrink:0 |
| workbench/ARCHITECTURE.md | 坑 14（flex item 是 .form 非 .block、textarea autoresize 内联 height） |
| workbench/UI-CHANGES.md | 本报告 |

## 验证结论
- playwright 实测三档视口（1400×800 / 1120×640≈125% DPI / 933×533≈150% DPI）灌满输入框（30 行文本）：发送/贴文件按钮全部在视口内（inViewport=true），styler 无溢出；125% 档修复前按钮 bottom 644 > 视口 640（FAIL），修复后 572（PASS）。
- 100% 档全页截图确认：输入框内部滚动（显示尾部行），回形针与发送按钮完整可见，页脚正常。
- exe 模式实测（2026-11-19 用户）：预填后「手动发送」链路通过，claude 回复流式显示并正常完成（第六轮零输出挂死未复现）；「项目上下文」页显示正常。

## 遗留风险 / 下一轮注意
1. 150% 缩放（逻辑视口 ~533px）下 chatbot min 160 + 页头占满可用高，页面整体溢出 ~65px 自然滚动——按钮仍可用，属可接受的极端场景；若要消除需同步下调 chatbot min-height 与 `--chat-reserved`。
2. 小窗口 + 多附件组合：附件缩略条（thumbnails）出现会再增 ~80px，可能溢出——页面滚动兜底，必要时可给缩略条单独限高。
3. `--chat-reserved: 160px` 与 textarea 限高公式中的 420px 均按 100% 缩放字体渲染校准，改字号/页头后需同步。

---

## 上一轮概要（第六轮 · 修复 · 业务 · 2026-11-13）
- 背景 exe 模式任务零事件卡死：claude_api.py `stdin=subprocess.DEVNULL` + stderr 收集（`stderr_lines()`）；jobs.py stderr 尾部落任务日志（finally 全路径覆盖）、手动停止改中性 `stopped` 状态且收尾线程不覆盖；common.py 停止态文案；launcher.py 启动自检 claude CLI 路径落 launcher.log ×2。
- exe 零输出根因未闭环，转观测闭环策略（观测入口沉淀于坑 13；2026-11-19 exe 模式实测未复现）。
- 验证：接口/导入链验证过；NULL stdin 句柄下 claude 回流正常（stdin 假设证伪）。

---

## 历史遗留汇总（各轮中仍有效的项；坑均在 ARCHITECTURE.md）
- `--chat-reserved: 160px`（聊天弹性布局预留高）按当前字体渲染校准，出现 ±几px 页面滚动时优先调它（textarea 限高公式的 420px 与它联动，见第七轮遗留 3）。
- Dropdown 自动预选后刷新列表，选中项与预览可能短暂不一致（影响小）。
- @ 联想候选 TTL 30 秒（common.py `_SUGGEST_TTL_SEC`）。
- 脚本生成「已生成禁勾」是提交时过滤而非 UI 置灰。
- 用例生成左列下方留白（左列内容仅 4 个组件）——确认过的方案，若想填充可加说明块。
- 1400×800 窗口下脚本生成解析后内容底 ~800+，页面轻微滚动（自然滚动模式，正常）。
- 预览对非标准用例 Excel（无 4 个关键表头）回退显示全部 12 列 → 容器内横滚兜底（行为可预期）。
- 视图懒挂载后 Gradio 渲染 sticky 表头 + 数据两个 table（th 重复两组）——验证选择器按表头文本去重。
- 多窗口模型：第一个 exe 进程持有服务，后续双击均为复用窗口（进程内无服务引用）；复用窗口点「退出服务」只能关自己、停不掉后台服务——彻底退出要在主窗口操作（用户确认不改，留意即可）。
- exe 模式 data 落盘在 `dist/测试工作台/_internal/workbench/data/`（与开发模式 `workbench/data/` 不同），查历史任务先确认模式。
