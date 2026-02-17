"""
领取邮件执行器 - 导航到邮箱界面，一键领取所有邮件奖励
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus
from ...core.logger import logger
from ...core.timeutils import now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ui.manager import UIManager
from .base import BaseExecutor
from .helpers import click_template

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"


class CollectMailExecutor(BaseExecutor):
    """领取邮件执行器"""

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
        self.logger.info(f"[领取邮件] 准备: account={account.login_id}")

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[领取邮件] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error("[领取邮件] 模拟器不存在: id={}", self.emulator_id)
            return False

        self.adapter = self._build_adapter()

        ok = self.adapter.push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[领取邮件] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[领取邮件] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[领取邮件] 执行: account={self.current_account.login_id}")

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
            self.logger.error("[领取邮件] 游戏就绪失败，未进入庭院")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. 导航到邮箱界面
        self.logger.info("[领取邮件] 开始导航至邮箱界面")
        in_mail = await self.ui.ensure_ui("YOUXIANG", max_steps=6, step_timeout=3.0)
        if not in_mail:
            self.logger.error("[领取邮件] 导航到邮箱界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航邮箱界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info("[领取邮件] 已到达邮箱界面")
        await asyncio.sleep(1.0)

        # 3. 截图检测一键领取按钮 (yijianlingqu.png)
        from ..vision.template import match_template

        screenshot = await self._capture()
        if screenshot is None:
            self.logger.warning("[领取邮件] 截图失败")
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

        yijian_result = match_template(screenshot, "assets/ui/templates/yijianlingqu.png")

        if not yijian_result:
            # 没有一键领取按钮 → 已领取过
            self.logger.info("[领取邮件] 未检测到一键领取按钮，邮件已领取")
            self._update_next_time()
            return {
                "status": TaskStatus.SUCCEEDED,
                "message": "邮件已领取",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 4. 点击一键领取
        yx, yy = yijian_result.random_point()
        await self._tap(yx, yy)
        self.logger.info(f"[领取邮件] 点击一键领取: ({yx}, {yy})")

        await asyncio.sleep(2.0)

        # 5. 点击确定按钮 (youxiang_queding.png)
        clicked_confirm = await click_template(
            self.adapter,
            self.ui.capture_method,
            "assets/ui/templates/youxiang_queding.png",
            timeout=5.0,
            interval=1.0,
            settle=0.5,
            post_delay=2.0,
            log=self.logger,
            label="领取邮件_确定",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked_confirm:
            self.logger.warning("[领取邮件] 未检测到确定按钮，继续尝试关闭奖励弹窗")

        # 6. 检测奖励弹窗 (jiangli.png) 或退出按钮 (exit.png) 并处理
        screenshot2 = await self._capture()
        if screenshot2 is not None:
            # 弹窗检测
            if await self.ui.popup_handler.check_and_dismiss(screenshot2) > 0:
                screenshot2 = await self._capture()

        handled = False
        if screenshot2 is not None:
            jiangli_result = match_template(screenshot2, "assets/ui/templates/jiangli.png")
            if jiangli_result:
                self.logger.info("[领取邮件] 检测到奖励弹窗，点击关闭")
                from ..vision.utils import random_point_in_circle

                close_x, close_y = random_point_in_circle(20, 20, 20)
                await self._tap(close_x, close_y)
                self.logger.info(f"[领取邮件] 随机点击 ({close_x}, {close_y}) 关闭弹窗")
                handled = True

            if not handled:
                exit_result = match_template(screenshot2, "assets/ui/templates/exit.png")
                if exit_result:
                    self.logger.info("[领取邮件] 检测到 exit 按钮，点击退出")
                    ex, ey = exit_result.random_point()
                    await self._tap(ex, ey)
                    self.logger.info(f"[领取邮件] 点击 exit: ({ex}, {ey})")
                    handled = True

        if not handled:
            self.logger.warning("[领取邮件] 未检测到奖励弹窗或 exit 按钮，尝试随机点击关闭")
            from ..vision.utils import random_point_in_circle

            close_x, close_y = random_point_in_circle(20, 20, 20)
            await self._tap(close_x, close_y)

        await asyncio.sleep(1.0)

        # 6. 更新 next_time
        self._update_next_time()

        self.logger.info("[领取邮件] 执行完成")
        return {
            "status": TaskStatus.SUCCEEDED,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _update_next_time(self) -> None:
        """更新领取邮件的 next_time 为明天 15:00-16:00 之间的随机时间"""
        try:
            bj_now = now_beijing()
            tomorrow = bj_now.date() + timedelta(days=1)
            random_minute = random.randint(0, 59)
            next_time = f"{tomorrow.isoformat()} 15:{random_minute:02d}"

            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    cfg = account.task_config or {}
                    mail_cfg = cfg.get("领取邮件", {})
                    mail_cfg["next_time"] = next_time
                    cfg["领取邮件"] = mail_cfg
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(f"[领取邮件] next_time 更新为 {next_time}")
        except Exception as e:
            self.logger.error(f"[领取邮件] 更新 next_time 失败: {e}")

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[领取邮件] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[领取邮件] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[领取邮件] 停止游戏失败: {e}")
