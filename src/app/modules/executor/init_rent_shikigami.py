"""
起号 - 租借式神执行器
时间驱动的重复任务，每天执行一次。
流程：导航到新手任务界面 → OCR 点击新手特权 → 等待租借界面加载 →
      检测各式神星级（紫色勾玉数量）→ 按 5★>6★ + 旧优先级排序后租借。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus
from ...core.logger import logger
from ...core.timeutils import add_hours_to_beijing_time, format_beijing_time, now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ui.dialog_detector import detect_dialog
from ..ui.manager import UIManager
from ..vision.color_detect import count_purple_gouyu
from ..vision.grid_detect import nms_by_distance
from ..vision.template import find_all_templates, match_template
from ..vision.utils import load_image, random_point_in_circle
from .base import BaseExecutor
from .db_logger import emit as db_log
from .helpers import click_template, click_text, wait_for_template

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# 租借式神候选列表：(模板路径, 中文名称, 旧优先级索引)
SHIKIGAMI_CANDIDATES: List[Tuple[str, str, int]] = [
    ("assets/ui/templates/zujie_axiuluo.png", "阿修罗", 0),
    ("assets/ui/templates/zujie_guhuoniao.png", "古火鸟", 1),
    ("assets/ui/templates/zujie_dayuewan.png", "大月丸", 2),
]

# 勾玉检测区域高度（模板下方多少像素包含勾玉图标）
GOUYU_ROI_HEIGHT = 25

# 模板路径
TPL_TAG_ZUJIE = "assets/ui/templates/tag_zujie.png"
TPL_ZUJIE_BLANK = "assets/ui/templates/zujie_blank.png"
TPL_BACK = "assets/ui/templates/back.png"


class InitRentShikigamiExecutor(BaseExecutor):
    """起号 - 租借式神"""

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
            f"[起号_租借式神] 准备: account_id={account.id}, login_id={account.login_id}"
        )

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[起号_租借式神] 复用 shared_adapter，跳过 push 登录数据")
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
                    f"[起号_租借式神] 模拟器不存在: id={self.emulator_id}"
                )
                return False

            self.adapter = self._build_adapter()

            ok = self.adapter.push_login_data(
                account.login_id, data_dir="putonglogindata"
            )
            if not ok:
                self.logger.error(
                    f"[起号_租借式神] push 登录数据失败: {account.login_id}"
                )
                return False
            self.logger.info(
                f"[起号_租借式神] push 登录数据成功: {account.login_id}"
            )

        # 跳过可能的剧情对话
        await self._skip_dialogs()
        return True

    async def execute(self) -> Dict[str, Any]:
        account = self.current_account
        self.logger.info(f"[起号_租借式神] 执行: account_id={account.id}")

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
            self.logger.error("[起号_租借式神] 游戏就绪失败，未进入庭院")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. 执行租借式神
        rented = await self._rent_shikigami()

        # 3. 更新 next_time (+24h)
        self._update_next_time()

        self.logger.info(f"[起号_租借式神] 执行完成: account_id={account.id}")
        return {
            "status": TaskStatus.SUCCEEDED,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _rent_shikigami(self) -> List[Dict[str, Any]]:
        """租借式神核心流程：导航到租借界面 → 检测星级 → 按优先级租借"""
        self.logger.info("[起号_租借式神] 开始租借式神流程")

        # 1. 导航到新手任务界面
        in_xinshou = await self.ui.ensure_ui(
            "XINSHOU", max_steps=6, step_timeout=3.0
        )
        if not in_xinshou:
            self.logger.error("[起号_租借式神] 导航到新手任务界面失败")
            return []

        self.logger.info("[起号_租借式神] 已到达新手任务界面")
        await asyncio.sleep(1.0)

        # 2. OCR 点击左侧"新手特权"标签
        LEFT_COL_ROI = (0, 50, 150, 450)
        clicked_tequan = await click_text(
            self.adapter,
            self.ui.capture_method,
            "新手特权",
            roi=LEFT_COL_ROI,
            timeout=5.0,
            settle=0.5,
            post_delay=1.5,
            log=self.logger,
            label="起号_点击新手特权",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked_tequan:
            self.logger.warning("[起号_租借式神] 未识别到新手特权标签，跳过")
            return []

        # 3. 等待租借界面加载（tag_zujie.png 出现）
        zujie_ready = await wait_for_template(
            self.adapter,
            self.ui.capture_method,
            TPL_TAG_ZUJIE,
            timeout=5.0,
            interval=1.0,
            log=self.logger,
            label="起号_等待租借界面",
            popup_handler=self.ui.popup_handler,
        )
        if not zujie_ready:
            self.logger.warning("[起号_租借式神] 租借界面未加载完成")
            return []

        self.logger.info("[起号_租借式神] 已到达租借界面")
        await asyncio.sleep(0.5)

        # 4. 检测空位数量
        raw_screenshot = self.adapter.capture(self.ui.capture_method)
        if raw_screenshot is None:
            self.logger.error("[起号_租借式神] 截图失败")
            return []
        screenshot = load_image(raw_screenshot)

        blank_matches = find_all_templates(screenshot, TPL_ZUJIE_BLANK, threshold=0.8)
        blank_matches = nms_by_distance(blank_matches)
        blank_count = len(blank_matches)
        self.logger.info(f"[起号_租借式神] 检测到 {blank_count} 个空位")

        if blank_count == 0:
            self.logger.info("[起号_租借式神] 没有空位，已全部租借")
            await click_template(
                self.adapter,
                self.ui.capture_method,
                TPL_BACK,
                timeout=5.0,
                settle=0.3,
                post_delay=1.0,
                log=self.logger,
                label="起号_租借返回",
                popup_handler=self.ui.popup_handler,
            )
            return []

        # 5. 检测各式神及其星级，构建候选列表
        candidates = self._detect_candidates(screenshot)

        if not candidates:
            self.logger.warning("[起号_租借式神] 未检测到可租借式神")
            await click_template(
                self.adapter,
                self.ui.capture_method,
                TPL_BACK,
                timeout=5.0,
                settle=0.3,
                post_delay=1.0,
                log=self.logger,
                label="起号_租借返回",
                popup_handler=self.ui.popup_handler,
            )
            return []

        # 6. 按优先级排序：5★ 优先于 6★，同星级按旧优先级
        candidates.sort(key=lambda c: (c["star"], c["priority_idx"]))
        self.logger.info(
            f"[起号_租借式神] 排序后候选: "
            + ", ".join(f"{c['name']}({c['star']}★)" for c in candidates)
        )

        # 7. 按排序顺序逐个租借
        rented_list: List[Dict[str, Any]] = []

        for cand in candidates:
            if blank_count == 0:
                self.logger.info("[起号_租借式神] 所有位置已满，停止租借")
                break

            # 重新检测该式神位置（截图可能已更新）
            m = match_template(screenshot, cand["tpl_path"], threshold=0.8)
            if not m:
                self.logger.info(f"[起号_租借式神] 重新检测未找到 {cand['name']}，跳过")
                continue

            # 点击式神
            cx, cy = m.center
            self.adapter.adb.tap(self.adapter.cfg.adb_addr, cx, cy)
            self.logger.info(
                f"[起号_租借式神] 点击 {cand['name']}({cand['star']}★) ({cx}, {cy})"
            )
            await asyncio.sleep(2.0)

            # 重新截图，检查空位变化
            raw_screenshot = self.adapter.capture(self.ui.capture_method)
            if raw_screenshot is None:
                self.logger.warning("[起号_租借式神] 租借后截图失败")
                continue
            screenshot = load_image(raw_screenshot)

            new_blank_matches = find_all_templates(
                screenshot, TPL_ZUJIE_BLANK, threshold=0.8
            )
            new_blank_matches = nms_by_distance(new_blank_matches)
            new_blank_count = len(new_blank_matches)

            if new_blank_count < blank_count:
                self.logger.info(
                    f"[起号_租借式神] {cand['name']}({cand['star']}★) 租借成功 "
                    f"(空位: {blank_count} → {new_blank_count})"
                )
                rented_list.append({"name": cand["name"], "star": cand["star"]})
                blank_count = new_blank_count
            else:
                self.logger.warning(
                    f"[起号_租借式神] {cand['name']} 租借未成功，空位未变化"
                )

        self.logger.info(
            f"[起号_租借式神] 租借完成，已租借: "
            + ", ".join(f"{r['name']}({r['star']}★)" for r in rented_list)
        )

        # 8. 保存租借式神信息
        if rented_list:
            self._save_rented_shikigami(rented_list)

        # 9. 点击 back 返回庭院
        await click_template(
            self.adapter,
            self.ui.capture_method,
            TPL_BACK,
            timeout=5.0,
            settle=0.3,
            post_delay=1.0,
            log=self.logger,
            label="起号_租借返回",
            popup_handler=self.ui.popup_handler,
        )

        return rented_list

    def _detect_candidates(self, screenshot) -> List[Dict[str, Any]]:
        """检测界面中各式神的位置和星级（紫色勾玉数量）。"""
        candidates: List[Dict[str, Any]] = []
        img_h = screenshot.shape[0]

        for tpl_path, name, priority_idx in SHIKIGAMI_CANDIDATES:
            m = match_template(screenshot, tpl_path, threshold=0.8)
            if not m:
                self.logger.info(f"[起号_租借式神] 未检测到 {name}")
                continue

            # 计算勾玉 ROI：模板正下方区域
            roi_y = m.y + m.h
            roi_h = min(GOUYU_ROI_HEIGHT, img_h - roi_y)
            if roi_h <= 0:
                self.logger.warning(
                    f"[起号_租借式神] {name} 勾玉 ROI 超出图像范围"
                )
                continue

            gouyu_roi = (m.x, roi_y, m.w, roi_h)
            star = count_purple_gouyu(screenshot, roi=gouyu_roi)

            # 未检测到勾玉时使用默认值 6
            if star == 0:
                self.logger.warning(
                    f"[起号_租借式神] {name} 未检测到勾玉，默认 6★"
                )
                star = 6

            self.logger.info(
                f"[起号_租借式神] 检测到 {name}: {star}★ "
                f"(位置={m.center}, 勾玉ROI={gouyu_roi})"
            )
            candidates.append({
                "tpl_path": tpl_path,
                "name": name,
                "star": star,
                "priority_idx": priority_idx,
            })

        return candidates

    def _save_rented_shikigami(self, rented_list: List[Dict[str, Any]]) -> None:
        """将租借式神列表（含名字和星级）保存到 shikigami_config。"""
        try:
            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    cfg = account.shikigami_config or {}
                    cfg["租借式神"] = rented_list
                    account.shikigami_config = cfg
                    flag_modified(account, "shikigami_config")
                    db.commit()
                    self.logger.info(
                        f"[起号_租借式神] 已保存租借式神: {rented_list}"
                    )
        except Exception as e:
            self.logger.error(f"[起号_租借式神] 保存租借式神失败: {e}")

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
                    rent_cfg = cfg.get("起号_租借式神", {})
                    rent_cfg["next_time"] = next_time
                    cfg["起号_租借式神"] = rent_cfg
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(
                        f"[起号_租借式神] next_time 更新为 {next_time}"
                    )
        except Exception as e:
            self.logger.error(f"[起号_租借式神] 更新 next_time 失败: {e}")

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[起号_租借式神] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[起号_租借式神] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[起号_租借式神] 停止游戏失败: {e}")

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
            self.logger.info(f"[起号_租借式神] 跳过了 {clicks} 轮剧情对话")
        return clicks
