"""
任务资源预检：检查执行任务所需的资产是否充足（通过 OCR 实时读取）。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from loguru import logger

from ...core.constants import TaskType
from ...db.base import SessionLocal
from ...db.models import GameAccount
from ..ui.assets import AssetType, get_asset_def

# 任务资源需求注册表：task_type → [(asset_type, min_amount), ...]
TASK_RESOURCE_REQUIREMENTS: Dict[TaskType, List[Tuple[AssetType, int]]] = {
    TaskType.DELEGATE_HELP: [(AssetType.STAMINA, 300)],
}


async def check_resources(
    ui,
    task_type: TaskType,
    account_id: int,
) -> Tuple[bool, Dict[str, int]]:
    """检查任务所需的资源是否满足。

    通过 OCR 实时读取资产值，同时更新数据库（仅用于展示）。

    Args:
        ui: UIManager 实例
        task_type: 当前任务类型
        account_id: 当前账号 ID

    Returns:
        (satisfied, read_values) - 是否满足, 以及读到的资产值字典
    """
    requirements = TASK_RESOURCE_REQUIREMENTS.get(task_type)
    if not requirements:
        return True, {}

    read_values: Dict[str, int] = {}
    all_satisfied = True

    for asset_type, min_amount in requirements:
        value = await ui.read_asset(asset_type)
        if value is None:
            logger.warning(
                "资源检查: {} OCR 读取失败，按不满足处理", asset_type.value
            )
            all_satisfied = False
            continue

        read_values[asset_type.value] = value

        # 更新数据库（仅展示用途，fire-and-forget offload）
        _fire_update_asset(account_id, asset_type, value)

        if value < min_amount:
            logger.info(
                "资源不足: {}={} < {}", asset_type.value, value, min_amount
            )
            all_satisfied = False

    return all_satisfied, read_values


def _fire_update_asset(account_id: int, asset_type: AssetType, value: int) -> None:
    """Fire-and-forget: 将资产更新 offload 到线程池。"""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        from ...core.thread_pool import get_io_pool
        loop.run_in_executor(
            get_io_pool(), _update_asset_in_db, account_id, asset_type, value
        )
    except RuntimeError:
        _update_asset_in_db(account_id, asset_type, value)


def _update_asset_in_db(account_id: int, asset_type: AssetType, value: int) -> None:
    """将 OCR 读取的资产值写入数据库（仅供展示）。"""
    asset_def = get_asset_def(asset_type)
    if not asset_def:
        return
    try:
        with SessionLocal() as db:
            acc = db.query(GameAccount).filter(GameAccount.id == account_id).first()
            if acc:
                setattr(acc, asset_def.db_field, value)
                db.commit()
                logger.debug(
                    "DB 更新: account={}, {}={}", account_id, asset_def.db_field, value
                )
    except Exception as e:
        logger.warning("更新资产到 DB 失败: {}", e)
