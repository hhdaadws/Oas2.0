"""
寮商店执行器 - 支持购买黑碎和蓝票，OCR 检测功勋和剩余数量
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus, TaskType
from ...core.logger import logger
from ...core.timeutils import now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ocr.recognize import ocr as ocr_recognize
from ..ui.assets import parse_number
from ..ui.manager import UIManager
from ..vision.template import Match, match_template
from .base import BaseExecutor
from .helpers import click_template, wait_for_template

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# 功勋 OCR 区域 (x, y, w, h)
GONGXUN_ROI = (709, 15, 84, 24)

# 购买成本
HEISUI_COST = 200
LANPIAO_COST = 120


class LiaoShopExecutor(BaseExecutor):
    """寮商店执行器 - 支持黑碎/蓝票购买"""

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

    # ------------------------------------------------------------------
    # OCR 辅助
    # ------------------------------------------------------------------

    def _read_gongxun(self, screenshot) -> Optional[int]:
        """OCR 读取寮商店界面右上角的功勋值"""
        result = ocr_recognize(screenshot, roi=GONGXUN_ROI)
        raw = result.text.strip()
        value = parse_number(raw)
        self.logger.info(f"[寮商店] 功勋 OCR: raw='{raw}' → value={value}")
        return value

    def _read_remaining(self, screenshot, m: Match) -> Optional[int]:
        """OCR 读取模板匹配位置下方的"本周剩余数量x"文本，提取剩余数"""
        # 模板下方区域：从模板底部向下延伸约 25px
        roi_x = max(0, m.x - 10)
        roi_y = m.y + m.h
        roi_w = m.w + 60
        roi_h = 30
        result = ocr_recognize(screenshot, roi=(roi_x, roi_y, roi_w, roi_h))
        raw = result.text.strip()
        self.logger.info(f"[寮商店] 剩余数量 OCR: raw='{raw}' roi=({roi_x},{roi_y},{roi_w},{roi_h})")

        # 提取数字
        digits = re.findall(r"\d+", raw)
        if digits:
            val = int(digits[-1])  # 取最后一个数字（"本周剩余数量1" → 1）
            self.logger.info(f"[寮商店] 解析剩余数量: {val}")
            return val
        # OCR 失败：记录详细原因
        box_details = [(b.text, f"{b.confidence:.2f}") for b in result.boxes]
        self.logger.warning(
            f"[寮商店] 剩余数量 OCR 无法提取数字: raw='{raw}', boxes={box_details}"
        )
        return None

    # ------------------------------------------------------------------
    # 购买流程
    # ------------------------------------------------------------------

    async def _buy_heisui(self) -> bool:
        """购买黑碎：点击黑碎 → 直接点击 buy.png（无需 top+）

        Returns:
            True 表示购买成功，False 表示 buy 未出现（已购买完毕或失败）
        """
        # 等待并点击黑碎
        heisui_match = await wait_for_template(
            self.adapter, self.ui.capture_method,
            "assets/ui/templates/heisui.png",
            timeout=5.0, interval=1.0,
            log=self.logger, label="寮商店-黑碎",
            popup_handler=self.ui.popup_handler,
        )
        if not heisui_match:
            self.logger.warning("[寮商店] 未检测到黑碎模板")
            return False

        cx, cy = heisui_match.center
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, cx, cy)
        self.logger.info(f"[寮商店] 点击黑碎: ({cx}, {cy})")
        await asyncio.sleep(1.5)

        # 点击 buy.png
        buy_ok = await click_template(
            self.adapter, self.ui.capture_method,
            "assets/ui/templates/buy.png",
            timeout=5.0, interval=1.0,
            settle=0.5, post_delay=2.0,
            log=self.logger, label="寮商店-黑碎购买",
            popup_handler=self.ui.popup_handler,
        )
        if not buy_ok:
            self.logger.info("[寮商店] 黑碎: buy 未出现，已购买完毕")
            return False

        # 关闭可能的奖励弹窗
        await self._dismiss_popups()
        self.logger.info("[寮商店] 黑碎购买成功")
        return True

    async def _buy_lanpiao(self, remaining: int, gongxun: int) -> tuple[bool, int]:
        """购买蓝票：点击蓝票 → 可选 top+ → buy.png

        Args:
            remaining: 本周剩余可购买数量
            gongxun: 当前功勋值

        Returns:
            (all_bought, gongxun_spent) - 是否全部购买完成, 消耗的功勋
        """
        # 等待并点击蓝票
        lanpiao_match = await wait_for_template(
            self.adapter, self.ui.capture_method,
            "assets/ui/templates/lanpiao.png",
            timeout=5.0, interval=1.0,
            log=self.logger, label="寮商店-蓝票",
            popup_handler=self.ui.popup_handler,
        )
        if not lanpiao_match:
            self.logger.warning("[寮商店] 未检测到蓝票模板")
            return False, 0

        cx, cy = lanpiao_match.center
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, cx, cy)
        self.logger.info(f"[寮商店] 点击蓝票: ({cx}, {cy})")
        await asyncio.sleep(1.5)

        # 判断是否需要 top+（买2张）
        can_buy_two = remaining >= 2 and gongxun >= LANPIAO_COST * 2
        if can_buy_two:
            top_ok = await click_template(
                self.adapter, self.ui.capture_method,
                "assets/ui/templates/top+.png",
                timeout=3.0, interval=0.5,
                settle=0.3, post_delay=1.0,
                log=self.logger, label="寮商店-蓝票top+",
                popup_handler=self.ui.popup_handler,
            )
            if top_ok:
                self.logger.info("[寮商店] 蓝票: 已选择2张")
            else:
                self.logger.warning("[寮商店] 蓝票: top+ 未出现，将购买1张")
                can_buy_two = False

        # 点击 buy.png
        buy_ok = await click_template(
            self.adapter, self.ui.capture_method,
            "assets/ui/templates/buy.png",
            timeout=5.0, interval=1.0,
            settle=0.5, post_delay=2.0,
            log=self.logger, label="寮商店-蓝票购买",
            popup_handler=self.ui.popup_handler,
        )
        if not buy_ok:
            self.logger.info("[寮商店] 蓝票: buy 未出现，已购买完毕")
            return False, 0

        # 关闭弹窗
        await self._dismiss_popups()

        actual_count = 2 if can_buy_two else 1
        spent = LANPIAO_COST * actual_count
        all_bought = actual_count >= remaining
        self.logger.info(f"[寮商店] 蓝票购买成功: {actual_count}张, 消耗{spent}功勋")
        return all_bought, spent

    async def _dismiss_popups(self) -> None:
        """关闭购买后的奖励画面"""
        await asyncio.sleep(1.0)
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            return
        # 通用弹窗检测
        if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
            screenshot = self.adapter.capture(self.ui.capture_method)
        # 检测 jiangli.png 奖励画面
        jiangli_match = match_template(screenshot, "assets/ui/templates/jiangli.png")
        if jiangli_match:
            self.logger.info("[寮商店] 检测到奖励画面，点击关闭")
        else:
            self.logger.warning("[寮商店] 未检测到奖励画面，仍尝试点击关闭")
        from ..vision.utils import random_point_in_circle
        close_x, close_y = random_point_in_circle(20, 20, 20)
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, close_x, close_y)
        self.logger.info(f"[寮商店] 随机点击 ({close_x}, {close_y}) 关闭奖励画面")
        await asyncio.sleep(0.5)

    # ------------------------------------------------------------------
    # 主执行逻辑
    # ------------------------------------------------------------------

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

        # 2. 导航到寮商店界面
        self.logger.info("[寮商店] 开始导航至寮商店界面")
        in_shop = await self.ui.ensure_ui("LIAO_SHANGDIAN", max_steps=10, step_timeout=3.0)
        if not in_shop:
            self.logger.error("[寮商店] 导航到寮商店界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航寮商店界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }
        self.logger.info("[寮商店] 已到达寮商店界面")

        # 3. 读取功勋（顶部固定显示，不受滚动影响）
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            return {
                "status": TaskStatus.FAILED,
                "error": "截图失败",
                "timestamp": datetime.utcnow().isoformat(),
            }
        if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is None:
                return {
                    "status": TaskStatus.FAILED,
                    "error": "截图失败",
                    "timestamp": datetime.utcnow().isoformat(),
                }

        gongxun = self._read_gongxun(screenshot)
        if gongxun is None:
            self.logger.warning("[寮商店] 功勋 OCR 读取失败，尝试默认流程")
            gongxun = 9999
        self._update_gongxun_in_db(gongxun)

        # 4. 读取购买选项
        buy_heisui, buy_lanpiao = self._get_buy_options()
        self.logger.info(f"[寮商店] 配置: buy_heisui={buy_heisui}, buy_lanpiao={buy_lanpiao}, 功勋={gongxun}")

        if not buy_heisui and not buy_lanpiao:
            self.logger.warning("[寮商店] 未启用任何购买选项，跳过")
            self._update_next_time(all_done=True)
            return {
                "status": TaskStatus.SUCCEEDED,
                "message": "未启用购买选项",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 5. 逐个查找并购买（找到一个买一个）
        MAX_SCROLL = 5
        heisui_done = True
        lanpiao_done = True
        insufficient_gongxun = False

        # 5a. 下滑查找并购买黑碎
        if buy_heisui:
            heisui_remaining = 0
            for scroll_i in range(MAX_SCROLL):
                self.adapter.adb.swipe(self.adapter.cfg.adb_addr, 480, 350, 480, 150, 500)
                await asyncio.sleep(1.5)
                screenshot = self.adapter.capture(self.ui.capture_method)
                if screenshot is None:
                    continue
                if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
                    screenshot = self.adapter.capture(self.ui.capture_method)
                    if screenshot is None:
                        continue
                heisui_match = match_template(screenshot, "assets/ui/templates/heisui.png")
                if heisui_match:
                    heisui_remaining = self._read_remaining(screenshot, heisui_match)
                    if heisui_remaining is None:
                        heisui_remaining = 1
                        self.logger.warning("[寮商店] 黑碎剩余数量 OCR 失败，假定为 1")
                    self.logger.info(f"[寮商店] 第{scroll_i + 1}次下滑找到黑碎, 剩余={heisui_remaining}")
                    break
            else:
                self.logger.warning(f"[寮商店] 下滑{MAX_SCROLL}次未找到黑碎")

            if heisui_remaining > 0:
                if gongxun >= HEISUI_COST:
                    bought = await self._buy_heisui()
                    if bought:
                        gongxun -= HEISUI_COST
                    heisui_done = True
                else:
                    self.logger.info(f"[寮商店] 功勋不足购买黑碎: {gongxun} < {HEISUI_COST}")
                    heisui_done = False
                    insufficient_gongxun = True
            else:
                self.logger.info("[寮商店] 黑碎本周已购买完毕")

        # 5b. 继续查找并购买蓝票
        if buy_lanpiao:
            lanpiao_remaining = 0
            for scroll_i in range(MAX_SCROLL):
                # 第一次先检查当前画面（买完黑碎后蓝票可能已在屏幕上）
                if scroll_i > 0:
                    self.adapter.adb.swipe(self.adapter.cfg.adb_addr, 480, 350, 480, 150, 500)
                    await asyncio.sleep(1.5)
                screenshot = self.adapter.capture(self.ui.capture_method)
                if screenshot is None:
                    continue
                if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
                    screenshot = self.adapter.capture(self.ui.capture_method)
                    if screenshot is None:
                        continue
                lanpiao_match = match_template(screenshot, "assets/ui/templates/lanpiao.png")
                if lanpiao_match:
                    lanpiao_remaining = self._read_remaining(screenshot, lanpiao_match)
                    if lanpiao_remaining is None:
                        lanpiao_remaining = 2
                        self.logger.warning("[寮商店] 蓝票剩余数量 OCR 失败，假定为 2")
                    self.logger.info(f"[寮商店] 第{scroll_i + 1}次查找找到蓝票, 剩余={lanpiao_remaining}")
                    break
            else:
                self.logger.warning(f"[寮商店] {MAX_SCROLL}次查找未找到蓝票")

            if lanpiao_remaining > 0:
                if gongxun >= LANPIAO_COST:
                    all_bought, spent = await self._buy_lanpiao(lanpiao_remaining, gongxun)
                    gongxun -= spent
                    lanpiao_done = all_bought or lanpiao_remaining == 0
                    if not all_bought and gongxun < LANPIAO_COST:
                        insufficient_gongxun = True
                else:
                    self.logger.info(f"[寮商店] 功勋不足购买蓝票: {gongxun} < {LANPIAO_COST}")
                    lanpiao_done = False
                    insufficient_gongxun = True
            else:
                self.logger.info("[寮商店] 蓝票本周已购买完毕")

        # 8. 更新功勋和 next_time
        self._update_gongxun_in_db(gongxun)

        all_done = True
        if buy_heisui and not heisui_done:
            all_done = False
        if buy_lanpiao and not lanpiao_done:
            all_done = False

        self._update_next_time(all_done=all_done)

        msg = "购买完成" if all_done else "功勋不足，稍后重试"
        self.logger.info(f"[寮商店] 执行完成: {msg}")
        return {
            "status": TaskStatus.SUCCEEDED,
            "message": msg,
            "gongxun": gongxun,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ------------------------------------------------------------------
    # 配置与数据库
    # ------------------------------------------------------------------

    def _get_buy_options(self) -> tuple[bool, bool]:
        """从 DB 读取 task_config 中的购买子选项"""
        try:
            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    cfg = (account.task_config or {}).get("寮商店", {})
                    buy_heisui = cfg.get("buy_heisui", True)
                    buy_lanpiao = cfg.get("buy_lanpiao", True)
                    return bool(buy_heisui), bool(buy_lanpiao)
        except Exception as e:
            self.logger.error(f"[寮商店] 读取购买选项失败: {e}")
        return True, True  # 默认都启用

    def _update_gongxun_in_db(self, value: int) -> None:
        """更新 DB 中的功勋值（仅展示用途）"""
        try:
            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    account.gongxun = value
                    db.commit()
        except Exception as e:
            self.logger.warning(f"[寮商店] 更新功勋到 DB 失败: {e}")

    def _update_next_time(self, *, all_done: bool) -> None:
        """更新寮商店 next_time

        Args:
            all_done: True → 下周六 12:00; False → 12小时后重试
        """
        try:
            bj_now = now_beijing()

            if all_done:
                # 下周六 12:00
                days_until_saturday = (5 - bj_now.weekday()) % 7
                if days_until_saturday == 0:
                    days_until_saturday = 7
                next_sat = bj_now.date() + timedelta(days=days_until_saturday)
                next_time = f"{next_sat.isoformat()} 12:00"
            else:
                # 12小时后重试
                retry_dt = bj_now + timedelta(hours=12)
                next_time = retry_dt.strftime("%Y-%m-%d %H:%M")

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
