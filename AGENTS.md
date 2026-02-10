# 仓库指南（Repository Guidelines）

## ?????????
- ?? PowerShell `Get-Content` ?????????????? `-Encoding UTF8`?

## 项目结构与模块组织
- `src/app/` 是后端主目录，入口为 `src/app/main.py`。
- 后端按层拆分：`core/`（配置、日志、常量）、`db/`（SQLAlchemy 模型与基类）、`modules/`（业务模块，如 `executor/`、`tasks/`、`emu/`、`web/`）。
- API 路由位于 `src/app/modules/web/routers/`，按功能拆分（如 `accounts.py`、`coop.py`、`dashboard.py`）。
- 前端（Vue 3 + Vite）位于 `frontend/src/`，页面在 `frontend/src/views/`，接口封装在 `frontend/src/api/`。
- 桌面端壳层（Electron）位于 `desktop/`，入口为 `desktop/main.js`。
- 设计文档在 `docs/`，图标与模板资源在 `assets/`。

## 构建、测试与开发命令
- 后端初始化：`python -m venv .venv && .venv\Scripts\pip install -r requirements.txt`
- 启动后端（开发模式）：`.venv\Scripts\python -m uvicorn app.main:app --app-dir src --reload --host 0.0.0.0 --port 9001`
- 后端辅助启动脚本：`powershell -ExecutionPolicy Bypass -File scripts/start-backend.ps1`
- 启动前端开发服务：`cd frontend && npm install && npm run dev`
- 构建前端：`cd frontend && npm run build`
- 启动桌面端：`cd desktop && npm install && npm run start`
- Windows 一键启动：`start.bat`

## 代码风格与命名规范
- Python 使用 4 空格缩进，遵循 PEP 8；公共函数优先补充类型标注。
- 提交前执行：`black src` 与 `flake8 src`。
- Python 命名：模块/函数用 `snake_case`，类用 `PascalCase`，常量用 `UPPER_SNAKE_CASE`。
- Vue 组件文件使用 `PascalCase`（如 `Dashboard.vue`）；API 模块按业务小写命名。

## 测试规范
- 后端测试框架为 `pytest`，配套 `pytest-asyncio` 与 `pytest-cov`。
- 运行测试：`.venv\Scripts\pytest`
- 覆盖率命令：`.venv\Scripts\pytest --cov=src --cov-report=term-missing`
- 新增测试建议放在 `tests/`，并镜像源代码路径，例如 `tests/modules/web/test_accounts.py`。
- 修复缺陷或调整 API 行为时，需补充对应回归测试。

## 提交与合并请求规范
- 提交信息遵循仓库现有约定：`feat(scope): ...`、`fix: ...`、`chore: ...`。
- 每次提交应聚焦单一变更，避免将后端、前端、文档的大量无关修改混在一起。
- PR 至少包含：变更说明、关联任务/Issue、已执行的验证命令；UI 变更需附截图或 GIF。
- 若涉及 `.env`、数据库模型或迁移，请在 PR 描述中明确说明影响范围。

## 安全与配置建议
- 首次开发请复制 `.env.example` 为 `.env`，严禁提交密钥与凭据。
- `data.db`、`logs/`、`putonglogindata/` 等目录视为本地运行产物，不应作为业务代码变更提交。
- 执行自动化任务前，先检查 ADB 与模拟器路径相关环境变量是否正确。

## 最新执行约定（2026-02）
- **调度链路优先级**：当前运行链路以 `ExecutorService + feeder` 为主；`simple_scheduler` 仍存在但仅作为兼容与回退逻辑，新增功能优先接入 `executor` 链路。
- **调度控制接口约定**：`/api/tasks/scheduler/start|stop|status` 统一表示运行时执行引擎（`feeder + executor`）控制；前端“启动/停止调度器”按钮等价于“启动/停止执行引擎”。
- **legacy 接口废弃**：`simple_scheduler` 启停接口已废弃，仅保留兼容诊断（`/api/tasks/simple-scheduler/*`）；严禁在新功能中调用或依赖 legacy 调度行为。
- **任务配置更新规则**：`/api/accounts/{id}/task-config` 必须采用“默认配置 + 现有配置 + 本次提交”的合并策略，禁止用默认值直接覆盖，避免“未勾选任务被重新启用”。
- **Pydantic 用法**：任务配置更新使用 `model_dump(exclude_unset=True)`；若请求体无有效字段，应返回“未变更”并保持原配置。
- **任务启用判定**：调度时仅 `enabled is True` 视为启用，禁止使用宽松默认值（如 `get(..., True)`）导致误触发。
- **弥助任务约定**：`simple_scheduler` 已补齐“弥助”时间触发、任务映射、`next_time` 回写与优先级（65）；排查弥助问题时优先检查这四处逻辑是否一致。
- **仪表盘队列数据源**：`/api/dashboard` 与 `/api/stats/realtime` 优先使用 `executor_service.queue_info()` / `running_info()`，仅在无数据时回退旧预览。
- **UI 启动/跳转策略**：任务模块调用 UI 时统一走 `UIManager.ensure_game_ready()`：未启动→启动；已启动且可识别 UI→UI 跳转；异常/未知 UI→重启后再进庭院。
- **ENTER 点击规则**：所有模拟器分辨率固定为 `960x540`，检测到 `ENTER` 后统一点击固定坐标 `(487, 447)`，不再使用模板中心点。
- **账号抓取页删除能力**：已提供“删除登录数据”按钮；后端接口 `DELETE /api/account-pull/device-login-data/{emulator_id}` 默认仅删除 `shared_prefs`，`clientconfig` 需显式参数开启删除。

## 执行沟通约定
- **沟通步骤约定**：执行任何排查、修改、验证动作前，需先用一句话说明本步目的，再进行具体操作。
