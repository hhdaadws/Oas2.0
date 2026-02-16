"""
每周分享执行器 - 在图鉴界面完成每周分享操作
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from ...core.constants import TaskStatus
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ui.manager import UIManager
from ..vision.template import match_template
from .base import BaseExecutor
from .helpers import click_template, wait_for_qrcode, wait_for_template

PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# 模板路径
_TPL_MEIZHOU_SHISHEN = "assets/ui/templates/meizhou_shishen.png"
_TPL_MEIZHOU_HUIJUAN = "assets/ui/templates/meizhou_huijuan.png"
_TPL_MEIZHOU_FENXIANG = "assets/ui/templates/meizhou_fenxiang.png"
_TPL_MEIZHOU_WEIXIN = "assets/ui/templates/meizhou_weixin.png"
_TPL_EXIT = "assets/ui/templates/exit.png"
_TPL_EXIT_DARK = "assets/ui/templates/exit_dark.png"
_TPL_EXIT_SHITI = "assets/ui/templates/exit_shiti.png"
_TPL_JIANGLI = "assets/ui/templates/jiangli.png"


class WeeklyShareExecutor(BaseExecutor):
    """每周分享执行器"""

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
        self.logger.info(f"[每周分享] 准备: account={account.login_id}")

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[每周分享] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error("[每周分享] 模拟器不存在: id={}", self.emulator_id)
            return False

        self.adapter = self._build_adapter()

        ok = self.adapter.push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[每周分享] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[每周分享] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[每周分享] 执行: account={self.current_account.login_id}")

        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = (
                self.system_config.capture_method if self.system_config else None
            ) or "adb"
            self.ui = UIManager(self.adapter, capture_method=capture_method)

        # 1. 确保游戏就绪
        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            self.logger.error("[每周分享] 游戏就绪失败，未进入庭院")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. 导航到图鉴界面
        self.logger.info("[每周分享] 开始导航至图鉴界面")
        in_tujian = await self.ui.ensure_ui("TUJIAN", max_steps=6, step_timeout=3.0)
        if not in_tujian:
            self.logger.error("[每周分享] 导航到图鉴界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航到图鉴界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info("[每周分享] 已到达图鉴界面")

        # 3. 点击每周式神
        ok = await click_template(
            self.adapter, self.ui.capture_method, _TPL_MEIZHOU_SHISHEN,
            timeout=8.0, settle=0.5, post_delay=1.5,
            log=self.logger, label="每周分享-每周式神",
            popup_handler=self.popup_handler,
        )
        if not ok:
            return {
                "status": TaskStatus.FAILED,
                "error": "未找到每周式神按钮",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 4. 点击每周绘卷
        ok = await click_template(
            self.adapter, self.ui.capture_method, _TPL_MEIZHOU_HUIJUAN,
            timeout=8.0, settle=0.5, post_delay=1.5,
            log=self.logger, label="每周分享-每周绘卷",
            popup_handler=self.popup_handler,
        )
        if not ok:
            return {
                "status": TaskStatus.FAILED,
                "error": "未找到每周绘卷按钮",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 5. 点击分享按钮
        ok = await click_template(
            self.adapter, self.ui.capture_method, _TPL_MEIZHOU_FENXIANG,
            timeout=8.0, settle=0.5, post_delay=1.5,
            log=self.logger, label="每周分享-分享",
            popup_handler=self.popup_handler,
        )
        if not ok:
            return {
                "status": TaskStatus.FAILED,
                "error": "未找到分享按钮",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 6. 点击微信分享
        ok = await click_template(
            self.adapter, self.ui.capture_method, _TPL_MEIZHOU_WEIXIN,
            timeout=8.0, settle=0.5, post_delay=0.5,
            log=self.logger, label="每周分享-微信",
            popup_handler=self.popup_handler,
        )
        if not ok:
            return {
                "status": TaskStatus.FAILED,
                "error": "未找到微信按钮",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 6.5 等待二维码出现
        qr_found = await wait_for_qrcode(
            self.adapter, self.ui.capture_method,
            timeout=15.0, interval=0.5,
            log=self.logger, label="每周分享-等待二维码",
        )
        if not qr_found:
            self.logger.warning("[每周分享] 等待二维码超时，尝试继续")

        # 7. 点击 exit 关闭分享弹窗
        ok = await click_template(
            self.adapter, self.ui.capture_method, _TPL_EXIT,
            timeout=8.0, settle=0.3, post_delay=1.5,
            log=self.logger, label="每周分享-关闭分享",
            popup_handler=self.popup_handler,
        )
        if not ok:
            self.logger.warning("[每周分享] 未检测到 exit 按钮，尝试继续")

        # 8. 处理可能出现的奖励弹窗 (jiangli.png)
        await self._dismiss_jiangli()

        # 9. 关闭退出返回图鉴（带验证）
        returned = await self._close_to_tujian()
        if not returned:
            self.logger.warning("[每周分享] 分享操作已完成但无法返回图鉴界面")
            return {
                "status": TaskStatus.FAILED,
                "error": "分享已完成但无法返回图鉴界面",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info("[每周分享] 执行完成")
        return {
            "status": TaskStatus.SUCCEEDED,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _dismiss_jiangli(self) -> None:
        """检测并关闭奖励弹窗"""
        await asyncio.sleep(1.0)
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            return

        # 先处理通用弹窗
        if self.popup_handler:
            dismissed = await self.popup_handler.check_and_dismiss(screenshot)
            if dismissed > 0:
                screenshot = self.adapter.capture(self.ui.capture_method)
                if screenshot is None:
                    return

        jiangli = match_template(screenshot, _TPL_JIANGLI)
        if jiangli:
            self.logger.info("[每周分享] 检测到奖励弹窗，点击关闭")
        else:
            self.logger.info("[每周分享] 未检测到奖励弹窗")
            return

        # 随机点击关闭奖励弹窗
        from ..vision.utils import random_point_in_circle

        close_x, close_y = random_point_in_circle(20, 20, 20)
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, close_x, close_y)
        self.logger.info(f"[每周分享] 随机点击 ({close_x}, {close_y}) 关闭奖励弹窗")
        await asyncio.sleep(1.0)

    async def _close_to_tujian(self) -> bool:
        """关闭弹窗/对话框并返回图鉴界面。

        循环尝试：清理弹窗 → 检测 UI → ensure_ui 导航 / 手动点击 exit。
        最多 5 轮，每轮验证是否已到达 TUJIAN。

        Returns:
            True 表示成功回到 TUJIAN，False 表示失败。
        """
        MAX_CLOSE_ATTEMPTS = 5

        for attempt in range(MAX_CLOSE_ATTEMPTS):
            # 先处理弹窗
            dismissed = await self.ui.popup_handler.check_and_dismiss()
            if dismissed > 0:
                self.logger.info(
                    f"[每周分享] 关闭了 {dismissed} 个弹窗 (attempt={attempt + 1})"
                )
                await asyncio.sleep(1.0)

            # 检测当前 UI
            cur = self.ui.detect_ui()
            if cur.ui == "TUJIAN":
                self.logger.info("[每周分享] 已确认回到图鉴界面")
                return True

            if cur.ui != "UNKNOWN":
                # 在已知界面但非 TUJIAN，交给 ensure_ui 导航
                self.logger.info(
                    f"[每周分享] 当前 UI={cur.ui}，尝试导航到 TUJIAN"
                )
                ok = await self.ui.ensure_ui("TUJIAN", max_steps=6, step_timeout=3.0)
                if ok:
                    self.logger.info("[每周分享] 导航到 TUJIAN 成功")
                    return True

            # UNKNOWN 状态，手动点击 exit 按钮关闭中间层
            clicked = False
            for tpl, label in [
                (_TPL_EXIT, "exit"),
                (_TPL_EXIT_DARK, "exit_dark"),
                (_TPL_EXIT_SHITI, "exit_shiti"),
            ]:
                screenshot = self.adapter.capture(self.ui.capture_method)
                if screenshot is None:
                    continue
                m = match_template(screenshot, tpl)
                if m:
                    cx, cy = m.center
                    self.adapter.adb.tap(self.adapter.cfg.adb_addr, cx, cy)
                    self.logger.info(
                        f"[每周分享] 点击 {label} ({cx}, {cy}) (attempt={attempt + 1})"
                    )
                    clicked = True
                    await asyncio.sleep(1.5)
                    break

            if not clicked:
                self.logger.warning(
                    f"[每周分享] 未找到 exit 按钮 (attempt={attempt + 1})"
                )
                await asyncio.sleep(1.0)

        # 最终验证
        cur = self.ui.detect_ui()
        if cur.ui == "TUJIAN":
            return True
        self.logger.error(
            f"[每周分享] 无法回到图鉴界面，当前 UI={cur.ui} score={cur.score:.3f}"
        )
        return False

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[每周分享] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[每周分享] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[每周分享] 停止游戏失败: {e}")
