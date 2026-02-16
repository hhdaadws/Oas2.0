"""
加好友执行器 - 导航到好友界面，循环点击加好友按钮发送好友申请
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus
from ...core.logger import logger
from ...core.timeutils import add_hours_to_beijing_time, format_beijing_time, now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ui.manager import UIManager
from ..vision.template import match_template
from .base import BaseExecutor
from .helpers import click_template, wait_for_template

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# 安全限制：最大加好友循环次数
MAX_ADD_FRIEND_LOOPS = 30


class AddFriendExecutor(BaseExecutor):
    """加好友执行器"""

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
        self.logger.info(f"[加好友] 准备: account={account.login_id}")

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[加好友] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error("[加好友] 模拟器不存在: id={}", self.emulator_id)
            return False

        self.adapter = self._build_adapter()

        ok = self.adapter.push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[加好友] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[加好友] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[加好友] 执行: account={self.current_account.login_id}")

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
            self.logger.error("[加好友] 游戏就绪失败，未进入庭院")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. 导航到好友界面
        self.logger.info("[加好友] 开始导航至好友界面")
        in_haoyou = await self.ui.ensure_ui("HAOYOU", max_steps=6, step_timeout=3.0)
        if not in_haoyou:
            self.logger.error("[加好友] 导航到好友界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航好友界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info("[加好友] 已到达好友界面")
        await asyncio.sleep(1.0)

        # 3. 点击"添加"按钮（tianjia.png）进入推荐好友列表
        clicked_tianjia = await click_template(
            self.adapter,
            self.ui.capture_method,
            "assets/ui/templates/tianjia.png",
            timeout=5.0,
            interval=1.0,
            settle=0.5,
            post_delay=2.0,
            log=self.logger,
            label="加好友-添加",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked_tianjia:
            self.logger.warning("[加好友] 未检测到添加按钮")
            self._update_next_time()
            return {
                "status": TaskStatus.SKIPPED,
                "reason": "未检测到添加按钮",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 4. 循环点击"加好友"按钮发送好友申请
        friends_added = 0
        for i in range(MAX_ADD_FRIEND_LOOPS):
            # 截图检测 jiahaoyou.png
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is None:
                self.logger.warning("[加好友] 截图失败，中断循环")
                break

            # 弹窗检测
            if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
                screenshot = self.adapter.capture(self.ui.capture_method)
                if screenshot is None:
                    break

            jiahaoyou_match = match_template(
                screenshot, "assets/ui/templates/jiahaoyou.png"
            )
            if not jiahaoyou_match:
                self.logger.info(
                    f"[加好友] 未检测到加好友按钮，循环结束 (已添加 {friends_added} 个)"
                )
                break

            # 点击 jiahaoyou 区域内随机位置
            jx, jy = jiahaoyou_match.random_point()
            self.adapter.adb.tap(self.adapter.cfg.adb_addr, jx, jy)
            self.logger.info(f"[加好友] 点击加好友: ({jx}, {jy}) (第 {i + 1} 次)")
            await asyncio.sleep(1.5)

            # 等待申请按钮（shenqing.png）出现
            shenqing_match = await wait_for_template(
                self.adapter,
                self.ui.capture_method,
                "assets/ui/templates/shenqing.png",
                timeout=5.0,
                interval=0.5,
                log=self.logger,
                label="加好友-申请",
                popup_handler=self.ui.popup_handler,
            )
            if shenqing_match:
                sx, sy = shenqing_match.random_point()
                self.adapter.adb.tap(self.adapter.cfg.adb_addr, sx, sy)
                self.logger.info(f"[加好友] 点击申请: ({sx}, {sy})")
                friends_added += 1
                await asyncio.sleep(1.0)
            else:
                self.logger.warning("[加好友] 申请按钮未出现，跳过本次")
                await asyncio.sleep(0.5)

        # 5. 更新 next_time
        self._update_next_time()

        self.logger.info(f"[加好友] 执行完成，共添加 {friends_added} 个好友")
        return {
            "status": TaskStatus.SUCCEEDED,
            "friends_added": friends_added,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _update_next_time(self) -> None:
        """更新加好友的 next_time 为当前时间 +10 小时"""
        try:
            bj_now_str = format_beijing_time(now_beijing())
            next_time = add_hours_to_beijing_time(bj_now_str, 10)

            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    cfg = account.task_config or {}
                    friend_cfg = cfg.get("加好友", {})
                    friend_cfg["next_time"] = next_time
                    cfg["加好友"] = friend_cfg
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(f"[加好友] next_time 更新为 {next_time}")
        except Exception as e:
            self.logger.error(f"[加好友] 更新 next_time 失败: {e}")

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[加好友] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[加好友] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[加好友] 停止游戏失败: {e}")
