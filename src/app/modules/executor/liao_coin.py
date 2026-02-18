"""
领取每日寮金币执行器 - 导航到寮界面，点击领取金币按钮
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus, TaskType
from ...core.logger import logger
from ...core.timeutils import now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ui.manager import UIManager
from ..vision.template import match_template
from .base import BaseExecutor

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"


class LiaoCoinExecutor(BaseExecutor):
    """领取每日寮金币执行器"""

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
        self.logger.info(f"[领取寮金币] 准备: account={account.login_id}")

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[领取寮金币] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error("[领取寮金币] 模拟器不存在: id={}", self.emulator_id)
            return False

        self.adapter = self._build_adapter()

        ok = await self._push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[领取寮金币] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[领取寮金币] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[领取寮金币] 执行: account={self.current_account.login_id}")

        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = (
                self.system_config.capture_method if self.system_config else None
            ) or "adb"
            self.ui = UIManager(self.adapter, capture_method=capture_method, cross_emulator_cache_enabled=self._cross_emulator_cache_enabled())

        # 1. 确保游戏就绪（进入庭院）
        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            self.logger.error("[领取寮金币] 游戏就绪失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. UI导航到寮界面
        self.logger.info("[领取寮金币] 开始导航至寮界面")
        in_liao = await self.ui.ensure_ui("LIAO", max_steps=8, step_timeout=3.0)
        if not in_liao:
            # 检测是否因为未加入寮
            from .helpers import check_and_handle_liao_not_joined
            not_joined = await check_and_handle_liao_not_joined(
                self.adapter,
                self.ui.capture_method,
                self.current_account.id,
                log=self.logger,
                label="领取寮金币",
            )
            if not_joined:
                return {
                    "status": TaskStatus.SKIPPED,
                    "reason": "账号未加入寮，已提交申请并延后寮任务",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            self.logger.error("[领取寮金币] 导航到寮界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航寮界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info("[领取寮金币] 已到达寮界面")

        # 3. 检测寮金币按钮 (liaojinbi_1.png) 并点击
        screenshot = await self._capture()
        if screenshot is None:
            self.logger.error("[领取寮金币] 截图失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "截图失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 弹窗检测
        if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
            screenshot = await self._capture()
            if screenshot is None:
                return {
                    "status": TaskStatus.FAILED,
                    "error": "截图失败",
                    "timestamp": datetime.utcnow().isoformat(),
                }

        jinbi_result = match_template(screenshot, "assets/ui/templates/liaojinbi_1.png")
        if not jinbi_result:
            self.logger.warning("[领取寮金币] 未检测到寮金币按钮，可能已领取")
            self._update_next_time()
            return {
                "status": TaskStatus.SUCCEEDED,
                "message": "未检测到寮金币按钮，可能已领取",
                "timestamp": datetime.utcnow().isoformat(),
            }

        jx, jy = jinbi_result.random_point()
        await self._tap(jx, jy)
        self.logger.info(f"[领取寮金币] 点击寮金币按钮: ({jx}, {jy})")
        await asyncio.sleep(2.0)

        # 4. 检测奖励弹窗 (jiangli.png) 并关闭
        screenshot2 = await self._capture()
        # 弹窗检测
        if screenshot2 is not None and await self.ui.popup_handler.check_and_dismiss(screenshot2) > 0:
            screenshot2 = await self._capture()
        jiangli_result = match_template(screenshot2, "assets/ui/templates/jiangli.png")

        if jiangli_result:
            self.logger.info("[领取寮金币] 检测到奖励弹窗，点击关闭")
        else:
            self.logger.warning("[领取寮金币] 未检测到奖励弹窗，仍尝试点击关闭")

        from ..vision.utils import random_point_in_circle
        close_x, close_y = random_point_in_circle(20, 20, 20)
        await self._tap(close_x, close_y)
        self.logger.info(f"[领取寮金币] 随机点击 ({close_x}, {close_y}) 关闭弹窗")
        await asyncio.sleep(1.0)

        self._update_next_time()

        self.logger.info("[领取寮金币] 执行完成")
        return {
            "status": TaskStatus.SUCCEEDED,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _update_next_time(self) -> None:
        """更新领取寮金币的 next_time 为明天 00:01"""
        try:
            bj_now = now_beijing()
            tomorrow = bj_now.date() + timedelta(days=1)
            next_time = f"{tomorrow.isoformat()} 00:01"

            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    cfg = account.task_config or {}
                    coin = cfg.get("领取寮金币", {})
                    coin["next_time"] = next_time
                    cfg["领取寮金币"] = coin
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(f"[领取寮金币] next_time 更新为 {next_time}")
        except Exception as e:
            self.logger.error(f"[领取寮金币] 更新 next_time 失败: {e}")

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[领取寮金币] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                await self._adb_force_stop(PKG_NAME)
                self.logger.info("[领取寮金币] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[领取寮金币] 停止游戏失败: {e}")
