# 多模拟器并发调度与 Worker 管理设计

目标：在多台模拟器上并发执行任务，同时保证每台模拟器上的操作串行不冲突，并与“调度器→执行器（FIFO 队列）→模拟器 Actor”的架构一致。

## 现状评估
- 已有 `TaskScheduler`：中心优先级队列 + 简易 worker 映射（MockExecutor），但未与数据库的 `Emulator/Worker` 表打通，也未形成每模拟器一个独占 worker 的模式。
- ADB 操作为阻塞式 `subprocess` 调用，直接在事件循环中使用会阻塞 `asyncio`。

## 架构概览（与 ExecutorService 对齐）
- `ExecutorService`：持有全局 FIFO 队列、运行态集合与 `WorkerManager`；内部包含一个严格 FIFO 的分配器（Dispatcher）。
- `WorkerManager`：读库构建 WorkerActors，并维护其生命周期与状态；向 `ExecutorService` 暴露空闲查询与投递接口。
- `WorkerActor`（每台 Emulator 一个）：串行消费自身 inbox 的任务；负责启动/截图/操作/清理。
- 数据持久化：`TaskRun` 绑定 `worker_id/emulator_id`；Worker/Emulator 状态写回数据库。

## 数据模型对齐
- `db.models.Emulator`：记录 ADB 地址、实例 ID、角色（general|coop|init）、状态（running/disconnected/down）。
- `db.models.Worker`：一台 Emulator 对应一个 Worker（1:1），记录 `role/state/last_beat`。
- `TaskRun`：增加 `emulator_id/worker_id`（已存在）。

## 接口设计（核心）
```python
class WorkerManager:
    def __init__(self, settings: Settings, db_session_factory): ...
    async def start(self): ...  # 读取 Emulators → 构建 WorkerActors → 心跳
    async def stop(self): ...   # 停止所有 actors
    def pick_idle(self, role: str | None = None) -> int | None: ...
    def submit(self, worker_id: int, task: Task, account: GameAccount) -> bool: ...
    def get_state(self) -> list[dict]: ...  # 观测

class WorkerActor:
    def __init__(self, worker_id: int, emulator_row: Emulator, syscfg: SystemConfig, settings: Settings): ...
    async def run_forever(self): ...  # from queue get → run_task → update state
    async def submit(self, task: Task, account: GameAccount) -> bool: ...
    def is_idle(self) -> bool: ...
```

## 生命周期
1) 启动：从 `Emulator` 表读取已配置实例，按记录创建/更新 `Worker` 表（1:1）。
2) 构造 `AdapterConfig` 并注入 `EmulatorAdapter` 到 Actor（含 adb/ipc/mumu 配置）。
3) Actor 启动时尝试 `adb connect` 并标记 state；失败则 DOWN 并退避重试。
4) ExecutorService 的 Dispatcher 从 FIFO 队列查看队首任务，找到空闲 Worker 后调用 `submit(worker_id, task, account)`。
5) Actor 串行执行：`BaseExecutor.prepare → execute → cleanup`，期间更新 `TaskRun`。
6) 健康检查：定期执行 `adb devices` 或小型操作，失败则打 DOWN，并尝试恢复。

## 调度算法
1) 角色约束：任务类型映射角色（如 FOSTER→general，COOP→coop，INIT→init）。
2) 选择策略：
   - 过滤出 `is_idle` 的 Worker（同一角色或通用 fallback）。
   - 可采用轮询或最少任务策略；支持优先绑定（同账号优先分配最近使用的 worker）。
3) 饥饿避免：为长队列的账号/任务提供轮转；同账号任务串行。

## 并发与阻塞处理
- 每个 Actor 串行执行自身队列任务（保障同一 Emulator 无冲突）。
- 通过 `asyncio.create_task(actor.run_forever())` 启动多个 Actor 并发运行。
- ADB 阻塞调用：在 executor 内部用 `asyncio.to_thread` 包装阻塞 `subprocess` 调用，避免阻塞事件循环。

## 错误与恢复
- 任务失败：记入 `TaskRun`，按 `max_retries` 与退避规则重试/放回队列。
- 设备故障：Actor 标记为 DOWN；`WorkerManager` 定期重试 `adb connect`，成功后恢复 IDLE。
- IPC/DLL 缺失：降级到 ADB 截图；连续失败可触发 `stop_app → start_app` 重置。

## 观测性
- `get_state()` 返回所有 WorkerActors 的 `state/queue_len/last_beat/current_task`。
- 心跳写回 `Worker.last_beat/state`；
- `TaskRun` 记录 `started_at/finished_at/status/artifacts`。

## 与现有代码融合
- 调度入口：在 `TaskScheduler.start()` 中 `worker_manager.start()`，并将 `_dispatch_loop` 的分派逻辑改为：
  1) `role = map_task_to_role(task.type)`
  2) `wid = worker_manager.pick_idle(role)`
  3) `worker_manager.submit(wid, task, account)`
- Executor：替换 `MockExecutor` 为真实执行器，并将 `emulator_id=actor.emulator_id` 写入 `TaskRun`。

## 配置
- 并发度 = `len(Emulator)`；每台模拟器一个 Actor。
- 可选：为 IPC 高性能实例单独分组（role 或标签），在选择策略中优先。

## 迁移计划
1) 增加 `WorkerManager/WorkerActor` 脚手架（占位实现）。
2) `TaskScheduler` 切换到 WorkerManager 分派；保留中心队列不变。
3) 执行器接入 UIManager 与 Vision 模块，替换 MockExecutor。
4) 补充健康检查与 DOWN→IDLE 恢复逻辑；完善日志与指标。
