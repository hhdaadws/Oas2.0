"""
探索突破执行器 - 体力驱动循环：探索章节战斗 + 结界突破

流程:
  1. 确保游戏就绪
  2. 庭院体力预检查（体力 < 阈值 → 跳过）
  3. 导航到 TANSUO 界面
  4. 构建手动阵容（仅首轮）
  5. 循环（上限 20 轮）:
     a. 执行探索章节（run_explore_chapter）
     b. 读取当前体力
     c. 体力 < 阈值 → 执行突破 → 停止
     d. 体力 >= 阈值 → 读突破票
        - 突破票 >= 30 → 执行突破 → 导航回 TANSUO → 继续
        - 突破票 < 30 → 确保在 TANSUO → 继续
  6. 返回汇总结果

前置条件处理:
  1. 未加入寮 → 一键申请（复用 check_and_handle_liao_not_joined）
  2. 未创建结界 → 自动创建（复用 check_and_create_jiejie）
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
from ..ui.assets import parse_number, AssetType
from ..ui.manager import UIManager
from .base import BaseExecutor
from .battle import run_battle, ManualLineupInfo, VICTORY, DEFEAT, TIMEOUT, ERROR
from .helpers import (
    check_and_create_jiejie,
    check_and_handle_liao_not_joined,
    click_template,
    wait_for_template,
)
from ..lineup import get_lineup_for_task
from ..shikigami import build_manual_lineup_info
from ..vision.explore_detect import detect_current_chapter
from ..vision.tupo_detect import detect_tupo_grid, TupoCardState
from ..vision.color_detect import detect_jiekai_lock
from ..vision.template import match_template as _match_template
from .explore_chapter import run_explore_chapter

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# 结界突破战斗相关模板
_TPL_JIEJIE_JINGONG = "assets/ui/templates/jiejie_jingong.png"
_TPL_JIEJIE_TUICHU = "assets/ui/templates/jiejie_tuichu.png"
_TPL_JIEJIE_QUEREN = "assets/ui/templates/jiejie_queren.png"
_TPL_JIEJIE_SHUAXIN = "assets/ui/templates/jiejie_shuaxin.png"
_TPL_JIEJIE_QUEDING = "assets/ui/templates/jiejie_queding.png"
_TPL_ZHANDOU_SHIBAI = "assets/ui/templates/zhandou_shibai.png"

# 突破票 OCR 区域 (x, y, w, h)
_TUPO_TICKET_ROI = (855, 13, 30, 18)              # 结界突破界面
_TANSUO_TICKET_ROI = (546, 9, 36, 26)             # TANSUO 主界面（无 tansuo_tansuo.png）
_DIFFICULTY_TICKET_ROI = (699, 10, 31, 21)         # 难度选择界面（有 tansuo_tansuo.png）

# 第3排卡片点击 y 偏移量（向上偏移，避免点到底部 UI）
_ROW2_Y_OFFSET = 20
# 最大刷新轮次
_MAX_REFRESH_ROUNDS = 3
# 进入结界突破的最低突破票数量
_MIN_TUPO_TICKET = 30

# 体力 OCR 区域（不同界面位置不同）
_STAMINA_ROI_TANSUO = (715, 9, 62, 22)       # TANSUO 界面体力坐标
_STAMINA_ROI_DIFFICULTY = (569, 10, 56, 21)   # 难度选择界面体力坐标
_TPL_TANSUO_TANSUO = "assets/ui/templates/tansuo_tansuo.png"
_TPL_EXIT = "assets/ui/templates/exit.png"

# 探索循环最大轮次
_MAX_EXPLORE_LOOPS = 20


class ExploreExecutor(BaseExecutor):
    """探索突破执行器 - 先探索章节后做结界突破"""

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

    def _read_tupo_ticket(self) -> Optional[int]:
        """OCR 读取结界突破界面右上角的突破票数量并更新数据库。"""
        import time
        for attempt in range(1, 4):
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is None:
                self.logger.warning(
                    f"[探索突破] 截图失败，无法读取突破票 (attempt={attempt}/3)"
                )
                time.sleep(0.3)
                continue
            result = ocr_digits(screenshot, roi=_TUPO_TICKET_ROI)
            raw = result.text.strip()
            value = parse_number(raw)
            self.logger.info(
                f"[探索突破] 突破票 OCR: raw='{raw}' → value={value} "
                f"(attempt={attempt}/3)"
            )
            if value is not None:
                self._update_tupo_ticket_db(value)
                return value
            time.sleep(0.3)
        return None

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
        self.logger.info(f"[探索突破] 准备: account={account.login_id}")

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[探索突破] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error(f"[探索突破] 模拟器不存在: id={self.emulator_id}")
            return False

        self.adapter = self._build_adapter()

        ok = self.adapter.push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[探索突破] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[探索突破] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[探索突破] 执行: account={self.current_account.login_id}")

        # 构造/复用 UIManager
        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = (
                (self.system_config.capture_method if self.system_config else None)
                or "adb"
            )
            self.ui = UIManager(self.adapter, capture_method=capture_method)

        # 1. 确保游戏就绪
        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            self.logger.error("[探索突破] 游戏就绪失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. 读取 task_config
        task_config = self.current_account.task_config or {}
        explore_cfg = task_config.get("探索突破", {})
        stamina_threshold = explore_cfg.get("stamina_threshold", 0)
        difficulty = explore_cfg.get("difficulty", "normal")
        sub_explore = explore_cfg.get("sub_explore", True)
        sub_tupo = explore_cfg.get("sub_tupo", True)

        # 2a. 两者都禁用 → 跳过
        if not sub_explore and not sub_tupo:
            self.logger.info("[探索突破] 探索和突破均已禁用，跳过")
            return {
                "status": TaskStatus.SKIPPED,
                "reason": "探索和突破均已禁用",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2b. 纯突破模式 → 跳过探索循环，直接执行突破
        if not sub_explore and sub_tupo:
            self.logger.info("[探索突破] 仅突破模式，跳过探索")
            tupo_result = await self._navigate_and_run_tupo()
            return {
                "status": tupo_result.get("status", TaskStatus.SUCCEEDED),
                "message": "仅突破模式",
                "tupo_result": tupo_result,
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 3. 庭院体力预检查
        if stamina_threshold > 0:
            try:
                current_stamina = await self.ui.read_asset(AssetType.STAMINA)
                if current_stamina is not None and current_stamina < stamina_threshold:
                    self.logger.info(
                        f"[探索突破] 体力低于保留线: {current_stamina} < {stamina_threshold}，跳过"
                    )
                    return {
                        "status": TaskStatus.SKIPPED,
                        "reason": f"体力低于保留线({current_stamina}<{stamina_threshold})",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                elif current_stamina is not None:
                    self.logger.info(
                        f"[探索突破] 当前体力 {current_stamina} >= 保留线 {stamina_threshold}，继续执行"
                    )
                else:
                    self.logger.warning("[探索突破] 体力 OCR 读取失败，继续执行")
            except Exception as e:
                self.logger.warning(f"[探索突破] 体力检查异常: {e}，继续执行")

        # 4. 导航到 TANSUO 界面
        in_tansuo = await self.ui.ensure_ui("TANSUO", max_steps=6, step_timeout=3.0)
        if not in_tansuo:
            self.logger.warning("[探索突破] 导航到 TANSUO 失败，检查前置条件")
            return await self._handle_prerequisites_and_tupo()

        # 5. 构建手动阵容
        explore_manual_lineup = self._build_explore_manual_lineup()

        self.logger.info(f"[探索突破] 探索难度: {difficulty}")

        # 6. 体力驱动循环
        total_victories = 0
        total_defeats = 0
        total_markers = 0
        tupo_done = False

        for loop_idx in range(_MAX_EXPLORE_LOOPS):
            self.logger.info(f"[探索突破] 探索循环 第{loop_idx + 1}轮")

            # 6a. 执行探索章节（手动阵容仅首轮传入）
            explore_result = await run_explore_chapter(
                self.adapter,
                self.ui.capture_method,
                mode="all",
                difficulty=difficulty,
                manual_lineup=explore_manual_lineup if loop_idx == 0 else None,
                first_fight=(loop_idx == 0),
                log=self.logger,
                popup_handler=self.ui.popup_handler,
            )
            total_victories += explore_result.victories
            total_defeats += explore_result.defeats
            total_markers += explore_result.markers_found
            self.logger.info(
                f"[探索突破] 第{loop_idx + 1}轮探索完成: "
                f"{explore_result.victories}胜 {explore_result.defeats}负, "
                f"标记={explore_result.markers_found} "
                f"(累计: {total_victories}胜 {total_defeats}负)"
            )

            # ── yield point: 检查高优先级任务中断 ──
            await self._check_and_run_interrupts()

            # 6b. 读取当前体力
            current_stamina = self._read_stamina_from_current_ui()

            # 6c. 体力 < 阈值 → 执行突破 → 停止
            if (
                stamina_threshold > 0
                and current_stamina is not None
                and current_stamina < stamina_threshold
            ):
                self.logger.info(
                    f"[探索突破] 体力 {current_stamina} < 阈值 {stamina_threshold}"
                )
                if sub_tupo:
                    self.logger.info("[探索突破] 执行结界突破后停止")
                    await self._ensure_back_to_tansuo()
                    tupo_result = await self._navigate_and_run_tupo()
                    tupo_done = True
                    return {
                        "status": tupo_result.get("status", TaskStatus.SUCCEEDED),
                        "message": (
                            f"探索循环完成({loop_idx + 1}轮): "
                            f"{total_victories}胜 {total_defeats}负, "
                            f"体力不足触发突破"
                        ),
                        "explore_victories": total_victories,
                        "explore_defeats": total_defeats,
                        "explore_markers": total_markers,
                        "explore_loops": loop_idx + 1,
                        "tupo_result": tupo_result,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                else:
                    self.logger.info("[探索突破] 突破已禁用，体力不足直接停止")
                    return {
                        "status": TaskStatus.SUCCEEDED,
                        "message": (
                            f"探索循环完成({loop_idx + 1}轮): "
                            f"{total_victories}胜 {total_defeats}负, "
                            f"体力不足"
                        ),
                        "explore_victories": total_victories,
                        "explore_defeats": total_defeats,
                        "explore_markers": total_markers,
                        "explore_loops": loop_idx + 1,
                        "timestamp": datetime.utcnow().isoformat(),
                    }

            # 6d. 体力 >= 阈值 → 读突破票
            if sub_tupo:
                ticket_count = self._read_tupo_ticket_from_current_ui()
                if ticket_count is not None and ticket_count >= _MIN_TUPO_TICKET:
                    self.logger.info(
                        f"[探索突破] 突破票={ticket_count}，先执行结界突破"
                    )
                    await self._ensure_back_to_tansuo()
                    tupo_result = await self._navigate_and_run_tupo()
                    tupo_done = True
                    # 突破后导航回 TANSUO 继续循环
                    in_tansuo = await self.ui.ensure_ui(
                        "TANSUO", max_steps=6, step_timeout=3.0
                    )
                    if not in_tansuo:
                        self.logger.warning(
                            "[探索突破] 突破后导航回 TANSUO 失败，结束循环"
                        )
                        return {
                            "status": TaskStatus.SUCCEEDED,
                            "message": (
                                f"探索循环完成({loop_idx + 1}轮): "
                                f"{total_victories}胜 {total_defeats}负, "
                                f"突破后无法回到探索"
                            ),
                            "explore_victories": total_victories,
                            "explore_defeats": total_defeats,
                            "explore_markers": total_markers,
                            "explore_loops": loop_idx + 1,
                            "tupo_result": tupo_result,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    self.logger.info("[探索突破] 突破后已回到 TANSUO，继续循环")
                    continue
                else:
                    continue
            else:
                # 突破禁用，直接继续探索循环
                continue

        # 7. 返回汇总结果
        self.logger.info(
            f"[探索突破] 循环结束: {total_victories}胜 {total_defeats}负, "
            f"标记={total_markers}"
        )
        return {
            "status": TaskStatus.SUCCEEDED,
            "message": (
                f"探索循环完成: {total_victories}胜 {total_defeats}负, "
                f"标记={total_markers}"
            ),
            "explore_victories": total_victories,
            "explore_defeats": total_defeats,
            "explore_markers": total_markers,
            "tupo_done": tupo_done,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[探索突破] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[探索突破] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[探索突破] 停止游戏失败: {e}")

    # ── 探索辅助方法 ──

    async def _ensure_back_to_tansuo(self) -> None:
        """如果当前在难度选择面板（检测到 tansuo_tansuo.png），点击 exit.png 返回 TANSUO。"""
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            return
        m = _match_template(screenshot, _TPL_TANSUO_TANSUO)
        if m:
            self.logger.info("[探索突破] 检测到难度选择面板，点击退出回到 TANSUO")
            await click_template(
                self.adapter, self.ui.capture_method, _TPL_EXIT,
                timeout=5.0, settle=0.3, post_delay=1.5,
                log=self.logger, label="探索突破-退出难度面板",
                popup_handler=self.ui.popup_handler,
            )
        else:
            self.logger.info("[探索突破] 已在 TANSUO 界面")

    async def _check_and_run_interrupts(self) -> list:
        """在 yield point 检查并执行更高优先级的到期任务。

        调用 Worker 注入的 interrupt_callback，执行完后导航回 TANSUO。

        Returns:
            已执行的任务名列表（空列表 = 无中断）。
        """
        if not self.interrupt_callback:
            return []

        from ...core.constants import TASK_PRIORITY, TaskType
        current_priority = TASK_PRIORITY.get(TaskType.EXPLORE, 50)

        completed = await self.interrupt_callback(current_priority)
        if not completed:
            return []

        self.logger.info(
            f"[探索突破] 中断执行了 {len(completed)} 个高优先级任务: {completed}，"
            f"导航回 TANSUO 继续"
        )
        # 子任务可能改变了 UI 状态，导航回 TANSUO
        in_tansuo = await self.ui.ensure_ui("TANSUO", max_steps=6, step_timeout=3.0)
        if not in_tansuo:
            self.logger.warning("[探索突破] 中断后导航回 TANSUO 失败")
        return completed

    def _build_explore_manual_lineup(self) -> Optional[ManualLineupInfo]:
        """构建探索专用的手动阵容配置（使用探索专用坐标）。"""
        lineup_config = self.current_account.lineup_config or {}
        lineup = get_lineup_for_task(lineup_config, "探索")
        has_lineup = (
            lineup.get("group", 0) > 0 and lineup.get("position", 0) > 0
        )

        if has_lineup:
            return None  # 有预设阵容，不需要手动配置

        if self.current_account.progress != "init":
            return None

        shikigami_cfg = self.current_account.shikigami_config or {}
        lineup_data = build_manual_lineup_info(shikigami_cfg)
        if not lineup_data:
            return None

        manual_lineup = ManualLineupInfo(
            rental_shikigami=lineup_data["rental_shikigami"],
            zuofu_template=lineup_data["zuofu_template"],
            config_btn=(165, 390),
            lineup_pos_1=(196, 270),
            lineup_pos_2=(479, 307),
        )
        self.logger.info(
            f"[探索突破] init账号 探索手动阵容: "
            f"租借={[n for _, n, _ in manual_lineup.rental_shikigami]}, "
            f"座敷={'有' if manual_lineup.zuofu_template else '无'}"
        )
        return manual_lineup

    def _read_stamina_from_current_ui(self) -> Optional[int]:
        """根据当前界面在不同 ROI 读取体力数值。

        探索退出后可能在 TANSUO 界面或难度选择界面，体力显示位置不同。
        通过检测 tansuo_tansuo.png 模板判断当前界面。
        """
        import time
        for attempt in range(1, 4):
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is None:
                self.logger.warning(
                    f"[探索突破] 体力截图失败 (attempt={attempt}/3)"
                )
                time.sleep(0.3)
                continue

            # 检测 tansuo_tansuo.png 判断是否在难度选择界面
            tansuo_m = _match_template(screenshot, _TPL_TANSUO_TANSUO)
            if tansuo_m:
                # 难度选择界面（有"探索"按钮）
                roi = _STAMINA_ROI_DIFFICULTY
                ui_label = "难度选择界面"
            else:
                # TANSUO 界面
                roi = _STAMINA_ROI_TANSUO
                ui_label = "TANSUO 界面"

            result = ocr_digits(screenshot, roi=roi)
            raw = result.text.strip()
            value = parse_number(raw)
            self.logger.info(
                f"[探索突破] 体力 OCR ({ui_label}): raw='{raw}' → value={value} "
                f"(attempt={attempt}/3)"
            )
            if value is not None:
                return value
            time.sleep(0.3)
        return None

    def _read_tupo_ticket_from_current_ui(self) -> Optional[int]:
        """根据当前界面在不同 ROI 读取突破票数量。

        通过检测 tansuo_tansuo.png 模板判断当前界面：
        - 匹配到 → 难度选择界面 → _DIFFICULTY_TICKET_ROI
        - 未匹配 → TANSUO 主界面 → _TANSUO_TICKET_ROI
        """
        import time
        for attempt in range(1, 4):
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is None:
                self.logger.warning(
                    f"[探索突破] 截图失败，无法读取突破票 (attempt={attempt}/3)"
                )
                time.sleep(0.3)
                continue

            # 用 tansuo_tansuo.png 判断界面
            tansuo_m = _match_template(screenshot, _TPL_TANSUO_TANSUO)
            if tansuo_m:
                roi = _DIFFICULTY_TICKET_ROI
                ui_label = "难度选择界面"
            else:
                roi = _TANSUO_TICKET_ROI
                ui_label = "TANSUO 界面"

            result = ocr_digits(screenshot, roi=roi)
            raw = result.text.strip()
            value = parse_number(raw)
            self.logger.info(
                f"[探索突破] 突破票 OCR ({ui_label}): raw='{raw}' → value={value} "
                f"(attempt={attempt}/3)"
            )

            if value is not None:
                self._update_tupo_ticket_db(value)
                return value
            time.sleep(0.3)
        return None

    def _update_tupo_ticket_db(self, value: int) -> None:
        """更新突破票数量到数据库。"""
        try:
            with SessionLocal() as db:
                acc = db.query(GameAccount).filter(
                    GameAccount.id == self.current_account.id
                ).first()
                if acc:
                    acc.tupo_ticket = value
                    db.commit()
        except Exception as e:
            self.logger.warning(f"[探索突破] 更新突破票到 DB 失败: {e}")

    async def _navigate_and_run_tupo(self) -> Dict[str, Any]:
        """从当前界面导航到结界突破并执行。"""
        in_tupo = await self.ui.ensure_ui(
            "JIEJIE_TUPO", max_steps=8, step_timeout=3.0
        )
        if not in_tupo:
            # 可能需要处理前置条件
            return await self._handle_prerequisites_and_tupo()

        self.logger.info("[探索突破] 已到达结界突破界面")
        ticket_count = self._read_tupo_ticket()
        return await self._run_tupo_loop(ticket_count)

    async def _handle_prerequisites_and_tupo(self) -> Dict[str, Any]:
        """处理寮相关前置条件后进入结界突破。"""
        detect_result = self.ui.detect_ui()
        self.logger.warning(
            f"[探索突破] 导航到结界突破失败，"
            f"当前 UI={detect_result.ui}，检查前置条件"
        )

        # 导航到寮界面
        in_liao = await self.ui.ensure_ui("LIAO", max_steps=8, step_timeout=3.0)
        if not in_liao:
            self.logger.error("[探索突破] 导航到寮界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航寮界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 检测是否未加入寮
        not_joined = await check_and_handle_liao_not_joined(
            self.adapter,
            self.ui.capture_method,
            self.current_account.id,
            log=self.logger,
            label="探索突破",
        )
        if not_joined:
            return {
                "status": TaskStatus.SKIPPED,
                "reason": "账号未加入寮，已提交申请并延后寮任务",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 检测并创建结界
        created = await check_and_create_jiejie(
            self.adapter,
            self.ui.capture_method,
            log=self.logger,
            label="探索突破",
            popup_handler=self.ui.popup_handler,
        )
        if created:
            self.logger.info("[探索突破] 结界已创建，重试进入突破界面")
        else:
            self.logger.info("[探索突破] 结界已存在，重试进入突破界面")

        # 重试导航到结界突破
        in_tupo = await self.ui.ensure_ui(
            "JIEJIE_TUPO", max_steps=8, step_timeout=3.0
        )
        if not in_tupo:
            self.logger.error("[探索突破] 处理前置条件后仍无法进入结界突破")
            return {
                "status": TaskStatus.FAILED,
                "error": "处理前置条件后仍无法进入结界突破",
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.logger.info("[探索突破] 已进入结界突破界面")
        ticket_count = self._read_tupo_ticket()
        return await self._run_tupo_loop(ticket_count)

    # ── 结界突破战斗逻辑 ──

    def _get_card_click_pos(self, card) -> tuple:
        """获取卡片的点击坐标。

        第3排(row=2)的卡片点击坐标偏上，避免点到底部 UI。
        """
        cx, cy = card.random_point()
        if card.row == 2:
            cy -= _ROW2_Y_OFFSET
        return (cx, cy)

    async def _ensure_lock_state(self, should_lock: bool) -> bool:
        """确保阵容锁定状态与期望一致。

        Args:
            should_lock: True=需要锁定, False=需要解锁

        Returns:
            True 表示状态已正确，False 表示操作失败
        """
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            self.logger.warning("[结界突破] 截图失败，无法检测锁定状态")
            return False

        lock_state = detect_jiekai_lock(screenshot)
        self.logger.info(
            f"[结界突破] 锁定状态: locked={lock_state.locked}, "
            f"score={lock_state.score:.2f}, 期望={'锁定' if should_lock else '解锁'}"
        )

        if lock_state.locked == should_lock:
            return True  # 状态已正确

        # 需要切换：重试最多 3 次
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            lock_x, lock_y = lock_state.center
            if lock_x == 0 and lock_y == 0:
                lock_x, lock_y = 626, 450

            self.adapter.adb.tap(self.adapter.cfg.adb_addr, lock_x, lock_y)
            self.logger.info(
                f"[结界突破] 点击锁图标 ({lock_x}, {lock_y}) "
                f"切换锁定状态 (attempt={attempt})"
            )
            await asyncio.sleep(1.0)

            # 验证
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is not None:
                new_state = detect_jiekai_lock(screenshot)
                if new_state.locked == should_lock:
                    self.logger.info(
                        f"[结界突破] 锁定状态切换成功: "
                        f"{'锁定' if should_lock else '解锁'}"
                    )
                    return True
                else:
                    self.logger.warning(
                        f"[结界突破] 锁定状态切换验证失败: "
                        f"期望={'锁定' if should_lock else '解锁'}, "
                        f"实际={'锁定' if new_state.locked else '解锁'} "
                        f"(attempt={attempt})"
                    )
                    lock_state = new_state
            else:
                self.logger.warning(
                    f"[结界突破] 验证截图失败 (attempt={attempt})"
                )

        return False  # 所有重试均失败

    async def _handle_normal_card(
        self, card, is_first: bool, has_lineup: bool, lineup: dict,
        manual_lineup: ManualLineupInfo | None = None,
    ) -> str:
        """处理普通卡片（index 0-7）的战斗。

        Args:
            card: TupoCard 对象
            is_first: 是否为首次战斗（首张卡片）
            has_lineup: 是否配置了阵容
            lineup: 阵容配置 {"group": int, "position": int}
            manual_lineup: 手动阵容配置（无预设时使用）

        Returns:
            "victory"|"defeat"|"timeout"|"error"
        """
        tag = f"[结界突破-卡片{card.index}]"

        if is_first:
            # 首次战斗：确保阵容解锁，允许阵容切换
            lock_ok = await self._ensure_lock_state(should_lock=False)
            battle_lineup = lineup if has_lineup else None
        else:
            # 后续战斗：确保阵容锁定
            lock_ok = await self._ensure_lock_state(should_lock=True)
            battle_lineup = None  # 锁定后不需要切换

        if not lock_ok:
            self.logger.error(f"{tag} 锁定状态未达预期，跳过本次战斗")
            return "error"

        # 点击卡片 + 战斗，失败重试
        max_card_retries = 3
        for attempt in range(1, max_card_retries + 1):
            cx, cy = self._get_card_click_pos(card)
            self.adapter.adb.tap(self.adapter.cfg.adb_addr, cx, cy)
            self.logger.info(f"{tag} 点击卡片 ({cx}, {cy}) (attempt={attempt})")
            await asyncio.sleep(1.5)

            result = await run_battle(
                self.adapter, self.ui.capture_method,
                confirm_template=_TPL_JIEJIE_JINGONG,
                battle_timeout=120.0,
                log=self.logger,
                popup_handler=self.ui.popup_handler,
                lineup=battle_lineup,
                manual_lineup=manual_lineup if not has_lineup and is_first else None,
            )

            if result != "error":
                return result
            self.logger.warning(
                f"{tag} 战斗异常，重试点击卡片 (attempt={attempt})"
            )

        return "error"  # 所有重试均失败

    async def _handle_card_9(self, card, has_lineup: bool, lineup: dict) -> str:
        """处理第9张卡片（index 8）的特殊逻辑。

        流程:
        1. 确保阵容解锁
        2. 点击卡片
        3. 4次退出循环（进攻→退出→确认→失败画面→关闭）
        4. 锁定阵容
        5. 再点击卡片，正常战斗一次
        """
        tag = "[结界突破-卡片8(特殊)]"

        # 1. 确保阵容解锁
        await self._ensure_lock_state(should_lock=False)

        cx, cy = self._get_card_click_pos(card)

        # 2-3. 4次退出循环
        for exit_round in range(4):
            self.logger.info(f"{tag} 退出循环 {exit_round + 1}/4")

            # 点击卡片
            self.adapter.adb.tap(self.adapter.cfg.adb_addr, cx, cy)
            self.logger.info(f"{tag} 点击卡片 ({cx}, {cy})")
            await asyncio.sleep(1.5)

            # 等待并点击进攻确认
            clicked = await click_template(
                self.adapter, self.ui.capture_method, _TPL_JIEJIE_JINGONG,
                timeout=8.0, settle=0.5, post_delay=1.5,
                log=self.logger, label=f"卡片8-进攻确认-R{exit_round + 1}",
                popup_handler=self.ui.popup_handler,
            )
            if not clicked:
                self.logger.warning(
                    f"{tag} 退出循环 {exit_round + 1}: 未检测到进攻确认"
                )
                break  # 进攻确认检测不到时终止

            # 等待并点击退出
            clicked = await click_template(
                self.adapter, self.ui.capture_method, _TPL_JIEJIE_TUICHU,
                timeout=8.0, settle=0.5, post_delay=1.5,
                log=self.logger, label=f"卡片8-退出-R{exit_round + 1}",
                popup_handler=self.ui.popup_handler,
            )
            if not clicked:
                self.logger.warning(
                    f"{tag} 退出循环 {exit_round + 1}: 未检测到退出按钮，跳过当轮"
                )
                continue

            # 等待并点击确认退出
            clicked = await click_template(
                self.adapter, self.ui.capture_method, _TPL_JIEJIE_QUEREN,
                timeout=8.0, settle=0.5, post_delay=1.5,
                log=self.logger, label=f"卡片8-确认退出-R{exit_round + 1}",
                popup_handler=self.ui.popup_handler,
            )
            if not clicked:
                self.logger.warning(
                    f"{tag} 退出循环 {exit_round + 1}: 未检测到确认按钮，跳过当轮"
                )
                continue

            # 等待战斗失败画面出现并点击关闭
            clicked = await click_template(
                self.adapter, self.ui.capture_method, _TPL_ZHANDOU_SHIBAI,
                timeout=15.0, settle=0.5, post_delay=1.5,
                log=self.logger, label=f"卡片8-失败画面-R{exit_round + 1}",
                popup_handler=self.ui.popup_handler,
            )
            if not clicked:
                self.logger.warning(
                    f"{tag} 退出循环 {exit_round + 1}: 未检测到失败画面，跳过当轮"
                )
                continue

            # 等待回到结界突破界面
            await asyncio.sleep(2.0)
            self.logger.info(f"{tag} 退出循环 {exit_round + 1}/4 完成")

        # 4. 锁定阵容
        await self._ensure_lock_state(should_lock=True)

        # 5. 再次点击卡片，正常战斗
        self.logger.info(f"{tag} 退出循环结束，开始正常战斗")
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, cx, cy)
        self.logger.info(f"{tag} 点击卡片 ({cx}, {cy})")
        await asyncio.sleep(1.5)

        result = await run_battle(
            self.adapter, self.ui.capture_method,
            confirm_template=_TPL_JIEJIE_JINGONG,
            battle_timeout=120.0,
            log=self.logger,
            popup_handler=self.ui.popup_handler,
            lineup=None,  # 已锁定，不切换
        )

        return result

    async def _check_need_refresh_after_card9_defeat(self) -> bool:
        """检查第9张卡片失败后是否需要刷新网格。

        条件: 除了失败的卡片外，其他都是已击败状态。

        Returns:
            True 表示需要刷新
        """
        await asyncio.sleep(1.0)
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            return False

        grid = detect_tupo_grid(screenshot)
        non_defeated = [
            c for c in grid.cards if c.state != TupoCardState.DEFEATED
        ]

        if len(non_defeated) <= 1:
            self.logger.info(
                f"[结界突破] 第9张失败且其余已击败"
                f" (non_defeated={len(non_defeated)})，需要刷新"
            )
            return True

        self.logger.info(
            f"[结界突破] 第9张失败但还有其他未击败卡片"
            f" (non_defeated={len(non_defeated)})，不刷新"
        )
        return False

    async def _refresh_tupo_grid(self) -> bool:
        """点击刷新按钮重置结界突破网格。

        Returns:
            True 表示刷新成功
        """
        for attempt in range(1, 3):
            self.logger.info(
                f"[结界突破] 尝试刷新网格 (attempt={attempt}/2)"
            )

            # 点击刷新按钮
            clicked = await click_template(
                self.adapter, self.ui.capture_method, _TPL_JIEJIE_SHUAXIN,
                timeout=5.0, settle=0.5, post_delay=1.0,
                log=self.logger, label=f"结界突破-刷新(attempt={attempt}/2)",
                popup_handler=self.ui.popup_handler,
            )
            if not clicked:
                self.logger.warning(
                    f"[结界突破] 未检测到刷新按钮 (attempt={attempt}/2)"
                )
                await asyncio.sleep(1.0)
                continue

            # 点击确定
            clicked = await click_template(
                self.adapter, self.ui.capture_method, _TPL_JIEJIE_QUEDING,
                timeout=5.0, settle=0.5, post_delay=2.0,
                log=self.logger, label=f"结界突破-刷新确定(attempt={attempt}/2)",
                popup_handler=self.ui.popup_handler,
            )
            if not clicked:
                self.logger.warning(
                    f"[结界突破] 未检测到刷新确定按钮 (attempt={attempt}/2)"
                )
                await asyncio.sleep(1.0)
                continue

            self.logger.info("[结界突破] 网格刷新成功")
            self._read_tupo_ticket()
            return True

        self.logger.warning("[结界突破] 网格刷新重试 2 次均失败")
        return False

    def _make_result(
        self, victories: int, defeats: int, refreshes: int
    ) -> Dict[str, Any]:
        """构建结界突破执行结果。"""
        if victories > 0:
            return {
                "status": TaskStatus.SUCCEEDED,
                "message": (
                    f"结界突破完成: {victories}胜 {defeats}负"
                    f" {refreshes}次刷新"
                ),
                "victories": victories,
                "defeats": defeats,
                "refreshes": refreshes,
                "timestamp": datetime.utcnow().isoformat(),
            }
        else:
            return {
                "status": TaskStatus.FAILED,
                "error": f"结界突破未获胜: {victories}胜 {defeats}负",
                "victories": victories,
                "defeats": defeats,
                "refreshes": refreshes,
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def _run_tupo_loop(
        self, ticket_count: Optional[int]
    ) -> Dict[str, Any]:
        """执行结界突破战斗主循环。

        在成功进入结界突破界面后调用。

        Args:
            ticket_count: OCR 读取到的突破票数量，None 表示读取失败

        Returns:
            执行结果字典
        """
        # 获取阵容配置
        lineup_config = self.current_account.lineup_config or {}
        lineup = get_lineup_for_task(lineup_config, "结界突破")
        has_lineup = (
            lineup.get("group", 0) > 0 and lineup.get("position", 0) > 0
        )

        # 构建手动阵容（仅 init 账号在无预设阵容时自动配置）
        manual_lineup = None
        if not has_lineup and self.current_account.progress == "init":
            shikigami_cfg = self.current_account.shikigami_config or {}
            lineup_data = build_manual_lineup_info(shikigami_cfg)
            if lineup_data:
                manual_lineup = ManualLineupInfo(
                    rental_shikigami=lineup_data["rental_shikigami"],
                    zuofu_template=lineup_data["zuofu_template"],
                )
                self.logger.info(
                    f"[结界突破] init账号，将使用手动阵容: "
                    f"租借={[n for _, n, _ in manual_lineup.rental_shikigami]}, "
                    f"座敷={'有' if manual_lineup.zuofu_template else '无'}"
                )
        elif not has_lineup:
            self.logger.info("[结界突破] 未配置阵容预设，维持当前阵容")

        total_victories = 0
        total_defeats = 0
        refresh_count = 0

        for refresh_round in range(_MAX_REFRESH_ROUNDS):
            self.logger.info(
                f"[结界突破] 第 {refresh_round + 1} 轮扫描开始"
            )

            # 截图检测网格（3 次截图重试）
            screenshot = None
            grid = None
            for grid_attempt in range(1, 4):
                screenshot = self.adapter.capture(self.ui.capture_method)
                if screenshot is None:
                    self.logger.warning(
                        f"[结界突破] 截图失败 (attempt={grid_attempt}/3)"
                    )
                    await asyncio.sleep(0.5)
                    continue

                grid = detect_tupo_grid(screenshot)
                if grid.cards:
                    break
                self.logger.warning(
                    f"[结界突破] 网格检测未发现卡片 (attempt={grid_attempt}/3)"
                )
                await asyncio.sleep(0.5)

            if screenshot is None or grid is None or not grid.cards:
                self.logger.error("[结界突破] 网格检测重试 3 次均失败")
                break
            available = grid.get_available()

            self.logger.info(
                f"[结界突破] 网格状态: "
                f"已击败={grid.defeated_count}, "
                f"失败={grid.failed_count}, "
                f"未挑战={grid.not_challenged_count}, "
                f"可挑战={len(available)}"
            )

            if not available:
                self.logger.info("[结界突破] 所有卡片已击败，尝试刷新")
                refreshed = await self._refresh_tupo_grid()
                if refreshed:
                    refresh_count += 1
                    continue
                else:
                    self.logger.warning("[结界突破] 刷新失败，结束战斗")
                    break

            # 检查突破票
            if ticket_count is not None and ticket_count <= 0:
                self.logger.info("[结界突破] 突破票已用完，结束")
                break

            # 按 index 排序处理可挑战的卡片
            available.sort(key=lambda c: c.index)

            need_break = False
            for card_idx, card in enumerate(available):
                # 每次战斗前检查突破票
                current_ticket = self._read_tupo_ticket()
                if current_ticket is not None and current_ticket <= 0:
                    self.logger.info("[结界突破] 突破票耗尽，终止")
                    need_break = True
                    break

                is_first_card = (
                    total_victories == 0
                    and total_defeats == 0
                    and card_idx == 0
                    and refresh_round == 0
                )
                is_last_card = card.index == 8  # 第9张卡片

                if is_last_card:
                    result = await self._handle_card_9(
                        card, has_lineup, lineup
                    )
                else:
                    result = await self._handle_normal_card(
                        card, is_first_card, has_lineup, lineup,
                        manual_lineup=manual_lineup,
                    )

                if result == VICTORY:
                    total_victories += 1
                    self.logger.info(
                        f"[结界突破] 卡片 {card.index} 胜利 "
                        f"(总计: {total_victories}胜 {total_defeats}负)"
                    )
                elif result == DEFEAT:
                    total_defeats += 1
                    self.logger.warning(
                        f"[结界突破] 卡片 {card.index} 失败 "
                        f"(总计: {total_victories}胜 {total_defeats}负)"
                    )
                    # 第9张失败特殊处理
                    if is_last_card:
                        should_refresh = (
                            await self._check_need_refresh_after_card9_defeat()
                        )
                        if should_refresh:
                            refreshed = await self._refresh_tupo_grid()
                            if refreshed:
                                refresh_count += 1
                                break  # 跳出 available 循环，外层重新扫描
                else:
                    self.logger.error(
                        f"[结界突破] 卡片 {card.index} 异常结果: {result}"
                    )
                    # 非胜利/失败结果，等待恢复
                    await asyncio.sleep(2.0)

                # 等待回到结界突破界面
                await asyncio.sleep(1.5)

            if need_break:
                break

        return self._make_result(
            total_victories, total_defeats, refresh_count
        )
