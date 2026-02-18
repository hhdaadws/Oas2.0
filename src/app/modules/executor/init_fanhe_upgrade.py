"""
起号 - 升级饭盒/酒壶执行器
仅 init 阶段账号使用。导航到结界界面后点击进入饭盒或酒壶界面，循环升级。
通过 OCR 判断勋章是否足够。等级上限 10 级。
策略：先升满饭盒，再升酒壶。两者都满级后永久禁用该任务。
"""
from __future__ import annotations

import asyncio
import re
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
from .helpers import click_template, wait_for_template, _adapter_capture, _adapter_tap

PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# OCR 区域定义（饭盒和酒壶共用同一布局）
_LEVEL_ROI = (336, 212, 19, 14)        # 等级
_ASSET_XUNZHANG_ROI = (567, 21, 60, 17)  # 当前拥有的勋章数
_NEED_XUNZHANG_ROI = (660, 359, 46, 25)  # 升级所需的勋章数

MAX_FANHE_LEVEL = 10
MAX_JIUHU_LEVEL = 10
MAX_UPGRADE_LOOPS = 12  # 防止无限循环

# 结界界面中进入饭盒/酒壶的点击坐标
_JIEJIE_TAP_X = 665
_JIEJIE_TAP_Y = 415


def _parse_number(text: str) -> Optional[int]:
    """从 OCR 文本中提取数字。"""
    cleaned = re.sub(r"[^\d]", "", text.strip())
    if cleaned:
        try:
            return int(cleaned)
        except ValueError:
            pass
    return None


class InitFanheUpgradeExecutor(BaseExecutor):
    """起号 - 升级饭盒/酒壶"""

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
            f"[起号_升级饭盒] 准备: account_id={account.id}, login_id={account.login_id}"
        )

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[起号_升级饭盒] 复用 shared_adapter，跳过 push 登录数据")
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
                    f"[起号_升级饭盒] 模拟器不存在: id={self.emulator_id}"
                )
                return False

            self.adapter = self._build_adapter()

            ok = await self._push_login_data(
                account.login_id, data_dir="putonglogindata"
            )
            if not ok:
                self.logger.error(
                    f"[起号_升级饭盒] push 登录数据失败: {account.login_id}"
                )
                return False
            self.logger.info(
                f"[起号_升级饭盒] push 登录数据成功: {account.login_id}"
            )

        # 跳过可能的剧情对话
        await self._skip_dialogs()
        return True

    def _determine_target(self) -> Optional[str]:
        """根据数据库中的饭盒/酒壶等级判断升级目标。

        Returns:
            "fanhe" / "jiuhu" / None（都满级）
        """
        with SessionLocal() as db:
            account = (
                db.query(GameAccount)
                .filter(GameAccount.id == self.current_account.id)
                .first()
            )
            if not account:
                return "fanhe"
            fanhe_lv = account.fanhe_level or 1
            jiuhu_lv = account.jiuhu_level or 1

        if fanhe_lv < MAX_FANHE_LEVEL:
            return "fanhe"
        if jiuhu_lv < MAX_JIUHU_LEVEL:
            return "jiuhu"
        return None

    async def _detect_current_screen(self) -> Optional[str]:
        """截图检测当前界面是 FANHE 还是 JIUHU。

        Returns:
            "FANHE" / "JIUHU" / None（无法识别）
        """
        screenshot = await self._capture()
        if screenshot is None:
            return None
        result = await self._detect_ui(screenshot)
        if result.ui in ("FANHE", "JIUHU"):
            return result.ui
        return None

    async def execute(self) -> Dict[str, Any]:
        account = self.current_account
        self.logger.info(f"[起号_升级饭盒] 执行: account_id={account.id}")

        # 构造或复用 UIManager
        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = (
                self.system_config.capture_method if self.system_config else None
            ) or "adb"
            self.ui = UIManager(self.adapter, capture_method=capture_method, cross_emulator_cache_enabled=self._cross_emulator_cache_enabled())

        # 1. 确保游戏就绪（进入庭院）
        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            self.logger.error("[起号_升级饭盒] 游戏就绪失败，未进入庭院")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. 判断升级目标
        target = self._determine_target()
        if target is None:
            self.logger.info("[起号_升级饭盒] 饭盒和酒壶都已满级，永久禁用任务")
            self._disable_task()
            return {
                "status": TaskStatus.SUCCEEDED,
                "message": "饭盒和酒壶都已满级",
                "timestamp": datetime.utcnow().isoformat(),
            }

        target_label = "饭盒" if target == "fanhe" else "酒壶"
        target_screen = "FANHE" if target == "fanhe" else "JIUHU"
        self.logger.info(f"[起号_升级饭盒] 升级目标: {target_label}")

        # 3. 导航到结界界面
        in_jiejie = await self.ui.ensure_ui("JIEJIE", max_steps=10, step_timeout=3.0)
        if not in_jiejie:
            self.logger.error("[起号_升级饭盒] 导航到结界界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航结界界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 4. 点击进入饭盒/酒壶区域（可能随机进入其中之一）
        await self._tap(_JIEJIE_TAP_X, _JIEJIE_TAP_Y)
        await asyncio.sleep(1.5)

        # 5. 检测当前进入了哪个界面
        current_screen = await self._detect_current_screen()
        self.logger.info(f"[起号_升级饭盒] 进入界面: {current_screen}，目标: {target_screen}")

        if current_screen is None:
            # 重试一次检测
            await asyncio.sleep(1.0)
            current_screen = await self._detect_current_screen()
            if current_screen is None:
                self.logger.error("[起号_升级饭盒] 无法识别当前界面")
                return {
                    "status": TaskStatus.FAILED,
                    "error": "无法识别饭盒/酒壶界面",
                    "timestamp": datetime.utcnow().isoformat(),
                }

        # 6. 如果当前界面与目标不符，点击切换
        if current_screen != target_screen:
            if target == "jiuhu":
                # 当前在饭盒，需要切换到酒壶
                switched = await click_template(
                    self.adapter,
                    self.ui.capture_method,
                    "assets/ui/templates/to_jiuhu.png",
                    timeout=5.0,
                    settle=0.5,
                    post_delay=1.5,
                    log=self.logger,
                    label="起号_切换到酒壶",
                    popup_handler=self.ui.popup_handler,
                )
            else:
                # 当前在酒壶，需要切换到饭盒
                switched = await click_template(
                    self.adapter,
                    self.ui.capture_method,
                    "assets/ui/templates/to_fanhe.png",
                    timeout=5.0,
                    settle=0.5,
                    post_delay=1.5,
                    log=self.logger,
                    label="起号_切换到饭盒",
                    popup_handler=self.ui.popup_handler,
                )
            if not switched:
                self.logger.warning(f"[起号_升级饭盒] 切换到{target_label}失败")
                self._update_next_time()
                return {
                    "status": TaskStatus.FAILED,
                    "error": f"切换到{target_label}失败",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            self.logger.info(f"[起号_升级饭盒] 已切换到{target_label}界面")

        self.logger.info(f"[起号_升级饭盒] 已到达{target_label}界面")
        await asyncio.sleep(1.0)

        # 7. OCR 等级
        level = await self._ocr_level()
        self._save_level(target, level)
        self.logger.info(f"[起号_升级饭盒] 当前{target_label}等级: {level}")

        max_level = MAX_FANHE_LEVEL if target == "fanhe" else MAX_JIUHU_LEVEL
        if level is not None and level >= max_level:
            self.logger.info(f"[起号_升级饭盒] {target_label}已满级({max_level})")
            # 检查是否需要切换到另一个目标
            other_target = self._determine_target()
            if other_target is None:
                self.logger.info("[起号_升级饭盒] 饭盒和酒壶都已满级，永久禁用任务")
                self._disable_task()
            else:
                self._update_next_time()
            return {
                "status": TaskStatus.SUCCEEDED,
                "message": f"{target_label}已满级",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 8. 点击升级按钮
        clicked_shengji = await click_template(
            self.adapter,
            self.ui.capture_method,
            "assets/ui/templates/fanhe_shengji.png",
            timeout=5.0,
            settle=0.5,
            post_delay=1.5,
            log=self.logger,
            label=f"起号_{target_label}升级按钮",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked_shengji:
            self.logger.warning(f"[起号_升级饭盒] 未检测到{target_label}升级按钮")
            self._update_next_time()
            return {
                "status": TaskStatus.FAILED,
                "error": f"未检测到{target_label}升级按钮",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 9. 循环升级
        upgraded_count = 0
        for loop_idx in range(MAX_UPGRADE_LOOPS):
            self.logger.info(f"[起号_升级饭盒] {target_label}升级循环 #{loop_idx + 1}")

            # 9a. 等待确认弹窗出现
            sure_match = await wait_for_template(
                self.adapter,
                self.ui.capture_method,
                "assets/ui/templates/fanhe_shengji_sure.png",
                timeout=8.0,
                interval=0.5,
                log=self.logger,
                label=f"起号_{target_label}等待确认弹窗",
                popup_handler=self.ui.popup_handler,
            )
            if not sure_match:
                self.logger.warning("[起号_升级饭盒] 等待确认弹窗超时，退出升级")
                break

            # 9b. 弹窗已出现，等待 UI 稳定后截图
            await asyncio.sleep(0.5)
            screenshot = await self._capture()
            if screenshot is None:
                self.logger.warning("[起号_升级饭盒] 截图失败，退出升级")
                break

            # 9c. 用同一张截图 OCR 当前勋章和所需勋章
            asset_val, need_val = await self._ocr_xunzhang_from_screenshot(screenshot)

            self.logger.info(
                f"[起号_升级饭盒] 勋章: 拥有={asset_val}, 需要={need_val}"
            )

            if asset_val is None or need_val is None:
                self.logger.warning("[起号_升级饭盒] OCR 勋章数失败，退出升级")
                break

            if asset_val < need_val:
                self.logger.info("[起号_升级饭盒] 勋章不足，退出升级")
                # 关闭升级弹窗
                await click_template(
                    self.adapter,
                    self.ui.capture_method,
                    "assets/ui/templates/exit_pink.png",
                    timeout=3.0,
                    settle=0.3,
                    post_delay=1.0,
                    log=self.logger,
                    label="起号_关闭升级弹窗",
                    popup_handler=self.ui.popup_handler,
                )
                break

            # 9d. 勋章足够，点击确认升级
            clicked_sure = await click_template(
                self.adapter,
                self.ui.capture_method,
                "assets/ui/templates/fanhe_shengji_sure.png",
                timeout=5.0,
                settle=0.5,
                post_delay=2.0,
                log=self.logger,
                label=f"起号_确认升级{target_label}",
                popup_handler=self.ui.popup_handler,
            )
            if not clicked_sure:
                self.logger.warning("[起号_升级饭盒] 未检测到确认升级按钮")
                break

            upgraded_count += 1
            self.logger.info(
                f"[起号_升级饭盒] {target_label}升级成功，累计 {upgraded_count} 次"
            )

            # 9e. 升级成功后，重新点击升级按钮触发下一轮确认弹窗
            await asyncio.sleep(1.0)
            clicked_next = await click_template(
                self.adapter,
                self.ui.capture_method,
                "assets/ui/templates/fanhe_shengji.png",
                timeout=5.0,
                settle=0.5,
                post_delay=1.5,
                log=self.logger,
                label=f"起号_{target_label}再次点击升级按钮",
                popup_handler=self.ui.popup_handler,
            )
            if not clicked_next:
                self.logger.info(
                    "[起号_升级饭盒] 未检测到升级按钮（可能已满级），退出升级"
                )
                break

        # 10. 回到升级界面重新 OCR 等级
        await asyncio.sleep(1.0)

        # 如果还在升级弹窗中，可能需要先关闭
        screenshot = await self._capture()
        if screenshot is not None:
            exit_pink = match_template(
                screenshot, "assets/ui/templates/exit_pink.png", threshold=0.7
            )
            if exit_pink:
                epx, epy = exit_pink.random_point()
                await self._tap(epx, epy)
                await asyncio.sleep(1.0)

        # OCR 最终等级并更新 DB
        final_level = await self._ocr_level()
        if final_level is not None:
            self._save_level(target, final_level)
            self.logger.info(f"[起号_升级饭盒] 最终{target_label}等级: {final_level}")

            if final_level >= max_level:
                self.logger.info(f"[起号_升级饭盒] {target_label}已满级({max_level})")
                # 再检查另一个是否也满级
                other_target = self._determine_target()
                if other_target is None:
                    self.logger.info("[起号_升级饭盒] 饭盒和酒壶都已满级，永久禁用任务")
                    self._disable_task()
                else:
                    self._update_next_time()
            else:
                self._update_next_time()
        else:
            self._update_next_time()

        db_log(account.id, f"升级{target_label}完成，升级 {upgraded_count} 次")

        self.logger.info(
            f"[起号_升级饭盒] 执行完成: account_id={account.id}, 目标={target_label}, 升级次数={upgraded_count}"
        )
        return {
            "status": TaskStatus.SUCCEEDED,
            "upgraded_count": upgraded_count,
            "target": target_label,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _ocr_level(self) -> Optional[int]:
        """OCR 等级（饭盒/酒壶共用同一 ROI）"""
        try:
            from ..ocr.async_recognize import async_ocr_digits

            screenshot = await self._capture()
            if screenshot is None:
                return None
            result = await async_ocr_digits(screenshot, roi=_LEVEL_ROI)
            raw = result.text.strip() if hasattr(result, "text") else ""
            if not raw and hasattr(result, "boxes") and result.boxes:
                raw = result.boxes[0].text.strip()
            return _parse_number(raw)
        except Exception as e:
            self.logger.error(f"[起号_升级饭盒] OCR 等级失败: {e}")
            return None

    async def _ocr_asset_xunzhang(self) -> Optional[int]:
        """OCR 当前拥有的勋章数"""
        try:
            from ..ocr.async_recognize import async_ocr_digits

            screenshot = await self._capture()
            if screenshot is None:
                return None
            result = await async_ocr_digits(screenshot, roi=_ASSET_XUNZHANG_ROI)
            raw = result.text.strip() if hasattr(result, "text") else ""
            if not raw and hasattr(result, "boxes") and result.boxes:
                raw = result.boxes[0].text.strip()
            return _parse_number(raw)
        except Exception as e:
            self.logger.error(f"[起号_升级饭盒] OCR 资产勋章失败: {e}")
            return None

    async def _ocr_need_xunzhang(self) -> Optional[int]:
        """OCR 升级所需的勋章数"""
        try:
            from ..ocr.async_recognize import async_ocr_digits

            screenshot = await self._capture()
            if screenshot is None:
                return None
            result = await async_ocr_digits(screenshot, roi=_NEED_XUNZHANG_ROI)
            raw = result.text.strip() if hasattr(result, "text") else ""
            if not raw and hasattr(result, "boxes") and result.boxes:
                raw = result.boxes[0].text.strip()
            return _parse_number(raw)
        except Exception as e:
            self.logger.error(f"[起号_升级饭盒] OCR 所需勋章失败: {e}")
            return None

    async def _ocr_xunzhang_from_screenshot(
        self, screenshot
    ) -> tuple[Optional[int], Optional[int]]:
        """从同一张截图 OCR 当前拥有勋章数和升级所需勋章数。

        Returns:
            (asset_val, need_val) 元组
        """
        try:
            from ..ocr.async_recognize import async_ocr_digits

            # 当前拥有的勋章数
            result_asset = await async_ocr_digits(screenshot, roi=_ASSET_XUNZHANG_ROI)
            raw_asset = result_asset.text.strip() if hasattr(result_asset, "text") else ""
            if not raw_asset and hasattr(result_asset, "boxes") and result_asset.boxes:
                raw_asset = result_asset.boxes[0].text.strip()
            asset_val = _parse_number(raw_asset)

            # 升级所需的勋章数
            result_need = await async_ocr_digits(screenshot, roi=_NEED_XUNZHANG_ROI)
            raw_need = result_need.text.strip() if hasattr(result_need, "text") else ""
            if not raw_need and hasattr(result_need, "boxes") and result_need.boxes:
                raw_need = result_need.boxes[0].text.strip()
            need_val = _parse_number(raw_need)

            return asset_val, need_val
        except Exception as e:
            self.logger.error(f"[起号_升级饭盒] OCR 勋章数失败: {e}")
            return None, None

    def _save_level(self, target: str, level: Optional[int]) -> None:
        """保存等级到数据库（根据 target 选择 fanhe_level 或 jiuhu_level）"""
        if level is None:
            return
        field = "fanhe_level" if target == "fanhe" else "jiuhu_level"
        label = "饭盒" if target == "fanhe" else "酒壶"
        try:
            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    setattr(account, field, level)
                    db.commit()
                    self.logger.info(f"[起号_升级饭盒] {label}等级已保存: {level}")
        except Exception as e:
            self.logger.error(f"[起号_升级饭盒] 保存{label}等级失败: {e}")

    def _save_fanhe_level(self, level: Optional[int]) -> None:
        """保存饭盒等级到数据库（兼容旧调用）"""
        self._save_level("fanhe", level)

    def _disable_task(self) -> None:
        """永久禁用升级饭盒任务（饭盒和酒壶都已满级）"""
        try:
            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    cfg = account.task_config or {}
                    fanhe_cfg = cfg.get("起号_升级饭盒", {})
                    fanhe_cfg["enabled"] = False
                    cfg["起号_升级饭盒"] = fanhe_cfg
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info("[起号_升级饭盒] 任务已永久禁用（饭盒和酒壶都已满级）")
        except Exception as e:
            self.logger.error(f"[起号_升级饭盒] 禁用任务失败: {e}")

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
                    fanhe_cfg = cfg.get("起号_升级饭盒", {})
                    fanhe_cfg["next_time"] = next_time
                    cfg["起号_升级饭盒"] = fanhe_cfg
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(
                        f"[起号_升级饭盒] next_time 更新为 {next_time}"
                    )
        except Exception as e:
            self.logger.error(f"[起号_升级饭盒] 更新 next_time 失败: {e}")

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[起号_升级饭盒] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                await self._adb_force_stop(PKG_NAME)
                self.logger.info("[起号_升级饭盒] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[起号_升级饭盒] 停止游戏失败: {e}")

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
            self.logger.info(f"[起号_升级饭盒] 跳过了 {clicks} 轮剧情对话")
        return clicks
