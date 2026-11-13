# 工作台迭代报告（第六轮 · 修复 · 业务 · 2026-11-13）

> 写给下一轮迭代的三条规则：①本文件记录**工作台全部迭代**（UI 与业务修复），仅保留最近两轮详报，更早轮次删除——「仍有效」的遗留并入文末「历史遗留汇总」，其余不保留；通用坑与经验一律沉淀进 ARCHITECTURE.md 坑清单。②改动前先读 `ARCHITECTURE.md`（文件地图 + 坑清单）。③迭代收尾顺序：更新本文件 → `git commit + push origin main` → **重新打包 exe**（命令见 CLAUDE.md）。回滚用 `git revert`（仓库在 `workbench/`）。

## 本轮改了什么（背景：exe 模式任务零事件卡死）

用户 exe 实测脚本生成任务：面板「等待事件流」10+ 分钟，claude 子进程活着但 stdout/stderr 零字节（PID 15244 实证）。排查证据链：CLI/网络/认证正常（终端 headless 秒回）→ stdin 挂起假设证伪（claude 对无数据 stdin 有 3 秒兜底）→ cwd/PROJECT_ROOT 正确 → pythonw / `SetStdHandle(NULL)` 模拟均不复现 → **根因未锁定**（疑 exe 引导层或安全软件干预），转为观测闭环策略。

### 1. claude_api.py：stdin=DEVNULL + stderr 可观测
`Popen` 显式 `stdin=subprocess.DEVNULL`（不继承父进程句柄，兜底 windowed exe 句柄问题，无害实践）；stderr 排空线程挂到实例（`self._stderr`），新增 `stderr_lines()` 暴露收集内容。

### 2. jobs.py：stderr 落盘 + 手动停止改中性状态
- `_run_claude` 的 `finally` 把 claude stderr 尾部（10 行）落任务日志——正常/异常/停止三路径全覆盖，**下次零输出复现时这里有直接证据**。
- `stop()` 设 `status="stopped"`（此前只杀进程不设状态，收尾线程按 `result_text is None` 覆盖为 error → 面板红标「出错」）；claude/pytest 两个收尾线程见到 `stopped` 不再覆盖。pytest 被手动停止同样受益。
- 任务面板 result 行：停止显示「（任务已手动停止，未产出结果）」，徽章显示「已停止」（common.py）。

### 3. launcher.py：启动自检
服务启动时把 claude CLI 解析路径与存在性落 launcher.log（窗口模式与纯服务模式两处启动点），exe 环境差异排查锚点。

## 涉及文件
| 文件 | 改动 |
|---|---|
| workbench/claude_api.py | stdin=DEVNULL；`_stderr` 暴露 + `stderr_lines()` |
| workbench/jobs.py | stderr 落盘（finally）；stop 设 stopped；两收尾线程 stopped 不覆盖 |
| workbench/ui/common.py | 面板 stopped 的 result 文案 |
| workbench/launcher.py | `_log_claude_check` 启动自检 ×2 |
| workbench/ARCHITECTURE.md | 坑 13（exe 零输出挂死观测入口）、坑 4/11 第五轮修正 |
| workbench/UI-CHANGES.md | 本报告 |

## 验证结论
- 接口/导入链验证过（`stderr_lines()` 未迭代安全、`status_badge('stopped')='已停止'`、launcher 语法）；NULL stdin 句柄下 claude 回流正常（stdin 假设证伪的实验依据）。
- **exe 根因未闭环**：三种模拟均不复现，需重打包后用户实测——正常则 DEVNULL 歪打正着；再卡死则任务日志尾部必有 claude stderr 原话，按证据继续。

## 遗留风险 / 下一轮注意
1. **exe 零输出根因未定位**——复现时先看任务日志 stderr 尾部 + launcher.log 自检行（坑 13）。
2. stderr 落盘发生在任务结束后——零输出挂死时需手动停止（或进程退出）才能看到内容。

---

## 上一轮概要（第五轮 · UI · 提交 ddb9dea · 2026-11-13）
- 脚本生成 Excel 预览「4 列精简」：仅保留编号/优先级/测试步骤/预期结果，CSS 去 860px 强制宽、列宽按内容分配（实测 79/62/179/189px），无横滚；窄列 min-width 56px 防表头竖排。
- 修复预览表头显示列序号问题（gr.DataFrame 列名须拆 `headers` 参数，坑 11）。
- 坑 4 改写：隐藏视图懒渲染——初始 DOM 不存在，点侧边栏 `visible=True` 后才挂载，验证须先点击再等待。
- 验证惯例固化：标准验证脚本骨架（起服务→切视图→等待→断言）+ 诊断定序（截图 dump → stash 对照 → 深挖）进 ARCHITECTURE.md（提交 a5c9d56）。
- 验证 7 项断言全过；遗留「非标准 Excel 回退全列横滚兜底」已并入文末汇总。

---

## 历史遗留汇总（各轮中仍有效的项；坑均在 ARCHITECTURE.md）
- 预填后「手动发送」的 submit 链路未自动实测（会真调 claude CLI）——窗口模式首次使用留意。
- `--chat-reserved: 160px`（聊天弹性布局预留高）按当前字体渲染校准，出现 ±几px 页面滚动时优先调它。
- Dropdown 自动预选后刷新列表，选中项与预览可能短暂不一致（影响小）。
- @ 联想候选 TTL 30 秒（common.py `_SUGGEST_TTL_SEC`）。
- 脚本生成「已生成禁勾」是提交时过滤而非 UI 置灰。
- exe 打包后建议实测：窗口模式开窗 + 上下文页（ast 解析是为 frozen 场景修的）。
- 用例生成左列下方留白（左列内容仅 4 个组件）——确认过的方案，若想填充可加说明块。
- 1400×800 窗口下脚本生成解析后内容底 ~800+，页面轻微滚动（自然滚动模式，正常）。
- 预览对非标准用例 Excel（无 4 个关键表头）回退显示全部 12 列 → 容器内横滚兜底（行为可预期）。
- 视图懒挂载后 Gradio 渲染 sticky 表头 + 数据两个 table（th 重复两组）——验证选择器按表头文本去重。
- 多窗口模型：第一个 exe 进程持有服务，后续双击均为复用窗口（进程内无服务引用）；复用窗口点「退出服务」只能关自己、停不掉后台服务——彻底退出要在主窗口操作（用户确认不改，留意即可）。
- exe 模式 data 落盘在 `dist/测试工作台/_internal/workbench/data/`（与开发模式 `workbench/data/` 不同），查历史任务先确认模式。
