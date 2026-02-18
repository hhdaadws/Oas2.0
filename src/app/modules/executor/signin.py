"""
签到执行器 - 推送登录数据、启动游戏、执行每日签到
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus
from ...core.timeutils import now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ui.manager import UIManager
from ..tasks.signin import perform_signin
from .base import BaseExecutor

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"


class SigninExecutor(BaseExecutor):
    """签到执行器"""

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
        self.logger.info(f"[签到] 准备: account={account.login_id}")

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[签到] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error("[签到] 模拟器不存在: id={}", self.emulator_id)
            return False

        self.adapter = self._build_adapter()

        ok = await self._push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[签到] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[签到] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[签到] 执行: account={self.current_account.login_id}")

        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = (
                self.system_config.capture_method if self.system_config else None
            ) or "adb"
            self.ui = UIManager(self.adapter, capture_method=capture_method, cross_emulator_cache_enabled=self._cross_emulator_cache_enabled())

        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            self.logger.error("[签到] 游戏就绪失败，未进入庭院")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 导航到签到界面
        self.logger.info("[签到] 开始导航至签到界面")
        in_qiandao = await self.ui.ensure_ui("QIANDAO", max_steps=6, step_timeout=3.0)
        if not in_qiandao:
            self.logger.error("[签到] 导航到签到界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航到签到界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        signed = await perform_signin(
            self.adapter,
            capture_method=self.ui.capture_method,
            log=self.logger,
            popup_handler=self.popup_handler,
        )

        if not signed:
            self.logger.warning("[签到] 签到流程未完成")
            return {
                "status": TaskStatus.FAILED,
                "error": "签到流程未完成",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self._update_next_time()

        self.logger.info("[签到] 执行完成")
        return {
            "status": TaskStatus.SUCCEEDED,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _update_next_time(self) -> None:
        """更新签到的 next_time 为明天 18:00"""
        try:
            bj_now = now_beijing()
            tomorrow = bj_now.date() + timedelta(days=1)
            next_time = f"{tomorrow.isoformat()} 18:00"

            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    cfg = account.task_config or {}
                    signin_cfg = cfg.get("签到", {})
                    signin_cfg["next_time"] = next_time
                    cfg["签到"] = signin_cfg
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(f"[签到] next_time 更新为 {next_time}")
        except Exception as e:
            self.logger.error(f"[签到] 更新 next_time 失败: {e}")

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[签到] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                await self._adb_force_stop(PKG_NAME)
                self.logger.info("[签到] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[签到] 停止游戏失败: {e}")
