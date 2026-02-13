"""
起号 - 经验副本执行器
重复任务，刷经验副本提升等级，完成后更新 next_time。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus
from ...core.logger import logger
from ...core.timeutils import format_beijing_time, now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from .base import BaseExecutor
from .db_logger import emit as db_log


class InitExpDungeonExecutor(BaseExecutor):
    """起号 - 经验副本"""

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
        self.logger.info(
            f"[起号_经验副本] 准备: account_id={account.id}, login_id={account.login_id}"
        )
        return True

    async def execute(self) -> Dict[str, Any]:
        account = self.current_account
        self.logger.info(f"[起号_经验副本] 执行: account_id={account.id}")

        # TODO: 实现具体的经验副本逻辑
        # 1. 导航到经验副本界面
        # 2. 选择合适难度的副本
        # 3. 战斗
        # 4. 领取奖励
        # 5. OCR 检测等级变化并更新 account.level

        # 更新 next_time
        self._update_next_time(account.id)

        self.logger.info(f"[起号_经验副本] 执行完成: account_id={account.id}")
        return {
            "status": TaskStatus.SUCCEEDED,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _update_next_time(self, account_id: int) -> None:
        """更新 next_time"""
        try:
            bj_now = now_beijing()
            next_time = format_beijing_time(bj_now + timedelta(hours=2))

            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == account_id)
                    .first()
                )
                if account:
                    cfg = account.task_config or {}
                    dungeon_cfg = cfg.get("起号_经验副本", {})
                    dungeon_cfg["next_time"] = next_time
                    cfg["起号_经验副本"] = dungeon_cfg
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(
                        f"[起号_经验副本] next_time 更新为 {next_time}"
                    )
        except Exception as e:
            self.logger.error(
                f"[起号_经验副本] 更新 next_time 失败: account_id={account_id}, error={e}"
            )

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[起号_经验副本] 批次中非最后任务，跳过 cleanup")
            return
        self.logger.info("[起号_经验副本] cleanup")
