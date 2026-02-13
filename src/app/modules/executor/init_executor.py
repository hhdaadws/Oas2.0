"""
起号执行器 - 已废弃
起号功能已拆分为独立的子执行器：
- InitCollectRewardExecutor（起号_领取奖励）
- InitRentShikigamiExecutor（起号_租借式神）
- InitNewbieQuestExecutor（起号_新手任务）
- InitExpDungeonExecutor（起号_经验副本）

此类保留用于向后兼容，仅作为空操作占位。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from ...core.constants import TaskStatus
from ...core.logger import logger
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from .base import BaseExecutor


class InitExecutor(BaseExecutor):
    """起号执行器（已废弃，保留向后兼容）"""

    def __init__(
        self,
        worker_id: int,
        emulator_id: int,
        emulator_row: Optional[Emulator] = None,
        system_config: Optional[SystemConfig] = None,
    ):
        super().__init__(worker_id=worker_id, emulator_id=emulator_id)
        self.emulator_row = emulator_row
        self.system_config = system_config

    async def prepare(self, task: Task, account: GameAccount) -> bool:
        self.logger.warning(
            f"[起号] 使用了已废弃的 InitExecutor: account_id={account.id}"
        )
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.warning("[起号] InitExecutor 已废弃，直接返回成功")
        return {
            "status": TaskStatus.SUCCEEDED,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def cleanup(self) -> None:
        pass
