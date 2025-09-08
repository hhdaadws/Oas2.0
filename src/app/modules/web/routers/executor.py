"""
Executor status API
"""
from fastapi import APIRouter

from ...executor.service import executor_service


router = APIRouter(prefix="/api/executor", tags=["executor"])


@router.get("/queue")
async def get_executor_queue():
    return {"queue": executor_service.queue_info()}


@router.get("/running")
async def get_executor_running():
    return {"running": executor_service.running_info()}

