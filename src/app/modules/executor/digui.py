"""
地鬼执行器 - 导航到地鬼界面，完成3次挑战战斗
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
from ..vision.template import find_all_templates
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

# 地鬼总共需要完成的战斗次数
TOTAL_ROUNDS = 3
# 判定为同一个按钮的最小距离（像素）
_SAME_BTN_DIST = 30


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
            self.logger.info("[地鬼] 未配置阵容，跳过切换")

        # 导航到地鬼界面
        in_digui = await self.ui.ensure_ui("DIGUI", max_steps=8, step_timeout=3.0)
        if not in_digui:
            self.logger.error("[地鬼] 导航到地鬼界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航地鬼界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info("[地鬼] 已到达地鬼界面，开始挑战")

        victories = 0
        clicked_positions: List[Tuple[int, int]] = []  # 记录已点击的挑战按钮位置

        for round_idx in range(1, TOTAL_ROUNDS + 1):
            self.logger.info(f"[地鬼] 第 {round_idx}/{TOTAL_ROUNDS} 轮")

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
            self.adapter.adb.tap(self.adapter.cfg.adb_addr, cx, cy)
            self.logger.info(
                f"[地鬼] 第 {round_idx} 轮点击挑战按钮 ({cx}, {cy})"
            )
            await asyncio.sleep(1.5)

            # 3. 等待确认界面出现后交给战斗模块
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
            if round_idx < TOTAL_ROUNDS:
                await click_template(
                    self.adapter, self.ui.capture_method, _TPL_EXIT,
                    timeout=8.0, settle=0.5, post_delay=1.5,
                    log=self.logger, label=f"地鬼R{round_idx}-返回",
                    popup_handler=self.ui.popup_handler,
                )

        if victories == TOTAL_ROUNDS:
            self.logger.info(f"[地鬼] 全部 {TOTAL_ROUNDS} 轮胜利，任务完成")
            return {
                "status": TaskStatus.SUCCEEDED,
                "victories": victories,
                "timestamp": datetime.utcnow().isoformat(),
            }
        else:
            self.logger.warning(f"[地鬼] 仅完成 {victories}/{TOTAL_ROUNDS} 轮")
            return {
                "status": TaskStatus.FAILED,
                "error": f"仅完成 {victories}/{TOTAL_ROUNDS} 轮",
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
