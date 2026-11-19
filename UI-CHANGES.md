# 工作台迭代报告（第九轮 · 修复 · 2026-11-20 · v1.9）

> 写给下一轮迭代的规则：①本文件记录**工作台全部迭代**（UI 与业务修复），仅保留最近两轮详报，更早轮次删除——「仍有效」的遗留并入文末「历史遗留汇总」，其余不保留；通用坑与经验一律沉淀进 ARCHITECTURE.md 坑清单。②改动前先读 `ARCHITECTURE.md`（文件地图 + 坑清单）。③迭代收尾顺序：更新本文件 → `git commit + push origin main` → **重新打包 exe**（命令见 CLAUDE.md）。**commit message 以版本号开头**：格式 `v1.N：摘要`，N 为迭代轮次（第九轮 → `v1.9`，以此类推）。回滚用 `git revert`（仓库在 `workbench/`）。

## 本轮改了什么（背景：聊天窗口粘贴大段文字报错「Invalid file type: text/plain. Please upload a file that is one of these formats: ['image']」，消息发不出去）

### 根因（Gradio issue #10630，5.50 仍复现）

粘贴大段文本时 Gradio 前端（`max_plain_text_length` 机制）会把文本转成 `paste.txt` 附件随消息提交；发送时后端 `MultimodalTextbox.preprocess` 按 `file_types=['image']` 校验 MIME，`text/plain` 不在白名单 → 直接 `raise Error` → **消息根本发不出去**（报错在 submit 校验，不在粘贴瞬间）。上游修复合入 Gradio 6.x，评估升级工作量（DOM/CSS 全量回归）过大，按用户确认维持不升级，采用白名单放宽方案。

### 修复（chat.py）

1. `MultimodalTextbox(file_types=["image", "text"])`：text 进白名单，`paste.txt` 附件过校验（前端 accept 同步为 `image/*, text/*`）。
2. 新增模块级 `_build_prompt_with_attachments(text, attachments)`：附件分流——图片类给绝对路径（模型读图），文本类（.txt/.md/.py 等）**内容直接内联进 prompt**（read_text 80k 截断兜底），模型无需再读盘。粘贴的大段文字完整到达模型。

### 体验说明（与「文字直接进输入框」的差异）

粘贴大段文本后，文字以 `paste.txt` **附件缩略**形态出现在输入框下方（不撑开输入框），发送后内容完整进 prompt。已向用户说明并确认接受；如后续要求「文字直接显示在输入框」，需升级 Gradio 6.x（独立迭代评估）。

## 涉及文件
| 文件 | 改动 |
|---|---|
| workbench/ui/chat.py | file_types 加 "text"；新模块级 `_build_prompt_with_attachments`（附件分流组装） |
| workbench/UI-CHANGES.md / ARCHITECTURE.md | 本报告；坑 18 |

## 验证结论
- **preprocess 单测**：旧白名单 `['image']` 复现报错（铁证）；新 `['image','text']` 接受 `text/plain` 附件。
- **组装函数单测** 4 场景全过：文本附件+文字（内联+暗号 MANGO-77 完整）、纯文本不变、仅文本附件（发送且内联）、图片附件（路径引用不内联）。
- 前端 accept 属性实测已反映 `image/*, text/*`。

## 遗留风险 / 下一轮注意
1. / 命令（SKILL 任务）分支的附件仍是路径引用方式（未内联）——粘贴文本 + /命令组合场景少，模型可读盘；若需要可复用 `_build_prompt_with_attachments`。
2. Gradio 升级（6.x）的完整评估见第八轮概要末尾；「文字直接进输入框」体验需升级才能实现。

---

## 上一轮概要（第八轮 · 修复 · 2026-11-19 · v1.8）
- **claude cmd shim 截断（坑 15）**：prompt 改走 stdin（`claude -p` 从 stdin 读）；fatal 事件进聊天流。根因：`claude.cmd` shim 经 cmd.exe 按行截断多行 prompt 且丢失 `--output-format`/`--permission-mode`。验证：多行暗号完整传达、stream-json 正常。
- **聊天首帧即时反馈**：stream_chat 进入即 yield（user 消息上屏 + 「正在连接 claude…」），不再等 CLI 首包 ~10 秒。用户 exe 实测发送已解决。
- **用例生成页弹性布局（坑 16/17）**：预览从固定 620px 改 flex 占满右列剩余高、外框唯一滚动宿主，消除三层滚动。150% DPI 档（逻辑视口 ~533px）页面仍溢出 ~65px（侧边栏自然高撑开页面级 Row）+ 预览内滚 = 用户 exe 实测「双滚动条」，**用户决定暂缓根治**（需整页 flex 重构）；100%/125% 档验证零溢出。
- **launcher.log 膨胀治理**：uvicorn.access 降 WARNING。
- **Gradio 升级评估（未实施）**：修复在 6.x；升级需 breaking changes 核对 + 基于旧 DOM 结构的全部自定义 CSS 重新校准（坑 7/8/11/14/16/17）+ 7 视图三档视口回归，预估为当轮修复的 5-10 倍工作量，维持不升级。

---

## 历史遗留汇总（各轮中仍有效的项；坑均在 ARCHITECTURE.md）
- **150% 缩放档双滚动条（用户确认暂缓）**：exe 窗口 1400×800 物理像素在 150% DPI 下逻辑视口 ~933×533，页面级固定开销（页头 103 + 侧边栏 ~420 + 页脚）超视口，页面级 Row 被侧边栏撑开溢出 ~65px + 页面内局部滚动并存。根治需整页 flex 重构（页面级 Row/侧边栏纳入视口约束，牵连 7 视图）。缓解备查（未验证）：exe 窗口最大化提高逻辑视口；launcher 默认尺寸按 DPI 反算。
- fnm 环境：双击 exe 的 PATH 来自 explorer 快照，装/换 node 版本管理器后旧常驻实例可能解析不到 claude CLI——fatal 已进聊天流可感知；彻底解决需 launcher 重试解析或解析 .cmd shim 直连 node。
- `--chat-reserved: 160px` 与 textarea 限高公式 420px 按 100% 缩放字体渲染校准，改字号/页头需同步。
- Dropdown 自动预选后刷新列表，选中项与预览可能短暂不一致（影响小）。
- @ 联想候选 TTL 30 秒（common.py `_SUGGEST_TTL_SEC`）。
- 脚本生成「已生成禁勾」是提交时过滤而非 UI 置灰。
- 用例生成左列下方留白（左列内容仅 4 个组件）——确认过的方案，若想填充可加说明块。
- 预览对非标准用例 Excel（无 4 个关键表头）回退显示全部 12 列 → 容器内横滚兜底（行为可预期）。
- 视图懒挂载后 Gradio 渲染 sticky 表头 + 数据两个 table（th 重复两组）——验证选择器按表头文本去重。
- 多窗口模型：第一个 exe 进程持有服务，后续双击均为复用窗口；复用窗口点「退出服务」停不掉后台服务——彻底退出要在主窗口操作（用户确认不改）。
- exe 模式 data 落盘在 `dist/测试工作台/_internal/workbench/data/`（与开发模式不同），查历史任务先确认模式。
- exe 零输出挂死（第六轮）：根因未闭环转观测闭环（坑 13 观测入口）；2026-11-19 exe 实测未复现。
