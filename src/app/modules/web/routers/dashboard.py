"""
仪表盘API
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ....core.constants import AccountStatus, DEFAULT_TASK_CONFIG, DEFAULT_INIT_TASK_CONFIG, TASK_PRIORITY, TaskType
from ....core.timeutils import format_beijing_time, is_time_reached, now_beijing
from ....db.base import get_db
from ....db.models import CoopAccount, GameAccount, Log
from ...cloud import cloud_task_poller, runtime_mode_state
from ...executor.service import executor_service
from ...tasks.feeder import feeder


router = APIRouter(prefix="/api", tags=["dashboard"])

# 时间类任务（有 next_time 字段）
_TIME_TASK_KEYS = [
    "寄养", "悬赏", "弥助", "勾协", "加好友", "领取登录礼包", "领取邮件",
    "爬塔", "逢魔", "地鬼", "道馆", "寮商店", "领取寮金币", "每日一抽",
    "每周商店", "秘闻", "探索突破", "每周分享", "召唤礼包", "斗技",
]

# 起号阶段：有 next_time 的时间类任务
_INIT_TIME_TASK_KEYS = [
    "起号_新手任务", "起号_经验副本", "起号_领取锦囊",
    "探索突破", "地鬼", "每周商店", "寮商店", "领取寮金币", "领取邮件", "加好友",
    "领取成就奖励", "每周分享", "召唤礼包", "斗技",
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
    mode = runtime_mode_state.get_mode()

    executor_running = executor_service.running_info()
    executor_queue = executor_service.queue_info()

    if mode == "cloud":
        # 云端模式：不查询勾协库，但需要查 GameAccount 获取 login_id 映射
        active_count = 0
        coop_active = 0
        scheduled_preview = []

        # 收集相关 account_id 并查 DB 获取 login_id
        relevant_ids = set()
        for item in executor_running:
            if item.get("account_id"):
                relevant_ids.add(item["account_id"])
        for item in executor_queue:
            if item.get("account_id"):
                relevant_ids.add(item["account_id"])

        account_map = {}
        if relevant_ids:
            accs = (
                db.query(GameAccount)
                .filter(GameAccount.id.in_(list(relevant_ids)))
                .all()
            )
            account_map = {a.id: a.login_id for a in accs}
    else:
        # 本地模式：查询本地账号和勾协库
        active_accounts = (
            db.query(GameAccount).filter(GameAccount.status == AccountStatus.ACTIVE).all()
        )
        active_count = len(active_accounts)
        account_map = {acc.id: acc.login_id for acc in active_accounts}

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
                        "is_due": True,
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
                        "is_due": is_time_reached(next_time),
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
                        "is_due": is_time_reached(next_time),
                    })
        # 分离已到期和未到期任务，分别排序后合并展示
        due_tasks = [t for t in scheduled_preview if t.get("is_due")]
        pending_tasks = [t for t in scheduled_preview if not t.get("is_due")]
        due_tasks.sort(key=lambda x: x.get("next_time", ""))
        pending_tasks.sort(key=lambda x: x.get("next_time", ""))
        MAX_DUE = 20
        MAX_TOTAL = 50
        due_tasks = due_tasks[-MAX_DUE:] if len(due_tasks) > MAX_DUE else due_tasks
        remaining_slots = MAX_TOTAL - len(due_tasks)
        pending_tasks = pending_tasks[:remaining_slots]
        scheduled_preview = due_tasks + pending_tasks

    running_account_ids = [
        item.get("account_id")
        for item in executor_running
        if item.get("account_id")
    ]
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
        "斗技": 36,
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

    # 云端模式：构建已获取任务预览
    cloud_jobs_preview = []
    if mode == "cloud":
        poller_status = cloud_task_poller.status()
        tracked = poller_status.get("tracked_job_details", [])
        deferred = poller_status.get("deferred_job_details", [])

        for item in tracked:
            cloud_jobs_preview.append({
                "job_id": item.get("job_id"),
                "account_id": item.get("account_id"),
                "account_login_id": item.get("login_id") or account_map.get(item.get("account_id"), ""),
                "task_type": item.get("task_type", ""),
                "status": "执行中",
            })
        for item in deferred:
            cloud_jobs_preview.append({
                "job_id": item.get("job_id"),
                "account_id": item.get("account_id"),
                "account_login_id": item.get("login_id") or account_map.get(item.get("account_id"), ""),
                "task_type": item.get("task_type", ""),
                "status": "等待中",
            })

    return {
        "active_accounts": active_count,
        "running_accounts": len(running_account_ids),
        "running_tasks": running_tasks,
        "queue_preview": queue_preview,
        "scheduled_preview": scheduled_preview,
        "coop_active_accounts": coop_active,
        "mode": mode,
        "engine": "cloud_poller_executor" if mode == "cloud" else "feeder_executor",
        "feeder": feeder.metrics_snapshot(),
        "cloud_jobs_preview": cloud_jobs_preview,
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
