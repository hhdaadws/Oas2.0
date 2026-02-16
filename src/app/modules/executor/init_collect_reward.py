"""
起号 - 领取可领取奖励执行器
时间驱动的重复任务，每天执行一次。
流程：导航到新手任务界面 → OCR 点击缘初之路 → 等待页面加载 → 一键领取奖励。
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
from ..ui.dialog_detector import detect_dialog
from ..ui.manager import UIManager
from ..vision.template import match_template
from ..vision.utils import random_point_in_circle
from .base import BaseExecutor
from .db_logger import emit as db_log
from .helpers import click_template, click_text, wait_for_template

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"


class InitCollectRewardExecutor(BaseExecutor):
    """起号 - 领取可领取奖励"""

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
        self.logger.info(
            f"[起号_领取奖励] 准备: account_id={account.id}, login_id={account.login_id}"
        )

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[起号_领取奖励] 复用 shared_adapter，跳过 push 登录数据")
        else:
            if not self.emulator_row:
                with SessionLocal() as db:
                    self.emulator_row = (
                        db.query(Emulator)
                        .filter(Emulator.id == self.emulator_id)
                        .first()
                    )
                    self.system_config = db.query(SystemConfig).first()

            if not self.emulator_row:
                self.logger.error(
                    f"[起号_领取奖励] 模拟器不存在: id={self.emulator_id}"
                )
                return False

            self.adapter = self._build_adapter()

            ok = self.adapter.push_login_data(
                account.login_id, data_dir="putonglogindata"
            )
            if not ok:
                self.logger.error(
                    f"[起号_领取奖励] push 登录数据失败: {account.login_id}"
                )
                return False
            self.logger.info(
                f"[起号_领取奖励] push 登录数据成功: {account.login_id}"
            )

        # 跳过可能的剧情对话
        await self._skip_dialogs()
        return True

    async def execute(self) -> Dict[str, Any]:
        account = self.current_account
        self.logger.info(f"[起号_领取奖励] 执行: account_id={account.id}")

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
            self.logger.error("[起号_领取奖励] 游戏就绪失败，未进入庭院")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. 新手任务一键领取奖励
        newbie_ok = await self._collect_newbie_reward()
        if not newbie_ok:
            self.logger.warning("[起号_领取奖励] 新手任务领取奖励步骤失败")

        # 3. 更新 next_time (+24h)
        self._update_next_time()

        self.logger.info(f"[起号_领取奖励] 执行完成: account_id={account.id}")
        return {
            "status": TaskStatus.SUCCEEDED,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _collect_newbie_reward(self) -> bool:
        """新手任务领取奖励：导航到新手任务界面 → 点击缘初之路 → 一键领取 → 关闭奖励弹窗"""
        self.logger.info("[起号_领取奖励] 开始新手任务领取奖励")

        # 导航到新手任务界面
        in_xinshou = await self.ui.ensure_ui(
            "XINSHOU", max_steps=6, step_timeout=3.0
        )
        if not in_xinshou:
            self.logger.error("[起号_领取奖励] 导航到新手任务界面失败")
            return False

        self.logger.info("[起号_领取奖励] 已到达新手任务界面")
        await asyncio.sleep(1.0)

        # OCR 识别左侧标签列，点击"缘初之路"
        LEFT_COL_ROI = (0, 50, 150, 450)
        clicked_yuanchu = await click_text(
            self.adapter,
            self.ui.capture_method,
            "缘初之路",
            roi=LEFT_COL_ROI,
            timeout=5.0,
            settle=0.5,
            post_delay=1.5,
            log=self.logger,
            label="起号_点击缘初之路",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked_yuanchu:
            self.logger.warning("[起号_领取奖励] 未识别到缘初之路标签，跳过")
            return True

        # 等待缘初之路页面加载完成
        yuanchu_ready = await wait_for_template(
            self.adapter,
            self.ui.capture_method,
            "assets/ui/templates/tag_yuanchu.png",
            timeout=5.0,
            interval=1.0,
            log=self.logger,
            label="起号_等待缘初之路页面",
            popup_handler=self.ui.popup_handler,
        )
        if not yuanchu_ready:
            self.logger.warning("[起号_领取奖励] 缘初之路页面未加载完成")
            return True

        self.logger.info("[起号_领取奖励] 已到达缘初之路页面")

        # 点击一键领取
        clicked = await click_template(
            self.adapter,
            self.ui.capture_method,
            "assets/ui/templates/xinshou_yijianlingqu.png",
            timeout=5.0,
            interval=1.0,
            settle=0.5,
            post_delay=2.0,
            log=self.logger,
            label="起号_新手任务一键领取",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked:
            self.logger.warning("[起号_领取奖励] 未检测到新手任务一键领取按钮，跳过步骤1")
        else:
            # 关闭奖励弹窗
            await self._dismiss_jiangli("新手任务")

        # ---- 领取步骤 2：点击领取奖励 → 一键领取 → 关闭弹窗 ----
        self.logger.info("[起号_领取奖励] 开始领取步骤2")

        # 2a. 点击 lingqu_jiangli.png（领取奖励按钮）
        clicked_jiangli = await click_template(
            self.adapter,
            self.ui.capture_method,
            "assets/ui/templates/lingqu_jiangli.png",
            timeout=5.0,
            interval=1.0,
            settle=0.5,
            post_delay=2.0,
            log=self.logger,
            label="起号_点击领取奖励",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked_jiangli:
            self.logger.warning("[起号_领取奖励] 未检测到领取奖励按钮，跳过步骤2")
            return True

        # 2b. 点击 yijianlingqu.png（一键领取）
        clicked2 = await click_template(
            self.adapter,
            self.ui.capture_method,
            "assets/ui/templates/jiangli_yijianlingqu.png",
            timeout=5.0,
            interval=1.0,
            settle=0.5,
            post_delay=2.0,
            log=self.logger,
            label="起号_步骤2一键领取",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked2:
            self.logger.warning("[起号_领取奖励] 步骤2未检测到一键领取按钮")
            return True

        # 2c. 关闭弹窗（与步骤1相同）
        await self._dismiss_jiangli("步骤2")
        return True

    async def _dismiss_jiangli(self, step_label: str) -> None:
        """关闭 jiangli.png 奖励弹窗（统一模式），并处理可能出现的 chahua.png"""
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is not None:
            if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
                screenshot = self.adapter.capture(self.ui.capture_method)

        if screenshot is not None:
            jiangli_result = match_template(
                screenshot, "assets/ui/templates/jiangli.png"
            )
            if jiangli_result:
                self.logger.info(
                    f"[起号_领取奖励] {step_label} 检测到奖励弹窗，点击关闭"
                )
            else:
                self.logger.warning(
                    f"[起号_领取奖励] {step_label} 未检测到奖励弹窗，仍尝试点击关闭"
                )

        close_x, close_y = random_point_in_circle(20, 20, 20)
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, close_x, close_y)
        self.logger.info(
            f"[起号_领取奖励] {step_label} 随机点击 ({close_x}, {close_y}) 关闭弹窗"
        )
        await asyncio.sleep(1.0)

        # 关闭 jiangli 后可能出现 chahua.png，同样方式关闭
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is not None:
            chahua_result = match_template(
                screenshot, "assets/ui/templates/chahua.png"
            )
            if chahua_result:
                self.logger.info(
                    f"[起号_领取奖励] {step_label} 检测到插画弹窗，点击关闭"
                )
                cx, cy = random_point_in_circle(20, 20, 20)
                self.adapter.adb.tap(self.adapter.cfg.adb_addr, cx, cy)
                self.logger.info(
                    f"[起号_领取奖励] {step_label} 随机点击 ({cx}, {cy}) 关闭插画弹窗"
                )
                await asyncio.sleep(1.0)

    def _update_next_time(self) -> None:
        """更新 next_time 为当前时间 +24 小时"""
        try:
            bj_now_str = format_beijing_time(now_beijing())
            next_time = add_hours_to_beijing_time(bj_now_str, 24)

            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    cfg = account.task_config or {}
                    reward_cfg = cfg.get("起号_领取奖励", {})
                    reward_cfg["next_time"] = next_time
                    cfg["起号_领取奖励"] = reward_cfg
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(
                        f"[起号_领取奖励] next_time 更新为 {next_time}"
                    )
        except Exception as e:
            self.logger.error(f"[起号_领取奖励] 更新 next_time 失败: {e}")

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[起号_领取奖励] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[起号_领取奖励] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[起号_领取奖励] 停止游戏失败: {e}")

    async def _skip_dialogs(
        self,
        max_clicks: int = 50,
        interval: float = 0.8,
    ) -> int:
        """检测并点击跳过剧情对话。"""
        adapter = self.shared_adapter or self.adapter
        if adapter is None:
            return 0

        capture_method = "adb"
        if self.shared_ui and hasattr(self.shared_ui, "capture_method"):
            capture_method = self.shared_ui.capture_method

        clicks = 0
        for _ in range(max_clicks):
            screenshot = adapter.capture(capture_method)
            if screenshot is None:
                await asyncio.sleep(interval)
                continue

            if not detect_dialog(screenshot):
                break

            rx, ry = random_point_in_circle(480, 400, 40)
            adapter.adb.tap(adapter.cfg.adb_addr, rx, ry)
            clicks += 1
            await asyncio.sleep(interval)

        if clicks > 0:
            self.logger.info(f"[起号_领取奖励] 跳过了 {clicks} 轮剧情对话")
        return clicks
