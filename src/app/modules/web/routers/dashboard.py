"""
仪表盘API
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from ....db.base import get_db
from ....db.models import GameAccount, Task, TaskRun, Log
from ....core.constants import AccountStatus, TaskStatus
from ...tasks.simple_scheduler import simple_scheduler


router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
async def get_dashboard(db: Session = Depends(get_db)):
    """
    获取仪表盘数据
    """
    # 活跃账号数（状态=1且有正在执行或待执行任务的账号）
    active_accounts = db.query(GameAccount).filter(
        GameAccount.status == AccountStatus.ACTIVE
    ).all()
    
    # 统计正在执行任务的账号
    running_account_ids = list(simple_scheduler.running_accounts)
    
    # 实时任务执行列表
    running_tasks = simple_scheduler.get_running_tasks()
    
    # 任务队列预览（前10个）
    queue_preview = simple_scheduler.get_queue_info()
    
    return {
        "active_accounts": len(active_accounts),
        "running_accounts": len(running_account_ids),
        "running_tasks": running_tasks,
        "queue_preview": queue_preview
    }


@router.get("/stats/realtime")
async def get_realtime_stats(db: Session = Depends(get_db)):
    """
    获取实时统计
    """
    # 账号统计
    total_accounts = db.query(GameAccount).count()
    active_accounts = db.query(GameAccount).filter(
        GameAccount.status == AccountStatus.ACTIVE
    ).count()
    invalid_accounts = db.query(GameAccount).filter(
        GameAccount.status == AccountStatus.INVALID
    ).count()
    
    # 任务统计
    queue_size = len(simple_scheduler.get_queue_info())
    running_count = len(simple_scheduler.running_accounts)
    
    # 今日完成任务数（从日志统计）
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_completed = db.query(Log).filter(
        Log.ts >= today_start,
        Log.type == "task",
        Log.message.like("%任务执行成功")
    ).count()
    
    return {
        "accounts": {
            "total": total_accounts,
            "active": active_accounts,
            "invalid": invalid_accounts
        },
        "tasks": {
            "queue": queue_size,
            "running": running_count,
            "today_completed": today_completed
        },
        "timestamp": datetime.utcnow().isoformat()
    }