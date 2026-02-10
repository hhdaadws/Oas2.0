# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

中文回答

## 开发命令

### 环境初始化
```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

### 启动后端（Windows）
```powershell
# PowerShell
$env:PYTHONPATH="src"; venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 9001

# PowerShell（开发热重载）
$env:PYTHONPATH="src"; venv\Scripts\uvicorn app.main:app --reload --host 0.0.0.0 --port 9001

# CMD
set PYTHONPATH=src && venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 9001
```

也可以用 `--app-dir src` 代替 `PYTHONPATH=src`：
```bash
venv\Scripts\python -m uvicorn app.main:app --app-dir src --reload --host 0.0.0.0 --port 9001
```

**PYTHONPATH=src 是必须的**，否则 `from app.xxx` 导入会失败。

### 启动前端
```bash
cd frontend && npm install && npm run dev
```
前端默认端口 5173，后端端口 9001，CORS 已配置 `allow_origins=["*"]`。

### 数据库迁移
```bash
alembic upgrade head
# 或 Windows 脚本
powershell -ExecutionPolicy Bypass -File scripts/migrate.ps1
```

### 测试
```bash
venv\Scripts\pytest                                     # 全部测试
venv\Scripts\pytest tests/modules/executor/test_service.py  # 单个文件
venv\Scripts\pytest -k "test_feeder"                    # 按名称匹配
venv\Scripts\pytest --cov=src --cov-report=term-missing # 覆盖率
```

`tests/conftest.py` 会自动将 `src/` 加入 `sys.path`。测试目录结构镜像源码路径。

### 代码风格
```bash
black src
flake8 src
```

## 架构总览

阴阳师手游多账号自动化系统。通过 MuMu 模拟器运行多个游戏实例，用视觉识别（OCR + 模板匹配）驱动 UI 操作，调度器自动分发任务到各个模拟器 Worker。

### 调度执行链路（核心数据流）

```
Feeder（扫描器）→ ExecutorService（中央队列）→ WorkerActor（模拟器执行）
```

1. **Feeder**（`src/app/modules/tasks/feeder.py`）：每 10 秒循环扫描所有 `status=1, progress=ok` 的 GameAccount，检查 `task_config` 中各任务的 `enabled` 和 `next_time`，将到期任务收集为 `TaskIntent` 列表，按优先级排序后批量推送给 ExecutorService。同一账号的任务打包成一个 batch。签名去重机制防止重复入队。
2. **ExecutorService**（`src/app/modules/executor/service.py`）：中央任务队列。按 `PendingBatch`（account_id 粒度）管理待执行批次。异步 dispatcher 循环找到空闲 Worker 后将 batch 提交。同一 account 同时只能有一个 batch 在执行（`_running_accounts` 互斥）。失败批次最多重试 1 次。
3. **WorkerActor**（`src/app/modules/executor/worker.py`）：每个模拟器绑定一个 Worker。通过 `inbox` 队列接收批次，串行执行其中的每个 `TaskIntent`。同批次任务共享 `EmulatorAdapter` 和 `UIManager` 实例，避免重复启动游戏。

### 任务执行器

- **BaseExecutor**（`src/app/modules/executor/base.py`）：抽象基类，定义 `prepare() → execute() → cleanup()` 三阶段流程
- 具体执行器：`CollectLoginGiftExecutor`、`DelegateHelpExecutor` 等
- 未实现的任务类型使用 `MockExecutor`（直接返回成功）

### UI 系统

```
UIRegistry → UIDetector → UIGraph → UIManager → PopupHandler
```

- **UIRegistry**（`src/app/modules/ui/registry.py`）：注册所有已知 UI 界面的模板图片和匹配参数
- **UIDetector**（`src/app/modules/ui/detector.py`）：截图后通过模板匹配识别当前处于哪个界面（返回 `UIDetectResult`）
- **UIGraph**（`src/app/modules/ui/graph.py`）：UI 界面之间的有向图，BFS 规划从当前界面到目标界面的导航路径。每条边（`Edge`）包含 `Action` 列表（tap/swipe/sleep/tap_anchor）
- **UIManager**（`src/app/modules/ui/manager.py`）：对外统一入口。`ensure_game_ready()` 是任务执行前的标准调用（未启动→启动；已启动→UI 跳转到庭院；异常→重启）。`ensure_ui(target)` 自动规划路径并逐步导航
- **PopupHandler**（`src/app/modules/ui/popup_handler.py`）：弹窗检测与关闭，每次 UI 操作前自动调用

所有模拟器分辨率固定 `960×540`。检测到 `ENTER` 界面后点击固定坐标 `(487, 447)`。

### 视觉与 OCR

- **模板匹配**（`src/app/modules/vision/template.py`）：OpenCV `matchTemplate` 用于 UI 识别
- **OCR**（`src/app/modules/ocr/`）：PaddleOCR 中文识别，支持 ROI 裁剪优化。用于读取游戏内资源数值（体力、金币等）
- 截图方式：`adb`（默认）或 `ipc`（MuMu IPC DLL）

### 数据模型关系

- `Email` 1→N `GameAccount`（一个邮箱最多 4 个游戏账号，不同区服）
- `GameAccount.task_config`（JSON 字段）：存储每种任务的 `enabled`、`next_time` 等配置。Feeder 直接读取此字段判断任务是否到期
- `GameAccount.progress`：`init`（初始化中）/ `ok`（正常）。Feeder 只扫描 `progress=ok` 的账号
- `Emulator` 1→1 `WorkerActor`（运行时绑定）
- `CoopAccount`：勾协账号库（独立于 GameAccount），通过 `CoopPool` 与 GameAccount 配对

### 任务类型与优先级

定义在 `src/app/core/constants.py`，中文 Enum 值：

| 优先级 | TaskType | 中文 | next_time 更新策略 |
|--------|----------|------|-------------------|
| 100 | INIT | 起号 | - |
| 90 | ADD_FRIEND | 加好友 | 明天 00:01 |
| 80 | COOP | 勾协 | 下一个 18:00/21:00 |
| 70 | DELEGATE | 委托 | 下一个 12:00/18:00 |
| 65 | DELEGATE_HELP | 弥助 | 下一个 00:00/06:00/12:00/18:00 |
| 60 | FOSTER | 寄养 | +6 小时 |
| 55 | COLLECT_LOGIN_GIFT | 领取登录礼包 | 自定义更新 |
| 50 | EXPLORE | 探索突破 | +6 小时 |
| 40 | CARD_SYNTHESIS | 结界卡合成 | 条件触发（explore_count≥40） |

### 前端

Vue 3 + Vite + Element Plus + Pinia。页面在 `frontend/src/views/`，API 封装在 `frontend/src/api/`。

**认证**：JWT，token 存储在 `localStorage` key `yys_auth_token`。`apiRequest()`（`frontend/src/config/index.js`）自动附加 `Authorization: Bearer <token>`。非 JSON 响应（如截图 PNG）需用原始 `fetch()` 手动带 token。

## 关键约定

### 调度链路
- **主链路**：`Feeder + ExecutorService`，`simple_scheduler` 仅作为兼容回退，新功能禁止接入
- `/api/tasks/scheduler/start|stop|status` 控制的是 Feeder + ExecutorService，不是 simple_scheduler

### 任务配置更新
- `task_config` 更新必须采用"默认配置 + 现有配置 + 本次提交"的合并策略，禁止用默认值覆盖
- 使用 `model_dump(exclude_unset=True)` 获取请求体有效字段
- 任务启用判定：仅 `enabled is True` 视为启用，禁止宽松默认值

### 休息策略
- 全局休息时间 0:00-6:00（`GLOBAL_REST_START`/`GLOBAL_REST_END`）
- 每日随机休息 2-3 小时（`RestPlan` 由 Feeder 自动生成）

### 账号抓取
- 游戏渠道包名：`com.netease.onmyoji.wyzymnqsd_cps`
- 抓取数据源：`shared_prefs`（需 adb root）+ `clientconfig`
- 保存到 `gouxielogindata/` 或 `putonglogindata/` 目录