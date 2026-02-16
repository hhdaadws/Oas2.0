"""
爬塔执行器 - YAML 驱动

根据 assets/tasks/climb_tower.yaml 配置执行完整爬塔流程：
1. 从庭院按配置导航到挑战界面
2. OCR 读取门票数量
3. 首次战斗：租借式神 → 解锁阵容 → 配置阵容 → 战斗
4. 后续战斗：锁定阵容 → 直接挑战 → 战斗
5. 循环至门票耗尽
6. 返回庭院
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from ...core.constants import TaskStatus
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ocr.recognize import ocr_digits
from ..shikigami import build_manual_lineup_info
from ..ui.assets import parse_number
from ..ui.manager import UIManager
from ..vision.template import find_all_templates, match_template
from ..vision.utils import load_image
from .base import BaseExecutor
from .battle import (
    DEFEAT,
    ERROR,
    TIMEOUT,
    VICTORY,
    ManualLineupInfo,
    run_battle,
)
from .helpers import click_template, click_text, wait_for_template
from .yaml_loader import yaml_task_loader

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# YAML 配置中的任务名
YAML_TASK_NAME = "climb_tower"

# 爬塔 UI 阶段常量（用于状态感知导航）
_CLIMB_STATE_UNKNOWN = "unknown"
_CLIMB_STATE_TINGYUAN = "tingyuan"
_CLIMB_STATE_PATA_MAIN = "pata_main"
_CLIMB_STATE_PATA_MAP = "pata_map"
_CLIMB_STATE_CHALLENGE = "challenge"


class ClimbTowerExecutor(BaseExecutor):
    """爬塔执行器 - YAML 驱动"""

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
        self.yaml_config: Optional[Dict[str, Any]] = None

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
            activity_name=(
                syscfg.activity_name or ".MainActivity" if syscfg else ".MainActivity"
            ),
        )
        return EmulatorAdapter(cfg)

    async def prepare(self, task: Task, account: GameAccount) -> bool:
        self.logger.info(f"[爬塔] 准备: account={account.login_id}")

        # 加载 YAML 配置
        self.yaml_config = yaml_task_loader.load(YAML_TASK_NAME)
        if self.yaml_config is None:
            self.logger.error("[爬塔] YAML 配置加载失败")
            return False

        if not self.yaml_config.get("enabled", False):
            self.logger.info("[爬塔] YAML 全局开关关闭，跳过")
            return False

        # 复用或新建 adapter
        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[爬塔] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error(f"[爬塔] 模拟器不存在: id={self.emulator_id}")
            return False

        self.adapter = self._build_adapter()

        ok = self.adapter.push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[爬塔] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[爬塔] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[爬塔] 执行: account={self.current_account.login_id}")
        cfg = self.yaml_config

        # 构造或复用 UIManager
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
            return self._fail("游戏就绪失败")

        # 2. 状态感知导航到挑战界面（自动检测当前阶段，跳过已完成步骤）
        nav_ok = await self._navigate_with_state_awareness(cfg["navigation"])
        if not nav_ok:
            return self._fail("导航到挑战界面失败")

        self.logger.info("[爬塔] 已到达挑战界面")

        # 3. OCR 读取门票数
        ticket_cfg = cfg["ticket"]
        tickets = await self._read_tickets(ticket_cfg)
        if tickets is None:
            fallback = ticket_cfg.get("fallback")
            if fallback is not None:
                tickets = int(fallback)
                self.logger.warning(f"[爬塔] OCR 读票失败，使用 fallback={tickets}")
            else:
                return self._fail("门票 OCR 读取失败且无 fallback")

        max_battles = ticket_cfg.get("max_battles", 999)
        self.logger.info(f"[爬塔] 初始门票={tickets}, 安全上限={max_battles}")

        if tickets <= 0:
            self.logger.info("[爬塔] 门票为0，跳过战斗")
            return {
                "status": TaskStatus.SUCCEEDED,
                "tickets": 0,
                "victories": 0,
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 4. 循环战斗（每轮结束后重新 OCR 读票，票数为 0 退出）
        victories, total_rounds = await self._run_battle_loop(
            max_battles, ticket_cfg
        )

        self.logger.info(f"[爬塔] 完成: 胜利 {victories}/{total_rounds}")

        # 5. 返回导航（可选）
        return_nav = cfg.get("return_navigation")
        if return_nav and return_nav.get("steps"):
            self.logger.info("[爬塔] 执行返回导航")
            for step in return_nav["steps"]:
                await self._execute_step(step)

        return {
            "status": TaskStatus.SUCCEEDED if victories > 0 else TaskStatus.FAILED,
            "tickets": tickets,
            "victories": victories,
            "total_rounds": total_rounds,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ── 状态感知导航 ──

    def _detect_climb_state(self) -> str:
        """截图检测当前处于爬塔流程的哪个阶段。

        按从深到浅的顺序检测，优先识别更深层界面。

        Returns:
            _CLIMB_STATE_* 常量
        """
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            self.logger.warning("[爬塔] 状态检测: 截图失败")
            return _CLIMB_STATE_UNKNOWN

        cfg = self.yaml_config

        # 优先检测最深层：挑战界面
        verify_tpl = cfg["navigation"].get("verify_template")
        if verify_tpl:
            m = match_template(screenshot, verify_tpl)
            if m:
                self.logger.info(
                    f"[爬塔] 状态检测: 已在挑战界面 (score={m.score:.3f})"
                )
                return _CLIMB_STATE_CHALLENGE

        # 地图界面
        m = match_template(
            screenshot, "assets/ui/templates/climb/pata_tag_ditu.png"
        )
        if m:
            self.logger.info(
                f"[爬塔] 状态检测: 已在地图界面 (score={m.score:.3f})"
            )
            return _CLIMB_STATE_PATA_MAP

        # 爬塔主界面
        m = match_template(
            screenshot, "assets/ui/templates/climb/pata_tag.png"
        )
        if m:
            self.logger.info(
                f"[爬塔] 状态检测: 已在爬塔主界面 (score={m.score:.3f})"
            )
            return _CLIMB_STATE_PATA_MAIN

        # 用 UIManager 检测是否在庭院
        detect_result = self.ui.detect_ui(screenshot)
        if detect_result.ui == "TINGYUAN":
            self.logger.info("[爬塔] 状态检测: 在庭院")
            return _CLIMB_STATE_TINGYUAN

        self.logger.info(
            f"[爬塔] 状态检测: 未知 (UI={detect_result.ui})"
        )
        return _CLIMB_STATE_UNKNOWN

    def _steps_to_skip(self, state: str) -> int:
        """根据检测到的阶段，返回应跳过的 YAML 导航步骤数。

        YAML 步骤映射 (climb_tower.yaml 的 5 步配置):
          步骤0: click pata_rukou     → 进入爬塔主界面
          步骤1: wait  pata_tag       → 验证爬塔主界面
          步骤2: click pata_zhandou   → 进入地图
          步骤3: wait  pata_tag_ditu  → 验证地图界面
          步骤4: click pata_guaiwu    → 点击怪物进入挑战
        """
        if state == _CLIMB_STATE_PATA_MAIN:
            return 2  # 跳过入口+验证主界面，从进入地图开始
        elif state == _CLIMB_STATE_PATA_MAP:
            return 4  # 跳过前 4 步，只执行点击怪物
        elif state == _CLIMB_STATE_CHALLENGE:
            return 5  # 全部跳过
        return 0  # 庭院或未知，从头开始

    async def _try_back_to_tingyuan(self) -> bool:
        """尝试从当前状态返回庭院。

        策略:
          1. detect_ui 检查是否已在庭院
          2. 已知 UI → ensure_ui 走图导航
          3. 未知 UI → 连续点击 back/exit 最多 5 次
          4. 最终 ensure_ui 兜底
        """
        detect_result = self.ui.detect_ui()
        if detect_result.ui == "TINGYUAN":
            return True

        if detect_result.ui != "UNKNOWN":
            ok = await self.ui.ensure_ui(
                "TINGYUAN", max_steps=6, step_timeout=3.0
            )
            if ok:
                return True

        # 未知界面：连续点击 back / exit
        for i in range(5):
            clicked = await click_template(
                self.adapter,
                self.ui.capture_method,
                "assets/ui/templates/back.png",
                timeout=3.0,
                settle=0.3,
                post_delay=1.5,
                log=self.logger,
                label=f"爬塔-回退back({i + 1}/5)",
                popup_handler=self.ui.popup_handler,
            )
            if not clicked:
                await click_template(
                    self.adapter,
                    self.ui.capture_method,
                    "assets/ui/templates/exit.png",
                    timeout=2.0,
                    settle=0.3,
                    post_delay=1.5,
                    log=self.logger,
                    label=f"爬塔-回退exit({i + 1}/5)",
                    popup_handler=self.ui.popup_handler,
                )

            detect_result = self.ui.detect_ui()
            if detect_result.ui == "TINGYUAN":
                return True

        # 最终兜底
        return await self.ui.ensure_ui(
            "TINGYUAN", max_steps=6, step_timeout=3.0
        )

    async def _execute_remaining_steps(
        self, steps: list, step_offset: int = 0
    ) -> bool:
        """从指定位置开始执行导航步骤（复用原有重试逻辑）。

        Args:
            steps: 要执行的步骤列表
            step_offset: 步骤编号偏移（用于日志）
        """
        total = len(steps) + step_offset
        for i, step in enumerate(steps):
            actual_idx = i + step_offset
            label = step.get("label", f"导航步骤{actual_idx + 1}")
            max_retries = step.get("max_retries", 0)
            retry_actions = step.get("retry_actions", [])
            retry_delay = step.get("retry_delay", 1.0)

            ok = False
            for attempt in range(1, max_retries + 2):
                self.logger.info(
                    f"[爬塔] 导航 {actual_idx + 1}/{total}: {label}"
                    + (
                        f" (尝试 {attempt}/{max_retries + 1})"
                        if max_retries > 0
                        else ""
                    )
                )
                ok = await self._execute_step(step)
                if ok:
                    break

                if attempt <= max_retries:
                    self.logger.warning(
                        f"[爬塔] 步骤 {actual_idx + 1} 第 {attempt} 次失败，重试"
                    )
                    for retry_action in retry_actions:
                        ra_label = retry_action.get("label", "重试动作")
                        self.logger.info(f"[爬塔] 重试动作: {ra_label}")
                        await self._execute_step(retry_action)
                    if retry_delay > 0:
                        await asyncio.sleep(retry_delay)

            if not ok:
                self.logger.error(
                    f"[爬塔] 步骤 {actual_idx + 1} 最终失败: {label}"
                    + (f" (已重试 {max_retries} 次)" if max_retries > 0 else "")
                )
                return False

        return True

    async def _navigate_with_state_awareness(
        self, nav_cfg: dict, max_retries: int = 2
    ) -> bool:
        """状态感知导航：检测当前阶段，跳过已完成步骤。

        Args:
            nav_cfg: YAML navigation 配置
            max_retries: 整体导航失败时的重试次数
        """
        for attempt in range(max_retries + 1):
            state = self._detect_climb_state()

            if state == _CLIMB_STATE_CHALLENGE:
                self.logger.info("[爬塔] 已在挑战界面，跳过导航")
                return True

            skip_count = self._steps_to_skip(state)

            if state == _CLIMB_STATE_UNKNOWN:
                self.logger.info("[爬塔] 未知状态，先回庭院")
                back_ok = await self._try_back_to_tingyuan()
                if not back_ok:
                    self.logger.warning(
                        f"[爬塔] 回庭院失败 (attempt={attempt + 1}/{max_retries + 1})"
                    )
                    continue
                skip_count = 0

            # 执行剩余导航步骤
            steps = nav_cfg.get("steps", [])
            remaining_steps = steps[skip_count:]

            if remaining_steps:
                self.logger.info(
                    f"[爬塔] 从第 {skip_count + 1} 步开始导航 "
                    f"(跳过 {skip_count} 步, 剩余 {len(remaining_steps)} 步)"
                )
                nav_ok = await self._execute_remaining_steps(
                    remaining_steps, step_offset=skip_count
                )
            else:
                nav_ok = True

            # 验证到达目标界面（无论导航步骤是否全部成功都要检查，
            # 因为中间步骤失败可能恰恰是因为已经跳过了该步骤到达了更深层界面）
            verify_tpl = nav_cfg.get("verify_template")
            if verify_tpl:
                # 步骤全部成功时用完整超时，步骤失败时缩短超时（快速确认）
                verify_timeout = (
                    nav_cfg.get("verify_timeout", 8.0) if nav_ok else 3.0
                )
                m = await wait_for_template(
                    self.adapter,
                    self.ui.capture_method,
                    verify_tpl,
                    timeout=verify_timeout,
                    interval=1.0,
                    log=self.logger,
                    label="爬塔-验证界面",
                    popup_handler=self.ui.popup_handler,
                )
                if m:
                    return True

                self.logger.warning(
                    f"[爬塔] 导航后验证失败 "
                    f"(attempt={attempt + 1}/{max_retries + 1})"
                )
                await self._try_back_to_tingyuan()
                continue

            return True

        self.logger.error("[爬塔] 状态感知导航最终失败")
        return False

    async def _ensure_at_challenge(self) -> bool:
        """确保当前处于挑战界面。

        战斗结束后可能因异常停在其他位置，
        本方法检测当前状态并在需要时重新导航。
        """
        cfg = self.yaml_config
        verify_tpl = cfg["navigation"].get("verify_template")
        if not verify_tpl:
            return True

        # 快速检测
        m = await wait_for_template(
            self.adapter,
            self.ui.capture_method,
            verify_tpl,
            timeout=3.0,
            interval=0.5,
            log=self.logger,
            label="爬塔-检查挑战界面",
            popup_handler=self.ui.popup_handler,
        )
        if m:
            return True

        # 不在挑战界面，尝试恢复
        self.logger.warning("[爬塔] 未检测到挑战界面，尝试恢复导航")
        return await self._navigate_with_state_awareness(
            cfg["navigation"], max_retries=1
        )

    # ── 门票 OCR ──

    async def _read_tickets(self, ticket_cfg: dict) -> Optional[int]:
        """OCR 读取门票数量（使用 ddddocr 纯数字识别）。"""
        roi = tuple(ticket_cfg["roi"])

        for attempt in range(3):
            await asyncio.sleep(0.5)
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is None:
                self.logger.warning(
                    f"[爬塔] 门票 OCR 截图失败 (attempt={attempt + 1})"
                )
                continue

            # 检查弹窗
            if self.ui.popup_handler:
                dismissed = await self.ui.popup_handler.check_and_dismiss(screenshot)
                if dismissed > 0:
                    continue

            result = ocr_digits(screenshot, roi=roi)
            raw = result.text.strip()
            self.logger.info(
                f"[爬塔] 门票 OCR: raw='{raw}' (attempt={attempt + 1})"
            )

            value = parse_number(raw)
            if value is not None:
                return value

        return None

    # ── 租借式神 ──

    async def _rent_shikigami(self, rent_cfg: dict) -> bool:
        """在挑战界面进入租借界面，找到并借用目标式神。

        流程:
            1. 点击 enter_template 进入租借界面
            2. 截图 → 找到 shikigami_template 的位置 (目标 Y)
            3. find_all_templates 找所有 borrow_button
            4. 筛选 Y 坐标在 target_y ± y_tolerance 内的按钮
            5. 点击最近的借用按钮
            6. 验证 borrow_button 在该位置消失
            7. 点击 exit_template 返回挑战界面
        """
        tag = "[爬塔-租借]"
        timeout = rent_cfg.get("timeout", 8.0)
        y_tol = rent_cfg.get("y_tolerance", 30)

        # 1. 进入租借界面
        entered = await self._rapid_click_template(
            rent_cfg["enter_template"],
            timeout=timeout,
            settle=0.5,
            post_delay=2.0,
            label=f"{tag} 进入租借",
        )
        if not entered:
            self.logger.warning(f"{tag} 未找到租借入口，跳过租借")
            return False

        # 2. 找到目标式神位置
        await asyncio.sleep(1.0)
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            self.logger.warning(f"{tag} 截图失败")
            return False

        shikigami_match = match_template(
            screenshot, rent_cfg["shikigami_template"], threshold=0.80
        )
        if not shikigami_match:
            self.logger.warning(f"{tag} 未找到目标式神模板")
            # 退出租借界面
            await self._click_exit(rent_cfg)
            return False

        target_y = shikigami_match.center[1]
        self.logger.info(
            f"{tag} 找到目标式神 center=({shikigami_match.center[0]}, {target_y})"
            f" score={shikigami_match.score:.3f}"
        )

        # 3. 找所有借用按钮
        all_buttons = find_all_templates(
            screenshot, rent_cfg["borrow_button"], threshold=0.80
        )
        if not all_buttons:
            self.logger.info(f"{tag} 未找到任何借用按钮，推断已全部借用")
            await self._click_exit(rent_cfg)
            return True

        self.logger.info(f"{tag} 找到 {len(all_buttons)} 个借用按钮")

        # 4. 筛选同一水平线的按钮
        nearby_buttons = [
            m for m in all_buttons if abs(m.center[1] - target_y) <= y_tol
        ]
        if not nearby_buttons:
            self.logger.info(
                f"{tag} 同一水平线无借用按钮，推断已借用 "
                f"(target_y={target_y}, tolerance={y_tol})"
            )
            await self._click_exit(rent_cfg)
            return True

        # 取 score 最高的
        best_button = nearby_buttons[0]  # 已按 score 降序排列
        bx, by = best_button.random_point()
        self.logger.info(
            f"{tag} 选中借用按钮 ({bx}, {by}) score={best_button.score:.3f}"
        )

        # 5. 点击借用按钮
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, bx, by)
        await asyncio.sleep(1.5)

        # 6. 验证借用成功（borrow_button 在同一位置消失）
        verify_roi = (
            best_button.x - 5,
            best_button.y - 5,
            best_button.w + 10,
            best_button.h + 10,
        )
        for verify_attempt in range(3):
            screenshot_bytes = self.adapter.capture(self.ui.capture_method)
            if screenshot_bytes is None:
                await asyncio.sleep(0.5)
                continue
            screenshot = load_image(screenshot_bytes)

            # 在原按钮位置裁剪检测
            rx, ry, rw, rh = verify_roi
            # 确保 ROI 不越界
            img_h, img_w = screenshot.shape[:2]
            rx = max(0, rx)
            ry = max(0, ry)
            rw = min(rw, img_w - rx)
            rh = min(rh, img_h - ry)
            crop = screenshot[ry : ry + rh, rx : rx + rw]

            m_check = match_template(crop, rent_cfg["borrow_button"], threshold=0.75)
            if m_check is None:
                self.logger.info(f"{tag} 借用成功（按钮已消失）")
                break
            else:
                self.logger.info(
                    f"{tag} 按钮仍在 score={m_check.score:.3f} "
                    f"(verify attempt={verify_attempt + 1})"
                )
                # 可能需要再次点击
                if verify_attempt < 2:
                    self.adapter.adb.tap(self.adapter.cfg.adb_addr, bx, by)
                    await asyncio.sleep(1.0)
        else:
            self.logger.warning(f"{tag} 借用验证失败，继续流程")

        # 7. 退出租借界面
        await self._click_exit(rent_cfg)
        return True

    async def _click_exit(self, rent_cfg: dict) -> None:
        """点击退出按钮返回挑战界面。"""
        await click_template(
            self.adapter,
            self.ui.capture_method,
            rent_cfg["exit_template"],
            timeout=rent_cfg.get("timeout", 8.0),
            settle=0.5,
            post_delay=1.5,
            log=self.logger,
            label="[爬塔-租借] 退出",
            popup_handler=self.ui.popup_handler,
        )

    # ── 阵容锁定管理 ──

    async def _ensure_lock_state(self, should_lock: bool) -> bool:
        """确保阵容锁定状态与期望一致。

        使用爬塔专用 pata_lock.png 模板检测锁定状态，
        ROI 和阈值从 YAML lock 配置读取。

        Args:
            should_lock: True=需要锁定, False=需要解锁

        Returns:
            True 表示状态已正确，False 表示操作失败
        """
        lock_cfg = self.yaml_config["lock"]
        roi = tuple(lock_cfg["detect_roi"])
        threshold = lock_cfg.get("detect_threshold", 0.80)
        lock_tpl = lock_cfg.get(
            "lock_template", "assets/ui/templates/climb/pata_lock.png"
        )
        toggle_x, toggle_y = lock_cfg["toggle_pos"]
        max_retries = lock_cfg.get("max_retries", 3)
        addr = self.adapter.cfg.adb_addr

        def _check_locked(raw_screenshot) -> tuple:
            """用 pata_lock.png 模板检测是否锁定。"""
            img = load_image(raw_screenshot)
            rx, ry, rw, rh = roi
            search_img = img[ry : ry + rh, rx : rx + rw]
            m = match_template(search_img, lock_tpl, threshold=threshold)
            if m is not None:
                return True, m.score
            # 未匹配时获取实际分数用于调试
            m_any = match_template(search_img, lock_tpl, threshold=0.0)
            score = m_any.score if m_any else 0.0
            return False, score

        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            self.logger.warning("[爬塔-锁定] 截图失败，无法检测锁定状态")
            return False

        locked, score = _check_locked(screenshot)
        self.logger.info(
            f"[爬塔-锁定] locked={locked}, score={score:.2f}, "
            f"期望={'锁定' if should_lock else '解锁'}"
        )

        if locked == should_lock:
            return True

        # 需要切换
        for attempt in range(1, max_retries + 1):
            self.adapter.adb.tap(addr, toggle_x, toggle_y)
            self.logger.info(
                f"[爬塔-锁定] 点击切换 ({toggle_x}, {toggle_y}) "
                f"(attempt={attempt}/{max_retries})"
            )
            await asyncio.sleep(1.0)

            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is not None:
                new_locked, new_score = _check_locked(screenshot)
                if new_locked == should_lock:
                    self.logger.info(
                        f"[爬塔-锁定] 切换成功: "
                        f"{'锁定' if should_lock else '解锁'}"
                    )
                    return True
                self.logger.warning(
                    f"[爬塔-锁定] 切换验证失败 (attempt={attempt}): "
                    f"score={new_score:.2f}"
                )

        self.logger.error("[爬塔-锁定] 锁定状态切换失败")
        return False

    # ── 首次战斗阵容配置 ──

    def _build_climb_manual_lineup(self) -> ManualLineupInfo:
        """将 YAML first_battle_lineup 配置转为 ManualLineupInfo。

        租借式神模板从 YAML 读取，座敷童子模板从 shikigami 模块获取。
        """
        lineup_cfg = self.yaml_config.get("first_battle_lineup", {})
        shangzhen = lineup_cfg.get("shangzhen_template", "")
        pos1 = tuple(lineup_cfg.get("lineup_pos_1", [127, 281]))
        pos2 = tuple(lineup_cfg.get("lineup_pos_2", [297, 295]))
        config_btn = tuple(lineup_cfg.get("config_btn", [462, 446]))

        # 座敷模板从 shikigami 模块获取（根据觉醒状态选择）
        zuofu_template = None
        shikigami_cfg = self.current_account.shikigami_config or {}
        lineup_data = build_manual_lineup_info(shikigami_cfg)
        if lineup_data:
            zuofu_template = lineup_data.get("zuofu_template")

        return ManualLineupInfo(
            rental_shikigami=[(shangzhen, "爬塔式神", 6)] if shangzhen else [],
            zuofu_template=zuofu_template,
            config_btn=config_btn,
            lineup_pos_1=pos1,
            lineup_pos_2=pos2,
        )

    # ── 战斗循环 ──

    async def _run_battle_loop(
        self, max_rounds: int, ticket_cfg: dict
    ) -> tuple[int, int]:
        """执行战斗循环，每轮结束后重新 OCR 读票，票数为 0 退出。

        首次战斗: 租借式神 → 解锁阵容 → 挑战 → 配置阵容 → 战斗
        后续战斗: 锁定阵容 → 挑战 → 自动准备战斗

        Args:
            max_rounds: 安全上限轮次（防止无限循环）
            ticket_cfg: 门票 OCR 配置（用于每轮重新读票）

        Returns:
            (victories, total_rounds) 胜利次数和实际执行轮次数
        """
        cfg = self.yaml_config
        rent_cfg = cfg.get("rent")
        battle_cfg = cfg["battle"]
        on_failure = cfg.get("on_failure", {})

        victories = 0
        round_idx = 0

        while round_idx < max_rounds:
            round_idx += 1
            is_first = round_idx == 1
            self.logger.info(
                f"[爬塔] 第 {round_idx} 轮"
                f" ({'首次' if is_first else '后续'})"
            )

            if is_first:
                # 首次战斗流程
                # 1. 租借式神
                if rent_cfg:
                    rent_ok = await self._rent_shikigami(rent_cfg)
                    if not rent_ok:
                        self.logger.warning("[爬塔] 租借式神失败，继续战斗流程")

                # 2. 解锁阵容
                await self._ensure_lock_state(should_lock=False)

                # 3. 点击挑战
                challenge_ok = await self._rapid_click_template(
                    battle_cfg["challenge_template"],
                    timeout=8.0,
                    settle=0.5,
                    post_delay=1.5,
                    label="爬塔-点击挑战",
                )
                if not challenge_ok:
                    self.logger.error("[爬塔] 点击挑战按钮失败")
                    break

                # 4. 带阵容配置的战斗
                manual_lineup = self._build_climb_manual_lineup()
                result = await run_battle(
                    self.adapter,
                    self.ui.capture_method,
                    battle_timeout=battle_cfg.get("battle_timeout", 120.0),
                    log=self.logger,
                    popup_handler=self.ui.popup_handler,
                    manual_lineup=manual_lineup,
                )
            else:
                # 后续战斗流程
                # 1. 锁定阵容
                await self._ensure_lock_state(should_lock=True)

                # 2. 点击挑战
                challenge_ok = await self._rapid_click_template(
                    battle_cfg["challenge_template"],
                    timeout=8.0,
                    settle=0.5,
                    post_delay=1.5,
                    label="爬塔-点击挑战",
                )
                if not challenge_ok:
                    self.logger.error("[爬塔] 点击挑战按钮失败")
                    break

                # 3. 直接战斗（阵容已锁定，自动准备）
                result = await run_battle(
                    self.adapter,
                    self.ui.capture_method,
                    battle_timeout=battle_cfg.get("battle_timeout", 120.0),
                    log=self.logger,
                    popup_handler=self.ui.popup_handler,
                )

            # 处理战斗结果
            if result == VICTORY:
                victories += 1
                self.logger.info(f"[爬塔] 第 {round_idx} 轮胜利")
                # 确保在挑战界面后重新 OCR 读票
                if not await self._ensure_at_challenge():
                    self.logger.error("[爬塔] 胜利后恢复到挑战界面失败")
                    break
                remaining = await self._read_tickets(ticket_cfg)
                if remaining is not None:
                    self.logger.info(f"[爬塔] 剩余门票={remaining}")
                    if remaining <= 0:
                        self.logger.info("[爬塔] 门票已耗尽，结束战斗循环")
                        break
                else:
                    self.logger.warning("[爬塔] OCR 读票失败，继续下一轮")
            elif result == DEFEAT:
                self.logger.warning(f"[爬塔] 第 {round_idx} 轮失败")
                if not on_failure.get("continue_on_defeat", False):
                    break
                # 继续前确保在挑战界面
                if not await self._ensure_at_challenge():
                    self.logger.error("[爬塔] 战败后恢复到挑战界面失败")
                    break
            elif result == TIMEOUT:
                self.logger.warning(f"[爬塔] 第 {round_idx} 轮超时")
                if not on_failure.get("continue_on_timeout", False):
                    break
                # 继续前确保在挑战界面
                if not await self._ensure_at_challenge():
                    self.logger.error("[爬塔] 超时后恢复到挑战界面失败")
                    break
            else:
                self.logger.error(f"[爬塔] 第 {round_idx} 轮异常结果: {result}")
                # 尝试恢复到挑战界面
                if not await self._ensure_at_challenge():
                    self.logger.error("[爬塔] 异常后恢复到挑战界面失败")
                    break
                self.logger.info("[爬塔] 异常后恢复成功，继续战斗循环")

        return victories, round_idx

    # ── 快速多次检测+点击 ──

    async def _rapid_click_template(
        self,
        template: str,
        *,
        timeout: float = 8.0,
        settle: float = 0.3,
        post_delay: float = 0.8,
        threshold: float | None = None,
        label: str = "",
        rapid_count: int = 5,
        rapid_interval: float = 0.3,
    ) -> bool:
        """快速多次截图检测+点击模式（爬塔专用）。

        与标准 click_template 的区别：检测到模板后不是单次点击，
        而是快速连续检测 rapid_count 次，每次检测到就点击，确保点击生效。

        流程:
            Phase 1: wait_for_template(timeout) - 正常等待模板出现
            Phase 2: settle 等待（仅 Phase 1 找到模板时）
            Phase 3: rapid_count 次快速截图→检测→点击循环
                     始终执行全部次数，用于确认/补充点击
            Phase 4: post_delay（仅至少成功点击一次时）

        Returns:
            True 表示至少点击了一次，False 表示从未检测到模板。
        """
        tag = f"[{label}] " if label else ""
        addr = self.adapter.cfg.adb_addr
        kwargs = {"threshold": threshold} if threshold is not None else {}

        # Phase 1: 等待模板出现
        m = await wait_for_template(
            self.adapter,
            self.ui.capture_method,
            template,
            timeout=timeout,
            interval=0.5,
            threshold=threshold,
            log=self.logger,
            label=label,
            popup_handler=self.ui.popup_handler,
        )

        # Phase 2: settle（仅模板找到时）
        if m and settle > 0:
            await asyncio.sleep(settle)

        # Phase 3: 快速连续检测 + 点击
        clicked_count = 0
        for i in range(rapid_count):
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is None:
                await asyncio.sleep(rapid_interval)
                continue

            # 弹窗检查
            if self.ui.popup_handler:
                dismissed = await self.ui.popup_handler.check_and_dismiss(
                    screenshot
                )
                if dismissed > 0:
                    await asyncio.sleep(rapid_interval)
                    continue

            rm = match_template(screenshot, template, **kwargs)
            if rm:
                cx, cy = rm.random_point()
                self.adapter.adb.tap(addr, cx, cy)
                clicked_count += 1
                self.logger.info(
                    f"{tag}快速点击 ({cx}, {cy}) "
                    f"(cycle={i + 1}/{rapid_count}, "
                    f"total_clicks={clicked_count}, "
                    f"score={rm.score:.3f})"
                )

            await asyncio.sleep(rapid_interval)

        if clicked_count > 0:
            self.logger.info(
                f"{tag}快速检测完成, 共点击{clicked_count}次"
            )
        else:
            self.logger.warning(
                f"{tag}快速检测{rapid_count}次均未找到模板"
            )

        # Phase 4: post_delay（仅点击成功时）
        if clicked_count > 0 and post_delay > 0:
            await asyncio.sleep(post_delay)

        return clicked_count > 0

    # ── 通用步骤执行 ──

    async def _execute_step(self, step: dict) -> bool:
        """执行单个 YAML 定义的操作步骤。"""
        action = step.get("action", "")
        label = step.get("label", f"步骤-{action}")

        if action == "click_template":
            return await self._rapid_click_template(
                step["template"],
                timeout=step.get("timeout", 8.0),
                settle=step.get("settle", 0.5),
                post_delay=step.get("post_delay", 1.5),
                threshold=step.get("threshold"),
                label=label,
                rapid_count=step.get("rapid_count", 5),
                rapid_interval=step.get("rapid_interval", 0.3),
            )

        if action == "click_text":
            roi = tuple(step["roi"]) if "roi" in step else None
            return await click_text(
                self.adapter,
                self.ui.capture_method,
                step["keyword"],
                roi=roi,
                timeout=step.get("timeout", 8.0),
                settle=step.get("settle", 0.5),
                post_delay=step.get("post_delay", 1.5),
                log=self.logger,
                label=label,
                popup_handler=self.ui.popup_handler,
            )

        if action == "wait_for_template":
            m = await wait_for_template(
                self.adapter,
                self.ui.capture_method,
                step["template"],
                timeout=step.get("timeout", 8.0),
                interval=step.get("interval", 1.0),
                log=self.logger,
                label=label,
                popup_handler=self.ui.popup_handler,
            )
            return m is not None

        if action == "swipe":
            params = step.get("params", [480, 350, 480, 150, 500])
            self.adapter.adb.swipe(
                self.adapter.cfg.adb_addr,
                params[0],
                params[1],
                params[2],
                params[3],
                params[4],
            )
            post_delay = step.get("post_delay", 1.5)
            await asyncio.sleep(post_delay)
            return True

        if action == "tap":
            x, y = step["x"], step["y"]
            self.adapter.adb.tap(self.adapter.cfg.adb_addr, x, y)
            post_delay = step.get("post_delay", 1.0)
            await asyncio.sleep(post_delay)
            return True

        if action == "sleep":
            await asyncio.sleep(step.get("seconds", 1.0))
            return True

        self.logger.error(f"[爬塔] 未知 action 类型: {action}")
        return False

    # ── 工具方法 ──

    def _fail(self, error: str) -> Dict[str, Any]:
        """构造失败结果。"""
        self.logger.error(f"[爬塔] {error}")
        return {
            "status": TaskStatus.FAILED,
            "error": error,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[爬塔] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[爬塔] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[爬塔] 停止游戏失败: {e}")
