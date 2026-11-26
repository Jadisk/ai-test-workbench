# 工作台迭代报告（第十轮 · 修复 · 2026-11-26 · v1.10）

> 本轮目标：脚本生成统一经 `script-common` 调度，修正工作台与 SKILL 的 draft 产物口径冲突，并把“分类差异记录与维护评估”纳入固定流程。

## 本轮改了什么

### 根因

- 工作台脚本提示词直接读取 `script-func` / `script-ui`，绕过共有入口 `script-common`，导致 PERF、维护评估和最新共有判据无法保证进入上下文。
- 提示词要求“试运行完整输出落盘 `results/`”，与 SKILL 的生成期 `--draft` / `debug/` 契约冲突。
- 脚本生成后没有统一的分类差异记录与维护评估步骤，现场问题依赖人工再次发起讨论。

### 修复

1. `workbench/config.py`：`build_script_prompt` 改为先读 `script-common`，再按 FUNC/UI/PERF 前缀读取子技能；数量上限的具体入选/跳过规则交回 `script-common`。
2. 统一生成期试运行必须带 `--draft`，报告只落 `debug/`；明确不得产出 `results/` 正式归档。
3. 提示词增加分类差异记录与维护评估：写入 `docs/script-generation-findings.md`，按通用规则/B 站知识/上游预期/无需回流分类；AI 只提候选，不自动修改 SKILL。
4. `build_skill_prompt` 对脚本子技能快捷调用也先加载 `script-common`，避免聊天入口绕过共有真源。
5. `workbench/ARCHITECTURE.md`：新增“SKILL 路由与产物口径”稳定约束。

### 配套规则真源

- `.agents/skills/script-common/`：新增维护评估步骤与模板，资产表增加“适用范围”，POM 增加 `DOM_QUERIES`，自检增加维护评估项。
- `script-common/references/edge-cases.md`：补 popup、定位/URL API、直接/间接代理边界。
- `script-common/references/bili-env-notes.md`：补新标签页、有效卡片、搜索上限、频道页空正文边界；`bili-noise-whitelist.md` 增加来源证据门槛。
- `web-test-analysis` / `test-case-generation`：补归属复核清单与预期可判定门槛。
- `docs/script-generation-findings.md`：原日期记录改为滚动台账，并完成 16 项问题分类处置。

## 涉及文件

| 文件 | 改动 |
|---|---|
| `workbench/config.py` | 脚本提示词统一走 common，修正 draft/debug 口径，增加维护评估 |
| `workbench/ARCHITECTURE.md` | 新增 SKILL 路由与产物口径 |
| `workbench/UI-CHANGES.md` | 本轮报告 |
| `tests/test_workbench_config.py` | 提示词路由、draft 契约、维护评估回归 |
| `.agents/skills/script-common/` 及子技能 | 维护闭环、资产范围、POM/popup/断言规则 |
| `.agents/skills/web-test-analysis/`、`test-case-generation/` | 上游归属与预期可判定门槛 |
| `docs/script-generation-findings.md` | 滚动问题台账与分类处置 |

## 验证结论

- `tests/test_workbench_config.py`：4 项通过，覆盖统一入口、draft/debug 契约、维护评估与快捷调用。
- 环境冒烟 + 报告隐私/渲染 + PERF 运行时 + 提示词回归：共 34 项通过。
- `py_compile workbench/config.py tests/test_workbench_config.py`：通过。
- SKILL 资源指针已核对，`maintenance-review.md`、`edge-cases.md`、`bili-*.md` 与 `page-object-5-section.md` 均存在。
- 未运行新的 B 站在线全量用例；站点事实沿用 2026-11-26 现场记录，后续改版需复核。
- pytest 仅提示 `.pytest_cache` 写入权限警告，不影响测试结果。

## 遗留风险 / 下一轮注意

1. 工作台仍只提供 FUNC/UI 快捷入口；PERF 入口与自动门禁未在本轮扩展。
2. B 站站点事实带 2026-11-26 校准日期，后续改版仍需现场复核。
3. 空输入/空格搜索、XSS 过滤页、主导航范围三项上游口径仍开放，未通过改 SKILL 放宽断言。

---

# 工作台迭代报告（第九轮 · 修复 · 2026-11-20 · v1.9）

> 写给下一轮迭代的规则：①本文件记录**工作台全部迭代**（UI 与业务修复），仅保留最近两轮详报，更早轮次删除——「仍有效」的遗留并入文末「历史遗留汇总」，其余不保留；通用坑与经验一律沉淀进 ARCHITECTURE.md 坑清单。②改动前先读 `ARCHITECTURE.md`（文件地图 + 坑清单）。③迭代收尾顺序：更新本文件 → `git commit + push origin main` → **重新打包 exe**（命令见 CLAUDE.md）。**commit message 以版本号开头**：格式 `v1.N：摘要`，N 为迭代轮次（第九轮 → `v1.9`）；**同一天内的多轮迭代第三段递增**（`v1.9` → `v1.9.1` → `v1.9.2`…，次日恢复 `v1.N` 主线）。④**上游依赖问题优先评估直接升级**：遇到上游库的 bug（如 Gradio issue）先评估升级影响面（API 兼容 + 自定义 CSS/DOM 依赖 + 打包回归），可通过则直接升级并同步更新 requirements.txt（版本不默认钉死，升级评估优先于绕行 workaround）。回滚用 `git revert`（仓库在 `workbench/`）。

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
