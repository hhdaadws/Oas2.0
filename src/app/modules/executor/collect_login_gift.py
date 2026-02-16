"""
领取登录礼包执行器 - 推送登录数据、启动游戏、导航到商店领取每日礼包
"""
from __future__ import annotations

import asyncio
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

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"


class CollectLoginGiftExecutor(BaseExecutor):
    """领取登录礼包执行器"""

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
        """根据 emulator_row 和 system_config 构造 EmulatorAdapter"""
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

    @staticmethod
    def _extract_anchor_from_debug(
        detect_result: Any, keyword: str
    ) -> Optional[tuple[int, int]]:
        if not detect_result or not isinstance(
            getattr(detect_result, "debug", None), dict
        ):
            return None

        anchors = detect_result.debug.get("anchors") or {}
        if not isinstance(anchors, dict):
            return None

        target = str(keyword).lower()
        for name, pos in anchors.items():
            if target not in str(name).lower():
                continue
            if isinstance(pos, dict) and "x" in pos and "y" in pos:
                return int(pos["x"]), int(pos["y"])
        return None

    async def prepare(self, task: Task, account: GameAccount) -> bool:
        """
        准备阶段：
        1. 构造 EmulatorAdapter（或复用 shared_adapter）
        2. push 登录数据到模拟器（批次中非首个任务跳过）
        """
        self.logger.info(f"[领取登录礼包] 准备: account={account.login_id}")

        # 批次复用：若 Worker 传入了 shared_adapter，直接复用，跳过 push
        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[领取登录礼包] 复用 shared_adapter，跳过 push 登录数据")
            return True

        # 若未传入 emulator_row，从 DB 重新加载
        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error("[领取登录礼包] 模拟器不存在: id={}", self.emulator_id)
            return False

        self.adapter = self._build_adapter()

        # push 登录数据
        ok = self.adapter.push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[领取登录礼包] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[领取登录礼包] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        """
        执行阶段：
        1. 确保游戏就绪（进入庭院）
        2. 签到（若启用）
        3. 导航到商店界面
        4. 点击礼包物（libaowu）
        5. 点击日常（richang）
        6. 更新 next_time 为明天
        """
        self.logger.info(f"[领取登录礼包] 执行: account={self.current_account.login_id}")

        # 构造 UIManager（或复用 shared_ui）
        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = (
                self.system_config.capture_method if self.system_config else None
            ) or "adb"
            self.ui = UIManager(self.adapter, capture_method=capture_method)

        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            self.logger.error("[领取登录礼包] 游戏就绪失败，未进入庭院")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info("[领取登录礼包] 开始导航至商店界面")
        in_shop = await self.ui.ensure_ui("SHANGDIAN", max_steps=6, step_timeout=3.0)
        if not in_shop:
            self.logger.error("[领取登录礼包] 导航到商店界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航商店界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info("[领取登录礼包] 已到达商店界面")

        self.logger.info("[领取登录礼包] 点击礼包物")
        libaowu_result = self.ui.detect_ui()
        libaowu_anchor = self._extract_anchor_from_debug(libaowu_result, "libaowu")

        if libaowu_anchor:
            self.adapter.adb.tap(
                self.adapter.cfg.adb_addr, libaowu_anchor[0], libaowu_anchor[1]
            )
        else:
            self.logger.warning("[领取登录礼包] 未检测到 libaowu 锚点，尝试固定坐标点击")
            self.adapter.adb.tap(self.adapter.cfg.adb_addr, 200, 400)

        await asyncio.sleep(2.0)

        self.logger.info("[领取登录礼包] 检测并点击日常按钮")
        from ..vision.template import match_template

        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            self.logger.warning("[领取登录礼包] 截图失败，无法检测日常按钮")
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

        result = match_template(screenshot, "assets/ui/templates/richang.png")
        if result:
            rx, ry = result.random_point()
            self.adapter.adb.tap(self.adapter.cfg.adb_addr, rx, ry)
            self.logger.info(f"[领取登录礼包] 点击日常按钮: ({rx}, {ry})")
        else:
            self.logger.warning("[领取登录礼包] 未检测到日常按钮")
            return {
                "status": TaskStatus.FAILED,
                "error": "未检测到日常按钮",
                "timestamp": datetime.utcnow().isoformat(),
            }

        await asyncio.sleep(2.0)

        # 检测领取按钮 (lingqu.png)
        self.logger.info("[领取登录礼包] 检测领取按钮")
        screenshot2 = self.adapter.capture(self.ui.capture_method)
        # 弹窗检测
        if screenshot2 is not None and await self.ui.popup_handler.check_and_dismiss(screenshot2) > 0:
            screenshot2 = self.adapter.capture(self.ui.capture_method)
        lingqu_result = match_template(screenshot2, "assets/ui/templates/lingqu.png") if screenshot2 else None

        if not lingqu_result:
            # 没有领取按钮 → 今天已经领取过了
            self.logger.info("[领取登录礼包] 未检测到领取按钮，今日已领取")
            self._update_next_time()
            return {
                "status": TaskStatus.SUCCEEDED,
                "message": "今日已领取",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 点击领取按钮
        lx, ly = lingqu_result.random_point()
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, lx, ly)
        self.logger.info(f"[领取登录礼包] 点击领取按钮: ({lx}, {ly})")

        await asyncio.sleep(2.0)

        # 检测奖励弹窗 (jiangli.png)
        self.logger.info("[领取登录礼包] 检测奖励弹窗")
        screenshot3 = self.adapter.capture(self.ui.capture_method)
        # 弹窗检测
        if screenshot3 is not None and await self.ui.popup_handler.check_and_dismiss(screenshot3) > 0:
            screenshot3 = self.adapter.capture(self.ui.capture_method)
        jiangli_result = match_template(screenshot3, "assets/ui/templates/jiangli.png") if screenshot3 else None

        if jiangli_result:
            self.logger.info("[领取登录礼包] 检测到奖励弹窗，点击关闭")
        else:
            self.logger.warning("[领取登录礼包] 未检测到奖励弹窗，仍尝试点击关闭")

        # 随机点击关闭奖励弹窗
        from ..vision.utils import random_point_in_circle

        close_x, close_y = random_point_in_circle(20, 20, 20)
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, close_x, close_y)
        self.logger.info(f"[领取登录礼包] 随机点击 ({close_x}, {close_y}) 关闭弹窗")

        await asyncio.sleep(1.0)

        self._update_next_time()

        self.logger.info("[领取登录礼包] 执行完成")
        return {
            "status": TaskStatus.SUCCEEDED,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _update_next_time(self) -> None:
        """更新领取登录礼包的 next_time 为明天 00:01"""
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
                    gift = cfg.get("领取登录礼包", {})
                    gift["next_time"] = next_time
                    cfg["领取登录礼包"] = gift
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(f"[领取登录礼包] next_time 更新为 {next_time}")
        except Exception as e:
            self.logger.error(f"[领取登录礼包] 更新 next_time 失败: {e}")

    async def cleanup(self) -> None:
        """停止游戏（批次中非最后一个任务跳过）"""
        if self.skip_cleanup:
            self.logger.info("[领取登录礼包] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[领取登录礼包] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[领取登录礼包] 停止游戏失败: {e}")
