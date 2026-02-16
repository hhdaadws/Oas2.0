"""
每周商店执行器 - 勋章商店，支持购买蓝票、黑蛋、体力
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus, TaskType
from ...core.logger import logger
from ...core.timeutils import now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ocr.recognize import ocr as ocr_recognize
from ..ocr.recognize import ocr_digits
from ..ui.assets import parse_number
from ..ui.manager import UIManager
from ..vision.template import Match, match_template
from .base import BaseExecutor
from .helpers import click_template, wait_for_template

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# 勋章 OCR 区域 (x, y, w, h)
XUNZHANG_ROI = (441, 15, 70, 42)

# 购买成本
LANPIAO_COST = 180
HEIDAN_COST = 480
TILI_COST = 120

# 商品定义：(模板名, 成本, 配置键, 中文名)，按优先级排序：蓝票 > 黑蛋 > 体力
ITEMS: List[Tuple[str, int, str, str]] = [
    ("xunzhang_lanpiao", LANPIAO_COST, "buy_lanpiao", "蓝票"),
    ("xunzhang_heidan", HEIDAN_COST, "buy_heidan", "黑蛋"),
    ("xunzhang_tili", TILI_COST, "buy_tili", "体力"),
]


class WeeklyShopExecutor(BaseExecutor):
    """每周商店执行器 - 勋章商店购买蓝票/黑蛋/体力"""

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
        self.logger.info(f"[每周商店] 准备: account={account.login_id}")

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[每周商店] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error("[每周商店] 模拟器不存在: id={}", self.emulator_id)
            return False

        self.adapter = self._build_adapter()

        ok = self.adapter.push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[每周商店] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[每周商店] push 登录数据成功: {account.login_id}")
        return True

    # ------------------------------------------------------------------
    # OCR 辅助
    # ------------------------------------------------------------------

    def _read_xunzhang(self, screenshot) -> Optional[int]:
        """OCR 读取勋章商店界面的勋章值"""
        result = ocr_digits(screenshot, roi=XUNZHANG_ROI)
        raw = result.text.strip()
        value = parse_number(raw)
        self.logger.info(f"[每周商店] 勋章 OCR: raw='{raw}' → value={value}")
        return value

    def _read_remaining(self, screenshot, m: Match) -> Optional[int]:
        """OCR 读取模板匹配位置上方的"剩余购买次数:x"文本，提取剩余数"""
        # 模板上方区域：覆盖模板顶部向上约 65px 的文字区域
        roi_x = max(0, m.x - 50)
        roi_y = max(0, m.y - 65)
        roi_w = m.w + 120
        roi_h = 60
        result = ocr_recognize(screenshot, roi=(roi_x, roi_y, roi_w, roi_h))
        raw = result.text.strip()
        self.logger.info(
            f"[每周商店] 剩余数量 OCR: raw='{raw}' roi=({roi_x},{roi_y},{roi_w},{roi_h})"
        )

        # 提取数字
        digits = re.findall(r"\d+", raw)
        if digits:
            val = int(digits[-1])
            self.logger.info(f"[每周商店] 解析剩余数量: {val}")
            return val
        box_details = [(b.text, f"{b.confidence:.2f}") for b in result.boxes]
        self.logger.warning(
            f"[每周商店] 剩余数量 OCR 无法提取数字: raw='{raw}', boxes={box_details}"
        )
        return None

    # ------------------------------------------------------------------
    # 购买流程
    # ------------------------------------------------------------------

    async def _buy_item(self, template_name: str, label: str) -> bool:
        """购买单个商品：点击商品 → buy_xunzhang.png → 关闭奖励

        Args:
            template_name: 商品模板文件名（不含路径和后缀）
            label: 商品中文名（用于日志）

        Returns:
            True 表示购买成功
        """
        # 等待并点击商品
        item_match = await wait_for_template(
            self.adapter, self.ui.capture_method,
            f"assets/ui/templates/{template_name}.png",
            timeout=5.0, interval=1.0,
            log=self.logger, label=f"每周商店-{label}",
            popup_handler=self.ui.popup_handler,
        )
        if not item_match:
            self.logger.warning(f"[每周商店] 未检测到{label}模板")
            return False

        cx, cy = item_match.random_point()
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, cx, cy)
        self.logger.info(f"[每周商店] 点击{label}: ({cx}, {cy})")
        await asyncio.sleep(1.5)

        # 点击 buy_xunzhang.png
        buy_ok = await click_template(
            self.adapter, self.ui.capture_method,
            "assets/ui/templates/buy_xunzhang.png",
            timeout=5.0, interval=1.0,
            settle=0.5, post_delay=2.0,
            log=self.logger, label=f"每周商店-{label}购买",
            popup_handler=self.ui.popup_handler,
        )
        if not buy_ok:
            self.logger.info(f"[每周商店] {label}: buy_xunzhang 未出现，已购买完毕")
            return False

        # 关闭可能的奖励弹窗
        await self._dismiss_popups()
        self.logger.info(f"[每周商店] {label}购买成功")
        return True

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
            self.logger.info("[每周商店] 检测到奖励画面，点击关闭")
        else:
            self.logger.warning("[每周商店] 未检测到奖励画面，仍尝试点击关闭")
        from ..vision.utils import random_point_in_circle
        close_x, close_y = random_point_in_circle(20, 20, 20)
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, close_x, close_y)
        self.logger.info(f"[每周商店] 随机点击 ({close_x}, {close_y}) 关闭奖励画面")
        await asyncio.sleep(0.5)

    # ------------------------------------------------------------------
    # 主执行逻辑
    # ------------------------------------------------------------------

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[每周商店] 执行: account={self.current_account.login_id}")

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
            self.logger.error("[每周商店] 游戏就绪失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. 导航到商店界面
        self.logger.info("[每周商店] 开始导航至商店界面")
        in_shop = await self.ui.ensure_ui("SHANGDIAN", max_steps=10, step_timeout=3.0)
        if not in_shop:
            self.logger.error("[每周商店] 导航到商店界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航商店界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }
        self.logger.info("[每周商店] 已到达商店界面")

        # 3. 点击杂货铺
        zahuopu_ok = await click_template(
            self.adapter, self.ui.capture_method,
            "assets/ui/templates/zahuopu.png",
            timeout=5.0, interval=1.0,
            settle=0.5, post_delay=2.0,
            log=self.logger, label="每周商店-杂货铺",
            popup_handler=self.ui.popup_handler,
        )
        if not zahuopu_ok:
            self.logger.error("[每周商店] 点击杂货铺失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "点击杂货铺失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 4. 点击勋章标签
        xunzhang_ok = await click_template(
            self.adapter, self.ui.capture_method,
            "assets/ui/templates/xunzhang.png",
            timeout=5.0, interval=1.0,
            settle=0.5, post_delay=2.0,
            log=self.logger, label="每周商店-勋章",
            popup_handler=self.ui.popup_handler,
        )
        if not xunzhang_ok:
            self.logger.error("[每周商店] 点击勋章标签失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "点击勋章标签失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 5. 读取勋章数量
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

        xunzhang = self._read_xunzhang(screenshot)
        if xunzhang is None:
            self.logger.warning("[每周商店] 勋章 OCR 读取失败，尝试默认流程")
            xunzhang = 9999
        self._update_xunzhang_in_db(xunzhang)

        # 6. 读取购买选项
        buy_options = self._get_buy_options()
        self.logger.info(f"[每周商店] 配置: {buy_options}, 勋章={xunzhang}")

        any_enabled = any(buy_options.values())
        if not any_enabled:
            self.logger.warning("[每周商店] 未启用任何购买选项，跳过")
            self._update_next_time(all_done=True)
            return {
                "status": TaskStatus.SUCCEEDED,
                "message": "未启用购买选项",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 6b. 检查勋章是否足够购买任何一种已启用商品
        enabled_costs = [
            cost for _, cost, config_key, _ in ITEMS
            if buy_options.get(config_key, True)
        ]
        min_cost = min(enabled_costs)
        if xunzhang < min_cost:
            self.logger.info(f"[每周商店] 勋章不足以购买任何商品: {xunzhang} < {min_cost}，直接结束")
            self._update_next_time(all_done=True)
            return {
                "status": TaskStatus.SUCCEEDED,
                "message": f"勋章不足({xunzhang})，无法购买任何商品",
                "xunzhang": xunzhang,
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 7. 按优先级遍历商品并购买
        MAX_SCROLL = 5
        all_done = True
        insufficient_xunzhang = False

        for template_name, cost, config_key, label in ITEMS:
            if not buy_options.get(config_key, True):
                self.logger.info(f"[每周商店] {label}未启用，跳过")
                continue

            # 查找商品模板
            item_remaining = 0
            for scroll_i in range(MAX_SCROLL):
                if scroll_i > 0:
                    self.adapter.adb.swipe(
                        self.adapter.cfg.adb_addr, 480, 350, 480, 150, 500
                    )
                    await asyncio.sleep(1.5)
                screenshot = self.adapter.capture(self.ui.capture_method)
                if screenshot is None:
                    continue
                if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
                    screenshot = self.adapter.capture(self.ui.capture_method)
                    if screenshot is None:
                        continue
                item_match = match_template(
                    screenshot, f"assets/ui/templates/{template_name}.png"
                )
                if item_match:
                    item_remaining = self._read_remaining(screenshot, item_match)
                    if item_remaining is None:
                        item_remaining = 1
                        self.logger.warning(
                            f"[每周商店] {label}剩余数量 OCR 失败，假定为 1"
                        )
                    self.logger.info(
                        f"[每周商店] 第{scroll_i + 1}次查找找到{label}, 剩余={item_remaining}"
                    )
                    break
            else:
                self.logger.warning(f"[每周商店] {MAX_SCROLL}次查找未找到{label}")

            if item_remaining > 0:
                if xunzhang >= cost:
                    bought = await self._buy_item(template_name, label)
                    if bought:
                        xunzhang -= cost
                else:
                    self.logger.info(
                        f"[每周商店] 勋章不足购买{label}: {xunzhang} < {cost}"
                    )
                    all_done = False
                    insufficient_xunzhang = True
            else:
                self.logger.info(f"[每周商店] {label}本周已购买完毕")

        # 8. 更新勋章和 next_time
        self._update_xunzhang_in_db(xunzhang)
        self._update_next_time(all_done=all_done)

        msg = "购买完成" if all_done else "勋章不足，稍后重试"
        self.logger.info(f"[每周商店] 执行完成: {msg}")
        return {
            "status": TaskStatus.SUCCEEDED,
            "message": msg,
            "xunzhang": xunzhang,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ------------------------------------------------------------------
    # 配置与数据库
    # ------------------------------------------------------------------

    def _get_buy_options(self) -> Dict[str, bool]:
        """从 DB 读取 task_config 中的购买子选项"""
        try:
            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    cfg = (account.task_config or {}).get("每周商店", {})
                    return {
                        "buy_lanpiao": bool(cfg.get("buy_lanpiao", True)),
                        "buy_heidan": bool(cfg.get("buy_heidan", True)),
                        "buy_tili": bool(cfg.get("buy_tili", True)),
                    }
        except Exception as e:
            self.logger.error(f"[每周商店] 读取购买选项失败: {e}")
        return {"buy_lanpiao": True, "buy_heidan": True, "buy_tili": True}

    def _update_xunzhang_in_db(self, value: int) -> None:
        """更新 DB 中的勋章值（仅展示用途）"""
        try:
            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    account.xunzhang = value
                    db.commit()
        except Exception as e:
            self.logger.warning(f"[每周商店] 更新勋章到 DB 失败: {e}")

    def _update_next_time(self, *, all_done: bool) -> None:
        """更新每周商店 next_time

        Args:
            all_done: True → 下周一 12:00; False → 12小时后重试
        """
        try:
            bj_now = now_beijing()

            if all_done:
                # 下周一 12:00
                days_until_monday = (7 - bj_now.weekday()) % 7
                if days_until_monday == 0:
                    days_until_monday = 7
                next_mon = bj_now.date() + timedelta(days=days_until_monday)
                next_time = f"{next_mon.isoformat()} 12:00"
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
                    shop = cfg.get("每周商店", {})
                    shop["next_time"] = next_time
                    cfg["每周商店"] = shop
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(f"[每周商店] next_time 更新为 {next_time}")
        except Exception as e:
            self.logger.error(f"[每周商店] 更新 next_time 失败: {e}")

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[每周商店] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[每周商店] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[每周商店] 停止游戏失败: {e}")
