"""
起号 - 领取锦囊执行器
时间驱动的重复任务，每 8 小时执行一次。
流程：导航到新手任务界面 → OCR 点击成长锦囊 → 等待页面加载 → 一键领取奖励。
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
from .helpers import click_template, click_text, wait_for_template, _adapter_capture, _adapter_tap

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"


class InitCollectJinnangExecutor(BaseExecutor):
    """起号 - 领取锦囊"""

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
            f"[起号_领取锦囊] 准备: account_id={account.id}, login_id={account.login_id}"
        )

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[起号_领取锦囊] 复用 shared_adapter，跳过 push 登录数据")
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
                    f"[起号_领取锦囊] 模拟器不存在: id={self.emulator_id}"
                )
                return False

            self.adapter = self._build_adapter()

            ok = self.adapter.push_login_data(
                account.login_id, data_dir="putonglogindata"
            )
            if not ok:
                self.logger.error(
                    f"[起号_领取锦囊] push 登录数据失败: {account.login_id}"
                )
                return False
            self.logger.info(
                f"[起号_领取锦囊] push 登录数据成功: {account.login_id}"
            )

        # 跳过可能的剧情对话
        await self._skip_dialogs()
        return True

    async def execute(self) -> Dict[str, Any]:
        account = self.current_account
        self.logger.info(f"[起号_领取锦囊] 执行: account_id={account.id}")

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
            self.logger.error("[起号_领取锦囊] 游戏就绪失败，未进入庭院")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. 领取锦囊
        jinnang_ok = await self._collect_jinnang()
        if not jinnang_ok:
            self.logger.warning("[起号_领取锦囊] 领取锦囊步骤失败")

        # 3. 更新 next_time (+8h)
        self._update_next_time()

        self.logger.info(f"[起号_领取锦囊] 执行完成: account_id={account.id}")
        return {
            "status": TaskStatus.SUCCEEDED,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _collect_jinnang(self) -> bool:
        """领取锦囊：导航到新手任务界面 → 点击成长锦囊 → 一键领取 → 关闭弹窗"""
        self.logger.info("[起号_领取锦囊] 开始领取锦囊")

        # 导航到新手任务界面
        in_xinshou = await self.ui.ensure_ui(
            "XINSHOU", max_steps=6, step_timeout=3.0
        )
        if not in_xinshou:
            self.logger.error("[起号_领取锦囊] 导航到新手任务界面失败")
            return False

        self.logger.info("[起号_领取锦囊] 已到达新手任务界面")
        await asyncio.sleep(1.0)

        # OCR 识别左侧标签列，点击"成长锦囊"
        LEFT_COL_ROI = (0, 50, 150, 450)
        clicked_jinnang = await click_text(
            self.adapter,
            self.ui.capture_method,
            "成长锦囊",
            roi=LEFT_COL_ROI,
            timeout=5.0,
            settle=0.5,
            post_delay=1.5,
            log=self.logger,
            label="起号_点击成长锦囊",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked_jinnang:
            self.logger.warning("[起号_领取锦囊] 未识别到成长锦囊标签，跳过")
            return True

        # 等待成长锦囊页面加载完成
        jinnang_ready = await wait_for_template(
            self.adapter,
            self.ui.capture_method,
            "assets/ui/templates/tag_jinnang.png",
            timeout=5.0,
            interval=1.0,
            log=self.logger,
            label="起号_等待锦囊页面",
            popup_handler=self.ui.popup_handler,
        )
        if not jinnang_ready:
            self.logger.warning("[起号_领取锦囊] 锦囊页面未加载完成")
            return True

        self.logger.info("[起号_领取锦囊] 已到达成长锦囊页面")

        # 点击一键领取
        clicked = await click_template(
            self.adapter,
            self.ui.capture_method,
            "assets/ui/templates/jinnang_yijianlingqu.png",
            timeout=5.0,
            interval=1.0,
            settle=0.5,
            post_delay=2.0,
            log=self.logger,
            label="起号_锦囊一键领取",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked:
            self.logger.warning("[起号_领取锦囊] 未检测到锦囊一键领取按钮")
            return True

        # 关闭奖励弹窗
        await self._dismiss_jiangli("锦囊")
        return True

    async def _dismiss_jiangli(self, step_label: str) -> None:
        """关闭 jiangli.png 奖励弹窗，之后可能出现 chahua.png 也一并关闭"""
        screenshot = await self._capture()
        if screenshot is not None:
            if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
                screenshot = await self._capture()

        if screenshot is not None:
            jiangli_result = match_template(
                screenshot, "assets/ui/templates/jiangli.png"
            )
            if jiangli_result:
                self.logger.info(
                    f"[起号_领取锦囊] {step_label} 检测到奖励弹窗，点击关闭"
                )
            else:
                self.logger.warning(
                    f"[起号_领取锦囊] {step_label} 未检测到奖励弹窗，仍尝试点击关闭"
                )

        close_x, close_y = random_point_in_circle(20, 20, 20)
        await self._tap(close_x, close_y)
        self.logger.info(
            f"[起号_领取锦囊] {step_label} 随机点击 ({close_x}, {close_y}) 关闭弹窗"
        )
        await asyncio.sleep(1.0)

        # 关闭可能出现的插画弹窗 (chahua.png)
        screenshot = await self._capture()
        if screenshot is not None:
            chahua_result = match_template(
                screenshot, "assets/ui/templates/chahua.png"
            )
            if chahua_result:
                self.logger.info(
                    f"[起号_领取锦囊] {step_label} 检测到插画弹窗，点击关闭"
                )
                close_x2, close_y2 = random_point_in_circle(20, 20, 20)
                await self._tap(close_x2, close_y2)
                await asyncio.sleep(1.0)

                # 关闭 chahua 后必定出现的取消按钮 (chahua_quxiao.png)
                screenshot = await self._capture()
                if screenshot is not None:
                    quxiao_result = match_template(
                        screenshot, "assets/ui/templates/chahua_quxiao.png"
                    )
                    if quxiao_result:
                        self.logger.info(
                            f"[起号_领取锦囊] {step_label} 检测到插画取消按钮，点击关闭"
                        )
                        cx, cy = quxiao_result.center
                        rx, ry = random_point_in_circle(cx, cy, 5)
                        await self._tap(rx, ry)
                        await asyncio.sleep(1.0)

    def _update_next_time(self) -> None:
        """更新 next_time 为当前时间 +8 小时"""
        try:
            bj_now_str = format_beijing_time(now_beijing())
            next_time = add_hours_to_beijing_time(bj_now_str, 8)

            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    cfg = account.task_config or {}
                    jinnang_cfg = cfg.get("起号_领取锦囊", {})
                    jinnang_cfg["next_time"] = next_time
                    cfg["起号_领取锦囊"] = jinnang_cfg
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(
                        f"[起号_领取锦囊] next_time 更新为 {next_time}"
                    )
        except Exception as e:
            self.logger.error(f"[起号_领取锦囊] 更新 next_time 失败: {e}")

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[起号_领取锦囊] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[起号_领取锦囊] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[起号_领取锦囊] 停止游戏失败: {e}")

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
            screenshot = await _adapter_capture(adapter, capture_method)
            if screenshot is None:
                await asyncio.sleep(interval)
                continue

            if not detect_dialog(screenshot):
                break

            rx, ry = random_point_in_circle(480, 400, 40)
            await _adapter_tap(adapter, rx, ry)
            clicks += 1
            await asyncio.sleep(interval)

        if clicks > 0:
            self.logger.info(f"[起号_领取锦囊] 跳过了 {clicks} 轮剧情对话")
        return clicks
