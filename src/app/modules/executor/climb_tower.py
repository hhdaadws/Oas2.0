"""
爬塔执行器 - YAML 驱动

根据 assets/tasks/climb_tower.yaml 配置执行：
1. 从庭院按配置导航到爬塔界面
2. OCR 读取门票数量
3. 循环调用 run_battle 执行对应次数战斗
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from ...core.constants import TaskStatus
from ...core.logger import logger
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ocr.recognize import ocr as ocr_recognize
from ..ui.assets import parse_number
from ..ui.manager import UIManager
from .base import BaseExecutor
from .battle import DEFEAT, TIMEOUT, VICTORY, run_battle
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

        # 2. 按 YAML 导航到爬塔界面
        nav_ok = await self._execute_navigation(cfg["navigation"])
        if not nav_ok:
            return self._fail("导航到爬塔界面失败")

        self.logger.info("[爬塔] 已到达爬塔界面")

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
        battle_cfg = cfg["battle"]
        victories = await self._run_battle_loop(battle_cfg, battles_to_run)

        self.logger.info(f"[爬塔] 完成: 胜利 {victories}/{battles_to_run}")
        return {
            "status": TaskStatus.SUCCEEDED if victories > 0 else TaskStatus.FAILED,
            "tickets": tickets,
            "victories": victories,
            "total_rounds": battles_to_run,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _execute_navigation(self, nav_cfg: dict) -> bool:
        """按 YAML navigation 配置执行导航步骤。"""
        steps = nav_cfg.get("steps", [])
        for i, step in enumerate(steps):
            label = step.get("label", f"导航步骤{i + 1}")
            self.logger.info(f"[爬塔] 导航 {i + 1}/{len(steps)}: {label}")
            ok = await self._execute_step(step)
            if not ok:
                self.logger.error(f"[爬塔] 导航步骤 {i + 1} 失败: {label}")
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

    async def _run_battle_loop(self, battle_cfg: dict, total: int) -> int:
        """执行战斗循环，返回胜利次数。"""
        on_failure = self.yaml_config.get("on_failure", {})
        victories = 0

        for round_idx in range(1, total + 1):
            self.logger.info(f"[爬塔] 第 {round_idx}/{total} 轮")

            # 执行战斗前步骤
            pre_ok = True
            for step in battle_cfg.get("pre_battle", []):
                if not await self._execute_step(step):
                    self.logger.error(f"[爬塔] 第 {round_idx} 轮战前步骤失败")
                    pre_ok = False
                    break
            if not pre_ok:
                break

            # 执行战斗
            result = await run_battle(
                self.adapter,
                self.ui.capture_method,
                confirm_template=battle_cfg.get("confirm_template"),
                battle_timeout=battle_cfg.get("battle_timeout", 120.0),
                log=self.logger,
                popup_handler=self.ui.popup_handler,
            )

            if result == VICTORY:
                victories += 1
                self.logger.info(f"[爬塔] 第 {round_idx} 轮胜利")
            else:
                self.logger.warning(f"[爬塔] 第 {round_idx} 轮结果: {result}")
                if result == DEFEAT and not on_failure.get(
                    "continue_on_defeat", False
                ):
                    break
                if result == TIMEOUT and not on_failure.get(
                    "continue_on_timeout", False
                ):
                    break
                if result not in (DEFEAT, TIMEOUT):
                    break

            # 执行战斗后步骤（最后一轮可选跳过）
            is_last = round_idx == total
            if is_last and battle_cfg.get("skip_post_on_last", True):
                continue
            for step in battle_cfg.get("post_battle", []):
                await self._execute_step(step)

        return victories

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
