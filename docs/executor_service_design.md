# ExecutorService 设计（调度器→执行器→模拟器，多线程/并发模型）

本设计以“调度器推送、执行器排队、按模拟器并发执行”为准：
- 调度器只会把“未在运行、且不在执行器队列中的任务”推送给执行器。
- 执行器内部维护一个全局 FIFO 队列与运行中集合；严格 FIFO 出队分配给空闲模拟器。
- 每台模拟器一个执行线程（Actor）：串行执行自己的任务队列，跨模拟器并行。

## 角色与边界
- 调度器（Scheduler）
  - 负责决定何时创建任务，并调用执行器的 `enqueue()` 推送。
  - 推送前可调用执行器的查询接口，避免重复。
- 执行器（ExecutorService）
  - 维护全局 FIFO 队列（待分配）与去重集合、运行中集合。
  - 分配策略与并发执行；对外提供查询（是否在队列/是否在运行/当前队列与运行态）。
- 模拟器 WorkerActor（每台模拟器一个）
  - 从自己的 inbox 串行消费任务；封装 `BaseExecutor.prepare/execute/cleanup` 调用。

## 数据结构
- `pending: deque[QueueItem]` 全局待分配队列（严格 FIFO）
- `queued_keys: set[(account_id, task_type)]` 队列去重键（调度器幂等防护）
- `running_accounts: set[int]` 当前在任何模拟器上运行的账号集合
- `workers: Dict[int, WorkerActor]` 以 `emulator_id` 为键的 Actor 集合
- `idle_event: asyncio.Event` 任一 Actor 空闲时触发，用于唤醒分配协程

`QueueItem = {task_id, account_id, task_type, priority?, enqueue_ts}`（优先级字段保留但不参与出队顺序）

## 接口（Scheduler → ExecutorService）
- `enqueue(task: Task, account: GameAccount) -> bool`
  - 原子检查：若 `(account_id, task_type)` 在 `queued_keys` 中或 `account_id` 在 `running_accounts` 中，返回 False；否则入队并返回 True。
- `is_queued(account_id: int, task_type: str) -> bool`
- `is_running(account_id: int) -> bool`
- `queue_info() -> list[dict]`（用于观测）
- `running_info() -> list[dict]`（用于观测）

调度器遵循：仅当 `!is_running && !is_queued` 时调用 `enqueue`。执行器内部同样做幂等校验。

## 分配器（Dispatcher）
- 单独的异步协程：严格遵循 FIFO，不会“弹出队首再回退”。
- 算法：
  1) 若 `pending` 为空，等待 `idle_event` 或新入队事件。
  2) 查看队首 `item`（不弹出）。查找空闲 WorkerActor（如无空闲，等待 `idle_event`）。
  3) 将 `item` 投递给该 Worker（`submit()` 成功后）再从 `pending` 弹出，并将 `account_id` 加入 `running_accounts`，从 `queued_keys` 移除对应键。
  4) 若投递失败（例如 Actor 正在关闭），切换下一台空闲 Worker；若无，则继续等待。

说明：为保持严格 FIFO，分配器不会跳过队首任务。若引入“角色/区域”等约束导致头阻塞，可在后续扩展“多 FIFO 队列（分桶）”以避免阻塞，但默认实现遵循单队列 FIFO。

## WorkerActor（每台模拟器一个）
- 属性：
  - `emulator_id`、`name`、`adapter: EmulatorAdapter`
  - `inbox: asyncio.Queue[QueueItem]`、`current: Optional[QueueItem]`
  - `state: idle|busy|down`、`last_beat`
- 方法：
  - `is_idle() -> bool`：`current is None and inbox.empty()`
  - `submit(item) -> bool`：投入 inbox；返回是否成功
  - `run_forever()`：循环 `inbox.get()` → 调用真实执行器 `run_task()` → 写入 TaskRun → 清理 `running_accounts` → 设置 `idle_event`

注意：`run_task()` 中包含 UIManager.ensure_ui 与模板驱动步骤执行；ADB/图像操作若为阻塞调用，务必用 `asyncio.to_thread` 包装，避免阻塞事件循环。

## 生命周期
- `start()`：
  1) 从数据库读取 Emulators，创建 `WorkerActor`（1:1）。
  2) 为每个 Actor 创建 `asyncio.create_task(actor.run_forever())`。
  3) 启动分配器协程 `asyncio.create_task(dispatcher())`。
- `stop()`：
  - 停止分配器；为每个 Actor 发送关闭信号并等待退出；清理集合。

## 失败与清理
- 任务结束（成功/失败）后：
  - 从 `running_accounts` 移除 `account_id`；
  - 写入 `TaskRun.finished_at/status/artifacts`；
  - 若需重试，由调度器重新决定是否再次 `enqueue`（遵循幂等规则）。
- Actor Down：
  - 将 Actor 标记为 down，不接受新任务；分配器等待其他 Actor 空闲或 Actor 恢复。
  - 恢复策略（可选）：后台心跳尝试重连 ADB，成功后置 idle 并触发 `idle_event`。

## 观测与运维
- `queue_info()`：返回 FIFO 队列中的任务快照（账号/类型/入队时间）。
- `running_info()`：列出当前运行中的账号与归属 `emulator_id`。
- 日志：队列长度变化、分配事件、Actor 状态变化、任务开始/结束与耗时。

## 与现有代码的对接
- 在 `TaskScheduler` 中：
  1) 启动时创建并启动 `ExecutorService`；
  2) 需要入队时，先用 `executor.is_running/is_queued` 判断，再 `executor.enqueue(task, account)`；
  3) 删除现有直接 `asyncio.create_task(executor.run_task(...))` 的分发方式。
- 数据库：`TaskRun.worker_id/emulator_id` 由 WorkerActor 填写真实值；`Task.status` 的变更在入队/开始/结束阶段适当更新。

## 配置
- 并发度 = 模拟器数量（每台一个 Actor）。
- 严格 FIFO default；如需避免“头阻塞”，可以在后续扩展为“多队列分桶 + 轮转”。

