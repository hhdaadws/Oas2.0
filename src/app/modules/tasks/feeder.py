"""
Feeder scheduler: scans accounts and pushes all eligible tasks to ExecutorService FIFO.
No DB Task objects are created; execution and de-duplication happen in ExecutorService.
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, time
from typing import Dict

from sqlalchemy.orm.attributes import flag_modified

from ...core.logger import logger
from ...core.timeutils import (
    now_beijing,
    is_time_reached,
    add_hours_to_beijing_time,
    get_next_fixed_time,
    format_beijing_time,
)
from ...core.constants import TaskType, DEFAULT_TASK_CONFIG
from ...db.base import SessionLocal
from ...db.models import GameAccount, RestPlan, AccountRestConfig
from ..executor.service import executor_service


class Feeder:
    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None
        self._rest_plan_generated_date: str | None = None
        self.log = logger.bind(module="Feeder")

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        self.log.info("Feeder started")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.log.info("Feeder stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._ensure_daily_rest_plans()
                await self._scan_accounts()
            except Exception as e:
                self.log.error(f"feeder loop error: {e}")
            await asyncio.sleep(10)

    async def _ensure_daily_rest_plans(self) -> None:
        bj_now = now_beijing()
        today_str = bj_now.date().isoformat()
        if bj_now.hour < 1 or self._rest_plan_generated_date == today_str:
            return
        try:
            with SessionLocal() as db:
                accounts = db.query(GameAccount).filter(GameAccount.status == 1).all()
                for account in accounts:
                    existing = (
                        db.query(RestPlan)
                        .filter(RestPlan.account_id == account.id, RestPlan.date == today_str)
                        .first()
                    )
                    if existing:
                        continue
                    rc = db.query(AccountRestConfig).filter(AccountRestConfig.account_id == account.id).first()
                    if rc and rc.mode == "custom" and rc.rest_start and rc.rest_duration:
                        start_time = rc.rest_start
                        duration_hours = float(rc.rest_duration)
                        start_dt = datetime.strptime(f"{today_str} {start_time}", "%Y-%m-%d %H:%M")
                    else:
                        duration_hours = random.uniform(2, 3)
                        start_min_dt = datetime.combine(bj_now.date(), time(7, 0))
                        latest_start_dt = datetime.combine(bj_now.date(), time(23, 0)) - timedelta(hours=duration_hours)
                        latest_start_dt = max(latest_start_dt, start_min_dt)
                        total_minutes = max(int((latest_start_dt - start_min_dt).total_seconds() // 60), 0)
                        start_dt = start_min_dt + timedelta(minutes=random.randint(0, total_minutes))
                        start_time = start_dt.strftime("%H:%M")
                    end_dt = min(start_dt + timedelta(hours=duration_hours), datetime.combine(bj_now.date(), time(23, 0)))
                    plan = RestPlan(
                        account_id=account.id,
                        date=today_str,
                        start_time=start_time,
                        end_time=end_dt.strftime("%H:%M"),
                    )
                    db.add(plan)
                db.commit()
            self._rest_plan_generated_date = today_str
        except Exception as e:
            self.log.error(f"create rest plans error: {e}")

    async def _scan_accounts(self) -> None:
        with SessionLocal() as db:
            accounts = db.query(GameAccount).filter(
                GameAccount.status == 1, GameAccount.progress == "ok"
            ).all()
            for account in accounts:
                cfg = account.task_config or DEFAULT_TASK_CONFIG.copy()
                await self._push_time_tasks(account, cfg)
                await self._push_conditional_tasks(account, cfg)

    async def _push_time_tasks(self, account: GameAccount, cfg: Dict) -> None:
        # 寄养/委托/勾协/加好友
        foster = cfg.get("寄养", {})
        if foster.get("enabled", True) and foster.get("next_time") and is_time_reached(foster["next_time"]):
            executor_service.enqueue(account.id, TaskType.FOSTER)
        delegate = cfg.get("委托", {})
        if delegate.get("enabled", True) and delegate.get("next_time") and is_time_reached(delegate["next_time"]):
            executor_service.enqueue(account.id, TaskType.DELEGATE)
        coop = cfg.get("勾协", {})
        if coop.get("enabled", True) and coop.get("next_time") and is_time_reached(coop["next_time"]):
            executor_service.enqueue(account.id, TaskType.COOP)
        addf = cfg.get("加好友", {})
        if addf.get("enabled", True) and addf.get("next_time") and is_time_reached(addf["next_time"]):
            executor_service.enqueue(account.id, TaskType.ADD_FRIEND)

    async def _push_conditional_tasks(self, account: GameAccount, cfg: Dict) -> None:
        # 结界卡合成优先
        card = cfg.get("结界卡合成", {})
        if card.get("enabled", True) and card.get("explore_count", 0) >= 40:
            executor_service.enqueue(account.id, TaskType.CARD_SYNTHESIS)
        # 探索突破（体力阈值）
        explore = cfg.get("探索突破", {})
        if explore.get("enabled", True) and account.stamina >= explore.get("stamina_threshold", 1000):
            executor_service.enqueue(account.id, TaskType.EXPLORE)


# Global instance
feeder = Feeder()

__all__ = ["feeder"]

