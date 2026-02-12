"""
Per-emulator worker actor: serially executes intents for a specific Emulator.
Supports batch execution: all tasks for the same account are executed consecutively.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Awaitable, Callable, List, Optional

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import AccountStatus, TaskStatus, TaskType
from ...core.logger import logger
from ...core.timeutils import (
    add_hours_to_beijing_time,
    format_beijing_time,
    get_next_fixed_time,
    now_beijing,
)
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..ui.manager import AccountExpiredException
from .base import MockExecutor
from .collect_login_gift import CollectLoginGiftExecutor
from .collect_mail import CollectMailExecutor
from .delegate_help import DelegateHelpExecutor
from .liao_shop import LiaoShopExecutor
from .liao_coin import LiaoCoinExecutor
from .types import TaskIntent

# 各任务类型的 next_time 更新策略（已有自己 _update_next_time 的执行器不在此列）
_EXECUTOR_HAS_OWN_UPDATE = {
    TaskType.DELEGATE_HELP,
    TaskType.COLLECT_LOGIN_GIFT,
    TaskType.COLLECT_MAIL,
    TaskType.LIAO_SHOP,
    TaskType.LIAO_COIN,
}

# 弥助固定时间点
_MIZHU_FIXED_TIMES = ["00:00", "06:00", "12:00", "18:00"]
# 委托固定时间点
_WEITUO_FIXED_TIMES = ["12:00", "18:00"]
# 勾协固定时间点
_GOUXIE_FIXED_TIMES = ["18:00", "21:00"]


class WorkerActor:
    def __init__(
        self,
        emulator_row: Emulator,
        system_config: Optional[SystemConfig],
        on_done: Optional[Callable[[int, bool], Awaitable[None] | None]],
    ) -> None:
        self.emulator = emulator_row
        self.syscfg = system_config
        self.on_done = on_done
        self.inbox: asyncio.Queue[List[TaskIntent]] = asyncio.Queue()
        self.current: Optional[TaskIntent] = None
        self._stop = asyncio.Event()
        self._intent_timeout_sec = 180.0
        self._log = logger.bind(
            module="WorkerActor", emulator_id=emulator_row.id, name=emulator_row.name
        )

    def is_idle(self) -> bool:
        return self.current is None and self.inbox.empty()

    async def submit(self, intents: List[TaskIntent]) -> bool:
        if self._stop.is_set():
            return False
        await self.inbox.put(intents)
        return True

    async def stop(self) -> None:
        self._stop.set()
        await self.inbox.put([TaskIntent(account_id=-1, task_type=TaskType.REST)])

    async def run_forever(self) -> None:
        self._log.info("WorkerActor started")
        while not self._stop.is_set():
            batch = await self.inbox.get()
            if self._stop.is_set():
                break
            if not batch or batch[0].account_id <= 0:
                continue

            account_id = batch[0].account_id
            batch_success = True
            self._log.info(f"开始执行批次: account={account_id}, 任务数={len(batch)}")

            with SessionLocal() as db:
                account = (
                    db.query(GameAccount).filter(GameAccount.id == account_id).first()
                )

            if not account:
                self._log.warning(f"Account not found: {account_id}")
                batch_success = False
            else:
                shared_adapter = None
                shared_ui = None
                batch_len = len(batch)
                for i, intent in enumerate(batch):
                    if self._stop.is_set():
                        break
                    is_last = (i == batch_len - 1)
                    self.current = intent
                    intent.started_at = datetime.utcnow()
                    try:
                        ok = await asyncio.wait_for(
                            self._run_intent(
                                intent, account,
                                shared_adapter=shared_adapter,
                                shared_ui=shared_ui,
                                skip_cleanup=not is_last,
                            ),
                            timeout=self._intent_timeout_sec,
                        )
                        if ok:
                            # 任务成功后统一更新 next_time
                            self._update_next_time_for_intent(intent, account_id)
                        else:
                            batch_success = False
                        # 无论成功失败，都提取 adapter/ui 供后续任务复用
                        if not shared_adapter and hasattr(self, '_last_executor_adapter'):
                            shared_adapter = self._last_executor_adapter
                        if not shared_ui and hasattr(self, '_last_executor_ui'):
                            shared_ui = self._last_executor_ui
                    except asyncio.TimeoutError:
                        batch_success = False
                        self._log.error(
                            f"Intent timeout: account={intent.account_id}, task={intent.task_type}, timeout={self._intent_timeout_sec}s"
                        )
                    except AccountExpiredException:
                        batch_success = False
                        self._log.warning(f"账号失效: account={intent.account_id}")
                        self._mark_account_invalid(intent.account_id)
                        break  # 中断批次剩余任务
                    except Exception as exc:
                        batch_success = False
                        self._log.error(f"Intent error: {exc}")

            self.current = None
            if self.on_done:
                done_result = self.on_done(account_id, batch_success)
                if asyncio.iscoroutine(done_result):
                    await done_result

            self._log.info(f"批次执行完毕: account={account_id}, success={batch_success}")

        self._log.info("WorkerActor stopped")

    def _mark_account_invalid(self, account_id: int) -> None:
        """将账号状态标记为失效"""
        try:
            with SessionLocal() as db:
                account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
                if account:
                    account.status = AccountStatus.INVALID
                    db.commit()
                    self._log.info(f"账号已标记为失效: account={account_id}")
        except Exception as e:
            self._log.error(f"标记账号失效失败: account={account_id}, error={e}")

    async def _run_intent(
        self,
        intent: TaskIntent,
        account: GameAccount,
        *,
        shared_adapter=None,
        shared_ui=None,
        skip_cleanup: bool = False,
    ) -> bool:
        task = Task(
            account_id=account.id,
            type=TaskType(intent.task_type),
            priority=50,
            status="pending",
        )

        if intent.task_type == TaskType.DELEGATE_HELP:
            executor = DelegateHelpExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.COLLECT_LOGIN_GIFT:
            executor = CollectLoginGiftExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.LIAO_SHOP:
            executor = LiaoShopExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.LIAO_COIN:
            executor = LiaoCoinExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.COLLECT_MAIL:
            executor = CollectMailExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        else:
            executor = MockExecutor(
                worker_id=self.emulator.id, emulator_id=self.emulator.id
            )

        # 传递批次上下文
        if shared_adapter:
            executor.shared_adapter = shared_adapter
        if shared_ui:
            executor.shared_ui = shared_ui
        executor.skip_cleanup = skip_cleanup

        result = await executor.run_task(task=task, account=account)

        # 保存 adapter/ui 供后续任务复用
        self._last_executor_adapter = getattr(executor, 'adapter', None)
        self._last_executor_ui = getattr(executor, 'ui', None)

        return result.get("status") in (TaskStatus.SUCCEEDED, TaskStatus.SKIPPED)

    def _update_next_time_for_intent(self, intent: TaskIntent, account_id: int) -> None:
        """任务成功后统一更新 task_config 中的 next_time。
        已有自定义 _update_next_time 的执行器（弥助、领取登录礼包）会跳过。
        """
        task_type = TaskType(intent.task_type)
        if task_type in _EXECUTOR_HAS_OWN_UPDATE:
            return

        config_key = task_type.value  # 例如 "寄养", "委托" 等
        next_time = self._compute_next_time(task_type)
        if next_time is None:
            return

        try:
            with SessionLocal() as db:
                account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
                if not account:
                    return
                cfg = account.task_config or {}
                task_cfg = cfg.get(config_key, {})
                task_cfg["next_time"] = next_time
                cfg[config_key] = task_cfg
                account.task_config = cfg
                flag_modified(account, "task_config")
                db.commit()
                self._log.info(f"[{config_key}] next_time 更新为 {next_time} (account={account_id})")
        except Exception as e:
            self._log.error(f"更新 next_time 失败: task={config_key}, account={account_id}, error={e}")

    @staticmethod
    def _compute_next_time(task_type: TaskType) -> Optional[str]:
        """根据任务类型计算下一次执行时间。"""
        bj_now_str = format_beijing_time(now_beijing())

        if task_type == TaskType.FOSTER:
            # 寄养: +6小时
            return add_hours_to_beijing_time(bj_now_str, 6)

        if task_type == TaskType.DELEGATE:
            # 委托: 下一个 12:00/18:00
            return get_next_fixed_time(bj_now_str, _WEITUO_FIXED_TIMES)

        if task_type == TaskType.COOP:
            # 勾协: 下一个 18:00/21:00
            return get_next_fixed_time(bj_now_str, _GOUXIE_FIXED_TIMES)

        if task_type in (
            TaskType.ADD_FRIEND,
            TaskType.CLIMB_TOWER,
            TaskType.FENGMO,
            TaskType.DIGUI,
            TaskType.DAOGUAN,
            TaskType.DAILY_SUMMON,
        ):
            # 每日任务: 明天 00:01
            tomorrow = now_beijing().date() + timedelta(days=1)
            return f"{tomorrow.isoformat()} 00:01"

        if task_type == TaskType.EXPLORE:
            # 探索突破: +6小时
            return add_hours_to_beijing_time(bj_now_str, 6)

        # 结界卡合成等条件触发型任务无需更新 next_time
        return None
