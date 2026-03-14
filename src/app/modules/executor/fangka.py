"""
放卡执行器 - 管理结界卡的放置（太鼓/斗鱼），支持星级范围和排序方向
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any, Dict, Optional

import cv2
import numpy as np

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus
from ...core.logger import logger
from ...core.timeutils import add_hours_to_beijing_time, format_beijing_time, now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ocr.async_recognize import async_ocr_digits, async_ocr_text
from ..ui.manager import UIManager
from ..vision.template import match_template
from .base import BaseExecutor
from .helpers import click_template

PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# OCR 区域定义 (x, y, w, h)
_COUNTDOWN_ROI = (692, 194, 72, 21)  # 倒计时 HH:mm:ss
_DURATION_ROI = (694, 194, 65, 21)   # 激活时长 "xx小时"

# 卡片模板映射：card_type -> level -> template_path
_CARD_TEMPLATES = {
    "taigu": {i: f"assets/ui/templates/fk_{i}xtg.png" for i in range(1, 7)},
    "douyu": {i: f"assets/ui/templates/fk_{i}xdy.png" for i in range(1, 7)},
}

# 4xtg/5xtg 灰色段数分类常量（放卡 UI 中模板底部图标区分析）
# 4xtg底部：4心 + 2灰图标 → 灰色列段数 >= 3
# 5xtg底部：5心 + 1灰图标 → 灰色列段数 < 3
_FK_TG_GRAY_S_MAX = 60    # 灰色饱和度上限
_FK_TG_GRAY_V_MIN = 60    # 灰色亮度下限
_FK_TG_STRIP_ROWS = 15    # 取底部行数（放卡UI需比寄养多取几行）
_FK_TG_COL_THR = 0.3      # 列灰色像素占比阈值
_FK_TG_SEG_THR = 3        # 段数 >= 此值 → 4xtg

# 滚动参数（与寄养任务一致）
_SCROLL_X = 306
_SCROLL_Y_FROM = 440
_SCROLL_Y_TO = 290           # 向上 ~150px
_SCROLL_DUR_MS = 400
_MAX_SCROLL_COUNT = 50       # 最大滚动次数安全上限


class FangkaExecutor(BaseExecutor):
    """放卡执行器"""

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

    @staticmethod
    def _classify_4xtg_5xtg(screenshot: np.ndarray, match) -> str:
        """通过底部灰色图标段数区分 4xtg / 5xtg。

        4xtg底部：4心 + 2灰图标 → 灰色列段数 >= 3
        5xtg底部：5心 + 1灰图标 → 灰色列段数 < 3
        """
        img_h, img_w = screenshot.shape[:2]
        y1 = max(0, match.y + match.h - _FK_TG_STRIP_ROWS)
        y2 = min(img_h, match.y + match.h)
        x1 = max(0, match.x)
        x2 = min(img_w, match.x + match.w)
        strip = screenshot[y1:y2, x1:x2]
        if strip.size == 0:
            return "4xtg"
        hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
        S = hsv[:, :, 1]
        V = hsv[:, :, 2]
        gray_mask = (S < _FK_TG_GRAY_S_MAX) & (V > _FK_TG_GRAY_V_MIN)
        gray_col = gray_mask.mean(axis=0)
        segments = 0
        in_seg = False
        for v in gray_col:
            if v > _FK_TG_COL_THR and not in_seg:
                segments += 1
                in_seg = True
            elif v <= _FK_TG_COL_THR:
                in_seg = False
        return "4xtg" if segments >= _FK_TG_SEG_THR else "5xtg"

    async def prepare(self, task: Task, account: GameAccount) -> bool:
        self.logger.info(f"[放卡] 准备: account={account.login_id}")

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[放卡] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error("[放卡] 模拟器不存在: id={}", self.emulator_id)
            return False

        self.adapter = self._build_adapter()

        ok = await self._push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[放卡] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[放卡] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[放卡] 执行: account={self.current_account.login_id}")

        # 构造或复用 UIManager
        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = (
                self.system_config.capture_method if self.system_config else None
            ) or "adb"
            self.ui = UIManager(
                self.adapter,
                capture_method=capture_method,
                cross_emulator_cache_enabled=self._cross_emulator_cache_enabled(),
            )

        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            self.logger.error("[放卡] 游戏就绪失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 读取放卡配置
        task_cfg = (self.current_account.task_config or {}).get("放卡", {})
        card_type = task_cfg.get("card_type", "taigu")
        level_min = task_cfg.get("level_min", 1)
        level_max = task_cfg.get("level_max", 6)
        sort_order = task_cfg.get("sort_order", "high_to_low")

        self.logger.info(
            f"[放卡] 配置: card_type={card_type}, "
            f"level={level_min}x~{level_max}x, sort={sort_order}"
        )

        # 导航到结界卡界面
        in_jiejie_ka = await self.ui.ensure_ui("JIEJIE_KA", max_steps=8, step_timeout=3.0)
        if not in_jiejie_ka:
            self.logger.error("[放卡] 导航到结界卡界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航结界卡界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        await asyncio.sleep(1.0)

        # 检测是否有正在放的卡（fk_xiexia.png）
        screenshot = await self._capture()
        if screenshot is None:
            self.logger.error("[放卡] 截图失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "截图失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        xiexia_match = match_template(screenshot, "assets/ui/templates/fk_xiexia.png")
        if xiexia_match:
            self.logger.info("[放卡] 检测到已有结界卡，读取倒计时")
            result = await self._handle_existing_card(screenshot)
            if result is not None:
                return result

        # 放新卡流程
        result = await self._place_new_card(card_type, level_min, level_max, sort_order)
        if result is not None:
            return result

        self.logger.info("[放卡] 执行完成")
        return {
            "status": TaskStatus.SUCCEEDED,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _handle_existing_card(self, screenshot) -> Optional[Dict[str, Any]]:
        """处理已有结界卡的情况。返回 dict 表示应终止执行，None 表示继续放新卡。"""
        # OCR 读取倒计时
        countdown_text = await self._ocr_region(_COUNTDOWN_ROI, digits_only=True)
        self.logger.info(f"[放卡] 倒计时 OCR 结果: '{countdown_text}'")

        if countdown_text and countdown_text.strip() != "00:00:00":
            # 还有剩余时间，解析并推迟任务
            delay_minutes = self._parse_countdown(countdown_text.strip())
            if delay_minutes > 0:
                self._update_next_time_minutes(delay_minutes)
                self.logger.info(f"[放卡] 卡片仍在生效，推迟 {delay_minutes} 分钟")
                return {
                    "status": TaskStatus.SUCCEEDED,
                    "timestamp": datetime.utcnow().isoformat(),
                }

        # 倒计时为 00:00:00 或解析失败，卸下旧卡
        self.logger.info("[放卡] 倒计时结束，卸下旧卡")
        clicked = await click_template(
            self.adapter,
            self.ui.capture_method,
            "assets/ui/templates/fk_xiexia.png",
            timeout=5.0,
            settle=0.5,
            post_delay=1.5,
            log=self.logger,
            label="卸下结界卡",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked:
            self.logger.warning("[放卡] 未能点击卸下按钮")

        # 点击确认
        await asyncio.sleep(0.5)
        clicked = await click_template(
            self.adapter,
            self.ui.capture_method,
            "assets/ui/templates/fk_queding.png",
            timeout=5.0,
            settle=0.5,
            post_delay=1.5,
            log=self.logger,
            label="确认卸下",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked:
            self.logger.warning("[放卡] 未能点击确认按钮")

        await asyncio.sleep(1.0)
        return None  # 继续放新卡

    async def _place_new_card(
        self,
        card_type: str,
        level_min: int,
        level_max: int,
        sort_order: str,
    ) -> Optional[Dict[str, Any]]:
        """放置新卡。返回 dict 表示执行结果，None 表示成功（由外层返回）。"""
        # 1. 点击全部
        clicked = await click_template(
            self.adapter,
            self.ui.capture_method,
            "assets/ui/templates/fk_quanbu.png",
            timeout=5.0,
            settle=0.5,
            post_delay=1.0,
            log=self.logger,
            label="全部筛选",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked:
            self.logger.warning("[放卡] 未能点击全部按钮")

        # 2. 选择卡片类型
        type_template = (
            "assets/ui/templates/fk_taigu.png"
            if card_type == "taigu"
            else "assets/ui/templates/fk_douyu.png"
        )
        type_label = "太鼓" if card_type == "taigu" else "斗鱼"
        clicked = await click_template(
            self.adapter,
            self.ui.capture_method,
            type_template,
            timeout=5.0,
            settle=0.5,
            post_delay=1.0,
            log=self.logger,
            label=type_label,
            popup_handler=self.ui.popup_handler,
        )
        if not clicked:
            self.logger.error(f"[放卡] 未能点击{type_label}筛选")
            return {
                "status": TaskStatus.FAILED,
                "error": f"未能点击{type_label}筛选",
                "timestamp": datetime.utcnow().isoformat(),
            }

        await asyncio.sleep(0.5)

        # 3. 排序方向：默认由高到低，如果需要由低到高则点击降序按钮
        if sort_order == "low_to_high":
            clicked = await click_template(
                self.adapter,
                self.ui.capture_method,
                "assets/ui/templates/fk_jiangxu.png",
                timeout=5.0,
                settle=0.5,
                post_delay=1.0,
                log=self.logger,
                label="切换排序",
                popup_handler=self.ui.popup_handler,
            )
            if not clicked:
                self.logger.warning("[放卡] 未能点击排序切换按钮")

        await asyncio.sleep(0.5)

        # 4. 扫描卡片（支持下滑翻页 + 范围外早停）
        templates = _CARD_TEMPLATES.get(card_type, {})

        if sort_order == "high_to_low":
            target_levels = list(range(level_max, level_min - 1, -1))
        else:
            target_levels = list(range(level_min, level_max + 1))

        card_clicked = False
        scroll_count = 0

        while True:
            screenshot = await self._capture()
            if screenshot is None:
                self.logger.warning("[放卡] 截图失败，重试")
                await asyncio.sleep(0.5)
                continue

            # 扫描当前屏幕上所有级别的卡片
            detected: Dict[int, Any] = {}
            for level in range(1, 7):
                template_path = templates.get(level)
                if not template_path:
                    continue

                # 4xtg/5xtg 特殊处理：模板几乎一样，需用灰色段数分类
                if card_type == "taigu" and level in (4, 5):
                    if 4 in detected or 5 in detected:
                        continue  # 已在本轮处理过
                    tpl_4 = templates.get(4, "")
                    tpl_5 = templates.get(5, "")
                    m4 = (
                        match_template(screenshot, tpl_4, threshold=0.8)
                        if tpl_4
                        else None
                    )
                    m5 = (
                        match_template(screenshot, tpl_5, threshold=0.8)
                        if tpl_5
                        else None
                    )
                    card_match = (
                        m4
                        if (m4 and (not m5 or m4.score >= m5.score))
                        else m5
                    )
                    if card_match:
                        classified = self._classify_4xtg_5xtg(
                            screenshot, card_match
                        )
                        actual_level = 4 if classified == "4xtg" else 5
                        self.logger.info(
                            f"[放卡] 4x/5x太鼓判定: {classified} "
                            f"(score={card_match.score:.3f})"
                        )
                        detected[actual_level] = card_match
                    continue

                card_match = match_template(screenshot, template_path)
                if card_match:
                    detected[level] = card_match

            # 在目标范围内按优先级查找
            for lv in target_levels:
                if lv in detected:
                    self.logger.info(f"[放卡] 检测到 {lv}x 卡片，点击")
                    cx, cy = detected[lv].center
                    await self._tap(cx, cy)
                    card_clicked = True
                    await asyncio.sleep(1.0)
                    break

            if card_clicked:
                break

            # 早停判断：检测到范围外的卡片说明目标范围内没卡了
            if detected:
                if sort_order == "high_to_low":
                    if any(lv < level_min for lv in detected):
                        no_card_msg = (
                            f"没有目标星级卡片"
                            f"（{level_min}x~{level_max}x {type_label}）"
                        )
                        self.logger.error(f"[放卡] {no_card_msg}")
                        return {
                            "status": TaskStatus.FAILED,
                            "error": no_card_msg,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                else:
                    if any(lv > level_max for lv in detected):
                        no_card_msg = (
                            f"没有目标星级卡片"
                            f"（{level_min}x~{level_max}x {type_label}）"
                        )
                        self.logger.error(f"[放卡] {no_card_msg}")
                        return {
                            "status": TaskStatus.FAILED,
                            "error": no_card_msg,
                            "timestamp": datetime.utcnow().isoformat(),
                        }

            # 滚动次数上限
            if scroll_count >= _MAX_SCROLL_COUNT:
                self.logger.error("[放卡] 已达最大滚动次数，未找到可用卡片")
                return {
                    "status": TaskStatus.FAILED,
                    "error": "未找到可用卡片",
                    "timestamp": datetime.utcnow().isoformat(),
                }

            # 下滑翻页
            self.logger.info(f"[放卡] 当前屏幕未找到目标卡片，下滑 (第{scroll_count + 1}次)")
            await self._swipe(
                _SCROLL_X, _SCROLL_Y_FROM, _SCROLL_X, _SCROLL_Y_TO, _SCROLL_DUR_MS
            )
            scroll_count += 1
            await asyncio.sleep(0.8)

        # 5. OCR 读取激活时长
        duration_text = await self._ocr_region(_DURATION_ROI, digits_only=True)
        self.logger.info(f"[放卡] 激活时长 OCR 结果: '{duration_text}'")
        duration_hours = self._parse_duration_hours(duration_text)

        # 6. 点击激活
        clicked = await click_template(
            self.adapter,
            self.ui.capture_method,
            "assets/ui/templates/fk_jihuo.png",
            timeout=5.0,
            settle=0.5,
            post_delay=1.5,
            log=self.logger,
            label="激活结界卡",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked:
            self.logger.warning("[放卡] 未能点击激活按钮")

        # 6.1 检测并点击确认按钮（激活后可能出现确认弹窗）
        clicked_queren = await click_template(
            self.adapter,
            self.ui.capture_method,
            "assets/ui/templates/fk_queren.png",
            timeout=3.0,
            settle=0.5,
            post_delay=1.0,
            log=self.logger,
            label="确认激活",
            popup_handler=self.ui.popup_handler,
        )
        if clicked_queren:
            self.logger.info("[放卡] 已点击确认按钮")

        # 7. 更新 next_time
        if duration_hours > 0:
            self._update_next_time_hours(duration_hours)
            self.logger.info(f"[放卡] 设置 next_time 为 {duration_hours} 小时后")
        else:
            self._update_next_time_hours(8)
            self.logger.warning("[放卡] 未能解析时长，默认 8 小时后")

        return None

    async def _ocr_region(self, roi: tuple, *, digits_only: bool = False) -> str:
        """对指定区域进行 OCR 识别，返回文本。"""
        for attempt in range(3):
            screenshot = await self._capture()
            if screenshot is None:
                continue
            try:
                if digits_only:
                    result = await async_ocr_digits(screenshot, roi=roi)
                    text = (result.text or "").strip()
                else:
                    text = await async_ocr_text(screenshot, roi=roi, min_confidence=0.3)
                    text = (text or "").strip()
                if text:
                    return text
            except Exception as e:
                # OCR 不可用时降级为空字符串，避免整个任务直接失败。
                self.logger.warning(
                    f"[放卡] OCR 识别失败 (attempt={attempt + 1}): {e}"
                )
            await asyncio.sleep(0.3)
        return ""

    @staticmethod
    def _parse_countdown(text: str) -> int:
        """解析倒计时 HH:mm:ss 格式，返回总分钟数。"""
        # 尝试匹配 HH:mm:ss
        m = re.match(r"(\d{1,2}):(\d{2}):(\d{2})", text)
        if m:
            hours = int(m.group(1))
            minutes = int(m.group(2))
            secs = int(m.group(3))
            if hours == 0 and minutes == 0 and secs == 0:
                return 0
            total = hours * 60 + minutes + (1 if secs > 0 else 0)
            return max(total, 1)

        # ddddocr 可能只返回数字（如 "012345" -> 01:23:45）。
        digits = re.sub(r"\D", "", text)
        if not digits:
            return 0
        if len(digits) >= 6:
            digits = digits[-6:]
            hours = int(digits[:-4])
            minutes = int(digits[-4:-2])
            secs = int(digits[-2:])
        elif len(digits) == 5:
            hours = int(digits[0])
            minutes = int(digits[1:3])
            secs = int(digits[3:])
        elif len(digits) == 4:
            hours = 0
            minutes = int(digits[:2])
            secs = int(digits[2:])
        else:
            return 0

        if minutes >= 60 or secs >= 60:
            return 0
        if hours == 0 and minutes == 0 and secs == 0:
            return 0
        total = hours * 60 + minutes + (1 if secs > 0 else 0)
        return max(total, 1)

    @staticmethod
    def _parse_duration_hours(text: str) -> int:
        """解析 'xx小时' 格式，返回小时数。"""
        if not text:
            return 0
        m = re.search(r"(\d+)", text)
        if m:
            return int(m.group(1))
        return 0

    def _update_next_time_hours(self, hours: int) -> None:
        """更新 next_time 为当前时间 + hours 小时。"""
        try:
            bj_now_str = format_beijing_time(now_beijing())
            next_time = add_hours_to_beijing_time(bj_now_str, hours)

            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    cfg = account.task_config or {}
                    task_cfg = cfg.get("放卡", {})
                    task_cfg["next_time"] = next_time
                    cfg["放卡"] = task_cfg
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(f"[放卡] next_time 更新为 {next_time}")
        except Exception as e:
            self.logger.error(f"[放卡] 更新 next_time 失败: {e}")

    def _update_next_time_minutes(self, minutes: int) -> None:
        """更新 next_time 为当前时间 + minutes 分钟。"""
        try:
            from datetime import timedelta

            bj_now = now_beijing()
            next_time = format_beijing_time(bj_now + timedelta(minutes=minutes))

            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    cfg = account.task_config or {}
                    task_cfg = cfg.get("放卡", {})
                    task_cfg["next_time"] = next_time
                    cfg["放卡"] = task_cfg
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(f"[放卡] next_time 更新为 {next_time}（延迟 {minutes} 分钟）")
        except Exception as e:
            self.logger.error(f"[放卡] 更新 next_time 失败: {e}")

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[放卡] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                await self._adb_force_stop(PKG_NAME)
                self.logger.info("[放卡] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[放卡] 停止游戏失败: {e}")
