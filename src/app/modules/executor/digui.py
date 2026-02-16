"""
地鬼执行器 - 导航到地鬼界面，动态检测今日可用战斗数并完成挑战
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ...core.constants import TaskStatus
from ...core.logger import logger
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ui.manager import UIManager
from ..ocr.recognize import ocr_digits
from ..ui.assets import parse_number
from ..vision.template import find_all_templates, match_template
from ..vision.grid_detect import nms_by_distance
from .base import BaseExecutor
from .battle import run_battle, VICTORY
from .helpers import click_template, wait_for_template
from .lineup_switch import switch_lineup
from ..lineup import get_lineup_for_task

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# 模板路径
_TPL_SHAIXUAN = "assets/ui/templates/digui_shaixuan.png"
_TPL_TIAOZHAN = "assets/ui/templates/digui_tiaozhan.png"
_TPL_TIAOZHAN_SURE = "assets/ui/templates/digui_tiaozhan_sure.png"
_TPL_EXIT = "assets/ui/templates/exit.png"
_TPL_LOCK = "assets/ui/templates/lock_digui.png"
_TPL_JINRI = "assets/ui/templates/digui_jinri.png"
_TPL_WEIXUANZE = "assets/ui/templates/digui_weixuanze.png"
_TPL_TUODONG = "assets/ui/templates/digui_tuodong.png"

# 地鬼每日最大战斗次数（防御性上限）
MAX_ROUNDS = 3
# 判定为同一个按钮的最小距离（像素）
_SAME_BTN_DIST = 30
# 拖动重试上限
_MAX_DRAG_RETRIES = 3
# 挑战次数数字 OCR 区域：左上角(251,145) 右下角(266,173) → (x, y, w, h)
_CHALLENGE_COUNT_ROI = (251, 145, 15, 28)


def _is_near_any(
    pos: Tuple[int, int],
    visited: List[Tuple[int, int]],
    min_dist: int = _SAME_BTN_DIST,
) -> bool:
    """判断 pos 是否与 visited 中任一位置距离过近。"""
    min_dist_sq = min_dist * min_dist
    for vx, vy in visited:
        if (pos[0] - vx) ** 2 + (pos[1] - vy) ** 2 < min_dist_sq:
            return True
    return False


class DiGuiExecutor(BaseExecutor):
    """地鬼执行器"""

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
            activity_name=syscfg.activity_name or ".MainActivity" if syscfg else ".MainActivity",
        )
        return EmulatorAdapter(cfg)

    async def prepare(self, task: Task, account: GameAccount) -> bool:
        self.logger.info(f"[地鬼] 准备: account={account.login_id}")

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[地鬼] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error(f"[地鬼] 模拟器不存在: id={self.emulator_id}")
            return False

        self.adapter = self._build_adapter()

        ok = self.adapter.push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[地鬼] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[地鬼] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[地鬼] 执行: account={self.current_account.login_id}")

        # 构造/复用 UIManager
        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = (
                (self.system_config.capture_method if self.system_config else None)
                or "adb"
            )
            self.ui = UIManager(self.adapter, capture_method=capture_method)

        # 游戏就绪
        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            self.logger.error("[地鬼] 游戏就绪失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 切换阵容
        lineup_config = self.current_account.lineup_config or {}
        lineup = get_lineup_for_task(lineup_config, "地鬼")
        group = lineup.get("group", 0)
        position = lineup.get("position", 0)

        if group > 0 and position > 0:
            self.logger.info(f"[地鬼] 切换阵容: 分组={group}, 阵容={position}")
            ok = await switch_lineup(
                self.adapter,
                self.ui,
                self.ui.capture_method,
                group=group,
                position=position,
                log=self.logger,
            )
            if not ok:
                self.logger.error("[地鬼] 阵容切换失败")
                return {
                    "status": TaskStatus.FAILED,
                    "error": "阵容切换失败",
                    "timestamp": datetime.utcnow().isoformat(),
                }
        else:
            self.logger.info("[地鬼] 未配置阵容预设，维持当前阵容")

        # ── 第一阶段：导航到探索界面 ──
        in_tansuo = await self.ui.ensure_ui("TANSUO", max_steps=6, step_timeout=3.0)
        if not in_tansuo:
            self.logger.error("[地鬼] 导航到探索界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航探索界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }
        self.logger.info("[地鬼] 已到达探索界面")

        # ── 第二阶段：在探索界面立即检测地鬼是否被锁定 ──
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is not None:
            lock_match = match_template(screenshot, _TPL_LOCK)
            if lock_match:
                self.logger.warning(
                    f"[地鬼] 检测到锁定标识(score={lock_match.score:.2f})，等级不足，跳过"
                )
                return {
                    "status": TaskStatus.SKIPPED,
                    "reason": "等级不足，地鬼未解锁",
                    "timestamp": datetime.utcnow().isoformat(),
                }

        # ── 第三阶段：从探索导航到地鬼界面（仅需1步） ──
        in_digui = await self.ui.ensure_ui("DIGUI", max_steps=3, step_timeout=3.0)
        if not in_digui:
            self.logger.error("[地鬼] 导航到地鬼界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航地鬼界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info("[地鬼] 已到达地鬼界面")

        # ── 第四阶段：点击"今日"标签，检测可用战斗数（带重试） ──
        _JINRI_MAX_ATTEMPTS = 3
        total_rounds = 0
        for jinri_attempt in range(1, _JINRI_MAX_ATTEMPTS + 1):
            clicked_jinri = await click_template(
                self.adapter, self.ui.capture_method, _TPL_JINRI,
                timeout=5.0, settle=0.5, post_delay=1.0,
                log=self.logger,
                label=f"地鬼-今日标签(attempt={jinri_attempt}/{_JINRI_MAX_ATTEMPTS})",
                popup_handler=self.ui.popup_handler,
            )
            if not clicked_jinri:
                self.logger.warning(
                    f"[地鬼] 未检测到今日标签"
                    f" (attempt={jinri_attempt}/{_JINRI_MAX_ATTEMPTS})"
                )
                await asyncio.sleep(1.0)
                continue

            await asyncio.sleep(0.5)
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is None:
                self.logger.warning(
                    f"[地鬼] 截图失败"
                    f" (attempt={jinri_attempt}/{_JINRI_MAX_ATTEMPTS})"
                )
                await asyncio.sleep(1.0)
                continue

            raw_matches = find_all_templates(screenshot, _TPL_WEIXUANZE)
            unique_matches = nms_by_distance(raw_matches)
            if len(unique_matches) > 0:
                total_rounds = min(len(unique_matches), MAX_ROUNDS)
                self.logger.info(
                    f"[地鬼] 检测到 {len(unique_matches)} 个未选择标记，"
                    f"本次将战斗 {total_rounds} 轮"
                    f" (attempt={jinri_attempt})"
                )
                break
            else:
                self.logger.warning(
                    f"[地鬼] 未检测到未选择标记"
                    f" (attempt={jinri_attempt}/{_JINRI_MAX_ATTEMPTS})"
                )
                await asyncio.sleep(1.0)

        if total_rounds == 0:
            self.logger.info("[地鬼] 重试后仍未检测到未选择标记，今日地鬼已全部完成")
            return {
                "status": TaskStatus.SUCCEEDED,
                "victories": 0,
                "reason": "今日已完成",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info(f"[地鬼] 开始挑战，共 {total_rounds} 轮")

        victories = 0
        clicked_positions: List[Tuple[int, int]] = []  # 记录已点击的挑战按钮位置

        for round_idx in range(1, total_rounds + 1):
            self.logger.info(f"[地鬼] 第 {round_idx}/{total_rounds} 轮")

            # 1. 点击筛选按钮
            clicked = await click_template(
                self.adapter, self.ui.capture_method, _TPL_SHAIXUAN,
                timeout=8.0, settle=0.5, post_delay=1.5,
                log=self.logger, label=f"地鬼R{round_idx}-筛选",
                popup_handler=self.ui.popup_handler,
            )
            if not clicked:
                self.logger.error(f"[地鬼] 第 {round_idx} 轮未检测到筛选按钮")
                break

            # 2. 找到所有挑战按钮，选择未点击过的
            await asyncio.sleep(1.0)  # 等待列表加载
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is None:
                self.logger.error(f"[地鬼] 第 {round_idx} 轮截图失败")
                break

            all_matches = find_all_templates(screenshot, _TPL_TIAOZHAN)
            all_matches = nms_by_distance(all_matches)
            # 按 y 坐标排序（从上到下）
            all_matches.sort(key=lambda m: m.center[1])

            self.logger.info(
                f"[地鬼] 第 {round_idx} 轮检测到 {len(all_matches)} 个挑战按钮"
            )

            # 选择第一个未点击过的按钮
            target = None
            for m in all_matches:
                if not _is_near_any(m.center, clicked_positions):
                    target = m
                    break

            if target is None:
                self.logger.error(
                    f"[地鬼] 第 {round_idx} 轮没有可用的挑战按钮"
                )
                break

            cx, cy = target.center
            clicked_positions.append((cx, cy))
            tx, ty = target.random_point()
            self.adapter.adb.tap(self.adapter.cfg.adb_addr, tx, ty)
            self.logger.info(
                f"[地鬼] 第 {round_idx} 轮点击挑战按钮 ({tx}, {ty})"
            )
            await asyncio.sleep(1.5)

            # 3. 等待确认界面出现
            sure_match = await wait_for_template(
                self.adapter, self.ui.capture_method, _TPL_TIAOZHAN_SURE,
                timeout=8.0, log=self.logger, label=f"地鬼R{round_idx}-确认界面",
                popup_handler=self.ui.popup_handler,
            )
            if not sure_match:
                self.logger.error(f"[地鬼] 第 {round_idx} 轮未检测到确认界面")
                break

            # 4. 拖动滑块到最左并 OCR 验证次数为 1（最多重试）
            drag_ok = False
            for drag_attempt in range(1, _MAX_DRAG_RETRIES + 1):
                screenshot = self.adapter.capture(self.ui.capture_method)
                if screenshot is None:
                    self.logger.warning(
                        f"[地鬼] 第 {round_idx} 轮截图失败"
                        f"(drag attempt={drag_attempt})"
                    )
                    await asyncio.sleep(0.5)
                    continue

                tuodong_match = match_template(screenshot, _TPL_TUODONG)
                if tuodong_match:
                    tx, ty = tuodong_match.center
                    self.adapter.swipe(tx, ty, 10, ty, 500)
                    self.logger.info(
                        f"[地鬼] 第 {round_idx} 轮拖动滑块 "
                        f"({tx},{ty}) → (10,{ty}) "
                        f"(attempt={drag_attempt})"
                    )
                    await asyncio.sleep(0.8)
                else:
                    self.logger.warning(
                        f"[地鬼] 第 {round_idx} 轮未找到拖动滑块 "
                        f"(attempt={drag_attempt})"
                    )

                # OCR 验证挑战次数
                screenshot = self.adapter.capture(self.ui.capture_method)
                if screenshot is None:
                    continue
                result_ocr = ocr_digits(screenshot, roi=_CHALLENGE_COUNT_ROI)
                raw = result_ocr.text.strip()
                count_val = parse_number(raw)
                self.logger.info(
                    f"[地鬼] 第 {round_idx} 轮挑战次数 OCR: "
                    f"raw='{raw}' → value={count_val} "
                    f"(attempt={drag_attempt})"
                )
                if count_val == 1:
                    drag_ok = True
                    break

            if not drag_ok:
                self.logger.error(
                    f"[地鬼] 第 {round_idx} 轮拖动 {_MAX_DRAG_RETRIES} 次后"
                    f"挑战次数仍不为1，跳过本轮"
                )
                break

            # 5. 交给战斗模块（run_battle 会检测确认界面并点击准备）
            result = await run_battle(
                self.adapter, self.ui.capture_method,
                confirm_template=_TPL_TIAOZHAN_SURE,
                battle_timeout=120.0,
                log=self.logger,
                popup_handler=self.ui.popup_handler,
            )

            if result != VICTORY:
                self.logger.warning(f"[地鬼] 第 {round_idx} 轮战斗结果: {result}")
                break

            victories += 1
            self.logger.info(f"[地鬼] 第 {round_idx} 轮战斗胜利")

            # 4. 点击 exit 回到筛选界面（最后一轮不需要）
            if round_idx < total_rounds:
                await click_template(
                    self.adapter, self.ui.capture_method, _TPL_EXIT,
                    timeout=8.0, settle=0.5, post_delay=1.5,
                    log=self.logger, label=f"地鬼R{round_idx}-返回",
                    popup_handler=self.ui.popup_handler,
                )

        if victories == total_rounds:
            self.logger.info(f"[地鬼] 全部 {total_rounds} 轮胜利，任务完成")
            return {
                "status": TaskStatus.SUCCEEDED,
                "victories": victories,
                "timestamp": datetime.utcnow().isoformat(),
            }
        else:
            self.logger.warning(f"[地鬼] 仅完成 {victories}/{total_rounds} 轮")
            return {
                "status": TaskStatus.FAILED,
                "error": f"仅完成 {victories}/{total_rounds} 轮",
                "victories": victories,
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[地鬼] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[地鬼] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[地鬼] 停止游戏失败: {e}")
