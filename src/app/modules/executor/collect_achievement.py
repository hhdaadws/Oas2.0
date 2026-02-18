"""
领取成就奖励执行器 - 导航到花合战→成就界面，识别并领取可领取的成就奖励
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus, TaskType
from ...core.logger import logger
from ...core.timeutils import format_beijing_time, now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ui.manager import UIManager
from .base import BaseExecutor
from .helpers import click_template, wait_for_template

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# 最大领取轮次（防无限循环）
_MAX_COLLECT_ROUNDS = 20


class CollectAchievementExecutor(BaseExecutor):
    """领取成就奖励执行器"""

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
        self.logger.info(f"[领取成就奖励] 准备: account={account.login_id}")

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[领取成就奖励] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error("[领取成就奖励] 模拟器不存在: id={}", self.emulator_id)
            return False

        self.adapter = self._build_adapter()

        ok = await self._push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[领取成就奖励] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[领取成就奖励] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[领取成就奖励] 执行: account={self.current_account.login_id}")

        # 构造/复用 UIManager
        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = (
                self.system_config.capture_method if self.system_config else None
            ) or "adb"
            self.ui = UIManager(self.adapter, capture_method=capture_method, cross_emulator_cache_enabled=self._cross_emulator_cache_enabled())

        # 1. 确保游戏就绪
        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            self.logger.error("[领取成就奖励] 游戏就绪失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. 导航到花合战界面
        self.logger.info("[领取成就奖励] 导航至花合战界面")
        in_huahezhan = await self.ui.ensure_ui("HUAHEZHAN", max_steps=6, step_timeout=3.0)
        if not in_huahezhan:
            self.logger.error("[领取成就奖励] 导航到花合战界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航到花合战界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 3. 导航到成就界面
        self.logger.info("[领取成就奖励] 导航至成就界面")
        in_chengjiu = await self.ui.ensure_ui("CHENGJIU", max_steps=6, step_timeout=3.0)
        if not in_chengjiu:
            self.logger.error("[领取成就奖励] 导航到成就界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航到成就界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 4. 循环识别 chengjiu_lingqu.png 并点击领取
        _TPL_LINGQU = "assets/ui/templates/chengjiu_lingqu.png"

        collected_count = 0
        capture_method = self.ui.capture_method
        popup_handler = self.ui.popup_handler
        label = "领取成就奖励"

        for round_idx in range(_MAX_COLLECT_ROUNDS):
            # 等待领取按钮出现（popup_handler 自动关闭 jiangli/chengjiu_shengji 弹窗）
            m = await wait_for_template(
                self.adapter, capture_method, _TPL_LINGQU,
                timeout=10.0, interval=0.5,
                log=self.logger, label=label,
                popup_handler=popup_handler,
            )
            if not m:
                self.logger.info("[领取成就奖励] 未检测到领取按钮，领取完毕")
                break

            # 点击领取按钮
            ok = await click_template(
                self.adapter, capture_method, _TPL_LINGQU,
                timeout=3.0, settle=0.3, post_delay=0.5,
                log=self.logger, label=label,
                popup_handler=popup_handler,
            )
            if not ok:
                self.logger.warning("[领取成就奖励] 点击领取按钮失败")
                break

            collected_count += 1

        self._update_next_time()

        self.logger.info(f"[领取成就奖励] 执行完成，领取了 {collected_count} 个成就奖励")
        return {
            "status": TaskStatus.SUCCEEDED,
            "message": f"领取了 {collected_count} 个成就奖励",
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _update_next_time(self) -> None:
        """更新领取成就奖励的 next_time 为后天 00:01（每2天执行一次）"""
        try:
            bj_now = now_beijing()
            next_day = bj_now.date() + timedelta(days=2)
            next_time = f"{next_day.isoformat()} 00:01"

            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    cfg = account.task_config or {}
                    task_cfg = cfg.get("领取成就奖励", {})
                    task_cfg["next_time"] = next_time
                    cfg["领取成就奖励"] = task_cfg
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(f"[领取成就奖励] next_time 更新为 {next_time}")
        except Exception as e:
            self.logger.error(f"[领取成就奖励] 更新 next_time 失败: {e}")

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[领取成就奖励] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                await self._adb_force_stop(PKG_NAME)
                self.logger.info("[领取成就奖励] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[领取成就奖励] 停止游戏失败: {e}")
