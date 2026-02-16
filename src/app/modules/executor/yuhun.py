"""
御魂执行器 - 导航到御魂界面，支持10层滚动检测/解锁，执行指定次数的挑战战斗
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus
from ...core.logger import logger
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ui.manager import UIManager
from ..vision.template import match_template
from ..vision.yuhun_detect import (
    LevelState,
    YuHunLevel,
    detect_yuhun_levels,
    find_highest_unlocked_level,
)
from .base import BaseExecutor
from .battle import run_battle, ManualLineupInfo, VICTORY
from .helpers import click_template, wait_for_template
from .lineup_switch import switch_lineup
from ..lineup import get_lineup_for_task
from ..shikigami import build_manual_lineup_info

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# 模板路径
_TPL_TIAOZHAN = "assets/ui/templates/yuhun_tiaozhan.png"
_TPL_TAG_YUHUN = "assets/ui/templates/tag_yuhun.png"

# 御魂总共 10 层关卡
_TOTAL_LEVELS = 10

# ── 滚动常量（960×540 分辨率）──
_SWIPE_X = 150          # 列表左侧 x 坐标，用于滑动
_SWIPE_DUR_MS = 400     # 滑动持续时间（较慢以减少惯性漂移）
_SCROLL_SETTLE = 0.8    # 滚动后等待动画结束（秒）


class YuHunExecutor(BaseExecutor):
    """御魂执行器"""

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
        self.logger.info(f"[御魂] 准备: account={account.login_id}")

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[御魂] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error(f"[御魂] 模拟器不存在: id={self.emulator_id}")
            return False

        self.adapter = self._build_adapter()

        ok = self.adapter.push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[御魂] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[御魂] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[御魂] 执行: account={self.current_account.login_id}")

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
            self.logger.error("[御魂] 游戏就绪失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 读取 remaining_count
        remaining = self._get_remaining_count()
        if remaining <= 0:
            self.logger.info("[御魂] remaining_count <= 0，跳过")
            return {
                "status": TaskStatus.SKIPPED,
                "reason": "remaining_count <= 0",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info(f"[御魂] 计划执行 {remaining} 轮战斗")

        # 读取目标层级
        target_level = self._get_target_level()
        if target_level < 1 or target_level > _TOTAL_LEVELS:
            target_level = _TOTAL_LEVELS
        self.logger.info(f"[御魂] 目标层级: {target_level}")

        # 切换阵容
        lineup_config = self.current_account.lineup_config or {}
        lineup = get_lineup_for_task(lineup_config, "御魂")
        group = lineup.get("group", 0)
        position = lineup.get("position", 0)

        if group > 0 and position > 0:
            self.logger.info(f"[御魂] 切换阵容: 分组={group}, 阵容={position}")
            ok = await switch_lineup(
                self.adapter,
                self.ui,
                self.ui.capture_method,
                group=group,
                position=position,
                log=self.logger,
            )
            if not ok:
                self.logger.error("[御魂] 阵容切换失败")
                return {
                    "status": TaskStatus.FAILED,
                    "error": "阵容切换失败",
                    "timestamp": datetime.utcnow().isoformat(),
                }
        else:
            self.logger.info("[御魂] 未配置阵容，跳过切换")

        # 构建手动阵容（仅 init 账号在无预设阵容时自动配置）
        manual_lineup = None
        if (group == 0 or position == 0) and self.current_account.progress == "init":
            shikigami_cfg = self.current_account.shikigami_config or {}
            lineup_data = build_manual_lineup_info(shikigami_cfg)
            if lineup_data:
                manual_lineup = ManualLineupInfo(
                    rental_shikigami=lineup_data["rental_shikigami"],
                    zuofu_template=lineup_data["zuofu_template"],
                )
                self.logger.info(
                    f"[御魂] init账号，将使用手动阵容: "
                    f"租借={[n for _, n, _ in manual_lineup.rental_shikigami]}, "
                    f"座敷={'有' if manual_lineup.zuofu_template else '无'}"
                )
        elif group == 0 or position == 0:
            self.logger.info("[御魂] 未配置阵容预设，维持当前阵容")

        # ── 导航到御魂界面 ──
        in_yuhun = await self.ui.ensure_ui("YUHUN", max_steps=8, step_timeout=3.0)
        if not in_yuhun:
            self.logger.error("[御魂] 导航到御魂界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航御魂界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }
        self.logger.info("[御魂] 已到达御魂界面")

        # ── 复位到顶部并扫描解锁状态 ──
        await self._scroll_to_top()
        await asyncio.sleep(1.0)

        unlocked_count = await self._scan_unlocked_count()
        self._update_unlocked_count(unlocked_count)
        self.logger.info(f"[御魂] 当前解锁: {unlocked_count}/{_TOTAL_LEVELS}")

        # ── 逐层解锁到目标层（如果未达标） ──
        if unlocked_count < target_level:
            self.logger.info(
                f"[御魂] 需要解锁到第 {target_level} 层 "
                f"(当前 {unlocked_count})，开始逐层解锁"
            )
            unlock_ok = await self._unlock_to_target(target_level, manual_lineup)
            if not unlock_ok:
                self.logger.error("[御魂] 关卡解锁失败（战力不足）")
                return {
                    "status": TaskStatus.FAILED,
                    "error": "关卡解锁失败，战力不足",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            # 解锁后重新扫描确认
            unlocked_count = await self._scan_unlocked_count()
            self._update_unlocked_count(unlocked_count)
            self.logger.info(f"[御魂] 解锁后: {unlocked_count}/{_TOTAL_LEVELS}")

        # ── 滚动到目标层并选中 ──
        await self._scroll_to_level_visible(target_level)
        await asyncio.sleep(0.8)

        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            self.logger.error("[御魂] 截图失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "截图失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        vp_start = self._get_viewport_start(target_level)
        visible = detect_yuhun_levels(screenshot, start_index=vp_start)
        for lv in visible:
            self.logger.info(
                f"[御魂] 层级 {lv.index}: state={lv.state.value}, "
                f"hsv=({lv.avg_hsv[0]:.0f}, {lv.avg_hsv[1]:.0f}, {lv.avg_hsv[2]:.0f})"
            )

        target_lv = None
        for lv in visible:
            if lv.index == target_level:
                target_lv = lv
                break

        if target_lv is None or target_lv.state == LevelState.LOCKED:
            self.logger.error(f"[御魂] 第 {target_level} 层不可用")
            return {
                "status": TaskStatus.FAILED,
                "error": f"第{target_level}层不可用",
                "timestamp": datetime.utcnow().isoformat(),
            }

        if target_lv.state != LevelState.SELECTED:
            cx, cy = target_lv.center
            self.adapter.adb.tap(self.adapter.cfg.adb_addr, cx, cy)
            self.logger.info(
                f"[御魂] 点击选中第 {target_level} 层 ({cx}, {cy})"
            )
            await asyncio.sleep(1.0)

        # ── 战斗循环 ──
        victories = 0
        for round_idx in range(1, remaining + 1):
            self.logger.info(f"[御魂] 第 {round_idx}/{remaining} 轮")

            # 1. 点击挑战按钮
            clicked = await click_template(
                self.adapter, self.ui.capture_method, _TPL_TIAOZHAN,
                timeout=8.0, settle=0.5, post_delay=1.5,
                log=self.logger, label=f"御魂R{round_idx}-挑战",
                popup_handler=self.ui.popup_handler,
            )
            if not clicked:
                self.logger.error(f"[御魂] 第 {round_idx} 轮未检测到挑战按钮")
                break

            # 2. 执行战斗（准备→战斗→胜利→奖励全流程）
            result = await run_battle(
                self.adapter, self.ui.capture_method,
                confirm_template=None,
                battle_timeout=180.0,
                log=self.logger,
                popup_handler=self.ui.popup_handler,
                manual_lineup=manual_lineup if round_idx == 1 else None,
            )

            if result != VICTORY:
                self.logger.warning(f"[御魂] 第 {round_idx} 轮战斗结果: {result}")
                break

            victories += 1
            self.logger.info(f"[御魂] 第 {round_idx} 轮战斗胜利")

            # 3. 每次胜利后递减 remaining_count
            self._decrement_remaining_count()

            # 4. 等待回到御魂界面
            back = await wait_for_template(
                self.adapter, self.ui.capture_method, _TPL_TIAOZHAN,
                timeout=10.0, interval=1.0,
                log=self.logger, label=f"御魂R{round_idx}-等待回到界面",
                popup_handler=self.ui.popup_handler,
            )
            if not back:
                self.logger.warning(f"[御魂] 第 {round_idx} 轮等待回到御魂界面超时")
                await asyncio.sleep(2.0)

        if victories == remaining:
            self.logger.info(f"[御魂] 全部 {remaining} 轮胜利，任务完成")
            return {
                "status": TaskStatus.SUCCEEDED,
                "victories": victories,
                "timestamp": datetime.utcnow().isoformat(),
            }
        elif victories > 0:
            self.logger.warning(f"[御魂] 完成 {victories}/{remaining} 轮")
            return {
                "status": TaskStatus.FAILED,
                "error": f"仅完成 {victories}/{remaining} 轮",
                "victories": victories,
                "timestamp": datetime.utcnow().isoformat(),
            }
        else:
            self.logger.error(f"[御魂] 0/{remaining} 轮，任务失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "战斗失败",
                "victories": 0,
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[御魂] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[御魂] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[御魂] 停止游戏失败: {e}")

    # ── 滚动方法 ──

    async def _scroll_to_top(self) -> None:
        """复位列表到顶部，通过连续截图比对确认到顶。"""
        prev_screenshot = None
        for attempt in range(6):
            # 手指从低y拖到高y = 列表向上滚（回到顶部）
            self.adapter.swipe(_SWIPE_X, 150, _SWIPE_X, 400, _SWIPE_DUR_MS)
            await asyncio.sleep(0.6)
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is not None and prev_screenshot is not None:
                # 对比列表区域 ROI 的像素差异
                roi_curr = screenshot[100:420, 80:220]
                roi_prev = prev_screenshot[100:420, 80:220]
                diff = cv2.absdiff(roi_curr, roi_prev)
                if np.mean(diff) < 3.0:
                    self.logger.info(
                        f"[御魂] 列表已复位到顶部 (尝试 {attempt + 1} 次)"
                    )
                    return
            prev_screenshot = screenshot
        self.logger.warning("[御魂] scroll_to_top 达到最大尝试次数")

    async def _scroll_down_one_page(self) -> None:
        """向下滚动约 3 个层级的高度（~255px）。

        每次滚动 3 层而非 4 层，留 1 层重叠作为安全边距。
        """
        # 手指从高y拖到低y = 列表向下滚（显示更下面的层级）
        self.adapter.swipe(_SWIPE_X, 385, _SWIPE_X, 130, _SWIPE_DUR_MS)
        await asyncio.sleep(_SCROLL_SETTLE)

    @staticmethod
    def _get_viewport_start(level: int) -> int:
        """计算要让指定层级出现在屏幕上，视口起始层应该是多少。

        视口策略：每次滚动 3 层。
        level 1-4  → viewport_start=1  (不滚动)
        level 5-7  → viewport_start=4  (滚动 1 次)
        level 8-10 → viewport_start=7  (滚动 2 次)
        """
        if level <= 4:
            return 1
        elif level <= 7:
            return 4
        else:
            return 7

    async def _scroll_to_level_visible(self, level: int) -> None:
        """先回到顶部，再滚动使指定层出现在屏幕可见区域。"""
        await self._scroll_to_top()
        await asyncio.sleep(0.5)

        vp_start = self._get_viewport_start(level)
        scroll_count = (vp_start - 1) // 3  # 1→0次, 4→1次, 7→2次

        for i in range(scroll_count):
            self.logger.info(f"[御魂] 滚动第 {i + 1}/{scroll_count} 页")
            await self._scroll_down_one_page()

    # ── 扫描与解锁 ──

    async def _scan_unlocked_count(self) -> int:
        """从顶部开始滚动扫描，返回已解锁的最高层号。"""
        await self._scroll_to_top()
        await asyncio.sleep(0.5)

        max_unlocked = 0
        current_start = 1

        for vp in range(3):  # 最多 3 个视口: start=1, 4, 7
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is None:
                self.logger.error("[御魂-扫描] 截图失败")
                break

            visible = detect_yuhun_levels(screenshot, start_index=current_start)
            for lv in visible:
                self.logger.info(
                    f"[御魂-扫描] 层级 {lv.index}: {lv.state.value}"
                )
                if lv.state != LevelState.LOCKED:
                    max_unlocked = max(max_unlocked, lv.index)

            # 如果当前视口有锁定层，后面的层肯定也是锁定的
            if any(lv.state == LevelState.LOCKED for lv in visible):
                break

            # 已经到最后一个视口
            if current_start + 3 >= _TOTAL_LEVELS:
                break

            await self._scroll_down_one_page()
            current_start += 3

        self.logger.info(f"[御魂-扫描] 最高解锁层: {max_unlocked}")
        return max_unlocked

    async def _unlock_to_target(
        self, target: int,
        manual_lineup: ManualLineupInfo | None = None,
    ) -> bool:
        """逐层解锁直到目标层级解锁。

        算法：打赢第 N 层以解锁第 N+1 层，重复到 target 层解锁。
        每次战斗完回到御魂界面后列表位置可能重置，所以每轮都从顶部重新扫描。

        Returns:
            True = target 层已解锁, False = 某层战斗失败
        """
        for attempt in range(target - 1):  # 最多需要解锁 target-1 次
            # 全扫描找第一个锁定层
            await self._scroll_to_top()
            await asyncio.sleep(0.5)

            first_locked_idx = None
            all_levels: Dict[int, YuHunLevel] = {}
            current_start = 1

            for vp in range(3):
                screenshot = self.adapter.capture(self.ui.capture_method)
                if screenshot is None:
                    self.logger.error("[御魂-解锁] 截图失败")
                    return False

                visible = detect_yuhun_levels(screenshot, start_index=current_start)
                for lv in visible:
                    all_levels[lv.index] = lv

                # 检查是否找到锁定层
                for lv in visible:
                    if lv.state == LevelState.LOCKED:
                        first_locked_idx = lv.index
                        break
                if first_locked_idx is not None:
                    break

                if current_start + 3 >= _TOTAL_LEVELS:
                    break

                await self._scroll_down_one_page()
                current_start += 3

            # 判断是否已够
            if first_locked_idx is None or first_locked_idx > target:
                self.logger.info(f"[御魂-解锁] 目标层 {target} 已解锁")
                return True

            # 打 first_locked_idx - 1 层来解锁 first_locked_idx 层
            battle_level = first_locked_idx - 1
            if battle_level < 1:
                self.logger.error("[御魂-解锁] 第 1 层就是锁定状态，无法解锁")
                return False

            self.logger.info(
                f"[御魂-解锁] 打第 {battle_level} 层以解锁第 {first_locked_idx} 层"
            )

            # 滚动到 battle_level 所在视口
            await self._scroll_to_level_visible(battle_level)
            await asyncio.sleep(0.8)

            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is None:
                self.logger.error("[御魂-解锁] 截图失败")
                return False

            vp_start = self._get_viewport_start(battle_level)
            visible = detect_yuhun_levels(screenshot, start_index=vp_start)

            battle_lv = None
            for lv in visible:
                if lv.index == battle_level:
                    battle_lv = lv
                    break

            if battle_lv is None:
                self.logger.error(
                    f"[御魂-解锁] 无法在屏幕上找到第 {battle_level} 层"
                )
                return False

            # 选中该层
            if battle_lv.state != LevelState.SELECTED:
                cx, cy = battle_lv.center
                self.adapter.adb.tap(self.adapter.cfg.adb_addr, cx, cy)
                self.logger.info(
                    f"[御魂-解锁] 选中层级 {battle_level} ({cx}, {cy})"
                )
                await asyncio.sleep(1.0)

            # 点击挑战
            clicked = await click_template(
                self.adapter, self.ui.capture_method, _TPL_TIAOZHAN,
                timeout=8.0, settle=0.5, post_delay=1.5,
                log=self.logger, label=f"御魂-解锁L{first_locked_idx}-挑战",
                popup_handler=self.ui.popup_handler,
            )
            if not clicked:
                self.logger.error(
                    f"[御魂-解锁] 第 {first_locked_idx} 层: 挑战按钮未出现"
                )
                return False

            # 执行战斗
            result = await run_battle(
                self.adapter, self.ui.capture_method,
                confirm_template=None,
                battle_timeout=180.0,
                log=self.logger,
                popup_handler=self.ui.popup_handler,
                manual_lineup=manual_lineup if attempt == 0 else None,
            )
            if result != VICTORY:
                self.logger.warning(
                    f"[御魂-解锁] 第 {first_locked_idx} 层: 战斗失败 ({result})"
                )
                return False

            self.logger.info(
                f"[御魂-解锁] 第 {first_locked_idx} 层解锁成功"
            )

            # 等待回到御魂界面
            back = await wait_for_template(
                self.adapter, self.ui.capture_method, _TPL_TAG_YUHUN,
                timeout=10.0, interval=1.0,
                log=self.logger, label=f"御魂-解锁L{first_locked_idx}-回到界面",
                popup_handler=self.ui.popup_handler,
            )
            if not back:
                self.logger.warning("[御魂-解锁] 等待回到御魂界面超时")
                await asyncio.sleep(2.0)

            # 更新解锁进度
            self._update_unlocked_count(first_locked_idx)

        return True

    # ── 数据库辅助方法 ──

    def _get_remaining_count(self) -> int:
        """从数据库读取当前账号的御魂 remaining_count。"""
        try:
            with SessionLocal() as db:
                account = db.query(GameAccount).filter(
                    GameAccount.id == self.current_account.id
                ).first()
                if not account:
                    return 0
                cfg = (account.task_config or {}).get("御魂", {})
                return cfg.get("remaining_count", 0)
        except Exception as e:
            self.logger.error(f"[御魂] 读取 remaining_count 失败: {e}")
            return 0

    def _get_target_level(self) -> int:
        """从数据库读取当前账号的御魂目标层级。"""
        try:
            with SessionLocal() as db:
                account = db.query(GameAccount).filter(
                    GameAccount.id == self.current_account.id
                ).first()
                if not account:
                    return _TOTAL_LEVELS
                cfg = (account.task_config or {}).get("御魂", {})
                return cfg.get("target_level", _TOTAL_LEVELS)
        except Exception as e:
            self.logger.error(f"[御魂] 读取 target_level 失败: {e}")
            return _TOTAL_LEVELS

    def _update_unlocked_count(self, count: int) -> None:
        """更新数据库中的御魂解锁进度。"""
        try:
            with SessionLocal() as db:
                account = db.query(GameAccount).filter(
                    GameAccount.id == self.current_account.id
                ).first()
                if not account:
                    return
                cfg = account.task_config or {}
                yuhun_cfg = cfg.get("御魂", {})
                yuhun_cfg["unlocked_count"] = count
                cfg["御魂"] = yuhun_cfg
                account.task_config = cfg
                flag_modified(account, "task_config")
                db.commit()
                self.logger.info(
                    f"[御魂] unlocked_count 更新为 {count}/{_TOTAL_LEVELS}"
                )
        except Exception as e:
            self.logger.error(f"[御魂] 更新 unlocked_count 失败: {e}")

    def _decrement_remaining_count(self) -> None:
        """每次胜利后递减 remaining_count 并持久化到数据库。"""
        try:
            with SessionLocal() as db:
                account = db.query(GameAccount).filter(
                    GameAccount.id == self.current_account.id
                ).first()
                if not account:
                    return
                cfg = account.task_config or {}
                yuhun_cfg = cfg.get("御魂", {})
                current = yuhun_cfg.get("remaining_count", 0)
                yuhun_cfg["remaining_count"] = max(0, current - 1)
                cfg["御魂"] = yuhun_cfg
                account.task_config = cfg
                flag_modified(account, "task_config")
                db.commit()
                self.logger.info(
                    f"[御魂] remaining_count: {current} → {max(0, current - 1)}"
                )
        except Exception as e:
            self.logger.error(f"[御魂] 递减 remaining_count 失败: {e}")
