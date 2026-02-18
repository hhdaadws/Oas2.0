# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

中文回答

另见 `AGENTS.md`（通用 AI 代理指南，含最新执行约定）。

## 开发命令

### 环境初始化
```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
cp .env.example .env  # 首次需复制，然后编辑 .env 填入本地配置
```

### 启动后端（Windows）
```powershell
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

辅助启动脚本：`powershell -ExecutionPolicy Bypass -File scripts/start-backend.ps1`

### 启动前端
```bash
cd frontend && npm install && npm run dev
```
前端开发端口 9000（`vite.config.js` 配置），后端端口 9001。Vite 已配置 `/api` → `http://127.0.0.1:9001` 和 `/ws` → `ws://127.0.0.1:9001` 代理。后端 CORS 已配置 `allow_origins=["*"]`。

构建前端：`cd frontend && npm run build`

### 一键启动
```bash
start.bat                    # Windows 一键启动（含 Electron 桌面端）
cd desktop && npm run start  # 仅启动 Electron 桌面壳
```

### 数据库
数据库使用 SQLite，启动时通过 `Base.metadata.create_all()` 自动建表（见 `src/app/db/base.py`）。`alembic` 在依赖中但项目目前无独立迁移目录，模型变更直接删库重建或手动 ALTER。

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

### 提交规范
提交信息格式：`feat(scope): ...`、`fix: ...`、`chore: ...`。每次提交聚焦单一变更。

### 打包发布
```bash
python build.py   # 一键打包：前端构建 → PyInstaller → 后处理
```
输出到 `dist/YYSAutomation/`。`build.py` 中的 `CONDA_ENV` 路径需根据本地环境修改。打包规范文件为 `yys_automation.spec`，PyInstaller 钩子在 `hooks/` 目录。

### Windows 注意事项
- PowerShell 读取文件时若出现乱码，使用 `-Encoding UTF8` 参数（如 `Get-Content -Encoding UTF8`）

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
- 具体执行器位于 `src/app/modules/executor/` 下，每个任务一个文件
- 未实现的任务类型使用 `MockExecutor`（直接返回成功）
- `worker.py` 的 `_run_intent()` 根据 `task_type` 选择执行器，`_compute_next_time()` 控制下次执行时间
- 执行器若需自定义 `next_time` 更新，需加入 `_EXECUTOR_HAS_OWN_UPDATE` 集合并实现 `_update_next_time()`
- **新增任务类型的完整指南见 `docs/add-new-task.md`**，涵盖常量、调度、执行器、API、前端 UI 全链路

### UI 系统

```
UIRegistry → UIDetector → UIGraph → UIManager → PopupHandler
```

- **UIRegistry**（`src/app/modules/ui/registry.py`）：注册所有已知 UI 界面的模板图片和匹配参数
- **UIDetector**（`src/app/modules/ui/detector.py`）：截图后通过模板匹配识别当前处于哪个界面（返回 `UIDetectResult`）
- **UIGraph**（`src/app/modules/ui/graph.py`）：UI 界面之间的有向图，BFS 规划从当前界面到目标界面的导航路径。每条边（`Edge`）包含 `Action` 列表（tap/swipe/sleep/tap_anchor）
- **UIManager**（`src/app/modules/ui/manager.py`）：对外统一入口。`ensure_game_ready()` 是任务执行前的标准调用（未启动→启动；已启动→UI 跳转到庭院；异常→重启）。`ensure_ui(target)` 自动规划路径并逐步导航
- **PopupHandler**（`src/app/modules/ui/popup_handler.py`）：弹窗检测与关闭，每次 UI 操作前自动调用
- UI 模板图片存放在 `assets/ui/templates/`，弹窗模板在 `assets/ui/` 根目录

所有模拟器分辨率固定 `960×540`。检测到 `ENTER` 界面后点击固定坐标 `(487, 447)`。

### 视觉与 OCR

- **模板匹配**（`src/app/modules/vision/template.py`）：OpenCV `matchTemplate` 用于 UI 识别
- **专项视觉检测器**（`src/app/modules/vision/`）：
  - `explore_detect.py` — 探索格子/光标检测
  - `tupo_detect.py` — 结界突破卡片检测
  - `yuhun_detect.py` — 御魂副本检测
  - `battle_lineup_detect.py` — 战斗阵容检测
  - `color_detect.py` — 基于颜色的 UI 元素检测
- **OCR**（`src/app/modules/ocr/`）：PaddleOCR 中文识别，支持 ROI 裁剪优化。启动时初始化 OCR 实例池（`ocr_pool_size` + `digit_ocr_pool_size`，默认各 2 个）
- 截图方式：`adb`（默认）或 `ipc`（MuMu IPC DLL）

### 线程池

`src/app/core/thread_pool.py` 提供两种全局线程池，将阻塞操作从 asyncio 事件循环 offload 出去：

- **I/O 池**（`get_io_pool()` / `run_in_io()` / `run_in_db()`）：ADB subprocess 调用、同步 DB 操作。大小自动计算 `max(8, emulator_count * 2 + 4)`，上限 32
- **计算池**（`get_compute_pool()` / `run_in_compute()`）：OpenCV 模板匹配、OCR。大小自动计算 `max(4, cpu_count // 2)`，上限 24
- 可通过 `.env` 的 `IO_THREAD_POOL_SIZE` / `COMPUTE_THREAD_POOL_SIZE` 手动覆盖

### 阵容系统

`src/app/modules/lineup/` 管理战斗阵容配置。`LINEUP_SUPPORTED_TASKS` 定义支持阵容的任务列表。执行器通过 `get_lineup_for_task(account.lineup_config, "任务名")` 获取分组和位置。

### 式神数据

`src/app/modules/shikigami/` 管理式神（角色）相关数据与逻辑。

### 数据模型关系

- `Email` 1→N `GameAccount`（一个邮箱最多 4 个游戏账号，不同区服）
- `GameAccount.task_config`（JSON 字段）：存储每种任务的 `enabled`、`next_time` 等配置。Feeder 直接读取此字段判断任务是否到期
- `GameAccount.progress`：`init`（初始化中）/ `ok`（正常）。Feeder 只扫描 `progress=ok` 的账号
- `GameAccount.lineup_config`（JSON 字段）：按任务名存储阵容分组与位置
- `Emulator` 1→1 `WorkerActor`（运行时绑定）
- `CoopAccount`：勾协账号库（独立于 GameAccount），通过 `CoopPool` 与 GameAccount 配对

### 任务类型与优先级

定义在 `src/app/core/constants.py`，中文 Enum 值。`TASK_PRIORITY` 字典控制执行顺序：

| 优先级 | TaskType | 说明 |
|--------|----------|------|
| 100 | INIT | 起号 |
| 99-92 | INIT_* | 起号子任务（领取奖励、租借式神、经验副本、新手任务、领取锦囊） |
| 90 | ADD_FRIEND | 加好友 |
| 80 | COOP | 勾协 |
| 70 | XUANSHANG | 悬赏 |
| 65 | DELEGATE_HELP | 弥助 |
| 60 | FOSTER | 寄养 |
| 56 | SIGNIN | 签到 |
| 55 | COLLECT_LOGIN_GIFT | 领取登录礼包 |
| 50 | EXPLORE | 探索突破 |
| 49 | MIWEN | 秘闻 |
| 48 | FENGMO | 逢魔 |
| 46 | DIGUI | 地鬼 |
| 45 | COLLECT_MAIL | 领取邮件 |
| 44 | DAOGUAN | 道馆 |
| 43 | LIAO_COIN | 领取寮金币 |
| 42 | LIAO_SHOP | 寮商店 |
| 41 | WEEKLY_SHOP | 每周商店 |
| 40 | CARD_SYNTHESIS | 结界卡合成（explore_count≥40 触发） |
| 38 | DAILY_SUMMON | 每日一抽 |
| 35 | CLIMB_TOWER | 爬塔 |
| 20 | REST | 休息 |

### 前端

Vue 3 + Vite + Element Plus + Pinia。页面在 `frontend/src/views/`，API 封装在 `frontend/src/api/`。

**认证**：JWT，token 存储在 `localStorage` key `yys_auth_token`。`apiRequest()`（`frontend/src/config/index.js`）自动附加 `Authorization: Bearer <token>`。非 JSON 响应（如截图 PNG）需用原始 `fetch()` 手动带 token。

**实时通信**：通过 `python-socketio` WebSocket 推送实时状态更新（如任务进度、Worker 状态）。

### 后端入口与认证

`src/app/main.py` 是 FastAPI 入口。`AuthMiddleware` 对所有请求做 JWT Bearer 验证，以下路径免认证：`/`、`/health`、`/api/auth/login`、`/api/auth/status`。API 路由注册在 `src/app/modules/web/routers/`。

## 关键约定

### 调度链路
- **主链路**：`Feeder + ExecutorService`，`simple_scheduler` 仅作为兼容回退，新功能禁止接入
- `/api/tasks/scheduler/start|stop|status` 控制的是 Feeder + ExecutorService，不是 simple_scheduler
- `simple_scheduler` 启停接口已废弃（`/api/tasks/simple-scheduler/*`），仅保留兼容诊断，严禁在新功能中调用

### 仪表盘数据源
- `/api/dashboard` 与 `/api/stats/realtime` 优先使用 `executor_service.queue_info()` / `running_info()`，仅在无数据时回退旧预览

### 任务配置更新
- `task_config` 更新必须采用"默认配置 + 现有配置 + 本次提交"的合并策略，禁止用默认值覆盖
- 使用 `model_dump(exclude_unset=True)` 获取请求体有效字段
- 任务启用判定：仅 `enabled is True` 视为启用，禁止宽松默认值

### 休息策略
- 全局休息时间 0:00-6:00（`GLOBAL_REST_START`/`GLOBAL_REST_END`）
- 每日随机休息 2-3 小时（`RestPlan` 由 Feeder 自动生成）

### 环境配置
- 首次开发复制 `.env.example` 为 `.env`，关键配置项：
  - `DATABASE_URL`：SQLite 路径（默认 `sqlite:///./data.db`）
  - `MUMU_MANAGER_PATH`、`ADB_PATH`：模拟器和 ADB 路径
  - `OCR_MODEL_DIR`：PaddleOCR 模型目录（默认 `C:/data/ocr_model`）
  - `JWT_SECRET`：首次启动自动生成并追加到 `.env`
  - `COOP_TIMES`：勾协时间点（默认 `18:00,21:00`）
  - `DELEGATE_TIME`：弥助时间（默认 `18:00`）
  - `STAMINA_THRESHOLD`：体力阈值（默认 `1000`）
  - `IO_THREAD_POOL_SIZE` / `COMPUTE_THREAD_POOL_SIZE`：线程池大小（0 表示自动计算）
- `data.db`、`logs/`、`putonglogindata/`、`gouxielogindata/` 等为本地运行产物，不应提交

### 资源目录
- `assets/ui/templates/`：UI 界面识别模板图片（由 `UIRegistry` 加载）
- `assets/ui/`：弹窗模板图片（由 `PopupHandler` 加载）
- `assets/tasks/`：任务相关 YAML 配置（如 `climb_tower.yaml`）
- `assets/ui/shishen/`：式神相关图片资源

### 账号抓取
- 游戏渠道包名：`com.netease.onmyoji.wyzymnqsd_cps`
- 抓取数据源：`shared_prefs`（需 adb root）+ `clientconfig`
- 保存到 `gouxielogindata/` 或 `putonglogindata/` 目录
- 删除 API：`DELETE /api/account-pull/device-login-data/{emulator_id}` 默认仅删除 `shared_prefs`，`clientconfig` 需显式参数开启

### 桌面端
- Electron 壳层在 `desktop/`（入口 `desktop/main.js`），包装前端 Web 页面为桌面应用
