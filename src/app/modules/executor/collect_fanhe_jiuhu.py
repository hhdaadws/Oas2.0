"""
领取饭盒/酒壶执行器 - 导航到饭盒领取产出，补充育成式神，再导航到酒壶提取
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus
from ...core.logger import logger
from ...core.timeutils import add_hours_to_beijing_time, format_beijing_time, now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ui.manager import UIManager
from ..vision.template import find_all_templates, match_template
from ..vision.grid_detect import nms_by_distance
from .base import BaseExecutor
from .helpers import click_template

PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# 育成空位最多填充次数（防止无限循环）
MAX_FILL_LOOPS = 6


class CollectFanheJiuhuExecutor(BaseExecutor):
    """领取饭盒/酒壶执行器"""

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
        self.logger.info(f"[领取饭盒酒壶] 准备: account={account.login_id}")

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[领取饭盒酒壶] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error("[领取饭盒酒壶] 模拟器不存在: id={}", self.emulator_id)
            return False

        self.adapter = self._build_adapter()

        ok = await self._push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[领取饭盒酒壶] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[领取饭盒酒壶] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[领取饭盒酒壶] 执行: account={self.current_account.login_id}")

        # 构造或复用 UIManager
        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = (
                self.system_config.capture_method if self.system_config else None
            ) or "adb"
            self.ui = UIManager(self.adapter, capture_method=capture_method, cross_emulator_cache_enabled=self._cross_emulator_cache_enabled())

        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            self.logger.error("[领取饭盒酒壶] 游戏就绪失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # ===== 步骤1：领取饭盒 =====
        result = await self._collect_fanhe()
        if result:
            return result

        # ===== 步骤2：补充育成式神 =====
        await self._fill_yucheng_slots()

        # ===== 步骤3：领取酒壶 =====
        result = await self._collect_jiuhu()
        if result:
            return result

        # 更新 next_time
        self._update_next_time()

        self.logger.info("[领取饭盒酒壶] 执行完成")
        return {
            "status": TaskStatus.SUCCEEDED,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _collect_fanhe(self) -> Optional[Dict[str, Any]]:
        """导航到饭盒界面，点击取出，关闭奖励弹窗。返回 None 表示成功，返回 dict 表示失败。"""
        self.logger.info("[领取饭盒酒壶] 导航到饭盒界面")
        in_fanhe = await self.ui.ensure_ui("FANHE", max_steps=6, step_timeout=3.0)
        if not in_fanhe:
            self.logger.error("[领取饭盒酒壶] 导航到饭盒界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航饭盒界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 点击 fanhe_quchu.png
        clicked = await click_template(
            self.adapter,
            self.ui.capture_method,
            "assets/ui/templates/fanhe_quchu.png",
            timeout=5.0,
            settle=0.5,
            post_delay=2.0,
            log=self.logger,
            label="饭盒取出",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked:
            self.logger.warning("[领取饭盒酒壶] 未检测到饭盒取出按钮，可能无产出")
        else:
            # 关闭 jiangli.png 奖励弹窗
            await self._dismiss_jiangli("饭盒取出")

        return None

    async def _fill_yucheng_slots(self) -> None:
        """导航到结界养成界面，检测空位并补充育成式神。"""
        self.logger.info("[领取饭盒酒壶] 导航到结界养成界面")
        in_yangcheng = await self.ui.ensure_ui(
            "JIEJIE_YANGCHENG", max_steps=6, step_timeout=3.0
        )
        if not in_yangcheng:
            self.logger.warning("[领取饭盒酒壶] 导航到结界养成界面失败，跳过育成补充")
            return

        for loop_idx in range(MAX_FILL_LOOPS):
            screenshot = await self._capture()
            if screenshot is None:
                self.logger.warning("[领取饭盒酒壶] 截图失败，退出育成补充")
                break

            blanks = find_all_templates(
                screenshot, "assets/ui/templates/yucheng_blank.png"
            )
            blanks = nms_by_distance(blanks)
            blank_count = len(blanks)

            if blank_count == 0:
                self.logger.info("[领取饭盒酒壶] 育成位已满，无需补充")
                break

            self.logger.info(
                f"[领取饭盒酒壶] 第 {loop_idx + 1} 轮：检测到 {blank_count} 个育成空位"
            )

            # 尝试点击蓝蛋
            filled = await click_template(
                self.adapter,
                self.ui.capture_method,
                "assets/ui/templates/yucheng_landan.png",
                timeout=3.0,
                settle=0.3,
                post_delay=1.0,
                log=self.logger,
                label="育成蓝蛋",
            )
            if not filled:
                # 尝试点击红蛋
                filled = await click_template(
                    self.adapter,
                    self.ui.capture_method,
                    "assets/ui/templates/yucheng_hongdan.png",
                    timeout=3.0,
                    settle=0.3,
                    post_delay=1.0,
                    log=self.logger,
                    label="育成红蛋",
                )
            if not filled:
                self.logger.warning("[领取饭盒酒壶] 无可用式神补充，退出补充循环")
                break

            await asyncio.sleep(1.0)

    async def _collect_jiuhu(self) -> Optional[Dict[str, Any]]:
        """导航到酒壶界面，点击提取。返回 None 表示成功，返回 dict 表示失败。"""
        self.logger.info("[领取饭盒酒壶] 导航到酒壶界面")
        in_jiuhu = await self.ui.ensure_ui("JIUHU", max_steps=6, step_timeout=3.0)
        if not in_jiuhu:
            self.logger.error("[领取饭盒酒壶] 导航到酒壶界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航酒壶界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 点击 jiuhu_tiqu.png（点击后不会有 jiangli 弹窗）
        clicked = await click_template(
            self.adapter,
            self.ui.capture_method,
            "assets/ui/templates/jiuhu_tiqu.png",
            timeout=5.0,
            settle=0.5,
            post_delay=1.5,
            log=self.logger,
            label="酒壶提取",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked:
            self.logger.warning("[领取饭盒酒壶] 未检测到酒壶提取按钮，可能无产出")

        return None

    async def _dismiss_jiangli(self, step_label: str) -> None:
        """关闭 jiangli.png 奖励弹窗"""
        await asyncio.sleep(1.5)
        screenshot = await self._capture()

        if screenshot is not None:
            # 先让 popup_handler 处理可能的其他弹窗
            if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
                screenshot = await self._capture()

        if screenshot is not None:
            jiangli = match_template(screenshot, "assets/ui/templates/jiangli.png")
            if jiangli:
                self.logger.info(f"[领取饭盒酒壶] [{step_label}] 检测到奖励弹窗，点击关闭")
            else:
                self.logger.warning(
                    f"[领取饭盒酒壶] [{step_label}] 未检测到奖励弹窗，仍尝试点击关闭"
                )

        # 随机点击屏幕空白区域关闭弹窗
        from ..vision.utils import random_point_in_circle

        close_x, close_y = random_point_in_circle(20, 20, 20)
        await self._tap(close_x, close_y)
        self.logger.info(
            f"[领取饭盒酒壶] [{step_label}] 随机点击 ({close_x}, {close_y}) 关闭弹窗"
        )
        await asyncio.sleep(1.0)

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
                    task_cfg = cfg.get("领取饭盒酒壶", {})
                    task_cfg["next_time"] = next_time
                    cfg["领取饭盒酒壶"] = task_cfg
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(f"[领取饭盒酒壶] next_time 更新为 {next_time}")
        except Exception as e:
            self.logger.error(f"[领取饭盒酒壶] 更新 next_time 失败: {e}")

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[领取饭盒酒壶] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                await self._adb_force_stop(PKG_NAME)
                self.logger.info("[领取饭盒酒壶] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[领取饭盒酒壶] 停止游戏失败: {e}")
