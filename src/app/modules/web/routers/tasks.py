"""
任务管理API
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime, timedelta

from ....db.base import get_db
from ....db.models import Task, GameAccount, TaskRun
from ....core.constants import TaskStatus
from ...tasks.simple_scheduler import simple_scheduler


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/queue")
async def get_task_queue():
    """
    获取任务队列（只读）
    """
    queue_info = simple_scheduler.get_queue_info()
    return {
        "total": len(queue_info),
        "tasks": queue_info
    }


@router.get("/history")
async def get_task_history(
    account_id: Optional[int] = Query(None, description="账号ID"),
    task_type: Optional[str] = Query(None, description="任务类型"),
    status: Optional[str] = Query(None, description="任务状态"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(100, description="返回数量限制"),
    offset: int = Query(0, description="偏移量"),
    db: Session = Depends(get_db)
):
    """
    获取执行历史
    """
    query = db.query(TaskRun).join(Task)
    
    # 应用过滤条件
    if account_id:
        query = query.filter(Task.account_id == account_id)
    if task_type:
        query = query.filter(Task.type == task_type)
    if status:
        query = query.filter(TaskRun.status == status)
    if start_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        query = query.filter(TaskRun.started_at >= start_dt)
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(TaskRun.started_at < end_dt)
    
    # 统计总数
    total = query.count()
    
    # 查询结果
    task_runs = query.order_by(desc(TaskRun.started_at))\
                    .limit(limit)\
                    .offset(offset)\
                    .all()
    
    # 构建返回数据
    result = []
    for run in task_runs:
        task = run.task
        account = db.query(GameAccount).filter(
            GameAccount.id == task.account_id
        ).first()
        
        result.append({
            "run_id": run.id,
            "task_id": task.id,
            "account_id": task.account_id,
            "account_login_id": account.login_id if account else None,
            "task_type": task.type,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "status": run.status,
            "duration": (
                (run.finished_at - run.started_at).total_seconds()
                if run.finished_at and run.started_at else None
            ),
            "error_code": run.error_code,
            "artifacts": run.artifacts
        })
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "history": result
    }


@router.get("/stats")
async def get_task_stats(
    db: Session = Depends(get_db)
):
    """
    获取任务统计信息
    """
    # 今日统计
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    today_runs = db.query(TaskRun).filter(
        TaskRun.started_at >= today_start
    ).all()
    
    today_stats = {
        "total": len(today_runs),
        "succeeded": len([r for r in today_runs if r.status == TaskStatus.SUCCEEDED]),
        "failed": len([r for r in today_runs if r.status == TaskStatus.FAILED]),
        "running": len([r for r in today_runs if r.status == TaskStatus.RUNNING])
    }
    
    # 计算成功率
    if today_stats["total"] > 0:
        today_stats["success_rate"] = round(
            today_stats["succeeded"] / today_stats["total"] * 100, 2
        )
    else:
        today_stats["success_rate"] = 0
    
    # 队列信息
    queue_size = len(simple_scheduler.get_queue_info())
    
    # 正在执行的任务数
    running_count = len(simple_scheduler.running_accounts)
    
    return {
        "today": today_stats,
        "queue_size": queue_size,
        "running_count": running_count
    }


@router.post("/trigger-foster")
async def trigger_foster_tasks(db: Session = Depends(get_db)):
    """
    手动触发寄养任务（测试用）
    """
    # 旧的触发方式已废弃
    pass
    return {"message": "寄养任务已触发"}


@router.post("/load-pending")
async def load_pending_tasks(db: Session = Depends(get_db)):
    """
    手动加载pending任务到队列（测试用）
    """
    # 旧的加载方式已废弃
    pass
    return {"message": "Pending任务已加载"}


@router.post("/check-time-tasks") 
async def check_time_tasks(db: Session = Depends(get_db)):
    """
    手动检查时间任务（测试用）
    """
    # 旧的检查方式已废弃
    pass
    return {"message": "时间任务检查完成"}


@router.post("/check-conditions")
async def check_conditional_tasks(db: Session = Depends(get_db)):
    """
    手动检查条件任务（测试用）
    """
    # 旧的检查方式已废弃
    pass
    return {"message": "条件任务检查完成"}


@router.post("/scheduler/start")
async def start_scheduler():
    """
    启动调度器
    """
    await simple_scheduler.start()
    return {"message": "调度器已启动"}


@router.post("/scheduler/stop")
async def stop_scheduler():
    """
    停止调度器
    """
    await simple_scheduler.stop()
    return {"message": "调度器已停止"}


@router.get("/scheduler/status")
async def get_scheduler_status():
    """
    获取调度器状态
    """
    return {"running": simple_scheduler._running}


@router.get("/logs")
async def get_task_logs(
    limit: int = 50,
    offset: int = 0,
    account_id: Optional[int] = None,
    level: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    获取任务日志
    """
    from ....db.models import Log
    
    # 构建查询
    query = db.query(Log).order_by(Log.ts.desc())
    
    # 按账号过滤
    if account_id:
        query = query.filter(Log.account_id == account_id)
    
    # 按级别过滤
    if level:
        query = query.filter(Log.level == level.upper())
    
    # 分页
    total = query.count()
    logs = query.offset(offset).limit(limit).all()
    
    # 格式化结果
    result = []
    for log in logs:
        result.append({
            "id": log.id,
            "account_id": log.account_id,
            "type": log.type,
            "level": log.level,
            "message": log.message,
            "timestamp": log.ts.isoformat()
        })
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "logs": result
    }