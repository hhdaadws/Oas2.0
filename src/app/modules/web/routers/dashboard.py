"""
仪表盘API
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ....core.constants import AccountStatus, DEFAULT_TASK_CONFIG, DEFAULT_INIT_TASK_CONFIG, TASK_PRIORITY, TaskType
from ....core.timeutils import format_beijing_time, now_beijing
from ....db.base import get_db
from ....db.models import CoopAccount, GameAccount, Log
from ...executor.service import executor_service
from ...tasks.feeder import feeder
from ...tasks.simple_scheduler import simple_scheduler


router = APIRouter(prefix="/api", tags=["dashboard"])

ENABLE_LEGACY_DASHBOARD_FALLBACK = False

# 时间类任务（有 next_time 字段）
_TIME_TASK_KEYS = [
    "寄养", "悬赏", "弥助", "勾协", "加好友", "领取登录礼包", "领取邮件",
    "爬塔", "逢魔", "地鬼", "道馆", "寮商店", "领取寮金币", "每日一抽",
    "每周商店", "秘闻", "探索突破",
]

# 起号阶段：有 next_time 的时间类任务
_INIT_TIME_TASK_KEYS = [
    "起号_新手任务", "起号_经验副本",
    "探索突破", "地鬼", "每周商店", "寮商店", "领取寮金币", "领取邮件", "加好友",
]

# 起号阶段：一次性任务（无 next_time，用 completed 标记）
_INIT_ONETIME_TASK_KEYS = [
    "起号_领取奖励", "起号_租借式神",
]


def _get_priority(task_key: str) -> int:
    """通过 TaskType 枚举查找任务优先级。"""
    try:
        return TASK_PRIORITY.get(TaskType(task_key), 30)
    except ValueError:
        return 30


@router.get("/dashboard")
async def get_dashboard(db: Session = Depends(get_db)):
    """
    获取仪表盘数据
    """
    active_accounts = (
        db.query(GameAccount).filter(GameAccount.status == AccountStatus.ACTIVE).all()
    )

    executor_running = executor_service.running_info()
    executor_queue = executor_service.queue_info()

    if ENABLE_LEGACY_DASHBOARD_FALLBACK and not executor_running:
        running_account_ids = list(simple_scheduler.running_accounts)
        running_tasks = simple_scheduler.get_running_tasks()
    else:
        running_account_ids = [
            item.get("account_id")
            for item in executor_running
            if item.get("account_id")
        ]
        account_map = {acc.id: acc.login_id for acc in active_accounts}
        running_tasks = []
        now_iso = datetime.utcnow().isoformat()
        for item in executor_running:
            account_id = item.get("account_id")
            running_tasks.append(
                {
                    "account_id": account_id,
                    "account_login_id": account_map.get(account_id),
                    "task_type": item.get("task_type") or "执行中",
                    "started_at": item.get("started_at") or now_iso,
                    "emulator_name": item.get("emulator_name"),
                }
            )

    if ENABLE_LEGACY_DASHBOARD_FALLBACK and not executor_queue:
        queue_preview = simple_scheduler.get_queue_info()
    else:
        account_map = {acc.id: acc.login_id for acc in active_accounts}
        priority_map = {
            "加好友": 90,
            "勾协": 80,
            "悬赏": 70,
            "弥助": 65,
            "寄养": 60,
            "领取登录礼包": 55,
            "探索突破": 50,
            "领取邮件": 45,
            "结界卡合成": 40,
            "爬塔": 35,
            "休息": 20,
        }
        queue_preview = []
        for item in executor_queue[:10]:
            task_type = item.get("task_type")
            queue_preview.append(
                {
                    "account_id": item.get("account_id"),
                    "account_login_id": account_map.get(item.get("account_id")),
                    "task_type": task_type,
                    "next_time": item.get("enqueue_time"),
                    "enqueue_time": item.get("enqueue_time"),
                    "priority": priority_map.get(task_type, 30),
                    "state": item.get("state") or "queued",
                    "retry_count": item.get("retry_count") or 0,
                }
            )

    today = datetime.now().date()
    coop_all = (
        db.query(CoopAccount).filter(CoopAccount.status == AccountStatus.ACTIVE).all()
    )
    coop_active = 0
    for coop in coop_all:
        expired = False
        if getattr(coop, "expire_date", None):
            try:
                date_value = datetime.strptime(coop.expire_date, "%Y-%m-%d").date()
                expired = date_value < today
            except Exception:
                expired = False
        if not expired:
            coop_active += 1

    # 计划任务预览：扫描所有活跃账号的 task_config，展示即将执行的任务
    account_map = {acc.id: acc.login_id for acc in active_accounts}
    preview_accounts = (
        db.query(GameAccount)
        .filter(
            GameAccount.status == AccountStatus.ACTIVE,
            GameAccount.progress.in_(["ok", "init"]),
        )
        .all()
    )
    scheduled_preview = []
    for acc in preview_accounts:
        if acc.progress == "init":
            cfg = acc.task_config or DEFAULT_INIT_TASK_CONFIG.copy()
            # 一次性任务（enabled 且未完成 → 即时执行）
            for task_key in _INIT_ONETIME_TASK_KEYS:
                task_cfg = cfg.get(task_key, {})
                if task_cfg.get("enabled") is not True:
                    continue
                if task_cfg.get("completed", False):
                    continue
                scheduled_preview.append({
                    "account_id": acc.id,
                    "account_login_id": acc.login_id,
                    "task_type": task_key,
                    "next_time": "即时",
                    "priority": _get_priority(task_key),
                })
            # 时间类任务
            for task_key in _INIT_TIME_TASK_KEYS:
                task_cfg = cfg.get(task_key, {})
                if task_cfg.get("enabled") is not True:
                    continue
                next_time = task_cfg.get("next_time")
                if not next_time:
                    continue
                scheduled_preview.append({
                    "account_id": acc.id,
                    "account_login_id": acc.login_id,
                    "task_type": task_key,
                    "next_time": next_time,
                    "priority": _get_priority(task_key),
                })
        else:
            cfg = acc.task_config or DEFAULT_TASK_CONFIG.copy()
            for task_key in _TIME_TASK_KEYS:
                task_cfg = cfg.get(task_key, {})
                if task_cfg.get("enabled") is not True:
                    continue
                next_time = task_cfg.get("next_time")
                if not next_time:
                    continue
                scheduled_preview.append({
                    "account_id": acc.id,
                    "account_login_id": acc.login_id,
                    "task_type": task_key,
                    "next_time": next_time,
                    "priority": _get_priority(task_key),
                })
    # 按 next_time 排序，取前 20 个
    scheduled_preview.sort(key=lambda x: x.get("next_time", ""))
    scheduled_preview = scheduled_preview[:20]

    return {
        "active_accounts": len(active_accounts),
        "running_accounts": len(running_account_ids),
        "running_tasks": running_tasks,
        "queue_preview": queue_preview,
        "scheduled_preview": scheduled_preview,
        "coop_active_accounts": coop_active,
        "engine": "feeder_executor",
        "feeder": feeder.metrics_snapshot(),
    }


@router.get("/stats/realtime")
async def get_realtime_stats(db: Session = Depends(get_db)):
    """
    获取实时统计
    """
    total_accounts = db.query(GameAccount).count()
    active_accounts = (
        db.query(GameAccount).filter(GameAccount.status == AccountStatus.ACTIVE).count()
    )
    invalid_accounts = (
        db.query(GameAccount)
        .filter(GameAccount.status == AccountStatus.INVALID)
        .count()
    )

    queue_size = len(executor_service.queue_info())
    running_count = len(executor_service.running_info())
    if ENABLE_LEGACY_DASHBOARD_FALLBACK:
        if queue_size == 0:
            queue_size = len(simple_scheduler.get_queue_info())
        if running_count == 0:
            running_count = len(simple_scheduler.running_accounts)

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_completed = (
        db.query(Log)
        .filter(
            Log.ts >= today_start,
            Log.type == "task",
            Log.message.like("%任务执行成功"),
        )
        .count()
    )

    return {
        "accounts": {
            "total": total_accounts,
            "active": active_accounts,
            "invalid": invalid_accounts,
        },
        "tasks": {
            "queue": queue_size,
            "running": running_count,
            "today_completed": today_completed,
        },
        "timestamp": format_beijing_time(now_beijing()),
        "engine": "feeder_executor",
    }
