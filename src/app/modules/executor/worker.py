"""
Per-emulator worker actor: serially executes intents for a specific Emulator.
Supports batch execution: all tasks for the same account are executed consecutively.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, List, Optional, Tuple

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import AccountStatus, TaskStatus, TaskType
from ...core.logger import logger
from ...core.thread_pool import (
    get_emulator_io_pool,
    run_in_db,
    run_in_emulator_io,
)
from ...core.timeutils import (
    add_hours_to_beijing_time,
    format_beijing_time,
    get_next_fixed_time,
    now_beijing,
    parse_beijing_time,
)
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..ui.manager import AccountExpiredException, CangbaogeListedException
from ..ui.popups import JihaoPopupException
from ..emu.adapter import EmulatorAdapter
from ..emu.async_adapter import AsyncEmulatorAdapter
from .base import MockExecutor
from .collect_login_gift import CollectLoginGiftExecutor
from .collect_mail import CollectMailExecutor
from .delegate_help import DelegateHelpExecutor
from .liao_shop import LiaoShopExecutor
from .liao_coin import LiaoCoinExecutor
from .add_friend import AddFriendExecutor
from .init_executor import InitExecutor
from .init_collect_reward import InitCollectRewardExecutor
from .init_rent_shikigami import InitRentShikigamiExecutor
from .init_newbie_quest import InitNewbieQuestExecutor
from .init_exp_dungeon import InitExpDungeonExecutor
from .init_collect_jinnang import InitCollectJinnangExecutor
from .init_shikigami_train import InitShikigamiTrainExecutor
from .init_fanhe_upgrade import InitFanheUpgradeExecutor
from .digui import DiGuiExecutor
from .explore import ExploreExecutor
from .xuanshang import XuanShangExecutor
from .climb_tower import ClimbTowerExecutor
from .weekly_shop import WeeklyShopExecutor
from .miwen import MiWenExecutor
from .signin import SigninExecutor
from .yuhun import YuHunExecutor
from .collect_achievement import CollectAchievementExecutor
from .summon_gift import SummonGiftExecutor
from .weekly_share import WeeklyShareExecutor
from .collect_fanhe_jiuhu import CollectFanheJiuhuExecutor
from .duiyi_jingcai import DuiyiJingcaiExecutor
from .db_logger import emit as db_log
from .types import TaskIntent

# 各任务类型的 next_time 更新策略（已有自己 _update_next_time 的执行器不在此列）
_EXECUTOR_HAS_OWN_UPDATE = {
    TaskType.INIT,
    TaskType.INIT_COLLECT_REWARD,
    TaskType.INIT_RENT_SHIKIGAMI,
    TaskType.INIT_COLLECT_JINNANG,
    TaskType.INIT_SHIKIGAMI_TRAIN,
    TaskType.INIT_EXP_DUNGEON,
    TaskType.INIT_FANHE_UPGRADE,
    TaskType.DELEGATE_HELP,
    TaskType.COLLECT_LOGIN_GIFT,
    TaskType.COLLECT_MAIL,
    TaskType.LIAO_SHOP,
    TaskType.LIAO_COIN,
    TaskType.ADD_FRIEND,
    TaskType.WEEKLY_SHOP,
    TaskType.SIGNIN,
    TaskType.YUHUN,
    TaskType.COLLECT_ACHIEVEMENT,
    TaskType.SUMMON_GIFT,
    TaskType.COLLECT_FANHE_JIUHU,
}

# 弥助固定时间点
_MIZHU_FIXED_TIMES = ["00:00", "06:00", "12:00", "18:00"]
# 勾协固定时间点
_GOUXIE_FIXED_TIMES = ["18:00", "21:00"]
# 对弈竞猜固定时间窗口（10:00 起，每 2 小时一个窗口）
_DUIYI_FIXED_TIMES = ["10:00", "12:00", "14:00", "16:00", "18:00", "20:00", "22:00"]


class WorkerActor:
    _MAX_RESCAN_ROUNDS = 3  # re-scan 最大轮次
    _PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

    def __init__(
        self,
        emulator_row: Emulator,
        system_config: Optional[SystemConfig],
        on_done: Optional[Callable[[int, bool], Awaitable[None] | None]],
        rescan_callback: Optional[Callable[[int], List[TaskIntent]]] = None,
        executor_service_ref=None,
    ) -> None:
        self.emulator = emulator_row
        self.syscfg = system_config
        self.on_done = on_done
        self.rescan_callback = rescan_callback
        self._executor_service = executor_service_ref
        self.inbox: asyncio.Queue[List[TaskIntent]] = asyncio.Queue()
        self.current: Optional[TaskIntent] = None
        self._stop = asyncio.Event()
        self._stale_timeout_sec = 180.0  # 空闲超时（秒），仅在无 I/O 活动时计时
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

    async def _wait_with_stale_timeout(
        self, task: asyncio.Task, stale_timeout: float
    ) -> Any:
        """等待任务完成，仅在无 I/O 活动超过 stale_timeout 时才超时。

        与 asyncio.wait_for 不同，此方法不计算任务的总执行时间，
        只在 EmulatorAdapter 的心跳停止更新（即无截图/点击操作）时才触发超时。
        """
        adb_addr = self.emulator.adb_addr
        EmulatorAdapter.touch_heartbeat(adb_addr)

        while not task.done():
            await asyncio.sleep(5)
            if task.done():
                break
            last = EmulatorAdapter.get_heartbeat(adb_addr)
            idle_sec = time.monotonic() - last
            if idle_sec > stale_timeout:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                raise asyncio.TimeoutError(
                    f"空闲超时: {idle_sec:.0f}s 无 I/O 活动"
                )
        return task.result()

    async def run_forever(self) -> None:
        self._log.info("WorkerActor started")
        try:
            get_emulator_io_pool(self.emulator.adb_addr)
        except Exception as e:
            self._log.warning(f"预热模拟器 I/O 线程池失败: {e}")
        while not self._stop.is_set():
            batch = await self.inbox.get()
            if self._stop.is_set():
                break
            if not batch or batch[0].account_id <= 0:
                continue

            account_id = batch[0].account_id
            overall_success = True
            shared_adapter = None
            shared_ui = None
            rescan_round = 0

            task_names = ", ".join(
                i.task_type.value if isinstance(i.task_type, TaskType) else str(i.task_type)
                for i in batch
            )
            self._log.info(f"开始执行批次: account={account_id}, 任务数={len(batch)}")
            db_log(account_id, f"开始执行批次 ({len(batch)}个任务: {task_names})")

            def _load_account(aid: int):
                with SessionLocal() as db:
                    acc = db.query(GameAccount).filter(GameAccount.id == aid).first()
                    if acc:
                        db.expunge(acc)
                    return acc

            def _load_syscfg():
                with SessionLocal() as db:
                    cfg = db.query(SystemConfig).first()
                    if cfg:
                        db.expunge(cfg)
                    return cfg

            # 重新加载系统配置（确保 capture_method 等配置实时生效）
            fresh_syscfg = await run_in_db(_load_syscfg)
            if fresh_syscfg is not None:
                self.syscfg = fresh_syscfg

            account = await run_in_db(_load_account, account_id)

            if not account:
                self._log.warning(f"Account not found: {account_id}")
                overall_success = False
            else:
                # === Merge cloud task_config into local account (once per batch) ===
                cloud_tc = batch[0].payload.get("cloud_task_config") if batch[0].payload else None
                if cloud_tc:
                    def _merge_cloud_task_config(aid: int, ctc: dict):
                        with SessionLocal() as db:
                            acc = db.query(GameAccount).filter(GameAccount.id == aid).first()
                            if acc:
                                local_tc = dict(acc.task_config or {})
                                for task_name, task_cfg in ctc.items():
                                    if isinstance(task_cfg, dict):
                                        existing = local_tc.get(task_name, {})
                                        if isinstance(existing, dict):
                                            existing.update(task_cfg)
                                            local_tc[task_name] = existing
                                        else:
                                            local_tc[task_name] = task_cfg
                                acc.task_config = local_tc
                                flag_modified(acc, "task_config")
                                db.commit()

                    await run_in_db(_merge_cloud_task_config, account_id, cloud_tc)
                    self._log.info(f"已合并云端 task_config: account={account_id}")

                # === Merge cloud lineup_config into local account (once per batch) ===
                cloud_lineup = batch[0].payload.get("lineup_config") if batch[0].payload else None
                if cloud_lineup and isinstance(cloud_lineup, dict):
                    def _merge_cloud_lineup(aid: int, cfg: dict):
                        with SessionLocal() as db:
                            acc = db.query(GameAccount).filter(GameAccount.id == aid).first()
                            if acc:
                                acc.lineup_config = cfg
                                flag_modified(acc, "lineup_config")
                                db.commit()
                    await run_in_db(_merge_cloud_lineup, account_id, cloud_lineup)
                    account.lineup_config = cloud_lineup
                    self._log.info(f"已合并云端 lineup_config: account={account_id}")

                # === 主循环：batch 执行 + re-scan ===
                current_batch = batch
                abort = False

                while current_batch and not abort:
                    batch_success, shared_adapter, shared_ui, abort = (
                        await self._execute_batch_tasks(
                            current_batch, account,
                            shared_adapter=shared_adapter,
                            shared_ui=shared_ui,
                        )
                    )

                    if not batch_success:
                        overall_success = False

                    # 中断判断
                    if abort or self._stop.is_set():
                        break

                    # re-scan：检查是否有新到期任务
                    rescan_round += 1
                    if rescan_round > self._MAX_RESCAN_ROUNDS:
                        self._log.info(
                            f"达到 re-scan 上限 ({self._MAX_RESCAN_ROUNDS}), "
                            f"account={account_id}"
                        )
                        break

                    new_intents = await self._do_rescan(account_id)
                    if not new_intents:
                        break

                    new_task_names = ", ".join(
                        i.task_type.value if isinstance(i.task_type, TaskType)
                        else str(i.task_type)
                        for i in new_intents
                    )
                    self._log.info(
                        f"re-scan 发现 {len(new_intents)} 个新任务: "
                        f"account={account_id}, tasks=[{new_task_names}]"
                    )
                    db_log(
                        account_id,
                        f"re-scan 追加 {len(new_intents)} 个新到期任务: {new_task_names}",
                    )
                    current_batch = new_intents

                # === 所有轮次完成，最终 cleanup ===
                await self._final_cleanup(shared_adapter)

            self.current = None
            if self.on_done:
                done_result = self.on_done(account_id, overall_success)
                if asyncio.iscoroutine(done_result):
                    await done_result

            self._log.info(
                f"账号执行全部完毕: account={account_id}, "
                f"success={overall_success}, rescan_rounds={rescan_round}"
            )
            db_log(
                account_id,
                f"账号执行全部完毕 (结果: {'成功' if overall_success else '部分失败'}, "
                f"re-scan轮次: {rescan_round})",
                level="INFO" if overall_success else "WARNING",
            )

        self._log.info("WorkerActor stopped")

    async def _execute_batch_tasks(
        self,
        batch: List[TaskIntent],
        account: GameAccount,
        *,
        shared_adapter=None,
        shared_ui=None,
    ) -> Tuple[bool, Any, Any, bool]:
        """执行批次内所有任务，全部 skip_cleanup=True。

        Returns:
            (batch_success, shared_adapter, shared_ui, abort)
            abort=True 表示 AccountExpiredException 或 stop 信号。
        """
        batch_success = True
        abort = False
        account_id = account.id
        pending_next_time_ops: List[Tuple[str, str, Optional[str]]] = []

        for intent in batch:
            if self._stop.is_set():
                abort = True
                break
            self.current = intent
            intent.started_at = datetime.utcnow()
            try:
                intent_task = asyncio.create_task(
                    self._run_intent(
                        intent, account,
                        shared_adapter=shared_adapter,
                        shared_ui=shared_ui,
                        skip_cleanup=True,
                    )
                )
                ok = await self._wait_with_stale_timeout(
                    intent_task, self._stale_timeout_sec
                )
                if ok:
                    op = self._build_success_next_time_op(intent)
                    if op:
                        pending_next_time_ops.append(op)
                    task_name = intent.task_type.value if isinstance(intent.task_type, TaskType) else str(intent.task_type)
                    db_log(account_id, f"{task_name}任务执行成功")
                    # per-intent 完成回调
                    if self._executor_service:
                        await self._executor_service.notify_intent_done(account_id, intent, True)
                else:
                    batch_success = False
                    task_name = intent.task_type.value if isinstance(intent.task_type, TaskType) else str(intent.task_type)
                    db_log(account_id, f"{task_name}任务执行失败", level="WARNING")
                    # per-intent 完成回调
                    if self._executor_service:
                        await self._executor_service.notify_intent_done(account_id, intent, False)
                    op = self._build_failure_next_time_op(intent)
                    if op:
                        pending_next_time_ops.append(op)
                    await self._save_fail_screenshot(
                        intent, shared_adapter, reason="task_failed"
                    )
                # 提取 adapter/ui 供后续任务复用
                if not shared_adapter and hasattr(self, '_last_executor_adapter'):
                    shared_adapter = self._last_executor_adapter
                if not shared_ui and hasattr(self, '_last_executor_ui'):
                    shared_ui = self._last_executor_ui
            except asyncio.TimeoutError:
                batch_success = False
                self._log.error(
                    f"Intent stale timeout: account={intent.account_id}, "
                    f"task={intent.task_type}, stale_limit={self._stale_timeout_sec}s"
                )
                task_name = intent.task_type.value if isinstance(intent.task_type, TaskType) else str(intent.task_type)
                db_log(intent.account_id, f"{task_name}任务空闲超时 ({self._stale_timeout_sec}s 无活动)", level="ERROR")
                # per-intent 完成回调
                if self._executor_service:
                    await self._executor_service.notify_intent_done(account_id, intent, False)
                op = self._build_failure_next_time_op(intent)
                if op:
                    pending_next_time_ops.append(op)
                await self._save_fail_screenshot(
                    intent, shared_adapter, reason="stale_timeout"
                )
            except JihaoPopupException:
                if not shared_adapter and hasattr(self, '_last_executor_adapter') and self._last_executor_adapter:
                    shared_adapter = self._last_executor_adapter
                batch_success = False
                abort = True
                self._log.warning(f"检测到祭号弹窗，关闭游戏并批量延后任务: account={intent.account_id}")
                db_log(intent.account_id, "检测到祭号弹窗，关闭游戏并批量延后任务", level="WARNING")
                # per-intent 完成回调
                if self._executor_service:
                    await self._executor_service.notify_intent_done(account_id, intent, False)
                await self._save_fail_screenshot(
                    intent, shared_adapter, reason="jihao_popup"
                )
                await self._flush_next_time_updates(account_id, pending_next_time_ops)
                pending_next_time_ops.clear()
                await self._delay_all_tasks_on_jihao(account_id)
                if shared_adapter:
                    try:
                        await self._force_stop_game(shared_adapter)
                    except Exception as e:
                        self._log.error(f"祭号弹窗关闭游戏失败: {e}")
                break
            except AccountExpiredException:
                if not shared_adapter and hasattr(self, '_last_executor_adapter') and self._last_executor_adapter:
                    shared_adapter = self._last_executor_adapter
                batch_success = False
                abort = True
                self._log.warning(f"账号失效: account={intent.account_id}")
                await self._mark_account_invalid(intent.account_id)
                db_log(intent.account_id, "账号登录失效，已标记为无效", level="ERROR")
                # per-intent 完成回调
                if self._executor_service:
                    await self._executor_service.notify_intent_done(account_id, intent, False)
                await self._save_fail_screenshot(
                    intent, shared_adapter, reason="account_expired"
                )
                break
            except CangbaogeListedException:
                if not shared_adapter and hasattr(self, '_last_executor_adapter') and self._last_executor_adapter:
                    shared_adapter = self._last_executor_adapter
                batch_success = False
                abort = True
                self._log.warning(f"检测到藏宝阁界面，关闭游戏并标记账号: account={intent.account_id}")
                await self._mark_account_cangbaoge(intent.account_id)
                db_log(intent.account_id, "检测到账号已上架藏宝阁，已标记状态", level="WARNING")
                # per-intent 完成回调
                if self._executor_service:
                    await self._executor_service.notify_intent_done(account_id, intent, False)
                await self._save_fail_screenshot(
                    intent, shared_adapter, reason="cangbaoge_listed"
                )
                if shared_adapter:
                    try:
                        await self._force_stop_game(shared_adapter)
                    except Exception as e:
                        self._log.error(f"藏宝阁关闭游戏失败: {e}")
                break
            except Exception as exc:
                batch_success = False
                self._log.error(f"Intent error: {exc}")
                task_name = intent.task_type.value if isinstance(intent.task_type, TaskType) else str(intent.task_type)
                db_log(intent.account_id, f"{task_name}任务异常: {str(exc)[:200]}", level="ERROR")
                # per-intent 完成回调
                if self._executor_service:
                    await self._executor_service.notify_intent_done(account_id, intent, False)
                op = self._build_failure_next_time_op(intent)
                if op:
                    pending_next_time_ops.append(op)
                await self._save_fail_screenshot(
                    intent, shared_adapter, reason=str(exc)[:50]
                )

        await self._flush_next_time_updates(account_id, pending_next_time_ops)
        return batch_success, shared_adapter, shared_ui, abort

    async def _do_rescan(self, account_id: int) -> List[TaskIntent]:
        """通过 rescan_callback 获取新到期任务（offload 到线程池）。"""
        if not self.rescan_callback:
            return []
        try:
            return await run_in_db(self.rescan_callback, account_id)
        except Exception as e:
            self._log.error(f"rescan 回调异常: account={account_id}, error={e}")
            return []

    async def _force_stop_game(self, shared_adapter) -> None:
        if isinstance(shared_adapter, AsyncEmulatorAdapter):
            await shared_adapter.adb_force_stop(self._PKG_NAME)
            return
        adb_addr = shared_adapter.cfg.adb_addr
        await run_in_emulator_io(
            adb_addr,
            shared_adapter.adb.force_stop,
            adb_addr,
            self._PKG_NAME,
        )

    async def _adb_root(self, shared_adapter) -> bool:
        if isinstance(shared_adapter, AsyncEmulatorAdapter):
            return await shared_adapter.adb_root()
        adb_addr = shared_adapter.cfg.adb_addr
        return await run_in_emulator_io(
            adb_addr,
            shared_adapter.adb.root,
            adb_addr,
        )

    async def _adb_shell(
        self, shared_adapter, cmd: str, timeout: Optional[float] = None
    ) -> Tuple[int, str]:
        if isinstance(shared_adapter, AsyncEmulatorAdapter):
            return await shared_adapter.adb_shell(cmd, timeout=timeout)

        adb_addr = shared_adapter.cfg.adb_addr
        if timeout is None:
            return await run_in_emulator_io(
                adb_addr,
                shared_adapter.adb.shell,
                adb_addr,
                cmd,
            )

        return await run_in_emulator_io(
            adb_addr,
            lambda: shared_adapter.adb.shell(adb_addr, cmd, timeout=timeout),
        )

    async def _final_cleanup(self, shared_adapter) -> None:
        """所有任务（含 re-scan）完成后关闭游戏、删除登录数据。"""
        if not shared_adapter:
            self._log.info("最终 cleanup: 无 adapter，跳过")
            return

        # 1. 停止游戏
        try:
            await self._force_stop_game(shared_adapter)
            self._log.info("最终 cleanup: 游戏已停止")
        except Exception as e:
            self._log.error(f"最终 cleanup 停止游戏失败: {e}")

        # 2. 删除登录数据 (shared_prefs)
        shared_prefs_path = f"/data/user/0/{self._PKG_NAME}/shared_prefs"
        try:
            rooted = await self._adb_root(shared_adapter)
            if rooted:
                code, out = await self._adb_shell(
                    shared_adapter,
                    f"rm -rf {shared_prefs_path}",
                    timeout=30.0,
                )
                if code == 0:
                    self._log.info(f"最终 cleanup: 已删除登录数据 {shared_prefs_path}")
                else:
                    self._log.warning(
                        f"最终 cleanup: 删除登录数据失败: {out.strip()}"
                    )
            else:
                self._log.warning("最终 cleanup: adb root 失败，无法删除登录数据")
        except Exception as e:
            self._log.error(f"最终 cleanup 删除登录数据失败: {e}")

    async def _mark_account_invalid(self, account_id: int) -> None:
        """将账号状态标记为失效"""
        def _do():
            try:
                with SessionLocal() as db:
                    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
                    if account:
                        account.status = AccountStatus.INVALID
                        db.commit()
                        self._log.info(f"账号已标记为失效: account={account_id}")
            except Exception as e:
                self._log.error(f"标记账号失效失败: account={account_id}, error={e}")
        await run_in_db(_do)

    async def _mark_account_cangbaoge(self, account_id: int) -> None:
        """将账号状态标记为上架藏宝阁"""
        def _do():
            try:
                with SessionLocal() as db:
                    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
                    if account:
                        account.status = AccountStatus.CANGBAOGE
                        db.commit()
                        self._log.info(f"账号已标记为上架藏宝阁: account={account_id}")
            except Exception as e:
                self._log.error(f"标记账号上架藏宝阁失败: account={account_id}, error={e}")
        await run_in_db(_do)

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

        if intent.task_type == TaskType.INIT:
            executor = InitExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.INIT_COLLECT_REWARD:
            executor = InitCollectRewardExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.INIT_RENT_SHIKIGAMI:
            executor = InitRentShikigamiExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.INIT_NEWBIE_QUEST:
            executor = InitNewbieQuestExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.INIT_EXP_DUNGEON:
            executor = InitExpDungeonExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.INIT_COLLECT_JINNANG:
            executor = InitCollectJinnangExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.INIT_SHIKIGAMI_TRAIN:
            executor = InitShikigamiTrainExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.INIT_FANHE_UPGRADE:
            executor = InitFanheUpgradeExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.DELEGATE_HELP:
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
        elif intent.task_type == TaskType.ADD_FRIEND:
            executor = AddFriendExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.DIGUI:
            executor = DiGuiExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.EXPLORE:
            executor = ExploreExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
            # 注入中断回调：探索 yield point 时检查并执行高优先级任务
            executor.interrupt_callback = self._make_interrupt_callback(
                account, executor
            )
        elif intent.task_type == TaskType.XUANSHANG:
            executor = XuanShangExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.CLIMB_TOWER:
            executor = ClimbTowerExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.WEEKLY_SHOP:
            executor = WeeklyShopExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.MIWEN:
            executor = MiWenExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.SIGNIN:
            executor = SigninExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.YUHUN:
            executor = YuHunExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.COLLECT_ACHIEVEMENT:
            executor = CollectAchievementExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.SUMMON_GIFT:
            executor = SummonGiftExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.WEEKLY_SHARE:
            executor = WeeklyShareExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.COLLECT_FANHE_JIUHU:
            executor = CollectFanheJiuhuExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
            )
        elif intent.task_type == TaskType.DUIYI_JINGCAI:
            executor = DuiyiJingcaiExecutor(
                worker_id=self.emulator.id,
                emulator_id=self.emulator.id,
                emulator_row=self.emulator,
                system_config=self.syscfg,
                answer=intent.payload.get("answer") if intent.payload else None,
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

        # 自动包装为异步 adapter（offload ADB I/O 到线程池）
        executor._wrap_async()

        try:
            result = await executor.run_task(task=task, account=account)
        finally:
            # 无论成功或异常，始终保存 adapter/ui（供 cleanup 和后续任务复用）
            self._last_executor_adapter = getattr(executor, 'adapter', None) or executor.shared_adapter
            self._last_executor_ui = getattr(executor, 'ui', None) or executor.shared_ui

        return result.get("status") in (TaskStatus.SUCCEEDED, TaskStatus.SKIPPED)

    def _build_success_next_time_op(
        self, intent: TaskIntent
    ) -> Optional[Tuple[str, str, Optional[str]]]:
        """构建任务成功后的 next_time 更新操作。"""
        task_type = TaskType(intent.task_type)
        if task_type in _EXECUTOR_HAS_OWN_UPDATE:
            return None
        config_key = task_type.value
        next_time = self._compute_next_time(task_type)
        if next_time is None:
            return None
        return "set", config_key, next_time

    def _build_failure_next_time_op(
        self, intent: TaskIntent
    ) -> Optional[Tuple[str, str, Optional[str]]]:
        """构建任务失败后的 next_time 延迟操作。"""
        task_type = TaskType(intent.task_type)
        return "delay", task_type.value, None

    async def _flush_next_time_updates(
        self,
        account_id: int,
        ops: List[Tuple[str, str, Optional[str]]],
    ) -> None:
        """批量刷新 next_time 更新，单次 DB 读写完成。"""
        if not ops:
            return

        from ..cloud.runtime import runtime_mode_state
        if runtime_mode_state.is_cloud():
            return  # Cloud server manages next_time

        ops_copy = list(ops)

        def _do_update():
            try:
                with SessionLocal() as db:
                    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
                    if not account:
                        return
                    cfg = account.task_config or {}
                    changed = False
                    bj_now = now_beijing()
                    for action, config_key, value in ops_copy:
                        task_cfg = cfg.get(config_key, {})
                        if not isinstance(task_cfg, dict):
                            task_cfg = {}

                        if action == "set":
                            if not value:
                                continue
                            task_cfg["next_time"] = value
                            cfg[config_key] = task_cfg
                            changed = True
                            self._log.info(
                                f"[{config_key}] next_time 更新为 {value} (account={account_id})"
                            )
                            continue

                        if action == "delay":
                            fail_delay = task_cfg.get("fail_delay", 30)
                            if not isinstance(fail_delay, (int, float)) or fail_delay <= 0:
                                continue
                            new_next_time = format_beijing_time(
                                bj_now + timedelta(minutes=int(fail_delay))
                            )
                            task_cfg["next_time"] = new_next_time
                            cfg[config_key] = task_cfg
                            changed = True
                            self._log.info(
                                f"[{config_key}] 任务失败，next_time 延后 {int(fail_delay)} 分钟至 {new_next_time} (account={account_id})"
                            )

                    if changed:
                        account.task_config = cfg
                        flag_modified(account, "task_config")
                        db.commit()
            except Exception as e:
                self._log.error(f"批量更新 next_time 失败: account={account_id}, error={e}")

        await run_in_db(_do_update)

    async def _update_next_time_for_intent(self, intent: TaskIntent, account_id: int) -> None:
        """任务成功后统一更新 task_config 中的 next_time。
        已有自定义 _update_next_time 的执行器（弥助、领取登录礼包）会跳过。
        """
        op = self._build_success_next_time_op(intent)
        if not op:
            return
        await self._flush_next_time_updates(account_id, [op])

    async def _update_next_time_on_failure(self, intent: TaskIntent, account_id: int) -> None:
        """任务失败后，根据 task_config 中的 fail_delay 延迟 next_time。"""
        op = self._build_failure_next_time_op(intent)
        if not op:
            return
        await self._flush_next_time_updates(account_id, [op])

    async def _delay_all_tasks_on_jihao(self, account_id: int) -> None:
        """祭号弹窗出现后，批量延后所有即将到期的任务。

        对每个已启用且有 next_time 的任务：
        - 读取该任务的 fail_delay（默认 30 分钟）
        - 如果 next_time <= 当前时间 + fail_delay（已到期或即将到期），
          则将 next_time 设为 当前时间 + fail_delay
        """
        def _do_delay():
            try:
                with SessionLocal() as db:
                    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
                    if not account:
                        return
                    cfg = account.task_config or {}
                    bj_now = now_beijing()
                    updated_count = 0
                    for task_name, task_cfg in cfg.items():
                        if not isinstance(task_cfg, dict):
                            continue
                        if task_cfg.get("enabled") is not True:
                            continue
                        next_time_str = task_cfg.get("next_time")
                        if not next_time_str:
                            continue
                        fail_delay = task_cfg.get("fail_delay", 30)
                        if fail_delay <= 0:
                            continue
                        try:
                            current_next = parse_beijing_time(next_time_str)
                        except Exception:
                            continue
                        deadline = bj_now + timedelta(minutes=fail_delay)
                        if current_next <= deadline:
                            new_next_time = format_beijing_time(bj_now + timedelta(minutes=fail_delay))
                            task_cfg["next_time"] = new_next_time
                            updated_count += 1
                    if updated_count > 0:
                        account.task_config = cfg
                        flag_modified(account, "task_config")
                        db.commit()
                        self._log.info(f"祭号弹窗: 已延后 {updated_count} 个任务 (account={account_id})")
            except Exception as e:
                self._log.error(f"祭号弹窗批量延后失败: account={account_id}, error={e}")

        await run_in_db(_do_delay)

    async def _save_fail_screenshot(
        self,
        intent: TaskIntent,
        shared_adapter,
        reason: str = "",
    ) -> None:
        """任务失败时尝试保存模拟器截图。

        截图保存失败不影响主流程，所有异常静默捕获。
        """
        if not self.syscfg or not getattr(self.syscfg, 'save_fail_screenshot', False):
            return
        if not shared_adapter:
            self._log.debug("无法保存失败截图：adapter 未初始化")
            return
        try:
            from pathlib import Path

            capture_method = getattr(self.syscfg, 'capture_method', None) or 'adb'
            if isinstance(shared_adapter, AsyncEmulatorAdapter):
                png_data = await shared_adapter.capture(method=capture_method)
            else:
                adb_addr = shared_adapter.cfg.adb_addr
                png_data = await run_in_emulator_io(
                    adb_addr,
                    shared_adapter.capture,
                    capture_method,
                )
            if not png_data:
                self._log.warning("保存失败截图：截图数据为空")
                return

            task_name = (
                intent.task_type.value
                if isinstance(intent.task_type, TaskType)
                else str(intent.task_type)
            )
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            safe_reason = reason.replace(" ", "_").replace("/", "_").replace("\\", "_")[:50] if reason else "fail"

            fail_dir = Path("fail_screenshots")
            fail_dir.mkdir(parents=True, exist_ok=True)

            filename = f"{intent.account_id}_{task_name}_{ts}_{safe_reason}.png"
            filepath = fail_dir / filename

            # png_data 可能是 bytes(PNG) 或 ndarray(BGR)
            import numpy as np
            if isinstance(png_data, np.ndarray):
                import cv2
                ok, buf = cv2.imencode('.png', png_data)
                if not ok:
                    self._log.warning("保存失败截图：PNG 编码失败")
                    return
                with open(filepath, "wb") as f:
                    f.write(buf.tobytes())
            else:
                with open(filepath, "wb") as f:
                    f.write(png_data)

            self._log.info(f"失败截图已保存: {filepath}")
        except Exception as exc:
            self._log.warning(f"保存失败截图异常（不影响主流程）: {exc}")

    def _make_interrupt_callback(self, account: GameAccount, executor_ref):
        """创建中断回调闭包，供长任务执行器在 yield point 调用。

        探索等长时间执行器在每轮循环后调用此回调，检查是否有更高优先级
        的到期任务需要插队执行。

        Args:
            account: 当前账号
            executor_ref: 调用方执行器实例（用于获取其 adapter/ui）
        """
        from ...core.constants import TASK_PRIORITY

        async def _interrupt_cb(current_priority: int) -> list[str]:
            if not self.rescan_callback:
                return []

            due_intents = await run_in_db(self.rescan_callback, account.id)
            higher = [
                i for i in due_intents
                if TASK_PRIORITY.get(i.task_type, 0) > current_priority
            ]
            if not higher:
                return []

            higher.sort(
                key=lambda i: TASK_PRIORITY.get(i.task_type, 0), reverse=True
            )
            task_names = [i.task_type.value for i in higher]
            self._log.info(
                f"[中断] 发现 {len(higher)} 个高优先级任务: {task_names}, "
                f"account={account.id}"
            )

            completed = []
            for hi in higher:
                task_name = (
                    hi.task_type.value
                    if isinstance(hi.task_type, TaskType)
                    else str(hi.task_type)
                )
                try:
                    ok = await self._run_intent(
                        hi, account,
                        shared_adapter=executor_ref.adapter,
                        shared_ui=executor_ref.ui,
                        skip_cleanup=True,
                    )
                    if ok:
                        await self._update_next_time_for_intent(hi, account.id)
                        self._log.info(f"[中断] {task_name} 执行成功")
                    else:
                        await self._update_next_time_on_failure(hi, account.id)
                        self._log.warning(f"[中断] {task_name} 执行失败")
                    completed.append(task_name)
                except Exception as exc:
                    self._log.error(f"[中断] {task_name} 异常: {exc}")
                    await self._update_next_time_on_failure(hi, account.id)
                    completed.append(task_name)

            return completed

        return _interrupt_cb

    @staticmethod
    def _compute_next_time(task_type: TaskType) -> Optional[str]:
        """根据任务类型计算下一次执行时间。"""
        bj_now_str = format_beijing_time(now_beijing())

        if task_type == TaskType.FOSTER:
            # 寄养: +6小时
            return add_hours_to_beijing_time(bj_now_str, 6)

        if task_type == TaskType.COOP:
            # 勾协: 下一个 18:00/21:00
            return get_next_fixed_time(bj_now_str, _GOUXIE_FIXED_TIMES)

        if task_type == TaskType.DUIYI_JINGCAI:
            # 对弈竞猜: 下一个 2 小时窗口（10:00-22:00）
            return get_next_fixed_time(bj_now_str, _DUIYI_FIXED_TIMES)

        if task_type in (
            TaskType.CLIMB_TOWER,
            TaskType.FENGMO,
            TaskType.DIGUI,
            TaskType.DAOGUAN,
            TaskType.DAILY_SUMMON,
            TaskType.XUANSHANG,
            TaskType.DOUJI,
        ):
            # 每日任务: 明天 00:01
            tomorrow = now_beijing().date() + timedelta(days=1)
            return f"{tomorrow.isoformat()} 00:01"

        if task_type == TaskType.EXPLORE:
            # 探索突破: +6小时
            return add_hours_to_beijing_time(bj_now_str, 6)

        if task_type == TaskType.MIWEN:
            # 秘闻: 下周一 00:01
            bj_now = now_beijing()
            days_until_monday = (7 - bj_now.weekday()) % 7 or 7
            next_monday = bj_now.date() + timedelta(days=days_until_monday)
            return f"{next_monday.isoformat()} 00:01"

        if task_type == TaskType.WEEKLY_SHARE:
            # 每周分享: +7天
            bj_now = now_beijing()
            return format_beijing_time(bj_now + timedelta(days=7))

        if task_type == TaskType.SUMMON_GIFT:
            # 召唤礼包: 明天 00:01
            tomorrow = now_beijing().date() + timedelta(days=1)
            return f"{tomorrow.isoformat()} 00:01"

        # 结界卡合成等条件触发型任务无需更新 next_time
        return None
