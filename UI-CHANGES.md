# 工作台迭代报告（第十一轮 · 最小路径兼容 · 2026-11-26 · v1.11）

> 本轮目标：让工作台文件选择、pytest 目标、提示词和界面文案跟随项目 `pipeline/` 目录迁移；不改变业务逻辑、UI 行为或功能边界。

## 本轮改了什么

### 活跃路径映射

| 用途 | 工作台路径 |
|---|---|
| 输入截图 | `pipeline/01-screenshots/` |
| 测试点 | `pipeline/02-test-points/` |
| 测试用例 | `pipeline/03-test-cases/` |
| 测试脚本 | `pipeline/04-test-scripts/` |
| 失败截图 | 本次运行 `assets/`（正式为 `pipeline/05-results/reports/{时间戳}/assets/`，draft 为 `debug/scripts/assets/`） |
| 历史失败截图画廊 | `pipeline/05-results/screenshots/failures/`（保留原扫描逻辑） |
| 脚本截图 | `pipeline/05-results/script-output/` |
| 正式运行报告 | `pipeline/05-results/reports/` |
| 工作台临时文件 | `debug/scratch/workbench/` |
| 生成期草稿报告 | `debug/scripts/` |

### 兼容改动

1. `workbench/config.py`：目录常量切换到上述映射；SKILL 描述、示例、分析/用例/脚本提示词同步新路径。生成期 `--draft` 仍只落 `debug/scripts/`，正式报告不得在生成期写入；维护台账指向技能参考目录。
2. `workbench/ui/views_ops.py`：全量 pytest 目标改为 `pipeline/04-test-scripts/`；运行、报告、失败截图区块的路径文案同步更新；运行结果文件不再宣称包含 SKILL 试运行产物。
3. `workbench/ui/views_gen.py`、`ui/chat.py`、`ui/common.py`、`pytest_api.py`、`jobs.py`：文件选择提示、@ 引用示例、脚本输出说明、目录注释、默认 pytest 标题与结果落盘文案同步新路径。
4. `pipeline/04-test-scripts/test_workbench_config.py`：新增目录常量与生成提示词路径断言，并保留 draft、SKILL 路由和维护评估契约。
5. `workbench/ARCHITECTURE.md`：新增活跃产物路径表，验证脚本与调试截图示例同步到 `debug/scratch/workbench/`、`debug/screenshots/`。

### 明确未改

- API URL key（`test-points`、`test-cases`、`tests`、`results`、`failures`）保持不变，仅其指向目录随常量迁移。
- 未改失败截图画廊的扫描/展示逻辑；已知画廊目录与报告 `assets/` 产物不一致问题继续暂缓。
- 未改 `CLAUDE.md` 相关代码；其缺失只影响工作台项目上下文展示/状态，继续暂缓。
- 未改业务规则、任务互斥、报告解析、截图采集或 UI 交互。

## 涉及文件

| 文件 | 改动 |
|---|---|
| `workbench/config.py` | 目录常量、SKILL 描述与生成提示词路径 |
| `workbench/ui/views_ops.py` | 全量 pytest 目标与运行/报告界面文案 |
| `workbench/ui/views_gen.py`、`ui/chat.py`、`ui/common.py`、`pytest_api.py`、`jobs.py` | 旧路径文案与注释 |
| `pipeline/04-test-scripts/test_workbench_config.py` | 路径与提示词契约断言 |
| `workbench/AGENTS.md`、`ARCHITECTURE.md`、`UI-CHANGES.md` | 局部规范、活跃路径与本轮报告 |
| `workbench-TODO.md` | 旧提示词冲突标记已解决，登记两项暂缓事项并修正资料路径 |

## 验证结论

- `.venv/Scripts/python.exe -m py_compile`：7 个改动 Python 文件通过。
- 工作台配置与环境兼容回归：9 项通过；本地 draft 全链路回归：39 项通过；变异注入回归：64 项通过。
- 全量 collect-only：52 项收集成功，报告产物变化 0；draft 报告 `draft=true`、39 条用例结果齐全，调试脚本未被清单清理误删。
- 正式环境冒烟：2 项通过，时间戳报告与详情页齐全；历史失败运行验证到页级 console.log 与本次运行 `assets/` 截图。
- 本地浏览器逐页核验截图、测试点、用例、脚本、历史报告与项目上下文，均从迁移后的 `pipeline/` 目录读取；截图见 `debug/screenshots/workbench/migration-context-smoke.png`。
- 未运行 B 站在线全量用例；frozen exe 待本轮提交后重新打包并冒烟。

## 遗留风险 / 下一轮注意

1. `CLAUDE.md` 已不在项目根；工作台仍保留原项目上下文引用，需单独评估切换规则真源展示，不能混入目录兼容。
2. 失败截图画廊读取扁平 failures 目录，而正式报告截图位于各次运行的 `assets/`；修复涉及产物消费逻辑，需独立迭代。

---

# 工作台迭代报告（第十轮 · 补充修复 · 2026-11-26 · v1.10.2）

> 本轮目标：脚本生成统一经 `script-common` 调度，修正工作台与 SKILL 的 draft 产物口径冲突，把“分类差异记录与维护评估”纳入固定流程，并修复宿主代理环境下 frozen exe 无法启动的问题。

## 本轮改了什么

### 根因

- 工作台脚本提示词直接读取 `script-func` / `script-ui`，绕过共有入口 `script-common`，导致 PERF、维护评估和最新共有判据无法保证进入上下文。
- 提示词要求“试运行完整输出落盘 `results/`”，与 SKILL 的生成期 `--draft` / `debug/` 契约冲突。
- 脚本生成后没有统一的分类差异记录与维护评估步骤，现场问题依赖人工再次发起讨论。
- v1.10.1 打包后的 exe 在正常宿主环境启动时，被 `NO_PROXY` 中的 `[::1]` 触发 httpx 代理规则解析错误；清空代理虽可启动，但不能作为交付方案。

### 修复

1. `workbench/config.py`：`build_script_prompt` 改为先读 `script-common`，再按 FUNC/UI/PERF 前缀读取子技能；数量上限的具体入选/跳过规则交回 `script-common`。
2. 统一生成期试运行必须带 `--draft`，报告只落 `debug/`；明确不得产出 `results/` 正式归档。
3. 提示词增加分类差异记录与维护评估：写入 `docs/script-generation-findings.md`，按通用规则/B 站知识/上游预期/无需回流分类；AI 只提候选，不自动修改 SKILL。
4. `build_skill_prompt` 对脚本子技能快捷调用也先加载 `script-common`，避免聊天入口绕过共有真源。
5. `workbench/ARCHITECTURE.md`：新增“SKILL 路由与产物口径”稳定约束。
6. 新增 `workbench/env_compat.py`，在 `app.py` 导入 Gradio 前规范化 `NO_PROXY` / `no_proxy`：仅移除条目外层方括号，保留其它代理变量与条目语义，避免 `[::1]` 被 httpx 误解析为端口。

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
| `workbench/app.py`、`env_compat.py` | Gradio 导入前规范化带方括号的 IPv6 NO_PROXY 条目 |
| `workbench/ARCHITECTURE.md` | 新增 SKILL 路由与产物口径、启动期代理兼容坑 19 |
| `workbench/UI-CHANGES.md` | 本轮报告 |
| `tests/test_workbench_config.py` | 提示词路由、draft 契约、维护评估回归 |
| `tests/test_workbench_env_compat.py` | NO_PROXY 大小写、IPv6、空白与幂等回归 |
| `.agents/skills/script-common/` 及子技能 | 维护闭环、资产范围、POM/popup/断言规则 |
| `.agents/skills/web-test-analysis/`、`test-case-generation/` | 上游归属与预期可判定门槛 |
| `docs/script-generation-findings.md` | 滚动问题台账与分类处置 |

## 验证结论

- `tests/test_workbench_config.py`：4 项通过，覆盖统一入口、draft/debug 契约、维护评估与快捷调用。
- 环境冒烟 + 报告隐私/渲染 + PERF 运行时 + 提示词回归 + NO_PROXY 兼容：共 37 项通过。
- `py_compile workbench/env_compat.py workbench/app.py tests/test_workbench_env_compat.py`：通过。
- SKILL 资源指针已核对，`maintenance-review.md`、`edge-cases.md`、`bili-*.md` 与 `page-object-5-section.md` 均存在。
- 未运行新的 B 站在线全量用例；站点事实沿用 2026-11-26 现场记录，后续改版需复核。
- 回归使用 `-p no:cacheprovider`，规避既有 `.pytest_cache` 写入权限警告，不影响测试结果。
- v1.10.2 使用 PyInstaller 6.22.3 重新打包成功；exe 在保留宿主 `NO_PROXY=[::1]` 的正常环境下直接启动，HTTP 200，Playwright 切到“脚本生成”视图并通过 DOM/文案断言，浏览器 console 错误 0；截图见 `screenshots/debug/exe_smoke_v1_10_2.png`。

## 遗留风险 / 下一轮注意

1. 工作台仍只提供 FUNC/UI 快捷入口；PERF 入口与自动门禁未在本轮扩展。
2. B 站站点事实带 2026-11-26 校准日期，后续改版仍需现场复核。
3. 空输入/空格搜索、XSS 过滤页、主导航范围三项上游口径仍开放，未通过改 SKILL 放宽断言。

---

## 上一轮概要（第九轮 · 修复 · 2026-11-20 · v1.9）

> 写给下一轮迭代的规则：①本文件记录**工作台全部迭代**（UI 与业务修复），仅保留最近两轮详报，更早轮次删除——「仍有效」的遗留并入文末「历史遗留汇总」，其余不保留；通用坑与经验一律沉淀进 ARCHITECTURE.md 坑清单。②改动前先读 `ARCHITECTURE.md`（文件地图 + 坑清单）。③迭代收尾顺序：更新本文件 → `git commit + push origin main` → **重新打包 exe**（命令见 AGENTS.md）。**commit message 以版本号开头**：格式 `v1.N：摘要`，N 为迭代轮次（第九轮 → `v1.9`）；**同一天内的多轮迭代第三段递增**（`v1.9` → `v1.9.1` → `v1.9.2`…，次日恢复 `v1.N` 主线）。④**上游依赖问题优先评估直接升级**：遇到上游库的 bug（如 Gradio issue）先评估升级影响面（API 兼容 + 自定义 CSS/DOM 依赖 + 打包回归），可通过则直接升级并同步更新 requirements.txt（版本不默认钉死，升级评估优先于绕行 workaround）。回滚用 `git revert`（仓库在 `workbench/`）。

- **聊天粘贴文本兼容**：`MultimodalTextbox` 白名单加入 `text`，文本附件内容内联进 prompt，解决 Gradio issue #10630 导致的 `text/plain` 发送报错；通用坑见 ARCHITECTURE.md 坑 18。
- **用例生成页弹性布局**：预览改为占满右列剩余高度、外框唯一滚动宿主；150% DPI 档页面级双滚动条仍未根治，用户确认暂缓。
- **launcher.log 治理**：uvicorn access 日志降为 WARNING。
- **Gradio 6.x 升级评估未实施**：修复虽在上游，但需核对 breaking changes、重校准旧 DOM/CSS 并回归 7 视图三档视口；文字直接进输入框体验仍依赖升级。

---

## 上一轮概要（第八轮 · 修复 · 2026-11-19 · v1.8）
- **claude cmd shim 截断（坑 15）**：prompt 改走 stdin（`claude -p` 从 stdin 读）；fatal 事件进聊天流。根因：`claude.cmd` shim 经 cmd.exe 按行截断多行 prompt 且丢失 `--output-format`/`--permission-mode`。验证：多行暗号完整传达、stream-json 正常。
- **聊天首帧即时反馈**：stream_chat 进入即 yield（user 消息上屏 + 「正在连接 claude…」），不再等 CLI 首包 ~10 秒。用户 exe 实测发送已解决。
- **用例生成页弹性布局（坑 16/17）**：预览从固定 620px 改 flex 占满右列剩余高、外框唯一滚动宿主，消除三层滚动。150% DPI 档（逻辑视口 ~533px）页面仍溢出 ~65px（侧边栏自然高撑开页面级 Row）+ 预览内滚 = 用户 exe 实测「双滚动条」，**用户决定暂缓根治**（需整页 flex 重构）；100%/125% 档验证零溢出。
- **launcher.log 膨胀治理**：uvicorn.access 降 WARNING。
- **Gradio 升级评估（未实施）**：修复在 6.x；升级需 breaking changes 核对 + 基于旧 DOM 结构的全部自定义 CSS 重新校准（坑 7/8/11/14/16/17）+ 7 视图三档视口回归，预估为当轮修复的 5-10 倍工作量，维持不升级。

---

## 历史遗留汇总（各轮中仍有效的项；坑均在 ARCHITECTURE.md）
- **Gradio 6.x 与文字直接进输入框**：当前维持不升级，粘贴文本以 `paste.txt` 附件缩略显示、发送时内容内联。升级需核对 breaking changes、重校准依赖旧 DOM 的自定义 CSS，并回归 7 视图三档视口，必须作为独立迭代评估。
- **`/` 命令分支附件未内联**：SKILL 任务分支仍传附件路径；需要时复用 `workbench/ui/chat.py` 的 `_build_prompt_with_attachments`，不要另造一套组装逻辑。
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
