"""
ExecutorService: central queue + per-emulator workers (batch dispatch)

Responsibilities:
- Accept batched intents from scheduler (all eligible tasks per account)
- Deduplicate by account_id (one batch per account in queue)
- Dispatch batches to idle workers (one worker per Emulator)
- Same account's tasks execute consecutively on the same worker
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from ...core.constants import TASK_PRIORITY, TaskType
from ...core.logger import logger
from ...db.base import SessionLocal
from ...db.models import Emulator, SystemConfig
from .types import TaskIntent
from .worker import WorkerActor


@dataclass
class PendingBatch:
    account_id: int
    intents: List[TaskIntent]
    state: str = "queued"
    retry_count: int = 0
    enqueue_at: datetime = field(default_factory=datetime.utcnow)


class ExecutorService:
    def __init__(self) -> None:
        self._pending: List[PendingBatch] = []
        self._queued_keys: Set[Tuple[int, TaskType]] = set()
        self._queued_accounts: Set[int] = set()
        self._running_accounts: Set[int] = set()
        self._running_batches: Dict[int, PendingBatch] = {}
        self._workers: Dict[int, WorkerActor] = {}
        self._dispatcher_task: Optional[asyncio.Task] = None
        self._started = False
        self._have_items = asyncio.Event()
        self._lock = asyncio.Lock()
        self._dispatch_window = 8
        self._max_batch_retry = 1
        self._queue_wait_samples_ms: List[float] = []
        self._failed_batches: List[dict] = []
        self._metrics = {
            "dispatch_attempt": 0,
            "dispatch_success": 0,
            "dispatch_fail": 0,
            "dispatch_retry": 0,
            "batch_succeeded": 0,
            "batch_failed": 0,
        }
        self._last_dispatch_at: Optional[datetime] = None
        self._log = logger.bind(module="ExecutorService")

    async def start(self) -> None:
        if self._started:
            return
        self._log.info("Starting ExecutorService ...")
        with SessionLocal() as db:
            syscfg = db.query(SystemConfig).first()
            rows: List[Emulator] = db.query(Emulator).all()

        for row in rows:
            if row.id in self._workers:
                continue
            actor = WorkerActor(
                row,
                system_config=syscfg,
                on_done=self._on_task_done,
                rescan_callback=self.rescan_account,
            )
            self._workers[row.id] = actor
            asyncio.create_task(actor.run_forever())

        self._dispatcher_task = asyncio.create_task(self._dispatcher_loop())
        self._started = True
        self._log.info(f"ExecutorService started with {len(self._workers)} workers")

        # 预加载 UI 模板到缓存
        try:
            from ..ui.detector import UIDetector
            from ..ui.registry import registry as _global_registry
            detector = UIDetector(_global_registry)
            detector.warmup()
            self._log.info("UI 模板预加载完成")
        except Exception as e:
            self._log.warning("UI 模板预加载失败（不影响运行）: {}", e)

    async def stop(self) -> None:
        if not self._started:
            return

        self._log.info("Stopping ExecutorService ...")
        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass

        for worker in self._workers.values():
            await worker.stop()

        self._workers.clear()
        self._started = False
        self._pending.clear()
        self._queued_keys.clear()
        self._queued_accounts.clear()
        self._running_accounts.clear()
        self._running_batches.clear()
        self._have_items.clear()
        self._log.info("ExecutorService stopped")

    async def _dispatcher_loop(self) -> None:
        while True:
            await self._have_items.wait()
            dispatched_once = False

            while True:
                dispatch_ctx = await self._try_pick_dispatch_target()
                if dispatch_ctx is None:
                    break

                worker_id, batch = dispatch_ctx
                submitted = await self._submit_to_worker(worker_id, batch)
                if not submitted:
                    await asyncio.sleep(0.2)
                else:
                    dispatched_once = True

            if not dispatched_once:
                await asyncio.sleep(0.05)

    async def _try_pick_dispatch_target(self) -> Optional[Tuple[int, PendingBatch]]:
        async with self._lock:
            if not self._pending:
                self._have_items.clear()
                return None

            idle_id = self._pick_idle_worker()
            if idle_id is None:
                self._have_items.clear()
                return None

            batch_index = self._pick_dispatchable_index()
            if batch_index is None:
                self._have_items.clear()
                return None

            batch = self._pending[batch_index]
            batch.state = "dispatching"
            self._metrics["dispatch_attempt"] += 1
            return idle_id, batch

    async def _submit_to_worker(self, worker_id: int, batch: PendingBatch) -> bool:
        actor = self._workers.get(worker_id)
        if actor is None:
            async with self._lock:
                if batch.state == "dispatching":
                    batch.state = "queued"
                self._metrics["dispatch_fail"] += 1
                self._have_items.set()
            return False

        submitted = await actor.submit(batch.intents)
        now = datetime.utcnow()

        async with self._lock:
            if submitted:
                self._remove_pending_batch(batch.account_id)
                batch.state = "running"
                self._running_accounts.add(batch.account_id)
                self._running_batches[batch.account_id] = batch
                self._queued_accounts.discard(batch.account_id)
                for intent in batch.intents:
                    self._queued_keys.discard((intent.account_id, intent.task_type))
                    intent.started_at = now

                self._metrics["dispatch_success"] += 1
                self._last_dispatch_at = now

                wait_ms = max(0.0, (now - batch.enqueue_at).total_seconds() * 1000)
                self._queue_wait_samples_ms.append(wait_ms)
                if len(self._queue_wait_samples_ms) > 500:
                    self._queue_wait_samples_ms = self._queue_wait_samples_ms[-500:]

                if self._pending:
                    self._have_items.set()
                return True

            if batch.state == "dispatching":
                batch.state = "queued"
            self._metrics["dispatch_fail"] += 1
            if self._pending:
                self._have_items.set()
            return False

    def _pick_dispatchable_index(self) -> Optional[int]:
        window = min(self._dispatch_window, len(self._pending))
        for idx in range(window):
            if self._pending[idx].state == "queued":
                return idx

        for idx in range(window, len(self._pending)):
            if self._pending[idx].state == "queued":
                return idx
        return None

    def _remove_pending_batch(self, account_id: int) -> None:
        for idx, item in enumerate(self._pending):
            if item.account_id == account_id:
                self._pending.pop(idx)
                return

    def _pick_idle_worker(self) -> Optional[int]:
        for wid, worker in self._workers.items():
            if worker.is_idle():
                return wid
        return None

    async def _on_task_done(self, account_id: int, success: bool) -> None:
        async with self._lock:
            self._running_accounts.discard(account_id)
            batch = self._running_batches.pop(account_id, None)
            if batch is None:
                if self._pending:
                    self._have_items.set()
                return

            if success:
                self._metrics["batch_succeeded"] += 1
            else:
                # 失败批次不再立即重入队，由 worker 的 _update_next_time_on_failure
                # 延后各任务的 next_time，Feeder 会在延迟到期后自然重新调度
                self._metrics["batch_failed"] += 1
                self._failed_batches.append(
                    {
                        "account_id": account_id,
                        "task_types": [
                            it.task_type.value
                            if isinstance(it.task_type, TaskType)
                            else str(it.task_type)
                            for it in batch.intents
                        ],
                        "failed_at": datetime.utcnow().isoformat(),
                        "retry_count": batch.retry_count,
                    }
                )
                if len(self._failed_batches) > 200:
                    self._failed_batches = self._failed_batches[-200:]

            if self._pending:
                self._have_items.set()

    def rescan_account(self, account_id: int) -> List[TaskIntent]:
        """为正在执行的 account 做即时 re-scan，收集新到期任务。

        仅在 Worker 的 batch 执行完毕后、cleanup 之前调用。
        此时 account_id 仍在 _running_accounts 中，不存在与 Feeder 的竞争。
        """
        from ..tasks.feeder import feeder as feeder_instance

        try:
            return feeder_instance.collect_due_tasks_for_account(account_id)
        except Exception as e:
            self._log.error(f"rescan_account 失败: account={account_id}, error={e}")
            return []

    def enqueue(
        self, account_id: int, task_type: TaskType, payload: Optional[dict] = None
    ) -> bool:
        key = (int(account_id), TaskType(task_type))
        payload = payload or {}
        if account_id in self._running_accounts:
            return False
        if key in self._queued_keys:
            return False

        intent = TaskIntent(
            account_id=account_id, task_type=TaskType(task_type), payload=payload
        )
        if account_id in self._queued_accounts:
            for batch in self._pending:
                if batch.account_id == account_id:
                    batch.intents.append(intent)
                    batch.intents.sort(
                        key=lambda i: TASK_PRIORITY.get(i.task_type, 0), reverse=True
                    )
                    break
        else:
            self._pending.append(PendingBatch(account_id=account_id, intents=[intent]))
            self._queued_accounts.add(account_id)

        self._queued_keys.add(key)
        self._have_items.set()
        return True

    def enqueue_batch(self, account_id: int, intents: List[TaskIntent]) -> bool:
        if not intents:
            return False
        if account_id in self._running_accounts:
            return False
        if account_id in self._queued_accounts:
            return False

        intents.sort(key=lambda i: TASK_PRIORITY.get(i.task_type, 0), reverse=True)

        self._pending.append(PendingBatch(account_id=account_id, intents=intents))
        self._queued_accounts.add(account_id)
        for intent in intents:
            self._queued_keys.add((intent.account_id, intent.task_type))

        self._have_items.set()
        self._log.info(
            f"批次入队: account={account_id}, 任务={[i.task_type.value for i in intents]}"
        )
        return True

    def queue_info(self) -> List[dict]:
        result: List[dict] = []
        for batch in list(self._pending):
            for intent in batch.intents:
                result.append(
                    {
                        "account_id": intent.account_id,
                        "task_type": intent.task_type.value
                        if isinstance(intent.task_type, TaskType)
                        else str(intent.task_type),
                        "enqueue_time": intent.enqueue_time.isoformat(),
                        "state": batch.state,
                        "retry_count": batch.retry_count,
                    }
                )
        return result

    def running_info(self) -> List[dict]:
        result: List[dict] = []
        for wid, worker in self._workers.items():
            current = getattr(worker, "current", None)
            if not current or current.account_id <= 0:
                continue
            started_at = current.started_at or current.enqueue_time
            result.append(
                {
                    "account_id": current.account_id,
                    "task_type": current.task_type.value
                    if isinstance(current.task_type, TaskType)
                    else str(current.task_type),
                    "worker_id": wid,
                    "emulator_id": getattr(worker.emulator, "id", None),
                    "emulator_name": getattr(worker.emulator, "name", None),
                    "started_at": started_at.isoformat(),
                }
            )

        if result:
            return result
        return [{"account_id": aid} for aid in sorted(list(self._running_accounts))]

    def metrics_snapshot(self) -> dict:
        queue_wait_p50 = self._percentile(self._queue_wait_samples_ms, 50)
        queue_wait_p95 = self._percentile(self._queue_wait_samples_ms, 95)
        return {
            "engine": "feeder_executor",
            "queue": {
                "depth": len(self._pending),
                "wait_ms_p50": queue_wait_p50,
                "wait_ms_p95": queue_wait_p95,
                "failed_pool_size": len(self._failed_batches),
            },
            "running": {
                "count": len(self._running_accounts),
                "workers": len(self._workers),
                "idle_workers": len([w for w in self._workers.values() if w.is_idle()]),
            },
            "dispatch": {
                "window": self._dispatch_window,
                "max_batch_retry": self._max_batch_retry,
                **self._metrics,
            },
            "last_dispatch_at": self._last_dispatch_at.isoformat()
            if self._last_dispatch_at
            else None,
        }

    @staticmethod
    def _percentile(values: List[float], percentile: int) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        if len(ordered) == 1:
            return round(ordered[0], 2)
        rank = (len(ordered) - 1) * (percentile / 100)
        lower = int(rank)
        upper = min(lower + 1, len(ordered) - 1)
        weight = rank - lower
        value = ordered[lower] * (1 - weight) + ordered[upper] * weight
        return round(value, 2)


executor_service = ExecutorService()

__all__ = ["executor_service", "ExecutorService", "TaskIntent"]
