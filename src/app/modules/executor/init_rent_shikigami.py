"""
起号 - 租借式神执行器
一次性任务，租借式神并 OCR 识别式神名称，完成后标记 completed=True。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus
from ...core.logger import logger
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from .base import BaseExecutor
from .db_logger import emit as db_log


class InitRentShikigamiExecutor(BaseExecutor):
    """起号 - 租借式神"""

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
            f"[起号_租借式神] 准备: account_id={account.id}, login_id={account.login_id}"
        )
        return True

    async def execute(self) -> Dict[str, Any]:
        account = self.current_account
        self.logger.info(f"[起号_租借式神] 执行: account_id={account.id}")

        # TODO: 实现具体的租借式神逻辑
        # 1. 导航到好友/式神租借界面
        # 2. 选择可租借的式神
        # 3. OCR 识别式神名称
        # 4. 完成租借

        # 标记一次性任务完成
        self._mark_completed(account.id)

        self.logger.info(f"[起号_租借式神] 执行完成: account_id={account.id}")
        return {
            "status": TaskStatus.SUCCEEDED,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _mark_completed(self, account_id: int) -> None:
        """标记任务为已完成"""
        try:
            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == account_id)
                    .first()
                )
                if account:
                    cfg = account.task_config or {}
                    rent_cfg = cfg.get("起号_租借式神", {})
                    rent_cfg["completed"] = True
                    cfg["起号_租借式神"] = rent_cfg
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(
                        f"[起号_租借式神] 已标记 completed: account_id={account_id}"
                    )
                    db_log(account_id, "起号_租借式神 已完成")
        except Exception as e:
            self.logger.error(
                f"[起号_租借式神] 标记 completed 失败: account_id={account_id}, error={e}"
            )

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[起号_租借式神] 批次中非最后任务，跳过 cleanup")
            return
        self.logger.info("[起号_租借式神] cleanup")
