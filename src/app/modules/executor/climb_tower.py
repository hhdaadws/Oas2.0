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
from ..ocr.recognize import ocr as ocr_recognize
from ..shikigami import build_manual_lineup_info
from ..ui.assets import parse_number
from ..ui.manager import UIManager
from ..vision.color_detect import detect_explore_lock
from ..vision.template import find_all_templates, match_template
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

        # 1.5 确保在庭院界面（ensure_game_ready 可能停在其他界面）
        in_tingyuan = await self.ui.ensure_ui("TINGYUAN", max_steps=6, step_timeout=3.0)
        if not in_tingyuan:
            return self._fail("导航到庭院失败")

        # 2. 按 YAML 导航到挑战界面
        nav_ok = await self._execute_navigation(cfg["navigation"])
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

        max_battles = ticket_cfg.get("max_battles", 10)
        battles_to_run = min(tickets, max_battles)
        self.logger.info(f"[爬塔] 门票={tickets}, 计划战斗={battles_to_run}次")

        if battles_to_run <= 0:
            self.logger.info("[爬塔] 门票为0，跳过战斗")
            return {
                "status": TaskStatus.SUCCEEDED,
                "tickets": 0,
                "victories": 0,
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 4. 循环战斗
        victories = await self._run_battle_loop(battles_to_run)

        self.logger.info(f"[爬塔] 完成: 胜利 {victories}/{battles_to_run}")

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
            "total_rounds": battles_to_run,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ── 导航 ──

    async def _execute_navigation(self, nav_cfg: dict) -> bool:
        """按 YAML navigation 配置执行导航步骤。"""
        steps = nav_cfg.get("steps", [])
        for i, step in enumerate(steps):
            label = step.get("label", f"导航步骤{i + 1}")
            max_retries = step.get("max_retries", 0)
            retry_actions = step.get("retry_actions", [])
            retry_delay = step.get("retry_delay", 1.0)

            ok = False
            for attempt in range(1, max_retries + 2):
                self.logger.info(
                    f"[爬塔] 导航 {i + 1}/{len(steps)}: {label}"
                    + (f" (尝试 {attempt}/{max_retries + 1})" if max_retries > 0 else "")
                )
                ok = await self._execute_step(step)
                if ok:
                    break

                if attempt <= max_retries:
                    self.logger.warning(
                        f"[爬塔] 导航步骤 {i + 1} 第 {attempt} 次失败，"
                        f"将重试 ({attempt}/{max_retries})"
                    )
                    for retry_action in retry_actions:
                        ra_label = retry_action.get("label", "重试动作")
                        self.logger.info(f"[爬塔] 重试动作: {ra_label}")
                        await self._execute_step(retry_action)
                    if retry_delay > 0:
                        await asyncio.sleep(retry_delay)

            if not ok:
                self.logger.error(
                    f"[爬塔] 导航步骤 {i + 1} 最终失败: {label}"
                    + (f" (已重试 {max_retries} 次)" if max_retries > 0 else "")
                )
                return False

        # 验证到达目标界面
        verify_tpl = nav_cfg.get("verify_template")
        if verify_tpl:
            verify_timeout = nav_cfg.get("verify_timeout", 8.0)
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
            if not m:
                self.logger.error("[爬塔] 导航后验证失败：未检测到目标界面")
                return False

        return True

    # ── 门票 OCR ──

    async def _read_tickets(self, ticket_cfg: dict) -> Optional[int]:
        """OCR 读取门票数量。"""
        roi = tuple(ticket_cfg["roi"])
        keyword = ticket_cfg.get("keyword", "")

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

            result = ocr_recognize(screenshot, roi=roi)
            raw = result.text.strip()
            self.logger.info(
                f"[爬塔] 门票 OCR: raw='{raw}' (attempt={attempt + 1})"
            )

            if keyword:
                box = result.find(keyword)
                if box:
                    value = parse_number(box.text)
                    if value is not None:
                        return value
            else:
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
        entered = await click_template(
            self.adapter,
            self.ui.capture_method,
            rent_cfg["enter_template"],
            timeout=timeout,
            settle=0.5,
            post_delay=2.0,
            log=self.logger,
            label=f"{tag} 进入租借",
            popup_handler=self.ui.popup_handler,
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
            self.logger.warning(f"{tag} 未找到任何借用按钮")
            await self._click_exit(rent_cfg)
            return False

        self.logger.info(f"{tag} 找到 {len(all_buttons)} 个借用按钮")

        # 4. 筛选同一水平线的按钮
        nearby_buttons = [
            m for m in all_buttons if abs(m.center[1] - target_y) <= y_tol
        ]
        if not nearby_buttons:
            self.logger.warning(
                f"{tag} 同一水平线无借用按钮 "
                f"(target_y={target_y}, tolerance={y_tol})"
            )
            await self._click_exit(rent_cfg)
            return False

        # 取 score 最高的
        best_button = nearby_buttons[0]  # 已按 score 降序排列
        bx, by = best_button.center
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
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is None:
                await asyncio.sleep(0.5)
                continue

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

        使用 detect_explore_lock（zhenrong_lock.png 模板），
        ROI 和阈值从 YAML lock 配置读取。

        Args:
            should_lock: True=需要锁定, False=需要解锁

        Returns:
            True 表示状态已正确，False 表示操作失败
        """
        lock_cfg = self.yaml_config["lock"]
        roi = tuple(lock_cfg["detect_roi"])
        threshold = lock_cfg.get("detect_threshold", 0.80)
        toggle_x, toggle_y = lock_cfg["toggle_pos"]
        max_retries = lock_cfg.get("max_retries", 3)
        addr = self.adapter.cfg.adb_addr

        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            self.logger.warning("[爬塔-锁定] 截图失败，无法检测锁定状态")
            return False

        lock_state = detect_explore_lock(screenshot, roi=roi, threshold=threshold)
        self.logger.info(
            f"[爬塔-锁定] locked={lock_state.locked}, "
            f"score={lock_state.score:.2f}, "
            f"期望={'锁定' if should_lock else '解锁'}"
        )

        if lock_state.locked == should_lock:
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
                new_state = detect_explore_lock(
                    screenshot, roi=roi, threshold=threshold
                )
                if new_state.locked == should_lock:
                    self.logger.info(
                        f"[爬塔-锁定] 切换成功: "
                        f"{'锁定' if should_lock else '解锁'}"
                    )
                    return True
                self.logger.warning(
                    f"[爬塔-锁定] 切换验证失败 (attempt={attempt}): "
                    f"实际={'锁定' if new_state.locked else '解锁'}"
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

    async def _run_battle_loop(self, total: int) -> int:
        """执行战斗循环，返回胜利次数。

        首次战斗: 租借式神 → 解锁阵容 → 挑战 → 配置阵容 → 战斗
        后续战斗: 锁定阵容 → 挑战 → 自动准备战斗
        """
        cfg = self.yaml_config
        rent_cfg = cfg.get("rent")
        battle_cfg = cfg["battle"]
        on_failure = cfg.get("on_failure", {})

        victories = 0

        for round_idx in range(1, total + 1):
            is_first = round_idx == 1
            self.logger.info(
                f"[爬塔] 第 {round_idx}/{total} 轮"
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
                challenge_ok = await click_template(
                    self.adapter,
                    self.ui.capture_method,
                    battle_cfg["challenge_template"],
                    timeout=8.0,
                    settle=0.5,
                    post_delay=1.5,
                    log=self.logger,
                    label="爬塔-点击挑战",
                    popup_handler=self.ui.popup_handler,
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
                challenge_ok = await click_template(
                    self.adapter,
                    self.ui.capture_method,
                    battle_cfg["challenge_template"],
                    timeout=8.0,
                    settle=0.5,
                    post_delay=1.5,
                    log=self.logger,
                    label="爬塔-点击挑战",
                    popup_handler=self.ui.popup_handler,
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
            elif result == DEFEAT:
                self.logger.warning(f"[爬塔] 第 {round_idx} 轮失败")
                if not on_failure.get("continue_on_defeat", False):
                    break
            elif result == TIMEOUT:
                self.logger.warning(f"[爬塔] 第 {round_idx} 轮超时")
                if not on_failure.get("continue_on_timeout", False):
                    break
            else:
                self.logger.error(f"[爬塔] 第 {round_idx} 轮异常结果: {result}")
                break

        return victories

    # ── 通用步骤执行 ──

    async def _execute_step(self, step: dict) -> bool:
        """执行单个 YAML 定义的操作步骤。"""
        action = step.get("action", "")
        label = step.get("label", f"步骤-{action}")

        if action == "click_template":
            return await click_template(
                self.adapter,
                self.ui.capture_method,
                step["template"],
                timeout=step.get("timeout", 8.0),
                settle=step.get("settle", 0.5),
                post_delay=step.get("post_delay", 1.5),
                threshold=step.get("threshold"),
                log=self.logger,
                label=label,
                popup_handler=self.ui.popup_handler,
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
