"""
任务管理API
"""
import json
from collections import deque
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import datetime, timedelta

from ....db.base import get_db
from ....db.models import Task, GameAccount, TaskRun
from ....core.constants import TaskStatus
from ....core.config import settings
from ...tasks.simple_scheduler import simple_scheduler
from ...tasks.feeder import feeder
from ...executor.service import executor_service


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/queue")
async def get_task_queue():
    """
    获取任务队列（只读）
    """
    queue_info = executor_service.queue_info()
    return {
        "total": len(queue_info),
        "tasks": queue_info,
        "engine": "feeder_executor",
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
    db: Session = Depends(get_db),
):
    """
    获取执行历史
    """
    query = (
        db.query(
            TaskRun,
            Task,
            GameAccount.login_id.label("account_login_id"),
        )
        .join(Task, TaskRun.task_id == Task.id)
        .outerjoin(GameAccount, GameAccount.id == Task.account_id)
    )

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
    task_runs = (
        query.order_by(desc(TaskRun.started_at)).limit(limit).offset(offset).all()
    )

    # 构建返回数据
    result = []
    for run, task, account_login_id in task_runs:
        result.append(
            {
                "run_id": run.id,
                "task_id": task.id,
                "account_id": task.account_id,
                "account_login_id": account_login_id,
                "task_type": task.type,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "status": run.status,
                "duration": (
                    (run.finished_at - run.started_at).total_seconds()
                    if run.finished_at and run.started_at
                    else None
                ),
                "error_code": run.error_code,
                "artifacts": run.artifacts,
            }
        )

    return {"total": total, "limit": limit, "offset": offset, "history": result}


@router.get("/stats")
async def get_task_stats(db: Session = Depends(get_db)):
    """
    获取任务统计信息
    """
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    status_rows = (
        db.query(TaskRun.status, func.count(TaskRun.id))
        .filter(TaskRun.started_at >= today_start)
        .group_by(TaskRun.status)
        .all()
    )
    status_map = {status: count for status, count in status_rows}
    total = sum(status_map.values())

    today_stats = {
        "total": total,
        "succeeded": int(status_map.get(TaskStatus.SUCCEEDED, 0)),
        "failed": int(status_map.get(TaskStatus.FAILED, 0)),
        "running": int(status_map.get(TaskStatus.RUNNING, 0)),
    }

    if today_stats["total"] > 0:
        today_stats["success_rate"] = round(
            today_stats["succeeded"] / today_stats["total"] * 100, 2
        )
    else:
        today_stats["success_rate"] = 0

    queue_size = len(executor_service.queue_info())
    running_count = len(executor_service.running_info())

    return {
        "today": today_stats,
        "queue_size": queue_size,
        "running_count": running_count,
        "engine": "feeder_executor",
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
    启动运行时调度引擎（feeder + executor）
    """
    if simple_scheduler._running:
        await simple_scheduler.stop()

    await executor_service.start()
    await feeder.start()

    feeder_metrics = feeder.metrics_snapshot()
    executor_metrics = executor_service.metrics_snapshot()
    queue_depth = executor_metrics.get("queue", {}).get("depth", 0)
    running_count = executor_metrics.get("running", {}).get("count", 0)

    return {
        "message": "调度引擎已启动（feeder + executor）",
        "mode": "runtime",
        "engine": "feeder_executor",
        "running": True,
        "feeder_running": feeder._running,
        "executor_running": getattr(executor_service, "_started", False),
        "queue_depth": queue_depth,
        "running_count": running_count,
        "feeder_lag_ms": feeder_metrics.get("feeder_lag_ms", 0),
        "last_scan_at": feeder_metrics.get("last_scan_at"),
    }


@router.post("/scheduler/stop")
async def stop_scheduler():
    """
    停止运行时调度引擎（feeder + executor）
    """
    await feeder.stop()
    await executor_service.stop()

    if simple_scheduler._running:
        await simple_scheduler.stop()

    feeder_metrics = feeder.metrics_snapshot()

    return {
        "message": "调度引擎已停止（feeder + executor）",
        "mode": "runtime",
        "engine": "feeder_executor",
        "running": False,
        "feeder_running": feeder._running,
        "executor_running": getattr(executor_service, "_started", False),
        "queue_depth": 0,
        "running_count": 0,
        "feeder_lag_ms": feeder_metrics.get("feeder_lag_ms", 0),
        "last_scan_at": feeder_metrics.get("last_scan_at"),
    }


@router.get("/scheduler/status")
async def get_scheduler_status():
    """
    获取运行时调度引擎状态
    """
    feeder_running = feeder._running
    executor_running = getattr(executor_service, "_started", False)
    running = feeder_running and executor_running

    feeder_metrics = feeder.metrics_snapshot()
    executor_metrics = executor_service.metrics_snapshot()

    return {
        "running": running,
        "mode": "runtime",
        "engine": "feeder_executor",
        "feeder_running": feeder_running,
        "executor_running": executor_running,
        "queue_depth": executor_metrics.get("queue", {}).get("depth", 0),
        "running_count": executor_metrics.get("running", {}).get("count", 0),
        "feeder_lag_ms": feeder_metrics.get("feeder_lag_ms", 0),
        "last_scan_at": feeder_metrics.get("last_scan_at"),
        "legacy_simple_scheduler_deprecated": True,
        "legacy_simple_scheduler_running": simple_scheduler._running,
    }


@router.post("/simple-scheduler/start", deprecated=True)
async def start_simple_scheduler_deprecated():
    """废弃接口：simple_scheduler 已弃用，禁止启动。"""
    return {
        "deprecated": True,
        "running": simple_scheduler._running,
        "message": "simple_scheduler 启动接口已废弃，请使用 /api/tasks/scheduler/start（feeder + executor）",
    }


@router.post("/simple-scheduler/stop", deprecated=True)
async def stop_simple_scheduler_deprecated():
    """废弃接口：simple_scheduler 已弃用，建议保持停止状态。"""
    if simple_scheduler._running:
        await simple_scheduler.stop()
    return {
        "deprecated": True,
        "running": simple_scheduler._running,
        "message": "simple_scheduler 停止接口已废弃；legacy 调度器当前已停止",
    }


@router.get("/simple-scheduler/status", deprecated=True)
async def get_simple_scheduler_status_deprecated():
    """废弃接口：仅用于兼容诊断。"""
    return {
        "deprecated": True,
        "running": simple_scheduler._running,
        "message": "simple_scheduler 已废弃，仅保留兼容状态查询",
    }


@router.get("/logs")
async def get_task_logs(
    limit: int = 50,
    offset: int = 0,
    account_id: Optional[int] = None,
    level: Optional[str] = None,
    db: Session = Depends(get_db),
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
        result.append(
            {
                "id": log.id,
                "account_id": log.account_id,
                "type": log.type,
                "level": log.level,
                "message": log.message,
                "timestamp": log.ts.isoformat(),
            }
        )

    return {"total": total, "limit": limit, "offset": offset, "logs": result}


def _parse_runtime_cursor(cursor_value: Optional[str]) -> Optional[float]:
    if not cursor_value:
        return None
    try:
        return float(cursor_value)
    except (TypeError, ValueError):
        return None


def _format_runtime_cursor(timestamp_value: float) -> str:
    return f"{timestamp_value:.6f}"


@router.get("/runtime-logs")
async def get_runtime_logs(
    limit: int = Query(80, ge=1, le=500, description="返回条数"),
    level: Optional[str] = Query(None, description="日志级别过滤（INFO/WARNING/ERROR）"),
    module: Optional[str] = Query(None, description="模块关键字过滤"),
    keyword: Optional[str] = Query(None, description="消息关键字过滤"),
    emulator_id: Optional[int] = Query(None, description="按模拟器ID过滤"),
    since_ts: Optional[str] = Query(None, description="仅返回大于该时间戳的日志（Unix秒）"),
    cursor: Optional[str] = Query(None, description="增量游标，优先级高于 since_ts"),
):
    """读取运行时详细日志（含 UI 跳转、启动流程等），支持增量游标。"""
    log_dir = Path(settings.log_path)
    if not log_dir.exists():
        return {
            "total": 0,
            "limit": limit,
            "logs": [],
            "next_cursor": cursor or since_ts,
            "has_more": False,
        }

    app_logs = sorted(
        log_dir.glob("app_*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not app_logs:
        return {
            "total": 0,
            "limit": limit,
            "logs": [],
            "next_cursor": cursor or since_ts,
            "has_more": False,
        }

    runtime_modules = (
        "app.modules.executor",
        "app.modules.ui",
        "app.modules.emu",
        "app.modules.tasks.feeder",
    )

    filter_level = level.upper() if level else None
    filter_module = module.lower() if module else None
    filter_keyword = keyword.lower() if keyword else None
    filter_emulator_id = str(emulator_id) if emulator_id is not None else None

    threshold = _parse_runtime_cursor(cursor)
    if threshold is None:
        threshold = _parse_runtime_cursor(since_ts)

    entries = []
    max_seen_ts = threshold or 0.0
    scan_budget = max(limit * 60, 2000)
    has_more = False

    for file_path in app_logs:
        try:
            with file_path.open("r", encoding="utf-8", errors="ignore") as file_obj:
                tail_lines = deque(file_obj, maxlen=scan_budget)
        except Exception:
            continue

        for line in reversed(tail_lines):
            line = line.strip()
            if not line:
                continue

            try:
                payload = json.loads(line)
            except Exception:
                continue

            record = payload.get("record") or {}
            name = record.get("name") or ""
            msg = record.get("message") or ""
            level_name = (record.get("level") or {}).get("name") or ""
            extra = record.get("extra") or {}
            time_info = record.get("time") or {}
            ts_value = time_info.get("timestamp")
            try:
                ts_epoch = float(ts_value) if ts_value is not None else 0.0
            except (TypeError, ValueError):
                ts_epoch = 0.0

            if threshold is not None and ts_epoch <= threshold:
                continue
            if not name.startswith(runtime_modules):
                continue
            if filter_level and level_name.upper() != filter_level:
                continue
            if (
                filter_module
                and filter_module not in name.lower()
                and filter_module not in str(extra).lower()
            ):
                continue
            if filter_keyword and filter_keyword not in msg.lower():
                continue
            if (
                filter_emulator_id is not None
                and str(extra.get("emulator_id")) != filter_emulator_id
            ):
                continue

            max_seen_ts = max(max_seen_ts, ts_epoch)
            entries.append(
                {
                    "timestamp": (time_info.get("repr") or ""),
                    "timestamp_epoch": ts_epoch,
                    "level": level_name,
                    "module": name,
                    "function": record.get("function"),
                    "message": msg,
                    "worker_id": extra.get("worker_id"),
                    "emulator_id": extra.get("emulator_id"),
                    "account_id": extra.get("account_id"),
                }
            )

            if len(entries) >= limit:
                has_more = True
                break

        if len(entries) >= limit:
            break

    entries.sort(key=lambda x: x.get("timestamp_epoch") or 0.0)
    next_cursor = (
        _format_runtime_cursor(max_seen_ts)
        if (entries or threshold is not None)
        else None
    )

    return {
        "total": len(entries),
        "limit": limit,
        "logs": entries,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }
