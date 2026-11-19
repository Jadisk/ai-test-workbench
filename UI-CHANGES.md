# 工作台迭代报告（第八轮 · 修复 · 2026-11-19 · v1.8）

> 写给下一轮迭代的规则：①本文件记录**工作台全部迭代**（UI 与业务修复），仅保留最近两轮详报，更早轮次删除——「仍有效」的遗留并入文末「历史遗留汇总」，其余不保留；通用坑与经验一律沉淀进 ARCHITECTURE.md 坑清单。②改动前先读 `ARCHITECTURE.md`（文件地图 + 坑清单）。③迭代收尾顺序：更新本文件 → `git commit + push origin main` → **重新打包 exe**（命令见 CLAUDE.md）。**commit message 以版本号开头**：格式 `v1.N：摘要`，N 为迭代轮次（第八轮 → `v1.8`，以此类推）。回滚用 `git revert`（仓库在 `workbench/`）。

## 本轮改了什么（背景：三个用户报告——用例生成页双滚动条、聊天发送慢约 10 秒且无回复、脚本生成任务失败）

### 问题 2 + 3 同根因：claude 子进程经 `.cmd` shim 调用，多行 prompt 被截断且后续 CLI 参数全部丢失（坑 15）

`resolve_claude_exe()` 解析到 fnm 的 npm shim `claude.cmd`，此前 prompt 以 argv 传递（`claude -p <多行长文本> --output-format stream-json --permission-mode bypassPermissions`）。cmd.exe 按行解析命令行：**prompt 只送达前几行，其后所有参数一并丢失**。实证（exe 任务日志）：claude 自述「您的消息在冒号后截断」（缺「用例编号：HOME_FUNC_002 等」行）；模型回复走 stdout 非 JSON 行被归为 stderr、无 result 事件 → `result_text=null` → 任务 `status=error`；权限模式丢失 → Bash 全要审批、headless 挂起 2 分钟后模型放弃。聊天「无回复」同源（回复进状态行不进聊天流），叠加第一因素：21:10 首次 exe 启动时 fnm 路径不在双击环境 PATH，CLI 未找到直接抛 FileNotFoundError（仅状态行/toast 提示，用户不可感知）。

修复：
1. **prompt 改走 stdin**（claude_api.py）：`claude -p --output-format stream-json ...` 不带 prompt 参数，Popen 后写入 stdin 并关闭。多行/长 prompt 与参数丢失一并解决。
2. **启动失败进聊天流**：CLI 未找到等致命错误改 yield `fatal` 事件，聊天流显示 assistant 错误消息（不再只靠状态行）；jobs.py 日志、common.py 任务区渲染同步支持 fatal。

### 问题 2 的「发送慢约 10 秒」：首帧前无任何反馈

`stream_chat` 原来 append user 消息后不立即 yield，首帧要等 CLI 冷启动 + 模型首包（约 10 秒），用户以为没发出去而重发（chat_log 重复消息为证）。修复：进入即 yield 一帧（user 消息上屏 + assistant 占位「…」+ 状态「正在连接 claude…」）。

### 问题 1：用例生成页三层滚动（预览外框 + cm-scroller + 页面）收敛为单层（坑 16/17）

原布局：预览固定 `height: 620px`，任务区有内容后右列总高超视口 → 页面滚动 + 预览框双层内滚。方案 A 落地：视图加 `.cases-view` 类，Group 高度锚定视口、右列 flex 弹性、预览占剩余空间（544~618px 实测）、外框为唯一滚动宿主、CodeMirror 保持自然高全渲染。调试中连环踩坑（flex-wrap 横向换列、Gradio CSS 前缀副本致 @media 失效等）全部沉淀进 ARCHITECTURE.md 坑 16/17。

### 顺带：launcher.log 膨胀治理

Timer 每 2 秒 5-6 个轮询事件的 uvicorn.access 访问日志全量落盘（2 小时 257KB）。`_setup_file_logging` 中该 logger 降为 WARNING。

## 涉及文件
| 文件 | 改动 |
|---|---|
| workbench/claude_api.py | prompt 改 stdin 传递；`fatal` 事件；docstring 更新 |
| workbench/ui/chat.py | stream_chat 立即 yield 首帧；fatal 处理（错误进聊天流） |
| workbench/jobs.py | log_event 支持 fatal |
| workbench/ui/common.py | event_to_message / compact_progress_md 支持 fatal |
| workbench/launcher.py | uvicorn.access 日志降为 WARNING |
| workbench/ui/views_gen.py | 用例生成视图 Group 加 `cases-view` 类 |
| workbench/ui/__init__.py | 用例生成页弹性 CSS（cases-view 一组规则）；删除固定 620 规则 |
| workbench/UI-CHANGES.md / ARCHITECTURE.md | 本报告；坑 15/16/17；版本号提交规范（引导语③） |

## 验证结论
- **claude stdin 链路**（真实 CLI）：init/result 正常、多行暗号 PINEAPPLE-42 完整传达（截断场景复现验证）、stderr 0 行、is_error=False；CLI 即 `claude.cmd` shim——正是修复前的失效路径。
- **用例生成页** playwright 三档视口（1400×800 / 1120×640≈125% / 933×533≈150%）：页面 0 溢出（前两档）、预览单层滚动（外框滚、cm 不滚）、预览完整可见、生成按钮在视口内；150% 档见遗留 1。
- **聊天首帧**与 fatal 反馈：代码路径静态确认，待 exe 实测（首轮发送应立即上屏）。

## 遗留风险 / 下一轮注意
1. **150% 缩放档（逻辑视口 ~533px）页面仍溢出 ~65px**：根因是页面级固定开销（页头 103 + 侧边栏自然高 ~420 + 页脚）超过视口，页面级 Row 被侧边栏撑开——与聊天页第七轮遗留同源，根治需整页 flex 重构（牵连 7 视图，暂缓）。按钮可用、预览单层滚动，自然滚动兜底。
2. 聊天页 150% 档溢出遗留（第七轮遗留 1）与上述同根因，`--chat-reserved` 调整无法解决。
3. fnm 环境：双击 exe 的 PATH 来自 explorer 快照，装/换 node 版本管理器后旧常驻实例可能解析不到 claude CLI——现已通过 fatal 进聊天流可感知；彻底解决需 launcher 重试解析或解析 .cmd shim 直连 node。
4. `--chat-reserved` 160px 与 textarea 限高公式的 420px 校准值不变（见第七轮遗留 3）。

---

## 上一轮概要（第七轮 · 修复 · UI · 2026-11-19）
- 背景输入内容多时发送/贴文件按钮被顶出视口：textarea autoresize 内联 height（封顶 12 行 ~255px）+ styler flex item 实为 `.form` 包装。修复仅 CSS：`.chat-view textarea { max-height: min(220px, calc(100vh - 420px)) }` + `.chat-view .form { flex-shrink: 0 }`（细节在坑 14）。
- 验证：三档视口灌满输入框按钮均在视口内；exe 实测手动发送链路通过、claude 回复流式正常。

---

## 历史遗留汇总（各轮中仍有效的项；坑均在 ARCHITECTURE.md）
- `--chat-reserved: 160px`（聊天弹性布局预留高）按当前字体渲染校准，出现 ±几px 页面滚动时优先调它（textarea 限高公式的 420px 与它联动）。
- Dropdown 自动预选后刷新列表，选中项与预览可能短暂不一致（影响小）。
- @ 联想候选 TTL 30 秒（common.py `_SUGGEST_TTL_SEC`）。
- 脚本生成「已生成禁勾」是提交时过滤而非 UI 置灰。
- 用例生成左列下方留白（左列内容仅 4 个组件）——确认过的方案，若想填充可加说明块。
- 预览对非标准用例 Excel（无 4 个关键表头）回退显示全部 12 列 → 容器内横滚兜底（行为可预期）。
- 视图懒挂载后 Gradio 渲染 sticky 表头 + 数据两个 table（th 重复两组）——验证选择器按表头文本去重。
- 多窗口模型：第一个 exe 进程持有服务，后续双击均为复用窗口（进程内无服务引用）；复用窗口点「退出服务」只能关自己、停不掉后台服务——彻底退出要在主窗口操作（用户确认不改，留意即可）。
- exe 模式 data 落盘在 `dist/测试工作台/_internal/workbench/data/`（与开发模式 `workbench/data/` 不同），查历史任务先确认模式。
- exe 零输出挂死（第六轮）：根因未闭环转观测闭环（坑 13 观测入口）；2026-11-19 exe 实测未复现。
