"""
Executor status API
"""
from fastapi import APIRouter

from ...executor.service import executor_service
from ...tasks.feeder import feeder


router = APIRouter(prefix="/api/executor", tags=["executor"])


@router.get("/queue")
async def get_executor_queue():
    return {"queue": executor_service.queue_info()}


@router.get("/running")
async def get_executor_running():
    return {"running": executor_service.running_info()}


@router.get("/metrics")
async def get_executor_metrics():
    return {
        "engine": "feeder_executor",
        "executor": executor_service.metrics_snapshot(),
        "feeder": feeder.metrics_snapshot(),
    }
