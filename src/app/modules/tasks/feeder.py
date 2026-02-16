"""
Feeder scheduler: scans accounts and pushes all eligible tasks to ExecutorService.
Tasks for the same account are batched together for consecutive execution.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import random
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

from ...core.constants import DEFAULT_TASK_CONFIG, DEFAULT_INIT_TASK_CONFIG, TASK_PRIORITY, TaskType
from ...core.logger import logger
from ...core.timeutils import is_time_reached, now_beijing
from ...db.base import SessionLocal
from ...db.models import AccountRestConfig, GameAccount, RestPlan, SystemConfig
from ..executor.service import executor_service
from ..executor.types import TaskIntent
from ..executor.yaml_loader import yaml_task_loader


class Feeder:
    def __init__(self) -> None:
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._rest_plan_generated_date: Optional[str] = None

        self._scan_batch_size = 50
        self._min_rescan_seconds = 20
        self._full_scan_interval_seconds = 300
        self._signature_ttl_seconds = 300

        self._scan_cursor = 0
        self._last_scan_by_account: Dict[int, datetime] = {}
        self._last_enqueued_signature: Dict[int, Tuple[str, datetime]] = {}
        self._last_full_scan_at: Optional[datetime] = None

        self._scan_count = 0
        self._scan_total_ms = 0.0
        self._last_scan_ms = 0.0
        self._last_scan_at: Optional[datetime] = None
        self._last_scan_accounts = 0
        self._last_enqueued_batches = 0
        self._last_skipped_signatures = 0

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
                # 全局休息时间检查（0:00-6:00 北京时间不调度）
                bj_now = now_beijing()
                if 0 <= bj_now.hour < 6:
                    await asyncio.sleep(60)
                    continue

                await self._ensure_daily_rest_plans()
                await self._scan_accounts()
            except Exception as exc:
                self.log.error(f"feeder loop error: {exc}")
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
                        .filter(
                            RestPlan.account_id == account.id,
                            RestPlan.date == today_str,
                        )
                        .first()
                    )
                    if existing:
                        continue

                    rc = (
                        db.query(AccountRestConfig)
                        .filter(AccountRestConfig.account_id == account.id)
                        .first()
                    )
                    # 跳过禁用休息的账号
                    if rc and rc.enabled == 0:
                        continue

                    if (
                        rc
                        and rc.mode == "custom"
                        and rc.rest_start
                        and rc.rest_duration
                    ):
                        start_time = rc.rest_start
                        duration_hours = float(rc.rest_duration)
                        start_dt = datetime.strptime(
                            f"{today_str} {start_time}", "%Y-%m-%d %H:%M"
                        )
                        end_dt = start_dt + timedelta(hours=duration_hours)
                    else:
                        duration_hours = random.uniform(2, 3)
                        start_min_dt = datetime.combine(bj_now.date(), time(7, 0))
                        latest_start_dt = datetime.combine(
                            bj_now.date(), time(23, 0)
                        ) - timedelta(hours=duration_hours)
                        latest_start_dt = max(latest_start_dt, start_min_dt)
                        total_minutes = max(
                            int((latest_start_dt - start_min_dt).total_seconds() // 60),
                            0,
                        )
                        start_dt = start_min_dt + timedelta(
                            minutes=random.randint(0, total_minutes)
                        )
                        start_time = start_dt.strftime("%H:%M")
                        end_dt = min(
                            start_dt + timedelta(hours=duration_hours),
                            datetime.combine(bj_now.date(), time(23, 0)),
                        )

                    plan = RestPlan(
                        account_id=account.id,
                        date=today_str,
                        start_time=start_time,
                        end_time=end_dt.strftime("%H:%M"),
                    )
                    db.add(plan)
                db.commit()

            self._rest_plan_generated_date = today_str
        except Exception as exc:
            self.log.error(f"create rest plans error: {exc}")

    def _is_account_resting(self, account_id: int, db) -> bool:
        """检查账号当前是否在休息时段内。"""
        rc = (
            db.query(AccountRestConfig)
            .filter(AccountRestConfig.account_id == account_id)
            .first()
        )
        if rc and rc.enabled == 0:
            return False

        bj_now = now_beijing()
        today_str = bj_now.date().isoformat()
        plan = (
            db.query(RestPlan)
            .filter(
                RestPlan.account_id == account_id,
                RestPlan.date == today_str,
            )
            .first()
        )
        if not plan:
            return False

        try:
            now_hm = bj_now.hour * 60 + bj_now.minute
            parts_s = plan.start_time.split(":")
            parts_e = plan.end_time.split(":")
            start_hm = int(parts_s[0]) * 60 + int(parts_s[1])
            end_hm = int(parts_e[0]) * 60 + int(parts_e[1])

            if start_hm <= end_hm:
                # 不跨天
                return start_hm <= now_hm < end_hm
            else:
                # 跨天（如 22:00 ~ 02:00）
                return now_hm >= start_hm or now_hm < end_hm
        except Exception:
            return False

    async def _scan_accounts(self) -> None:
        started_at = datetime.utcnow()
        bj_now = now_beijing()
        enqueued_batches = 0
        skipped_by_signature = 0

        with SessionLocal() as db:
            # 读取全局任务开关
            syscfg = db.query(SystemConfig).first()
            global_switches = (syscfg.global_task_switches or {}) if syscfg else {}

            accounts = (
                db.query(GameAccount)
                .filter(
                    GameAccount.status == 1,
                    GameAccount.progress.in_(["ok", "init"]),
                )
                .order_by(GameAccount.id.asc())
                .all()
            )
            selected_accounts = self._select_accounts_for_scan(accounts, bj_now)

            need_commit = False
            for account in selected_accounts:
                self._last_scan_by_account[account.id] = bj_now

                # 账号级休息检查
                if self._is_account_resting(account.id, db):
                    continue

                # --- init 账号：使用起号任务库调度 ---
                if account.progress == "init":
                    cfg = account.task_config or DEFAULT_INIT_TASK_CONFIG.copy()

                    intents = self._collect_init_tasks(account, cfg, global_switches)
                    if not intents:
                        self._last_enqueued_signature.pop(account.id, None)
                        continue

                    signature = self._build_signature(account.id, cfg, intents)
                    if self._is_signature_recent(account.id, signature, bj_now):
                        skipped_by_signature += 1
                        continue
                    if executor_service.enqueue_batch(account.id, intents):
                        self._last_enqueued_signature[account.id] = (signature, bj_now)
                        enqueued_batches += 1
                    continue

                # --- ok 账号：正常调度逻辑 ---
                cfg = account.task_config or DEFAULT_TASK_CONFIG.copy()

                intents = self._collect_ready_tasks(account, cfg, global_switches)
                if not intents:
                    self._last_enqueued_signature.pop(account.id, None)
                    continue

                signature = self._build_signature(account.id, cfg, intents)
                if self._is_signature_recent(account.id, signature, bj_now):
                    skipped_by_signature += 1
                    continue

                if executor_service.enqueue_batch(account.id, intents):
                    self._last_enqueued_signature[account.id] = (signature, bj_now)
                    enqueued_batches += 1

            if need_commit:
                db.commit()

        elapsed_ms = max(0.0, (datetime.utcnow() - started_at).total_seconds() * 1000)
        self._scan_count += 1
        self._scan_total_ms += elapsed_ms
        self._last_scan_ms = elapsed_ms
        self._last_scan_at = datetime.utcnow()
        self._last_scan_accounts = len(selected_accounts)
        self._last_enqueued_batches = enqueued_batches
        self._last_skipped_signatures = skipped_by_signature

    def _select_accounts_for_scan(
        self, accounts: List[GameAccount], now_dt: datetime
    ) -> List[GameAccount]:
        if not accounts:
            return []

        force_full = self._should_force_full_scan(now_dt)
        if force_full:
            self._last_full_scan_at = now_dt
            self._scan_cursor = 0
            return accounts

        max_count = min(self._scan_batch_size, len(accounts))
        selected: List[GameAccount] = []
        total = len(accounts)
        cursor = self._scan_cursor % total
        checked = 0

        while checked < total and len(selected) < max_count:
            account = accounts[cursor]
            last_scan = self._last_scan_by_account.get(account.id)
            if (
                not last_scan
                or (now_dt - last_scan).total_seconds() >= self._min_rescan_seconds
            ):
                selected.append(account)

            cursor = (cursor + 1) % total
            checked += 1

        if not selected:
            selected.append(accounts[self._scan_cursor % total])
            cursor = (self._scan_cursor + 1) % total

        self._scan_cursor = cursor
        return selected

    def _should_force_full_scan(self, now_dt: datetime) -> bool:
        if self._last_full_scan_at is None:
            return True
        return (
            now_dt - self._last_full_scan_at
        ).total_seconds() >= self._full_scan_interval_seconds

    def _build_signature(
        self, account_id: int, cfg: Dict, intents: List[TaskIntent]
    ) -> str:
        task_items = []
        for intent in intents:
            task_name = (
                intent.task_type.value
                if isinstance(intent.task_type, TaskType)
                else str(intent.task_type)
            )
            task_cfg = cfg.get(task_name, {}) if isinstance(cfg, dict) else {}
            task_items.append(
                {
                    "task": task_name,
                    "next_time": task_cfg.get("next_time"),
                    "stamina_threshold": task_cfg.get("stamina_threshold"),
                    "explore_count": task_cfg.get("explore_count"),
                }
            )

        raw = {
            "account_id": account_id,
            "tasks": task_items,
        }
        data = json.dumps(raw, ensure_ascii=False, sort_keys=True)
        return hashlib.md5(data.encode("utf-8")).hexdigest()

    def _is_signature_recent(
        self, account_id: int, signature: str, now_dt: datetime
    ) -> bool:
        previous = self._last_enqueued_signature.get(account_id)
        if not previous:
            return False
        prev_signature, prev_ts = previous
        if prev_signature != signature:
            return False
        return (now_dt - prev_ts).total_seconds() < self._signature_ttl_seconds

    def _collect_init_tasks(self, account: GameAccount, cfg: Dict, global_switches: Dict) -> List[TaskIntent]:
        """收集 init 账号的待执行任务，按优先级和 next_time 并行调度。"""
        intents: List[TaskIntent] = []

        self._check_time_task(intents, account, cfg, "起号_租借式神", TaskType.INIT_RENT_SHIKIGAMI)
        self._check_time_task(intents, account, cfg, "起号_领取奖励", TaskType.INIT_COLLECT_REWARD)
        self._check_time_task(intents, account, cfg, "起号_新手任务", TaskType.INIT_NEWBIE_QUEST)
        self._check_time_task(intents, account, cfg, "起号_经验副本", TaskType.INIT_EXP_DUNGEON)
        self._check_time_task(intents, account, cfg, "起号_领取锦囊", TaskType.INIT_COLLECT_JINNANG)
        self._check_time_task(intents, account, cfg, "起号_式神养成", TaskType.INIT_SHIKIGAMI_TRAIN)
        self._check_time_task(intents, account, cfg, "起号_升级饭盒", TaskType.INIT_FANHE_UPGRADE)
        self._check_time_task(intents, account, cfg, "探索突破", TaskType.EXPLORE)
        if yaml_task_loader.is_enabled("climb_tower"):
            self._check_time_task(intents, account, cfg, "爬塔", TaskType.CLIMB_TOWER)
        self._check_time_task(intents, account, cfg, "地鬼", TaskType.DIGUI)
        self._check_time_task(intents, account, cfg, "每周商店", TaskType.WEEKLY_SHOP)
        self._check_time_task(intents, account, cfg, "寮商店", TaskType.LIAO_SHOP)
        self._check_time_task(intents, account, cfg, "领取寮金币", TaskType.LIAO_COIN)
        self._check_time_task(intents, account, cfg, "领取邮件", TaskType.COLLECT_MAIL)
        self._check_time_task(intents, account, cfg, "加好友", TaskType.ADD_FRIEND)
        self._check_time_task(intents, account, cfg, "签到", TaskType.SIGNIN)
        self._check_time_task(intents, account, cfg, "领取登录礼包", TaskType.COLLECT_LOGIN_GIFT)
        self._check_time_task(intents, account, cfg, "每日一抽", TaskType.DAILY_SUMMON)
        self._check_time_task(intents, account, cfg, "弥助", TaskType.DELEGATE_HELP)
        self._check_time_task(intents, account, cfg, "领取成就奖励", TaskType.COLLECT_ACHIEVEMENT)
        self._check_time_task(intents, account, cfg, "每周分享", TaskType.WEEKLY_SHARE)
        if global_switches.get("召唤礼包"):
            self._check_time_task(intents, account, cfg, "召唤礼包", TaskType.SUMMON_GIFT)
        self._check_time_task(intents, account, cfg, "领取饭盒酒壶", TaskType.COLLECT_FANHE_JIUHU)

        # 斗技：时间窗口检查
        douji_cfg = cfg.get("斗技", {})
        if (douji_cfg.get("enabled") is True
                and douji_cfg.get("next_time")
                and is_time_reached(douji_cfg["next_time"])):
            bj_hour = now_beijing().hour
            start_h = douji_cfg.get("start_hour", 12)
            end_h = douji_cfg.get("end_hour", 23)
            if start_h <= bj_hour < end_h:
                intents.append(TaskIntent(account_id=account.id, task_type=TaskType.DOUJI))

        # 当账号没有租借式神数据时，提升租借任务优先级至最高
        shiki_cfg = account.shikigami_config or {}
        has_rental = bool(shiki_cfg.get("租借式神"))

        def _priority(intent: TaskIntent) -> int:
            p = TASK_PRIORITY.get(intent.task_type, 0)
            if intent.task_type == TaskType.INIT_RENT_SHIKIGAMI and not has_rental:
                p = 200
            return p

        intents.sort(key=_priority, reverse=True)
        return intents

    def _collect_ready_tasks(self, account: GameAccount, cfg: Dict, global_switches: Dict) -> List[TaskIntent]:
        intents: List[TaskIntent] = []

        self._check_time_task(intents, account, cfg, "寄养", TaskType.FOSTER)
        self._check_time_task(intents, account, cfg, "悬赏", TaskType.XUANSHANG)
        self._check_time_task(intents, account, cfg, "弥助", TaskType.DELEGATE_HELP)
        self._check_time_task(intents, account, cfg, "勾协", TaskType.COOP)
        self._check_time_task(intents, account, cfg, "加好友", TaskType.ADD_FRIEND)
        self._check_time_task(
            intents, account, cfg, "领取登录礼包", TaskType.COLLECT_LOGIN_GIFT
        )
        self._check_time_task(intents, account, cfg, "领取邮件", TaskType.COLLECT_MAIL)
        if yaml_task_loader.is_enabled("climb_tower"):
            self._check_time_task(intents, account, cfg, "爬塔", TaskType.CLIMB_TOWER)
        self._check_time_task(intents, account, cfg, "逢魔", TaskType.FENGMO)
        self._check_time_task(intents, account, cfg, "地鬼", TaskType.DIGUI)
        self._check_time_task(intents, account, cfg, "道馆", TaskType.DAOGUAN)
        self._check_time_task(intents, account, cfg, "寮商店", TaskType.LIAO_SHOP)
        self._check_time_task(intents, account, cfg, "领取寮金币", TaskType.LIAO_COIN)
        self._check_time_task(intents, account, cfg, "每日一抽", TaskType.DAILY_SUMMON)
        self._check_time_task(intents, account, cfg, "每周商店", TaskType.WEEKLY_SHOP)
        self._check_time_task(intents, account, cfg, "秘闻", TaskType.MIWEN)
        self._check_time_task(intents, account, cfg, "签到", TaskType.SIGNIN)
        self._check_time_task(intents, account, cfg, "每周分享", TaskType.WEEKLY_SHARE)
        if global_switches.get("召唤礼包"):
            self._check_time_task(intents, account, cfg, "召唤礼包", TaskType.SUMMON_GIFT)
        self._check_time_task(intents, account, cfg, "领取饭盒酒壶", TaskType.COLLECT_FANHE_JIUHU)

        card = cfg.get("结界卡合成", {})
        if card.get("enabled") is True and card.get("explore_count", 0) >= 40:
            intents.append(
                TaskIntent(account_id=account.id, task_type=TaskType.CARD_SYNTHESIS)
            )

        # 御魂：次数驱动，remaining_count > 0 且 next_time 到期时触发
        yuhun = cfg.get("御魂", {})
        if yuhun.get("enabled") is True and yuhun.get("remaining_count", 0) > 0:
            yuhun_next_time = yuhun.get("next_time")
            if not yuhun_next_time or is_time_reached(yuhun_next_time):
                intents.append(
                    TaskIntent(account_id=account.id, task_type=TaskType.YUHUN)
                )

        # 探索突破：改为时间触发，实际体力检查由 Executor 通过 OCR 执行
        self._check_time_task(intents, account, cfg, "探索突破", TaskType.EXPLORE)

        # 斗技：时间窗口检查
        douji_cfg = cfg.get("斗技", {})
        if (douji_cfg.get("enabled") is True
                and douji_cfg.get("next_time")
                and is_time_reached(douji_cfg["next_time"])):
            bj_hour = now_beijing().hour
            start_h = douji_cfg.get("start_hour", 12)
            end_h = douji_cfg.get("end_hour", 23)
            if start_h <= bj_hour < end_h:
                intents.append(TaskIntent(account_id=account.id, task_type=TaskType.DOUJI))

        intents.sort(key=lambda i: TASK_PRIORITY.get(i.task_type, 0), reverse=True)
        return intents

    def _check_time_task(
        self,
        intents: List[TaskIntent],
        account: GameAccount,
        cfg: Dict,
        config_key: str,
        task_type: TaskType,
    ) -> None:
        task_cfg = cfg.get(config_key, {})
        if (
            task_cfg.get("enabled") is True
            and task_cfg.get("next_time")
            and is_time_reached(task_cfg["next_time"])
        ):
            intents.append(TaskIntent(account_id=account.id, task_type=task_type))

    def metrics_snapshot(self) -> dict:
        average_scan_ms = (
            round(self._scan_total_ms / self._scan_count, 2)
            if self._scan_count > 0
            else 0.0
        )
        lag_ms = 0
        if self._last_scan_at is not None:
            lag_ms = max(
                0, int((datetime.utcnow() - self._last_scan_at).total_seconds() * 1000)
            )

        return {
            "running": self._running,
            "scan": {
                "count": self._scan_count,
                "avg_ms": average_scan_ms,
                "last_ms": round(self._last_scan_ms, 2),
                "last_scanned_accounts": self._last_scan_accounts,
                "last_enqueued_batches": self._last_enqueued_batches,
                "last_skipped_signatures": self._last_skipped_signatures,
                "batch_size": self._scan_batch_size,
                "min_rescan_seconds": self._min_rescan_seconds,
                "full_scan_interval_seconds": self._full_scan_interval_seconds,
            },
            "last_scan_at": self._last_scan_at.isoformat()
            if self._last_scan_at
            else None,
            "feeder_lag_ms": lag_ms,
        }


    def collect_due_tasks_for_account(self, account_id: int) -> List[TaskIntent]:
        """为指定账号收集当前到期的任务（供 Worker re-scan 使用）。

        此方法从 DB 重新读取最新的 task_config，因此已执行任务
        （next_time 已被推后）不会再次出现。
        """
        try:
            with SessionLocal() as db:
                syscfg = db.query(SystemConfig).first()
                global_switches = (syscfg.global_task_switches or {}) if syscfg else {}

                account = (
                    db.query(GameAccount)
                    .filter(
                        GameAccount.id == account_id,
                        GameAccount.status == 1,
                    )
                    .first()
                )
                if not account or account.progress not in ("ok", "init"):
                    return []

                # 账号级休息检查
                if self._is_account_resting(account_id, db):
                    return []

                if account.progress == "init":
                    cfg = account.task_config or DEFAULT_INIT_TASK_CONFIG.copy()
                    return self._collect_init_tasks(account, cfg, global_switches)
                else:
                    cfg = account.task_config or DEFAULT_TASK_CONFIG.copy()
                    return self._collect_ready_tasks(account, cfg, global_switches)
        except Exception as exc:
            self.log.error(f"collect_due_tasks_for_account error: account={account_id}, {exc}")
            return []


feeder = Feeder()

__all__ = ["feeder"]
