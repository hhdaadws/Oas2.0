"""
弥助执行器 - 推送登录数据、启动游戏、执行弥助操作
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus, TaskType
from ...core.logger import logger
from ...core.timeutils import format_beijing_time, get_next_fixed_time, now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ui.manager import UIManager
from .base import BaseExecutor

# 弥助固定执行时间点
MIZHU_FIXED_TIMES = ["00:00", "06:00", "12:00", "18:00"]
# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"


class DelegateHelpExecutor(BaseExecutor):
    """弥助执行器"""

    def __init__(self, worker_id: int, emulator_id: int,
                 emulator_row: Optional[Emulator] = None,
                 system_config: Optional[SystemConfig] = None):
        super().__init__(worker_id=worker_id, emulator_id=emulator_id)
        self.emulator_row = emulator_row
        self.system_config = system_config
        self.adapter: Optional[EmulatorAdapter] = None
        self.ui: Optional[UIManager] = None

    def _build_adapter(self) -> EmulatorAdapter:
        """根据 emulator_row 和 system_config 构造 EmulatorAdapter"""
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
        """
        准备阶段：
        1. 构造 EmulatorAdapter（或复用 shared_adapter）
        2. push 登录数据到模拟器（批次中非首个任务跳过）
        """
        self.logger.info(f"[弥助] 准备: account={account.login_id}")

        # 批次复用：若 Worker 传入了 shared_adapter，直接复用，跳过 push
        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[弥助] 复用 shared_adapter，跳过 push 登录数据")
            return True

        # 若未传入 emulator_row，从 DB 重新加载
        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error("[弥助] 模拟器不存在: id={}", self.emulator_id)
            return False

        self.adapter = self._build_adapter()

        # push 登录数据
        ok = self.adapter.push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[弥助] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[弥助] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        """
        执行阶段：
        1. 根据游戏状态进行 启动/重启/UI跳转，确保进入庭院
        2. 从庭院导航到委派界面（占位）
        3. 更新 next_time
        """
        self.logger.info(f"[弥助] 执行: account={self.current_account.login_id}")

        # 构造 UIManager（或复用 shared_ui）
        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = (
                (self.system_config.capture_method if self.system_config else None)
                or "adb"
            )
            self.ui = UIManager(self.adapter, capture_method=capture_method)

        # 统一游戏就绪流程：未启动则启动；已启动则优先 UI 跳转；异常则重启
        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            self.logger.error("[弥助] 游戏就绪失败，未进入庭院")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # ---- 资源预检：弥助需要 300 体力 ----
        from .resource_check import check_resources

        satisfied, read_values = await check_resources(
            self.ui, TaskType.DELEGATE_HELP, self.current_account.id,
        )
        if not satisfied:
            stamina_val = read_values.get("stamina", "?")
            self.logger.info(f"[弥助] 体力不足 ({stamina_val} < 300)，跳过并更新 next_time")
            self._update_next_time()
            return {
                "status": TaskStatus.SKIPPED,
                "reason": f"体力不足: {stamina_val}",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 弥助占位：导航到委派界面即视为成功
        self.logger.info("[弥助] 开始导航至委派界面")

        in_weipai = await self.ui.ensure_ui("WEIPAI", max_steps=6, step_timeout=1.5)
        if not in_weipai:
            self.logger.error("[弥助] 导航到委派界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航委派界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info("[弥助] 已到达委派界面，开始弥助操作")

        # 领取已完成委派奖励（如有）
        await self._collect_completed_rewards()

        # --- 弥助操作逻辑 ---
        from .helpers import click_template

        # 步骤1: 点击弥助按钮（verify_gone 确保点击生效）
        clicked = await click_template(
            self.adapter, self.ui.capture_method,
            "assets/ui/templates/mizhu.png",
            verify_gone=True, max_clicks=3,
            log=self.logger, label="弥助按钮",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked:
            self.logger.info("[弥助] 未检测到弥助按钮，跳过本次执行，等待下一个时间窗口")
            self._update_next_time()
            return {
                "status": TaskStatus.SKIPPED,
                "reason": "未检测到弥助按钮",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 步骤2: 等待并点击跳过按钮
        await click_template(
            self.adapter, self.ui.capture_method,
            "assets/ui/templates/tiaoguo.png",
            log=self.logger, label="跳过",
            popup_handler=self.ui.popup_handler,
        )

        # 步骤3: 等待并点击委派确认
        await click_template(
            self.adapter, self.ui.capture_method,
            "assets/ui/templates/weipai_sure.png",
            log=self.logger, label="委派确认",
            popup_handler=self.ui.popup_handler,
        )

        # 步骤4: 等待并点击一键选择
        await click_template(
            self.adapter, self.ui.capture_method,
            "assets/ui/templates/yijianxuanze.png",
            log=self.logger, label="一键选择",
            popup_handler=self.ui.popup_handler,
        )

        # 步骤5: 等待并点击出发
        await click_template(
            self.adapter, self.ui.capture_method,
            "assets/ui/templates/chufa.png",
            log=self.logger, label="出发",
            popup_handler=self.ui.popup_handler,
        )

        self.logger.info("[弥助] 弥助操作完成")

        # 更新 task_config 中的弥助 next_time
        self._update_next_time()

        return {
            "status": TaskStatus.SUCCEEDED,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _update_next_time(self) -> None:
        """更新弥助的 next_time 到下一个 00:00/06:00/12:00/18:00"""
        try:
            bj_now = format_beijing_time(now_beijing())
            next_time = get_next_fixed_time(bj_now, MIZHU_FIXED_TIMES)

            with SessionLocal() as db:
                account = db.query(GameAccount).filter(
                    GameAccount.id == self.current_account.id
                ).first()
                if account:
                    cfg = account.task_config or {}
                    mizhu = cfg.get("弥助", {})
                    mizhu["next_time"] = next_time
                    cfg["弥助"] = mizhu
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(f"[弥助] next_time 更新为 {next_time}")
        except Exception as e:
            self.logger.error(f"[弥助] 更新 next_time 失败: {e}")

    async def _collect_completed_rewards(self) -> None:
        """检测并领取已完成的委派任务奖励"""
        from ..vision.template import match_template
        from ..vision.utils import random_point_in_circle

        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            return

        # 弹窗检测
        if self.ui:
            if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
                screenshot = self.adapter.capture(self.ui.capture_method)
                if screenshot is None:
                    return

        result = match_template(screenshot, "assets/ui/templates/wancheng.png")
        if not result:
            self.logger.info("[弥助] 未检测到已完成委派，跳过奖励领取")
            return

        # 点击 wancheng 中心下方 20px
        cx, cy = result.center
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, cx, cy + 20)
        self.logger.info(f"[弥助] 检测到已完成委派，点击 ({cx}, {cy + 20})")
        await asyncio.sleep(1.5)

        # 循环点击屏幕中间偏下，等待 wanchengrenwu.png 出现（对话结束标志）
        for _ in range(20):
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is not None:
                # 弹窗检测
                if self.ui and await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
                    screenshot = self.adapter.capture(self.ui.capture_method)
                if screenshot is not None:
                    wancheng_renwu = match_template(screenshot, "assets/ui/templates/wanchengrenwu.png")
                if wancheng_renwu:
                    self.logger.info("[弥助] 检测到完成任务弹窗，对话结束")
                    break
            rx, ry = random_point_in_circle(480, 400, 60)
            self.adapter.adb.tap(self.adapter.cfg.adb_addr, rx, ry)
            await asyncio.sleep(1.0)

        # 点击 wanchengrenwu
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is not None:
            # 弹窗检测
            if self.ui and await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
                screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is not None:
            wr = match_template(screenshot, "assets/ui/templates/wanchengrenwu.png")
            if wr:
                wrx, wry = wr.center
                self.adapter.adb.tap(self.adapter.cfg.adb_addr, wrx, wry)
                self.logger.info(f"[弥助] 点击完成任务按钮 ({wrx}, {wry})")
                await asyncio.sleep(1.5)

        # 等待 jiangli.png 出现并关闭奖励弹窗
        for _ in range(10):
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is not None:
                # 弹窗检测
                if self.ui and await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
                    screenshot = self.adapter.capture(self.ui.capture_method)
                if screenshot is not None:
                    jiangli = match_template(screenshot, "assets/ui/templates/jiangli.png")
                if jiangli:
                    self.logger.info("[弥助] 检测到奖励弹窗")
                    break
            await asyncio.sleep(1.0)

        await asyncio.sleep(0.5)
        close_x, close_y = random_point_in_circle(20, 20, 20)
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, close_x, close_y)
        self.logger.info(f"[弥助] 点击 ({close_x}, {close_y}) 关闭奖励弹窗")
        await asyncio.sleep(1.0)

    async def cleanup(self) -> None:
        """停止游戏（批次中非最后一个任务跳过）"""
        if self.skip_cleanup:
            self.logger.info("[弥助] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[弥助] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[弥助] 停止游戏失败: {e}")
