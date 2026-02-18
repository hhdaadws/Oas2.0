"""
起号 - 经验副本执行器
导航到组队界面 → 滑动查找经验妖怪 → 自动匹配 → 等待匹配画面判断冷却 →
等待准备按钮 → 点击准备进入战斗 → 循环。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus
from ...core.timeutils import format_beijing_time, now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ui.manager import UIManager
from ..vision.template import match_template
from .base import BaseExecutor
from .helpers import click_template, wait_for_template
from .db_logger import emit as db_log

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# 模板路径
_TPL_ZIDONGPIPEI = "assets/ui/templates/zidongpipei.png"
_TPL_JINGYANYAOGUAI = "assets/ui/templates/jingyanyaoguai.png"
_TPL_JINGYAN_SHENGLI = "assets/ui/templates/jingyan_shengli.png"
_TPL_SHIBAI = "assets/ui/templates/zhandou_shibai.png"
_TPL_JINGYAN_DENGDAI = "assets/ui/templates/jingyan_dengdai.png"
_TPL_ZHUNBEI_LIST = sorted(
    p.as_posix() for p in Path("assets/ui/templates").glob("zhandou_zhunbei_*.png")
)

# 冷却默认等待时间（无法精确获取冷却时间，保守等待 6 小时）
_COOLDOWN_DEFAULT = timedelta(hours=6)

# 最大战斗循环次数（安全上限）
_MAX_BATTLE_ROUNDS = 20


class InitExpDungeonExecutor(BaseExecutor):
    """起号 - 经验副本"""

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
            activity_name=(
                syscfg.activity_name or ".MainActivity" if syscfg else ".MainActivity"
            ),
        )
        return EmulatorAdapter(cfg)

    async def prepare(self, task: Task, account: GameAccount) -> bool:
        self.logger.info(
            f"[起号_经验副本] 准备: account_id={account.id}, login_id={account.login_id}"
        )

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[起号_经验副本] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error(f"[起号_经验副本] 模拟器不存在: id={self.emulator_id}")
            return False

        self.adapter = self._build_adapter()

        ok = await self._push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[起号_经验副本] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[起号_经验副本] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        account = self.current_account
        self.logger.info(f"[起号_经验副本] 执行: account_id={account.id}")

        # 构造/复用 UIManager
        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = (
                (self.system_config.capture_method if self.system_config else None)
                or "adb"
            )
            self.ui = UIManager(self.adapter, capture_method=capture_method, cross_emulator_cache_enabled=self._cross_emulator_cache_enabled())

        # 1. 确保游戏就绪
        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            self.logger.error("[起号_经验副本] 游戏就绪失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. 导航到组队界面
        in_zudui = await self.ui.ensure_ui("ZUDUI", max_steps=8, step_timeout=3.0)
        if not in_zudui:
            self.logger.error("[起号_经验副本] 导航到组队界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航组队界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info("[起号_经验副本] 已到达组队界面")

        # 3. 滑动查找并点击经验妖怪
        found = await self._scroll_find_and_click_jingyanyaoguai()
        if not found:
            self.logger.error("[起号_经验副本] 未找到经验妖怪图标")
            return {
                "status": TaskStatus.FAILED,
                "error": "未找到经验妖怪图标",
                "timestamp": datetime.utcnow().isoformat(),
            }

        await asyncio.sleep(1.0)

        # 4. 战斗循环
        victories = 0
        for round_idx in range(1, _MAX_BATTLE_ROUNDS + 1):
            self.logger.info(f"[起号_经验副本] 第 {round_idx} 轮")

            # 4a. 点击自动匹配并检测画面变化（判断是否冷却）
            match_result = await self._click_match_and_enter_battle(round_idx)

            if match_result == "cooldown":
                self.logger.info("[起号_经验副本] 冷却中，更新 next_time 并退出")
                self._update_next_time(account.id, _COOLDOWN_DEFAULT)
                db_log(account.id, f"经验副本完成 {victories} 轮，冷却中")
                break
            elif match_result == "error":
                self.logger.warning(
                    f"[起号_经验副本] 第 {round_idx} 轮自动匹配异常"
                )
                break

            # 4b. 画面变化了 → 等待经验胜利画面或战斗失败
            m_result = await wait_for_template(
                self.adapter, self.ui.capture_method,
                [_TPL_JINGYAN_SHENGLI, _TPL_SHIBAI],
                timeout=120.0, interval=2.0,
                log=self.logger, label=f"经验副本R{round_idx}-等待战斗结束",
                popup_handler=self.ui.popup_handler,
            )

            if not m_result:
                self.logger.warning(
                    f"[起号_经验副本] 第 {round_idx} 轮战斗超时"
                )
                self._update_next_time(account.id, timedelta(minutes=10))
                return {
                    "status": TaskStatus.FAILED,
                    "error": f"第 {round_idx} 轮战斗超时",
                    "victories": victories,
                    "timestamp": datetime.utcnow().isoformat(),
                }

            # 检查是否战斗失败
            await asyncio.sleep(0.5)
            screenshot = await self._capture()
            if screenshot is not None and match_template(screenshot, _TPL_SHIBAI):
                self.logger.warning(
                    f"[起号_经验副本] 第 {round_idx} 轮战斗失败"
                )
                await click_template(
                    self.adapter, self.ui.capture_method, _TPL_SHIBAI,
                    timeout=5.0, settle=0.5, post_delay=1.5,
                    log=self.logger, label=f"经验副本R{round_idx}-点击失败",
                    popup_handler=self.ui.popup_handler,
                )
                self._update_next_time(account.id, timedelta(minutes=10))
                return {
                    "status": TaskStatus.FAILED,
                    "error": f"第 {round_idx} 轮战斗失败",
                    "victories": victories,
                    "timestamp": datetime.utcnow().isoformat(),
                }

            # 胜利：反复点击 jingyan_shengli 直到消失 → 自动回到庭院
            await click_template(
                self.adapter, self.ui.capture_method, _TPL_JINGYAN_SHENGLI,
                timeout=8.0, settle=0.5, post_delay=1.5,
                verify_gone=True, max_clicks=5, gone_interval=1.5,
                log=self.logger, label=f"经验副本R{round_idx}-点击胜利",
                popup_handler=self.ui.popup_handler,
            )

            victories += 1
            self.logger.info(f"[起号_经验副本] 第 {round_idx} 轮战斗胜利")

            # 4c. 战斗结束后等待界面稳定
            await asyncio.sleep(2.0)

            # 4d. 检查是否还在组队界面，不在则导航回去
            cur = await self._detect_ui()
            if cur.ui != "ZUDUI":
                self.logger.info("[起号_经验副本] 战斗后不在组队界面，尝试返回")
                in_zudui = await self.ui.ensure_ui(
                    "ZUDUI", max_steps=6, step_timeout=3.0
                )
                if not in_zudui:
                    self.logger.error("[起号_经验副本] 战斗后返回组队界面失败")
                    break

            # 4e. 重新滑动查找经验妖怪
            found = await self._scroll_find_and_click_jingyanyaoguai()
            if not found:
                self.logger.warning("[起号_经验副本] 战斗后重新查找经验妖怪失败")
                break
            await asyncio.sleep(1.0)
        else:
            # 达到最大轮次安全上限
            self.logger.warning(f"[起号_经验副本] 达到最大轮次 {_MAX_BATTLE_ROUNDS}")
            self._update_next_time(account.id, timedelta(hours=2))

        self.logger.info(
            f"[起号_经验副本] 执行完成: account_id={account.id}, victories={victories}"
        )
        return {
            "status": TaskStatus.SUCCEEDED,
            "victories": victories,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _scroll_find_and_click_jingyanyaoguai(
        self, max_scrolls: int = 6
    ) -> bool:
        """滑动查找并点击经验妖怪图标。

        在组队界面中，循环截图 → 模板匹配 jingyanyaoguai.png →
        找到则点击 → 未找到则下滑 → 重复。

        Returns:
            True 找到并点击成功，False 滑动上限仍未找到。
        """
        for scroll_i in range(max_scrolls):
            screenshot = await self._capture()
            if screenshot is None:
                await asyncio.sleep(0.5)
                continue

            # 弹窗检测
            if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
                continue

            m = match_template(screenshot, _TPL_JINGYANYAOGUAI)
            if m:
                cx, cy = m.random_point()
                self.logger.info(
                    f"[起号_经验副本] 第{scroll_i + 1}次查找找到经验妖怪 "
                    f"(score={m.score:.3f}, pos=({cx}, {cy}))"
                )
                await self._tap(cx, cy)
                await asyncio.sleep(1.5)
                return True

            # 未找到 → 下滑
            self.logger.info(
                f"[起号_经验副本] 第{scroll_i + 1}次未找到经验妖怪，下滑"
            )
            await self._swipe(480, 350, 480, 150, 500)
            await asyncio.sleep(1.5)

        self.logger.warning(
            f"[起号_经验副本] 下滑{max_scrolls}次未找到经验妖怪"
        )
        return False

    async def _click_match_and_enter_battle(self, round_idx: int) -> str:
        """点击自动匹配 → 状态轮询等待匹配/准备 → 点击准备 → 确认进入战斗。

        流程:
            1. 点击 zidongpipei.png 自动匹配按钮
            2+3. 状态感知轮询：同时检测 dengdai 和 zhunbei
               - zhunbei 先出现 → 匹配极快，直接进入阶段 4
               - dengdai 先出现 → 继续等待 zhunbei（最长 60s）
               - 6s 内两者都未出现 → 检查冷却
            4. 循环检测并点击准备按钮，直到准备消失（15 秒超时）
               - 超时 → 返回 "error"

        Returns:
            "battle"   - 已成功进入战斗
            "cooldown" - 冷却中（dengdai 未出现）
            "error"    - 自动匹配按钮未出现 / 匹配超时 / 进入战斗超时
        """
        # ── 阶段 1：点击自动匹配 ──
        clicked = await click_template(
            self.adapter, self.ui.capture_method, _TPL_ZIDONGPIPEI,
            timeout=8.0, settle=0.5, post_delay=0.5,
            log=self.logger, label=f"经验副本R{round_idx}-自动匹配",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked:
            return "error"

        # ── 阶段 2+3（合并）：状态感知等待 dengdai 或 zhunbei ──
        # 同时检测两种模板，适应匹配速度快慢不同的情况：
        # - zhunbei 先出现 → 匹配极快，直接进入阶段 4
        # - dengdai 先出现 → 继续等待 zhunbei（最长 60s）
        # - 6s 内两者都未出现 → 检查 zidongpipei 判断冷却
        state = None  # None | "dengdai"
        elapsed = 0.0
        cooldown_window = 6.0
        match_timeout = 60.0
        poll_interval = 1.0
        zhunbei_found = False

        while elapsed < cooldown_window + match_timeout:
            screenshot = await self._capture()
            if screenshot is not None:
                # 弹窗处理
                if self.ui.popup_handler is not None:
                    dismissed = await self.ui.popup_handler.check_and_dismiss(
                        screenshot
                    )
                    if dismissed > 0:
                        continue  # 弹窗关闭后立即重试

                # 优先检测 zhunbei（准备按钮）— 匹配成功的终态
                for tpl in _TPL_ZHUNBEI_LIST:
                    m = match_template(screenshot, tpl)
                    if m:
                        zhunbei_found = True
                        break
                if zhunbei_found:
                    self.logger.info(
                        f"[起号_经验副本] 第 {round_idx} 轮: "
                        f"检测到准备按钮 (state={state}, elapsed={elapsed:.1f}s)"
                    )
                    break

                # 检测 dengdai（等待画面）— 匹配中的中间态
                if state is None:
                    m = match_template(screenshot, _TPL_JINGYAN_DENGDAI)
                    if m:
                        state = "dengdai"
                        self.logger.info(
                            f"[起号_经验副本] 第 {round_idx} 轮: "
                            f"匹配等待中... (elapsed={elapsed:.1f}s)"
                        )

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            # 冷却检测：6s 内 dengdai 和 zhunbei 都未出现
            if state is None and elapsed >= cooldown_window:
                screenshot = await self._capture()
                if screenshot is not None and match_template(
                    screenshot, _TPL_ZIDONGPIPEI
                ):
                    self.logger.info(
                        f"[起号_经验副本] 第 {round_idx} 轮: "
                        f"等待画面未出现且自动匹配按钮仍在，判定为冷却中"
                    )
                    return "cooldown"
                self.logger.warning(
                    f"[起号_经验副本] 第 {round_idx} 轮: "
                    f"等待画面未出现且自动匹配按钮消失，状态异常"
                )
                return "error"

        if not zhunbei_found:
            self.logger.warning(
                f"[起号_经验副本] 第 {round_idx} 轮: "
                f"等待准备按钮超时({cooldown_window + match_timeout:.0f}s)，匹配失败"
            )
            return "error"

        # ── 阶段 4：点击准备按钮并确认进入战斗 ──
        enter_elapsed = 0.0
        enter_timeout = 15.0
        enter_interval = 1.5

        while enter_elapsed < enter_timeout:
            screenshot = await self._capture()
            if screenshot is None:
                await asyncio.sleep(enter_interval)
                enter_elapsed += enter_interval
                continue

            # 检查准备按钮是否仍在
            still_zhunbei = False
            for tpl in _TPL_ZHUNBEI_LIST:
                m = match_template(screenshot, tpl)
                if m:
                    cx, cy = m.random_point()
                    self.logger.info(
                        f"[起号_经验副本] 第 {round_idx} 轮: "
                        f"点击准备按钮 ({cx}, {cy})"
                    )
                    await self._tap(cx, cy)
                    still_zhunbei = True
                    break

            if not still_zhunbei:
                self.logger.info(
                    f"[起号_经验副本] 第 {round_idx} 轮: "
                    f"准备按钮消失，已进入战斗"
                )
                return "battle"

            # 弹窗检测
            if self.ui.popup_handler is not None:
                await self.ui.popup_handler.check_and_dismiss(screenshot)

            await asyncio.sleep(enter_interval)
            enter_elapsed += enter_interval

        self.logger.warning(
            f"[起号_经验副本] 第 {round_idx} 轮: "
            f"点击准备后仍未进入战斗(15s)"
        )
        return "error"

    def _update_next_time(self, account_id: int, delta: timedelta) -> None:
        """根据冷却时间 delta 更新 next_time。"""
        try:
            bj_now = now_beijing()
            next_time = format_beijing_time(bj_now + delta)

            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == account_id)
                    .first()
                )
                if account:
                    cfg = account.task_config or {}
                    dungeon_cfg = cfg.get("起号_经验副本", {})
                    dungeon_cfg["next_time"] = next_time
                    cfg["起号_经验副本"] = dungeon_cfg
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(
                        f"[起号_经验副本] next_time 更新为 {next_time}"
                    )
        except Exception as e:
            self.logger.error(
                f"[起号_经验副本] 更新 next_time 失败: account_id={account_id}, error={e}"
            )

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[起号_经验副本] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                await self._adb_force_stop(PKG_NAME)
                self.logger.info("[起号_经验副本] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[起号_经验副本] 停止游戏失败: {e}")
