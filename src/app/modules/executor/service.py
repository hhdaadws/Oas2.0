"""
ExecutorService: central FIFO queue + per-emulator workers

Responsibilities:
- Accept intents from scheduler (enqueue all eligible tasks)
- Deduplicate by (account_id, task_type) and skip running accounts
- Strict FIFO dispatch to idle workers (one worker per Emulator)

Note: Uses MockExecutor to run for now; real executor can replace later.
"""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque, Dict, Optional, Set, Tuple, List

from ...core.logger import logger
from ...core.constants import TaskType
from ...db.base import SessionLocal
from ...db.models import Emulator, SystemConfig
from .worker import WorkerActor


@dataclass
class TaskIntent:
    account_id: int
    task_type: TaskType
    enqueue_time: datetime = field(default_factory=datetime.utcnow)
    payload: dict = field(default_factory=dict)


class ExecutorService:
    def __init__(self) -> None:
        self._pending: Deque[TaskIntent] = deque()
        self._queued_keys: Set[Tuple[int, TaskType]] = set()
        self._running_accounts: Set[int] = set()
        self._workers: Dict[int, WorkerActor] = {}
        self._dispatcher_task: Optional[asyncio.Task] = None
        self._started = False
        self._have_items = asyncio.Event()
        self._lock = asyncio.Lock()
        self._log = logger.bind(module="ExecutorService")

    async def start(self) -> None:
        if self._started:
            return
        self._log.info("Starting ExecutorService ...")
        # Build workers from Emulator table
        with SessionLocal() as db:
            syscfg = db.query(SystemConfig).first()
            rows: List[Emulator] = db.query(Emulator).all()
        for row in rows:
            if row.id in self._workers:
                continue
            actor = WorkerActor(row, system_config=syscfg, on_done=self._on_task_done)
            self._workers[row.id] = actor
            asyncio.create_task(actor.run_forever())
        # Start dispatcher
        self._dispatcher_task = asyncio.create_task(self._dispatcher_loop())
        self._started = True
        self._log.info(f"ExecutorService started with {len(self._workers)} workers")

    async def stop(self) -> None:
        if not self._started:
            return
        self._log.info("Stopping ExecutorService ...")
        # Stop dispatcher
        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass
        # Stop all workers
        for w in self._workers.values():
            await w.stop()
        self._workers.clear()
        self._started = False
        self._pending.clear()
        self._queued_keys.clear()
        self._running_accounts.clear()
        self._have_items.clear()
        self._log.info("ExecutorService stopped")

    async def _dispatcher_loop(self) -> None:
        while True:
            # Wait until there are items and an idle worker
            await self._have_items.wait()
            # Try dispatch under lock to keep FIFO invariant
            async with self._lock:
                # Reset the event tentatively; re-set if still items
                self._have_items.clear()
                if not self._pending:
                    continue
                # Find idle worker
                idle_id = self._pick_idle_worker()
                if idle_id is None:
                    # No idle worker; set event again and wait
                    self._have_items.set()
                    await asyncio.sleep(0.2)
                    continue
                item = self._pending[0]
                actor = self._workers[idle_id]
                submitted = await actor.submit(item)
                if submitted:
                    # Pop from FIFO and mark running
                    self._pending.popleft()
                    self._queued_keys.discard((item.account_id, item.task_type))
                    self._running_accounts.add(item.account_id)
                    # There may still be items left
                    if self._pending:
                        self._have_items.set()
                else:
                    # Submission failed; try later
                    self._have_items.set()
                    await asyncio.sleep(0.2)

    def _pick_idle_worker(self) -> Optional[int]:
        for wid, w in self._workers.items():
            if w.is_idle():
                return wid
        return None

    async def _on_task_done(self, account_id: int) -> None:
        # Called by WorkerActor when a task completes
        async with self._lock:
            self._running_accounts.discard(account_id)
            # Wake dispatcher in case queued tasks can proceed
            if self._pending:
                self._have_items.set()

    def enqueue(self, account_id: int, task_type: TaskType, payload: Optional[dict] = None) -> bool:
        """Enqueue a task intent if not duplicate and account not running.

        Returns True if enqueued, False if dropped due to duplicate/running.
        """
        key = (int(account_id), TaskType(task_type))
        payload = payload or {}
        if account_id in self._running_accounts:
            return False
        if key in self._queued_keys:
            return False
        intent = TaskIntent(account_id=account_id, task_type=TaskType(task_type), payload=payload)
        self._pending.append(intent)
        self._queued_keys.add(key)
        self._have_items.set()
        return True

    # Observability
    def queue_info(self) -> List[dict]:
        return [
            {
                "account_id": it.account_id,
                "task_type": str(it.task_type),
                "enqueue_time": it.enqueue_time.isoformat(),
            }
            for it in list(self._pending)
        ]

    def running_info(self) -> List[dict]:
        # report minimal info
        return [
            {"account_id": aid}
            for aid in sorted(list(self._running_accounts))
        ]


# Global singleton
executor_service = ExecutorService()

__all__ = ["executor_service", "ExecutorService", "TaskIntent"]

