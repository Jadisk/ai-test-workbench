# 工作台局部规范

本目录是独立 Git 仓库，负责 FastAPI + Gradio 工作台。根目录全局规则见 [../AGENTS.md](../AGENTS.md)；本文件只补充工作台专属约束，不重复全局规则。

## 适用范围与冻结边界

- 工作台业务修改一律暂缓，并登记到根目录 `workbench-TODO.md`。
- 目录迁移允许最小路径兼容：目录常量、pytest 目标、提示词和界面路径文案；不得顺带改业务逻辑、UI 行为或扩展功能。
- 当前不保留 `CLAUDE.md`。它对工作台上下文与规则兼容的影响已登记 TODO，不在本轮改代码补偿。

## 启动

```bash
python -m workbench.app
python workbench\launcher.py
workbench\dist\测试工作台\测试工作台.exe
```

窗口模式已有实例时复用，不重复启动；窗口关闭后服务默认常驻。设 `WORKBENCH_WINDOW=0` 可强制纯服务模式。

## 改动前必读

- 修改代码前先读 `ARCHITECTURE.md`，按其中 UI 文件地图、改动类型 → 最小读取集、事件绑定模板和 Gradio DOM 坑清单操作，避免全量扫描。
- 开始前读 `UI-CHANGES.md` 顶部最新一轮报告，确认已改内容与遗留风险。
- UI 改动通常只需 `ui/` 下对应视图文件与 `ui/__init__.py`，无需先读后端。

## 流水线路径契约

- 输入截图：`pipeline/01-screenshots/`
- 测试点：`pipeline/02-test-points/`
- 用例：`pipeline/03-test-cases/`
- 测试脚本：`pipeline/04-test-scripts/`
- 正式报告：`pipeline/05-results/reports/`
- 脚本截图：`pipeline/05-results/script-output/`
- 失败截图：本次运行目录的 `assets/`（正式为 `pipeline/05-results/reports/{时间戳}/assets/`，draft 为 `debug/scripts/assets/`）
- 历史失败截图画廊：`pipeline/05-results/screenshots/failures/`（与当前报告附件目录不一致，消费逻辑暂缓）
- 变异证据：`pipeline/05-results/mutation/`
- draft 报告：`debug/scripts/`
- 工作台临时文件：`debug/scratch/workbench/`

脚本生成提示词必须先读 `.claude/skills/script-common/SKILL.md`，再由 `script-common` 按 FUNC/UI/PERF 前缀调度子技能；工作台注册表只是快捷入口，不是动态技能发现器。生成期试运行统一带 `--draft`，报告只落 `debug/scripts/`；正式报告由下游执行产生。维护台账位于 `.agents/skills/script-common/references/script-generation-findings.md`。

## 迭代与交付

1. 更新 `UI-CHANGES.md`：本轮报告置顶，仅保留最近两轮详报；更早轮次仍有效的遗留并入文末汇总，其余删除。
2. 迭代中发现新的 Gradio DOM、组件行为、frozen/exe 等通用坑时，同步沉淀到 `ARCHITECTURE.md` 坑清单。
3. 提交信息以版本号开头：`v1.N：摘要`；同一天多轮使用 `v1.N.1`、`v1.N.2`，次日恢复 `v1.N`。
4. 提交并推送 `origin main`。
5. 代码有改动时重新打包 exe。

遇到上游库 bug，先评估直接升级的 API 兼容、自定义 CSS/DOM 依赖和打包回归影响；可通过则升级并同步 `requirements.txt`，不优先绕过。

## 打包

```bash
.venv/Scripts/pyinstaller workbench/workbench.spec --noconfirm --distpath workbench/dist --workpath workbench/build
```

打包前必须结束常驻服务进程。它持有 `dist/_internal/base_library.zip` 与 `launcher.log` 句柄时，PyInstaller 清理旧 dist 会报 `PermissionError: WinError 32`。用 PowerShell 将进程列表写入 UTF-8 文件后搜「测试工作台」，不要用中文 `tasklist /FI` 过滤；确认 PID 后用 `taskkill //F //PID <pid>` 结束。

## 运行模型与依赖

- Claude 与 pytest 任务各自互斥，同时各允许 1 个；任务记录在 `workbench/data/jobs/`，日志在 `workbench/data/logs/`，junitxml 在 `workbench/data/reports/`。
- 模型调用使用 headless `claude -p --output-format stream-json`，默认权限模式为 `bypassPermissions`，可用 `WORKBENCH_PERMISSION_MODE` 覆盖。
- 工具错误产生 `tool_error` 事件进入任务日志，用于证实或排除权限拒绝。
- exe 仍依赖本机 `.venv` 中的 pytest 与 claude CLI。
