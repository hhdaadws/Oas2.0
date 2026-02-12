"""
寮商店执行器 - 导航到寮商店界面，下滑购买蓝票礼包
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


class LiaoShopExecutor(BaseExecutor):
    """寮商店执行器"""

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
        self.logger.info(f"[寮商店] 准备: account={account.login_id}")

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[寮商店] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error("[寮商店] 模拟器不存在: id={}", self.emulator_id)
            return False

        self.adapter = self._build_adapter()

        ok = self.adapter.push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[寮商店] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[寮商店] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[寮商店] 执行: account={self.current_account.login_id}")

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
            self.logger.error("[寮商店] 游戏就绪失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. UI导航到寮商店界面
        self.logger.info("[寮商店] 开始导航至寮商店界面")
        in_shop = await self.ui.ensure_ui("LIAO_SHANGDIAN", max_steps=10, step_timeout=3.0)
        if not in_shop:
            self.logger.error("[寮商店] 导航到寮商店界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航寮商店界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info("[寮商店] 已到达寮商店界面，开始执行购买流程")

        # 3. 屏幕中部下滑
        self.adapter.adb.swipe(self.adapter.cfg.adb_addr, 480, 350, 480, 150, 500)
        await asyncio.sleep(1.5)

        # 4. 检测蓝票 (lanpiao.png) 并点击
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            self.logger.error("[寮商店] 截图失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "截图失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 弹窗检测
        if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is None:
                return {
                    "status": TaskStatus.FAILED,
                    "error": "截图失败",
                    "timestamp": datetime.utcnow().isoformat(),
                }

        lanpiao_result = match_template(screenshot, "assets/ui/templates/lanpiao.png")
        if not lanpiao_result:
            self.logger.warning("[寮商店] 未检测到蓝票，可能已购买或界面异常")
            self._update_next_time()
            return {
                "status": TaskStatus.SUCCEEDED,
                "message": "未检测到蓝票，可能已购买",
                "timestamp": datetime.utcnow().isoformat(),
            }

        lx, ly = lanpiao_result.center
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, lx, ly)
        self.logger.info(f"[寮商店] 点击蓝票: ({lx}, {ly})")
        await asyncio.sleep(1.5)

        # 5. 点击 top+.png
        screenshot2 = self.adapter.capture(self.ui.capture_method)
        # 弹窗检测
        if screenshot2 is not None and await self.ui.popup_handler.check_and_dismiss(screenshot2) > 0:
            screenshot2 = self.adapter.capture(self.ui.capture_method)
        top_result = match_template(screenshot2, "assets/ui/templates/top+.png") if screenshot2 else None
        if top_result:
            tx, ty = top_result.center
            self.adapter.adb.tap(self.adapter.cfg.adb_addr, tx, ty)
            self.logger.info(f"[寮商店] 点击 top+: ({tx}, {ty})")
        else:
            self.logger.warning("[寮商店] 未检测到 top+ 按钮")

        await asyncio.sleep(1.5)

        # 6. 点击 buy.png
        screenshot3 = self.adapter.capture(self.ui.capture_method)
        # 弹窗检测
        if screenshot3 is not None and await self.ui.popup_handler.check_and_dismiss(screenshot3) > 0:
            screenshot3 = self.adapter.capture(self.ui.capture_method)
        buy_result = match_template(screenshot3, "assets/ui/templates/buy.png") if screenshot3 else None
        if buy_result:
            bx, by = buy_result.center
            self.adapter.adb.tap(self.adapter.cfg.adb_addr, bx, by)
            self.logger.info(f"[寮商店] 点击购买: ({bx}, {by})")
        else:
            self.logger.warning("[寮商店] 未检测到购买按钮")
            self._update_next_time()
            return {
                "status": TaskStatus.FAILED,
                "error": "未检测到购买按钮",
                "timestamp": datetime.utcnow().isoformat(),
            }

        await asyncio.sleep(2.0)

        # 7. 检测奖励弹窗 (jiangli.png) 并关闭
        screenshot4 = self.adapter.capture(self.ui.capture_method)
        # 弹窗检测
        if screenshot4 is not None and await self.ui.popup_handler.check_and_dismiss(screenshot4) > 0:
            screenshot4 = self.adapter.capture(self.ui.capture_method)
        jiangli_result = match_template(screenshot4, "assets/ui/templates/jiangli.png") if screenshot4 else None

        if jiangli_result:
            self.logger.info("[寮商店] 检测到奖励弹窗，点击关闭")
        else:
            self.logger.warning("[寮商店] 未检测到奖励弹窗，仍尝试点击关闭")

        from ..vision.utils import random_point_in_circle
        close_x, close_y = random_point_in_circle(20, 20, 20)
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, close_x, close_y)
        self.logger.info(f"[寮商店] 随机点击 ({close_x}, {close_y}) 关闭弹窗")
        await asyncio.sleep(1.0)

        self._update_next_time()

        self.logger.info("[寮商店] 执行完成")
        return {
            "status": TaskStatus.SUCCEEDED,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _update_next_time(self) -> None:
        """更新寮商店的 next_time 为下周六 12:00"""
        try:
            bj_now = now_beijing()
            days_until_saturday = (5 - bj_now.weekday()) % 7
            if days_until_saturday == 0 and bj_now.hour >= 12:
                days_until_saturday = 7
            if days_until_saturday == 0:
                days_until_saturday = 7
            next_sat = bj_now.date() + timedelta(days=days_until_saturday)
            next_time = f"{next_sat.isoformat()} 12:00"

            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    cfg = account.task_config or {}
                    shop = cfg.get("寮商店", {})
                    shop["next_time"] = next_time
                    cfg["寮商店"] = shop
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(f"[寮商店] next_time 更新为 {next_time}")
        except Exception as e:
            self.logger.error(f"[寮商店] 更新 next_time 失败: {e}")

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[寮商店] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[寮商店] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[寮商店] 停止游戏失败: {e}")
