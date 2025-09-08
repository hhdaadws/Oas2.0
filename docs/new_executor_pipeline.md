# 新执行流水线与状态端点说明

本说明概述近期新增的“调度→执行器→模拟器”的执行流水线改造及相关端点，便于开发与联调。

## 改造要点
- 去除 TaskScheduler 直接执行的路径；简化调度器仅负责“发现可执行任务并全部投喂”。
- 新增 ExecutorService，统一管理：
  - 全局 FIFO 队列（严格先入先出）
  - 去重集合（队列内去重）与运行集合（账号级串行，避免同账号并发）
  - 每台模拟器一个 WorkerActor，串行消费自身任务，跨模拟器并行
- 新增 Feeder（投喂器）：按账号配置扫描所有可执行任务并入队到执行器（不创建 DB 任务）。
- 新增状态端点，便于观测队列与运行态。

## 代码结构
- 执行器核心
  - `src/app/modules/executor/service.py`：ExecutorService（FIFO + Dispatch + 状态查询）
  - `src/app/modules/executor/worker.py`：WorkerActor（每模拟器一个；当前使用 MockExecutor）
- 调度投喂
  - `src/app/modules/tasks/feeder.py`：按账号配置扫描并入队（寄养/委托/勾协/加好友/结界卡合成/探索突破）
- 应用接线
  - `src/app/main.py`：启动时初始化 DB/路由 → 启动 ExecutorService 与 Feeder；关闭时依次停止
- 状态端点
  - `GET /api/executor/queue`：返回执行器队列快照
  - `GET /api/executor/running`：返回当前运行账号列表

## 行为与约束
- 调度器（Feeder）每轮会把所有满足条件的任务尝试 `enqueue` 到执行器；
  - 执行器内部做幂等校验：若账号正在运行或（账号,任务类型）已在队列中，则拒绝入队。
- 分配策略：严格 FIFO。只有当存在空闲的模拟器 Worker 时，队首任务才会被弹出并分配。
- 并发模型：每台模拟器一个 WorkerActor（串行），多台模拟器并行；后续可接入健康检查与重连。

## 后续集成
- 将 MockExecutor 替换为真实执行器（含 UI 管理器与模板/OCR 流程），无需变更本流水线。
- 增强状态端点（如每任务耗时、每模板命中率）与健康检查。

