"""
Per-emulator worker actor: serially executes intents for a specific Emulator.
Currently uses MockExecutor to simulate execution.
"""
from __future__ import annotations

import asyncio
from typing import Callable, Optional

from ...core.logger import logger
from ...core.constants import TaskType
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from .service import TaskIntent
from .base import MockExecutor


class WorkerActor:
    def __init__(
        self,
        emulator_row: Emulator,
        system_config: Optional[SystemConfig],
        on_done: Callable[[int], None | asyncio.coroutine],
    ) -> None:
        self.emulator = emulator_row
        self.syscfg = system_config
        self.on_done = on_done
        self.inbox: asyncio.Queue[TaskIntent] = asyncio.Queue()
        self.current: Optional[TaskIntent] = None
        self._stop = asyncio.Event()
        self._log = logger.bind(module="WorkerActor", emulator_id=emulator_row.id, name=emulator_row.name)

    def is_idle(self) -> bool:
        return self.current is None and self.inbox.empty()

    async def submit(self, intent: TaskIntent) -> bool:
        if self._stop.is_set():
            return False
        await self.inbox.put(intent)
        return True

    async def stop(self) -> None:
        self._stop.set()
        # Drain by putting a sentinel no-op
        await self.inbox.put(TaskIntent(account_id=-1, task_type=TaskType.REST))

    async def run_forever(self) -> None:
        self._log.info("WorkerActor started")
        while not self._stop.is_set():
            intent = await self.inbox.get()
            # Stop sentinel
            if self._stop.is_set():
                break
            # Skip invalid
            if intent.account_id <= 0:
                continue
            self.current = intent
            try:
                await self._run_intent(intent)
            except Exception as e:
                self._log.error(f"Intent error: {e}")
            finally:
                # Notify executor service
                try:
                    await asyncio.sleep(0)
                    await asyncio.coroutine(lambda: None)()  # no-op; keep awaitable compatibility
                except Exception:
                    pass
                if self.on_done:
                    coro = self.on_done(intent.account_id)
                    if asyncio.iscoroutine(coro):
                        await coro  # type: ignore
                self.current = None
        self._log.info("WorkerActor stopped")

    async def _run_intent(self, intent: TaskIntent) -> None:
        account: Optional[GameAccount]
        with SessionLocal() as db:
            account = db.query(GameAccount).filter(GameAccount.id == intent.account_id).first()
        if not account:
            self._log.warning(f"Account not found: {intent.account_id}")
            return

        # Build a transient Task object (not persisted)
        task = Task(
            account_id=account.id,
            type=TaskType(intent.task_type),
            priority=50,  # ignored
            status="pending",
        )
        ex = MockExecutor(worker_id=self.emulator.id, emulator_id=self.emulator.id)
        await ex.run_task(task=task, account=account)

