"""
秘闻执行器 - 导航到秘闻界面（骨架，具体逻辑待补充）
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from ...core.constants import TaskStatus
from ...core.logger import logger
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..lineup import get_lineup_for_task
from ..ui.manager import UIManager
from .base import BaseExecutor
from .lineup_switch import switch_lineup

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"


class MiWenExecutor(BaseExecutor):
    """秘闻执行器（骨架）"""

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
        self.adapter: Optional[EmulatorAdapter] = None
        self.ui: Optional[UIManager] = None

    def _build_adapter(self) -> EmulatorAdapter:
        emu = self.emulator_row
        syscfg = self.system_config

        cfg = AdapterConfig(
            adb_path=syscfg.adb_path if syscfg else "adb",
            adb_addr=emu.adb_addr,
            pkg_name=PKG_NAME,
            ipc_dll_path=syscfg.ipc_dll_path or "" if syscfg else "",
            mumu_manager_path=syscfg.mumu_manager_path or "" if syscfg else "",
            nemu_folder=syscfg.nemu_folder or "" if syscfg else "",
            instance_id=emu.instance_id,
            activity_name=syscfg.activity_name or ".MainActivity" if syscfg else ".MainActivity",
        )
        return EmulatorAdapter(cfg)

    async def prepare(self, task: Task, account: GameAccount) -> bool:
        self.logger.info(f"[秘闻] 准备: account={account.login_id}")

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[秘闻] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error(f"[秘闻] 模拟器不存在: id={self.emulator_id}")
            return False

        self.adapter = self._build_adapter()

        ok = await self._push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[秘闻] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[秘闻] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[秘闻] 执行: account={self.current_account.login_id}")

        # 构造/复用 UIManager
        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = (
                (self.system_config.capture_method if self.system_config else None)
                or "adb"
            )
            self.ui = UIManager(self.adapter, capture_method=capture_method, cross_emulator_cache_enabled=self._cross_emulator_cache_enabled())

        # 1. 确保游戏就绪
        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            self.logger.error("[秘闻] 游戏就绪失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. 切换阵容
        lineup_config = self.current_account.lineup_config or {}
        lineup = get_lineup_for_task(lineup_config, "秘闻")
        group = lineup.get("group", 0)
        position = lineup.get("position", 0)

        if group > 0 and position > 0:
            self.logger.info(f"[秘闻] 切换阵容: 分组={group}, 阵容={position}")
            ok = await switch_lineup(
                self.adapter,
                self.ui,
                self.ui.capture_method,
                group=group,
                position=position,
                log=self.logger,
            )
            if not ok:
                self.logger.error("[秘闻] 阵容切换失败")
                return {
                    "status": TaskStatus.FAILED,
                    "error": "阵容切换失败",
                    "timestamp": datetime.utcnow().isoformat(),
                }
        else:
            self.logger.info("[秘闻] 未配置阵容，跳过切换")

        # 3. 导航到秘闻界面
        in_miwen = await self.ui.ensure_ui("MIWEN", max_steps=8, step_timeout=3.0)
        if not in_miwen:
            self.logger.error("[秘闻] 导航到秘闻界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航秘闻界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info("[秘闻] 已到达秘闻界面")

        # TODO: 具体秘闻逻辑待补充

        return {
            "status": TaskStatus.SUCCEEDED,
            "message": "秘闻骨架执行完成（具体逻辑待补充）",
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[秘闻] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                await self._adb_force_stop(PKG_NAME)
                self.logger.info("[秘闻] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[秘闻] 停止游戏失败: {e}")
