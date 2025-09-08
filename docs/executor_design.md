# 执行器模块设计（更新版）

本文档对执行器的目标、模块与接口进行说明，并根据当前代码实现调整了截图设计：截图统一通过 `src/app/modules/emu/adapter.py` 的 `EmulatorAdapter.capture()` 提供（支持 ADB/IPC），不再单列 `capture/` 子模块。

注意：仓库根目录原有的中文文档文件名在部分环境中存在编码乱码问题，因此新增本文件作为更新版设计说明。

## 1. 总体架构

### 设计目标
- 支持多种截图方式（ADB、IPC），统一由 `EmulatorAdapter.capture()` 暴露
- 支持 OCR 文字识别与模板匹配（后续逐步完善）
- 模块化设计，便于扩展和维护
- 统一的任务执行接口与调度对接
- 模拟器实例管理与调度

### 核心流程
```
调度 → 执行器 → 模拟器适配 → 截图（ADB/IPC）→ 识别 → 操作执行 → 结果返回
```

## 2. 模块结构（以当前仓库为准）

### 2.1 执行器核心（`src/app/modules/executor/`）
```
executor/
├── base.py            # 执行器基类与 MockExecutor（已实现）
└── real_executor.py   # 真实执行器（规划中）
```

功能：
- 接收调度器任务
- 管理任务执行生命周期、异常与重试
- 调用 `EmulatorAdapter` 完成启动/截图/操作

### 2.2 模拟器与截图通道（`src/app/modules/emu/`）
```
emu/
├── adapter.py         # 统一适配器（ADB/IPC/MuMu）；提供 capture()
├── adb.py             # ADB 封装（已实现）
├── ipc.py             # IPC 封装（ctypes 调 DLL，已实现）
└── manager.py         # MuMu 管理器封装（已实现）
```

约定：
- 截图仅通过 `EmulatorAdapter.capture(method='adb'|'ipc') -> bytes` 获取 PNG 字节
- 不再维护单独的 `executor/capture/` 包

### 2.3 视觉识别模块（`src/app/modules/vision/` 与 `src/app/modules/ocr/`）
```
vision/
├── __init__.py
├── template.py        # 模板匹配（规划）
├── detector.py        # 通用检测器（规划）
└── utils.py           # 工具（规划）

ocr/
├── __init__.py
└── ocr.py             # OCR 引擎（规划）
```

建议：优先实现模板匹配（OpenCV），随后接入 OCR（PaddleOCR 中文模型）。

### 2.4 任务与调度（`src/app/modules/tasks/`）
```
tasks/
├── simple_scheduler.py # 简化调度器（已实现，使用 MockExecutor）
├── scheduler.py        # 任务调度器（计划/条件检查）
└── queue.py            # 优先级队列
```

后续：当 `real_executor.py` 落地后，调度器可切换到真实执行器。

### 2.5 UI 管理器（`src/app/modules/ui/`）
```
ui/
├── manager.py         # UIManager：统一的 UI 检测与跳转
├── detector.py        # UI 检测实现（基于 vision.template / utils.pixel_match）
├── graph.py           # UI 有限状态机/路由图与跳转步骤
├── registry.py        # UI 定义注册，模板/像素锚点与阈值配置
├── types.py           # UIId/枚举、结果数据结构
└── __init__.py
```

职责：
- 负责“任务开始前”的 UI 就位：每个任务声明其“目标 UI”，执行器先调用 UIManager 导航到该 UI。
- 对外暴露：`detect_ui()`、`ensure_ui(target_ui)`、`navigate(from→to)` 等方法。
- 内部依赖：`modules.vision` 提供模板匹配与像素点匹配；`emu.adapter` 提供截图/点击；`adb` 可扩展按键（BACK/HOME）。

## 3. 接口设计

### 3.1 模拟器与截图接口（替代 BaseCapture）
```python
class EmulatorAdapter:
    def ensure_running(self) -> bool: ...
    def start_app(self, mode: str = 'adb_monkey', activity: str | None = None) -> None: ...
    def stop_app(self) -> None: ...
    def capture(self, method: str = 'adb') -> bytes: ...  # 统一截图入口（ADB/IPC）
    def tap(self, x: int, y: int) -> None: ...
    def swipe(self, x1: int, y1: int, x2: int, y2: int, dur_ms: int = 300) -> None: ...
```

说明：
- `capture('adb')` 通过 `adb exec-out screencap -p` 返回 PNG 字节
- `capture('ipc')` 通过 MuMu IPC DLL 返回 PNG 字节（需正确配置 DLL 与实例）

### 3.2 视觉识别接口
```python
class OCREngine:
    def recognize_text(self, image: bytes, roi: tuple | None = None) -> list[TextResult]: ...

class TemplateEngine:
    def match_template(self, image: bytes, template: str, threshold: float = 0.8) -> MatchResult: ...
```

### 3.3 执行器任务接口
```python
class BaseExecutor:
    async def prepare(self, task: Task, account: GameAccount) -> bool: ...
    async def execute(self) -> dict: ...
    async def cleanup(self) -> None: ...
```

### 3.4 UI 管理器接口
```python
class UIManager:
    def __init__(self, adapter: EmulatorAdapter, capture_method: str = 'adb'): ...

    def detect_ui(self, image: bytes | None = None) -> UIDetectResult:
        """识别当前 UI（可选传入截图，否则内部截图）。返回 UIId、score、anchors、debug 信息。"""

    def ensure_ui(
        self,
        target: 'UIId',
        *,
        max_steps: int = 8,
        step_timeout: float = 3.0,
        threshold: float | None = None,
    ) -> bool:
        """保证当前处于 target UI，不在则按路由图跳转；阈值未设置时默认 0.85。"""

    def navigate(self, source: 'UIId', target: 'UIId') -> bool:
        """使用有向图（graph）从 source 导航到 target，按边上定义的操作序列执行并逐步校验。"""
```

## 4. 执行流程

### 4.1 任务执行流程
1) 接收任务 → 2) 分配模拟器 → 3) 环境准备（启动应用） →
4) UI 就位：调用 `UIManager.ensure_ui(task.required_ui)`，不满足则按路由图跳转 →
5) 任务循环：截图（`adapter.capture()`）→ 识别（OCR/模板）→ 决策 → 操作（tap/swipe）→ 收敛 →
6) 结果处理 → 7) 资源释放

### 4.2 截图策略
- 默认使用 ADB；性能敏感场景可配置为 IPC
- 支持后续在执行器侧引入：截图缓存/节流、ROI 级后处理（裁剪）

### 4.3 识别策略
- OCR：读取体力/金币等数值
- 模板：识别按钮/图标/状态
- 组合：OCR+模板以提升鲁棒性
### 4.4 UI 策略
- UI 检测：优先使用模板匹配（默认阈值 0.85），必要时辅以像素锚点校验（容差匹配）。
- UI 路由：使用有向图定义 UI 状态与跳转边（边上绑定点击/滑动/返回等操作序列）。
- 回退方案：未知 UI 或异常时执行 BACK 若干次；支持“回到主页”的重置路径。
- 稳定性：每步操作后等待短暂时间并重新截图校验；允许重复尝试与超时退出。

## 5. 配置管理（对接 `src/app/core/config.py` 与数据库 `SystemConfig`）

### 5.1 核心运行配置（示例）
```python
LAUNCH_MODE = "adb_monkey"  # adb_monkey|adb_intent
CAPTURE_METHOD = "adb"      # adb|ipc（通过 EmulatorAdapter.capture 使用）
ADB_PATH = "adb"
PKG_NAME = "com.netease.onmyoji"
IPC_DLL_PATH = ""           # 为空则按 MuMu 安装目录自动探测
NEMU_FOLDER = ""            # MuMu 安装目录
ACTIVITY_NAME = ".MainActivity"
```

### 5.2 视觉配置（建议）
```python
VISION_CONFIG = {
    "ocr": {"lang": "ch"},
    "template": {"threshold": 0.8, "scale_range": (0.8, 1.2), "rotation_enable": False}
}
```

### 5.3 任务配置（示例）
```python
TASK_CONFIG = {
    "foster": {"timeout": 120, "retry_count": 3, "templates": ["foster_button", "confirm_button"]},
    "explore": {"timeout": 300, "retry_count": 2, "ocr_regions": [(100, 50, 200, 80)]},
}
```

### 5.4 UI 配置（建议）
```python
UI_CONFIG = {
    "assets_root": "assets/ui",          # UI 模板与锚点资源根目录
    "default_threshold": 0.85,            # 未设置时的模板匹配阈值
    "detect_retry": 2,                    # 检测重试次数
    "step_timeout": 3.0,                  # 单步跳转后等待/校验超时
    "max_steps": 8,                       # 最多跳转步数
}
```

## 6. 错误处理

### 6.1 异常类型
- `AdbError`/`IpcNotConfigured`：截图与连接相关
- `RecognitionError`：识别失败
- `UIUnknownError`：当前 UI 无法识别
- `UINavigateTimeout`：UI 跳转超时或达到最大步数
- `EmulatorError`：模拟器异常
- `TaskTimeoutError`：任务超时

### 6.2 重试机制
- 截图失败：切换方法或重试（ADB↔IPC，可配置）
- 识别失败：降低阈值/扩大 ROI 后重试
- 操作失败：退避等待后重试
- 模拟器异常：重启应用或重连 ADB

### 6.3 记录
- 关键步骤日志 + 截图/识别中间结果（按需落盘）
- 性能指标（截图耗时、识别耗时、循环次数）

## 7. 性能优化
- 并发控制：Worker 池、实例复用、优先级队列
- 资源优化：模板预加载、图像压缩与缓存
- 速度优化：ROI 裁剪、增量检测、必要处并行

## 8. 实施计划（里程碑）
1) 框架与接口（已完成：MockExecutor、emu.*）
2) ADB 截图 + 简单模板匹配（优先）
3) 模拟器管理细化与启动策略健壮化
4) 真实执行器主循环与一个示例任务
5) IPC 截图稳定化（DLL 自动探测/诊断）
6) 性能与错误处理完善

以上为更新后的设计：截图通道统一由 `EmulatorAdapter.capture()` 提供，避免 `capture/` 子模块与现有实现重复。

## 9. 多模拟器并发调度（概览）

为支持多台模拟器并发执行任务，调度层引入 WorkerManager（详见 `docs/worker_manager_design.md`）：
- 每个 Emulator 建立一个 WorkerActor（单并发），由调度器将任务投递到对应 Actor 的队列。
- 任务选择满足角色约束（general|coop|init）且空闲的 Worker；失败时降级或等待。
- Worker 执行 `BaseExecutor.run_task` 串行处理队列任务，期间独占对应 Emulator。
- 健康检查与状态恢复：ADB 连接失败将 Worker 标记为 DOWN 并退避重试；成功后恢复为 IDLE。
