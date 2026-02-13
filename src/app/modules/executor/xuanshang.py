"""
悬赏执行器 - 导航到悬赏界面，一键追踪悬赏任务，然后导航到探索界面
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
from ..ui.manager import UIManager
from .base import BaseExecutor
from .helpers import click_template

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# 模板路径
_TPL_YIJIANZHUIZONG = "assets/ui/templates/yijianzhuizong.png"


class XuanShangExecutor(BaseExecutor):
    """悬赏执行器"""

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
            activity_name=syscfg.activity_name or ".MainActivity"
            if syscfg
            else ".MainActivity",
        )
        return EmulatorAdapter(cfg)

    async def prepare(self, task: Task, account: GameAccount) -> bool:
        self.logger.info(f"[悬赏] 准备: account={account.login_id}")

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[悬赏] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error("[悬赏] 模拟器不存在: id={}", self.emulator_id)
            return False

        self.adapter = self._build_adapter()

        ok = self.adapter.push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[悬赏] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[悬赏] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[悬赏] 执行: account={self.current_account.login_id}")

        # 构造或复用 UIManager
        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = (
                self.system_config.capture_method if self.system_config else None
            ) or "adb"
            self.ui = UIManager(self.adapter, capture_method=capture_method)

        # 1. 确保游戏就绪（进入庭院）
        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            self.logger.error("[悬赏] 游戏就绪失败，未进入庭院")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. 导航到悬赏界面（庭院 -> 悬赏，通过 UIGraph 自动导航）
        self.logger.info("[悬赏] 开始导航至悬赏界面")
        in_xuanshang = await self.ui.ensure_ui(
            "XUANSHANG", max_steps=6, step_timeout=3.0
        )
        if not in_xuanshang:
            self.logger.error("[悬赏] 导航到悬赏界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航悬赏界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info("[悬赏] 已到达悬赏界面")
        await asyncio.sleep(1.0)

        # 3. 点击一键追踪（如果没找到，说明已追踪，不算失败）
        clicked = await click_template(
            self.adapter,
            self.ui.capture_method,
            _TPL_YIJIANZHUIZONG,
            timeout=8.0,
            settle=0.5,
            post_delay=1.5,
            log=self.logger,
            label="悬赏-一键追踪",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked:
            self.logger.info("[悬赏] 未检测到一键追踪按钮，可能已追踪")

        # 4. 导航到探索界面（悬赏 -> 庭院 -> 探索，通过 UIGraph 自动导航）
        self.logger.info("[悬赏] 开始导航至探索界面")
        in_tansuo = await self.ui.ensure_ui(
            "TANSUO", max_steps=8, step_timeout=3.0
        )
        if not in_tansuo:
            self.logger.warning("[悬赏] 导航到探索界面失败，但悬赏追踪已完成")

        self.logger.info("[悬赏] 执行完成")
        return {
            "status": TaskStatus.SUCCEEDED,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[悬赏] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[悬赏] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[悬赏] 停止游戏失败: {e}")
