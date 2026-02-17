"""
对弈竞猜执行器 - 状态机驱动

状态机循环：截图检测当前状态 → 执行对应操作 → 再检测 → 直到完成或超限。
具备从任意界面恢复的能力，关键操作采用快速多轮识别+点击机制。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, Optional

from ...core.constants import TaskStatus
from ...core.logger import logger
from ...core.timeutils import now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ui.manager import UIManager
from ..vision.grid_detect import nms_by_distance
from ..vision.template import Match, find_all_templates, match_template
from ..vision.utils import to_gray
from .base import BaseExecutor
from .helpers import click_template, wait_for_template

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"


class DuiyiState(Enum):
    """对弈竞猜状态枚举"""
    TINGYUAN = auto()       # 在庭院，需点击 dy_rukou.png 进入
    DY_WIN = auto()         # 上次赢了，dy_ying.png 可见，奖励未领取
    DY_JIANGLI = auto()     # 奖励弹窗 dy_jiangli.png 可见
    DY_NEXT = auto()        # dy_next.png 可见（输了/赢了已领奖后）
    DY_BET = auto()         # 本次未押注，可以押注
    DY_ALREADY_BET = auto() # 本次已押注（TODO，暂返回 SKIPPED）
    UNKNOWN = auto()        # 未知状态，回庭院重来


class DuiyiJingcaiExecutor(BaseExecutor):
    """对弈竞猜执行器 - 状态机驱动"""

    # ── 模板路径常量 ──
    _TPL_DY_RUKOU = "assets/ui/templates/dy/dy_rukou.png"
    _TPL_DY_YING = "assets/ui/templates/dy/dy_ying.png"
    _TPL_DY_NEXT = "assets/ui/templates/dy/dy_next.png"
    _TPL_JIANGLI = "assets/ui/templates/dy/dy_jiangli.png"
    _TPL_DY_LEFT = "assets/ui/templates/dy/dy_left.png"
    _TPL_DY_RIGHT = "assets/ui/templates/dy/dy_right.png"
    _TPL_DY_30 = "assets/ui/templates/dy/dy_30.png"
    _TPL_POPUP_JINBI = "assets/ui/templates/dy/popup_jinbi.png"
    _TPL_DY_JINGCAI = "assets/ui/templates/dy/dy_jingcai.png"
    _TPL_DY_QUEDING = "assets/ui/templates/dy/dy_queding.png"
    _TPL_DY_FINISH_LEFT = "assets/ui/templates/dy/dy_finish_left.png"
    _TPL_DY_FINISH_RIGHT = "assets/ui/templates/dy/dy_finish_right.png"

    # ── 配置常量 ──
    _MAX_STATE_ITERATIONS = 15
    _SCREEN_CENTER_X = 480  # 960x540 屏幕中线，用于按 X 坐标区分左右按钮
    _DUIYI_WINDOWS = ["10:00", "12:00", "14:00", "16:00", "18:00", "20:00", "22:00"]

    def __init__(
        self,
        worker_id: int,
        emulator_id: int,
        emulator_row: Optional[Emulator] = None,
        system_config: Optional[SystemConfig] = None,
        answer: Optional[str] = None,
    ):
        super().__init__(worker_id=worker_id, emulator_id=emulator_id)
        self.emulator_row = emulator_row
        self.system_config = system_config
        self._payload_answer = answer
        self.adapter: Optional[EmulatorAdapter] = None
        self.ui: Optional[UIManager] = None

    # ── 构造 Adapter ──

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
            activity_name=(
                syscfg.activity_name or ".MainActivity"
                if syscfg
                else ".MainActivity"
            ),
        )
        return EmulatorAdapter(cfg)

    # ── BaseExecutor 生命周期 ──

    async def prepare(self, task: Task, account: GameAccount) -> bool:
        """准备阶段：构造 Adapter 或复用 shared_adapter，push 登录数据。"""
        self.logger.info(f"[对弈竞猜] 准备: account={account.login_id}")

        # 批次复用
        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[对弈竞猜] 复用 shared_adapter，跳过 push 登录数据")
            return True

        # 从 DB 加载 emulator_row（若未传入）
        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error(f"[对弈竞猜] 模拟器不存在: id={self.emulator_id}")
            return False

        self.adapter = self._build_adapter()

        # push 登录数据
        ok = self.adapter.push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[对弈竞猜] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[对弈竞猜] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        """执行阶段：确保游戏就绪 → 获取答案 → 运行状态机。"""
        self.logger.info(f"[对弈竞猜] 执行: account={self.current_account.login_id}")

        # 构造或复用 UIManager
        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = (
                self.system_config.capture_method if self.system_config else None
            ) or "adb"
            self.ui = UIManager(self.adapter, capture_method=capture_method)

        # 确保游戏就绪
        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            self.logger.error("[对弈竞猜] 游戏就绪失败")
            return self._fail("游戏就绪失败")

        # 获取当前窗口答案
        answer = self._get_current_answer()
        if not answer:
            self.logger.warning("[对弈竞猜] 当前窗口无答案配置，跳过")
            return {
                "status": TaskStatus.SKIPPED,
                "message": "当前窗口无对弈竞猜答案配置",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 运行状态机
        return await self._run_state_machine(answer)

    async def cleanup(self) -> None:
        """停止游戏（批次中非最后一个任务跳过）"""
        if self.skip_cleanup:
            self.logger.info("[对弈竞猜] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[对弈竞猜] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[对弈竞猜] 停止游戏失败: {e}")

    # ── 答案获取 ──

    def _get_current_answer(self) -> Optional[str]:
        """获取当前窗口的对弈竞猜答案。优先使用 Feeder 传入的 payload 答案。"""
        # 优先使用 Feeder 已验证的答案（避免 system_config 缓存过期问题）
        if self._payload_answer in ("左", "右"):
            self.logger.info(f"[对弈竞猜] 使用 Feeder 传入答案: {self._payload_answer}")
            return self._payload_answer

        # 回退：从 system_config 读取
        if not self.system_config or not self.system_config.duiyi_jingcai_answers:
            self.logger.warning("[对弈竞猜] 无全局答案配置")
            return None

        answers = self.system_config.duiyi_jingcai_answers
        today_str = now_beijing().strftime("%Y-%m-%d")
        if answers.get("date") != today_str:
            self.logger.warning(
                f"[对弈竞猜] 答案日期不匹配: {answers.get('date')} != {today_str}"
            )
            return None

        # 确定当前窗口
        hour = now_beijing().hour
        if hour < 10:
            self.logger.info("[对弈竞猜] 当前时间 < 10:00，无窗口")
            return None

        current_window = None
        for t in self._DUIYI_WINDOWS:
            h = int(t.split(":")[0])
            if hour >= h:
                current_window = t

        if not current_window:
            return None

        answer = answers.get(current_window)
        if answer not in ("左", "右"):
            self.logger.warning(
                f"[对弈竞猜] 窗口 {current_window} 答案无效: {answer}"
            )
            return None

        self.logger.info(f"[对弈竞猜] 当前窗口={current_window}, 答案={answer}")
        return answer

    # ── 状态检测 ──

    async def _detect_state(self) -> DuiyiState:
        """截图检测当前所处的对弈竞猜状态。

        按优先级从高到低匹配多个模板，不使用 popup_handler（避免
        jiangli 被自动关闭而状态机无法感知）。
        截图预转灰度后复用，避免每次 match_template 重复转换。
        """
        screenshot = await self._capture()
        if screenshot is None:
            self.logger.warning("[对弈竞猜] 状态检测: 截图失败")
            return DuiyiState.UNKNOWN

        gray = to_gray(screenshot)  # 只转一次灰度，后续复用

        # 1. 奖励弹窗（遮挡其他元素，最优先）
        m = match_template(gray, self._TPL_JIANGLI)
        if m:
            self.logger.info(f"[对弈竞猜] 状态: DY_JIANGLI (score={m.score:.3f})")
            return DuiyiState.DY_JIANGLI

        # 1.5 金币弹窗（也属于 JIANGLI 类弹窗，同样关闭处理）
        m = match_template(gray, self._TPL_POPUP_JINBI)
        if m:
            self.logger.info(f"[对弈竞猜] 状态: DY_JIANGLI/popup_jinbi (score={m.score:.3f})")
            return DuiyiState.DY_JIANGLI

        # 2. 已押注完成（dy_finish_left / dy_finish_right）
        for finish_tpl in (self._TPL_DY_FINISH_LEFT, self._TPL_DY_FINISH_RIGHT):
            m = match_template(gray, finish_tpl)
            if m:
                self.logger.info(f"[对弈竞猜] 状态: DY_ALREADY_BET (score={m.score:.3f})")
                return DuiyiState.DY_ALREADY_BET

        # 3. 赢了未领奖
        m = match_template(gray, self._TPL_DY_YING)
        if m:
            self.logger.info(f"[对弈竞猜] 状态: DY_WIN (score={m.score:.3f})")
            return DuiyiState.DY_WIN

        # 4. 下一局按钮
        m = match_template(gray, self._TPL_DY_NEXT)
        if m:
            self.logger.info(f"[对弈竞猜] 状态: DY_NEXT (score={m.score:.3f})")
            return DuiyiState.DY_NEXT

        # 5. 押注界面：只检测 dy_jingcai（最具辨识度）
        m = match_template(gray, self._TPL_DY_JINGCAI)
        if m:
            self.logger.info(f"[对弈竞猜] 状态: DY_BET (score={m.score:.3f})")
            return DuiyiState.DY_BET

        # 6. 对弈入口（在庭院可见）
        m = match_template(gray, self._TPL_DY_RUKOU)
        if m:
            self.logger.info(f"[对弈竞猜] 状态: TINGYUAN (score={m.score:.3f})")
            return DuiyiState.TINGYUAN

        # 7. UIManager 检测庭院
        detect_result = await self._detect_ui(screenshot)
        if detect_result and detect_result.ui == "TINGYUAN":
            self.logger.info("[对弈竞猜] 状态: TINGYUAN (UIDetector)")
            return DuiyiState.TINGYUAN

        self.logger.info(
            f"[对弈竞猜] 状态: UNKNOWN "
            f"(UI={detect_result.ui if detect_result else 'None'})"
        )
        return DuiyiState.UNKNOWN

    # ── 快速多轮检测 ──

    async def _rapid_detect_state(self, rapid_count: int = 3, interval: float = 0.15) -> DuiyiState:
        """快速多轮截图检测状态，取首次非 UNKNOWN 结果。

        避免单次截图因动画或瞬态导致误判。
        """
        for i in range(rapid_count):
            state = await self._detect_state()
            if state != DuiyiState.UNKNOWN:
                return state
            if i < rapid_count - 1:
                await asyncio.sleep(interval)
        return DuiyiState.UNKNOWN

    # ── 状态机主循环 ──

    async def _run_state_machine(self, answer: str) -> Dict[str, Any]:
        """状态机主循环：检测状态 → 处理 → 再检测 → 直到完成或超限。"""
        for iteration in range(self._MAX_STATE_ITERATIONS):
            # 快速多轮检测当前状态
            state = await self._rapid_detect_state()
            self.logger.info(
                f"[对弈竞猜] 迭代 {iteration + 1}/{self._MAX_STATE_ITERATIONS}, "
                f"状态={state.name}"
            )

            if state == DuiyiState.TINGYUAN:
                ok = await self._handle_tingyuan()
                if not ok:
                    return self._fail("从庭院进入对弈失败")

            elif state == DuiyiState.DY_WIN:
                ok = await self._handle_dy_win()
                if not ok:
                    return self._fail("领取胜利奖励失败")

            elif state == DuiyiState.DY_JIANGLI:
                ok = await self._handle_dy_jiangli()
                if not ok:
                    return self._fail("关闭奖励弹窗失败")

            elif state == DuiyiState.DY_NEXT:
                ok = await self._handle_dy_next()
                if not ok:
                    return self._fail("点击下一局失败")

            elif state == DuiyiState.DY_BET:
                ok = await self._handle_dy_bet(answer)
                if not ok:
                    return self._fail("押注失败")
                # 押注完成，返回成功
                return {
                    "status": TaskStatus.SUCCEEDED,
                    "answer": answer,
                    "timestamp": datetime.utcnow().isoformat(),
                }

            elif state == DuiyiState.DY_ALREADY_BET:
                self.logger.info("[对弈竞猜] 本轮已押注，跳过")
                return {
                    "status": TaskStatus.SKIPPED,
                    "message": "本轮已押注",
                    "timestamp": datetime.utcnow().isoformat(),
                }

            elif state == DuiyiState.UNKNOWN:
                self.logger.warning("[对弈竞猜] 未知状态，尝试回庭院")
                ok = await self._try_back_to_tingyuan()
                if not ok:
                    return self._fail("回庭院失败")

            # 状态转换间短暂等待
            await asyncio.sleep(0.15)

        return self._fail(f"状态机超过最大迭代次数 ({self._MAX_STATE_ITERATIONS})")

    # ── 各状态处理 ──

    async def _handle_tingyuan(self) -> bool:
        """在庭院中点击对弈入口进入。"""
        return await self._rapid_click_template(
            self._TPL_DY_RUKOU,
            timeout=5.0,
            settle=0.15,
            post_delay=0.8,
            label="对弈竞猜-点击入口",
        )

    async def _handle_dy_win(self) -> bool:
        """上次赢了未领奖：dy_ying.png 可见，点击领取奖励。

        优先检测 dy_next.png，若存在则先点击下一局，让状态机重新识别；
        否则使用系统配置中的矩形区域随机点击领奖，未配置则回退模板匹配位置。
        """
        m = await wait_for_template(
            self.adapter,
            self.ui.capture_method,
            self._TPL_DY_YING,
            timeout=3.0,
            interval=0.2,
            log=self.logger,
            label="对弈竞猜-赢了领奖",
        )
        if not m:
            return False

        # 先检测 dy_next.png，若存在则优先点击下一局
        screenshot = await self._capture()
        if screenshot is not None:
            gray = to_gray(screenshot)
            m_next = match_template(gray, self._TPL_DY_NEXT)
            if m_next:
                cx, cy = m_next.random_point()
                await self._tap(cx, cy)
                self.logger.info(f"[对弈竞猜] DY_WIN 检测到 dy_next，优先点击下一局 ({cx}, {cy})")
                await asyncio.sleep(0.8)
                return True  # 让状态机重新检测画面

        # 优先使用配置的矩形区域随机点击
        coord = getattr(self.system_config, 'duiyi_reward_coord', None) if self.system_config else None
        if coord and all(k in coord for k in ('x1', 'y1', 'x2', 'y2')):
            import random
            cx = random.randint(int(coord['x1']), int(coord['x2']))
            cy = random.randint(int(coord['y1']), int(coord['y2']))
            self.logger.info(f"[对弈竞猜] 使用配置区域 ({coord['x1']},{coord['y1']})-({coord['x2']},{coord['y2']})")
        else:
            # 回退：使用模板匹配位置
            cx, cy = m.random_point()

        await self._tap(cx, cy)
        self.logger.info(f"[对弈竞猜] 点击领取胜利奖励 ({cx}, {cy})")
        await asyncio.sleep(0.8)
        return True

    async def _handle_dy_jiangli(self) -> bool:
        """关闭奖励弹窗：点击 (20, 20) 关闭。

        参考 default_popups.py 中 jiangli 的处理方式。
        关闭后可能出现插画(chahua)弹窗，由 popup_handler 自动处理。
        """
        from ..vision.utils import random_point_in_circle

        close_x, close_y = random_point_in_circle(20, 20, 20)
        await self._tap(close_x, close_y)
        self.logger.info(f"[对弈竞猜] 点击 ({close_x}, {close_y}) 关闭奖励弹窗")
        await asyncio.sleep(0.5)

        # 主动检查一次弹窗（处理可能的插画 chahua 等级联弹窗）
        if self.popup_handler:
            screenshot = await self._capture()
            if screenshot:
                await self.popup_handler.check_and_dismiss(screenshot)
        return True

    async def _handle_dy_next(self) -> bool:
        """点击 dy_next.png 进入下一局押注界面。"""
        return await self._rapid_click_template(
            self._TPL_DY_NEXT,
            timeout=5.0,
            settle=0.15,
            post_delay=0.8,
            label="对弈竞猜-下一局",
        )

    def _find_direction_buttons(
        self,
        screenshot,
    ) -> tuple[Optional[Match], Optional[Match]]:
        """在截图中定位左右方向按钮，用 X 坐标区分而非模板内容。

        dy_left.png 和 dy_right.png 视觉相似容易交叉匹配，因此同时用两个
        模板搜索所有匹配，合并去重后按 X 坐标判定左右。

        Returns:
            (left_match, right_match) - 左/右按钮的 Match，未找到返回 None。
        """
        gray = to_gray(screenshot) if screenshot.ndim != 2 else screenshot
        matches_l = find_all_templates(gray, self._TPL_DY_LEFT, threshold=0.80)
        matches_r = find_all_templates(gray, self._TPL_DY_RIGHT, threshold=0.80)

        all_matches = matches_l + matches_r
        if not all_matches:
            return None, None

        all_matches.sort(key=lambda m: m.score, reverse=True)
        unique = nms_by_distance(all_matches)

        self.logger.info(
            f"[对弈竞猜] 方向按钮检测: 合并 {len(matches_l)}+{len(matches_r)}="
            f"{len(all_matches)} 个匹配, NMS 后 {len(unique)} 个"
        )

        left_match: Optional[Match] = None
        right_match: Optional[Match] = None

        if len(unique) == 1:
            m = unique[0]
            if m.center[0] < self._SCREEN_CENTER_X:
                left_match = m
            else:
                right_match = m
            self.logger.info(
                f"[对弈竞猜] 仅找到 1 个按钮, X={m.center[0]}, "
                f"判定为{'左' if left_match else '右'}"
            )
        else:
            unique.sort(key=lambda m: m.center[0])
            left_match = unique[0]
            right_match = unique[-1]
            self.logger.info(
                f"[对弈竞猜] 左按钮 X={left_match.center[0]} "
                f"score={left_match.score:.3f}, "
                f"右按钮 X={right_match.center[0]} "
                f"score={right_match.score:.3f}"
            )

        return left_match, right_match

    async def _handle_dy_bet(self, answer: str) -> bool:
        """根据答案完成押注全流程。answer 为 '左' 或 '右'。

        完整步骤：
        1. 点击 dy_left.png 或 dy_right.png（选择方向）
        2. 点击 dy_30.png（选择押注额度）
        3. 关闭 popup_jinbi.png（金币弹窗，用 jiangli 方式点击 20,20 关闭）
        4. 点击 dy_jingcai.png（竞猜按钮）
        5. 点击 dy_queding.png（确定按钮）
        6. 验证：识别 dy_finish_left.png 或 dy_finish_right.png 确认押注成功
        """
        from ..vision.utils import random_point_in_circle

        # ── 步骤 1：选择方向（基于 X 坐标判断左右，避免模板误识别） ──
        self.logger.info(f"[对弈竞猜] 步骤1: 选择方向 {answer}")

        target_match: Optional[Match] = None
        elapsed = 0.0
        timeout = 8.0
        interval = 0.2

        while elapsed < timeout:
            screenshot = await self._capture()
            if screenshot is not None:
                if self.popup_handler:
                    dismissed = await self.popup_handler.check_and_dismiss(screenshot)
                    if dismissed > 0:
                        await asyncio.sleep(interval)
                        elapsed += interval
                        continue

                left_match, right_match = self._find_direction_buttons(screenshot)
                target_match = left_match if answer == "左" else right_match
                if target_match:
                    break

            await asyncio.sleep(interval)
            elapsed += interval

        if not target_match:
            self.logger.warning(
                f"[对弈竞猜] 方向按钮未找到: {answer} (超时 {timeout}s)"
            )
            return False

        cx, cy = target_match.random_point()
        await self._tap(cx, cy)
        self.logger.info(
            f"[对弈竞猜] 点击{answer}按钮 ({cx}, {cy}) "
            f"score={target_match.score:.3f}"
        )
        await asyncio.sleep(0.5)  # post_delay

        # ── 步骤 2：选择押注额度 dy_30.png ──
        self.logger.info("[对弈竞猜] 步骤2: 选择押注额度 dy_30")
        ok = await self._rapid_click_template(
            self._TPL_DY_30,
            timeout=4.0,
            settle=0.1,
            post_delay=0.5,
            label="对弈竞猜-押注额度",
        )
        if not ok:
            self.logger.warning("[对弈竞猜] dy_30 模板未找到")
            return False

        # ── 步骤 3：关闭金币弹窗 popup_jinbi.png ──
        self.logger.info("[对弈竞猜] 步骤3: 关闭金币弹窗")
        await self._dismiss_popup_jinbi()

        # ── 步骤 4：点击竞猜按钮 dy_jingcai.png ──
        self.logger.info("[对弈竞猜] 步骤4: 点击竞猜按钮")
        ok = await self._rapid_click_template(
            self._TPL_DY_JINGCAI,
            timeout=4.0,
            settle=0.1,
            post_delay=0.5,
            label="对弈竞猜-竞猜",
        )
        if not ok:
            self.logger.warning("[对弈竞猜] dy_jingcai 模板未找到")
            return False

        # ── 步骤 5：点击确定按钮 dy_queding.png ──
        self.logger.info("[对弈竞猜] 步骤5: 点击确定按钮")
        ok = await self._rapid_click_template(
            self._TPL_DY_QUEDING,
            timeout=4.0,
            settle=0.1,
            post_delay=0.6,
            label="对弈竞猜-确定",
        )
        if not ok:
            self.logger.warning("[对弈竞猜] dy_queding 模板未找到")
            return False

        # ── 步骤 6：验证押注完成 ──
        finish_tpl = (
            self._TPL_DY_FINISH_LEFT if answer == "左" else self._TPL_DY_FINISH_RIGHT
        )
        self.logger.info(f"[对弈竞猜] 步骤6: 验证押注完成，识别 {finish_tpl}")
        m = await wait_for_template(
            self.adapter,
            self.ui.capture_method,
            finish_tpl,
            timeout=6.0,
            interval=0.2,
            log=self.logger,
            label=f"对弈竞猜-验证{answer}",
        )
        if m:
            self.logger.info(
                f"[对弈竞猜] 押注 {answer} 验证成功 (score={m.score:.3f})"
            )
            return True

        self.logger.warning(f"[对弈竞猜] 押注验证超时，finish 模板未找到")
        return False

    async def _dismiss_popup_jinbi(self) -> None:
        """关闭金币弹窗 popup_jinbi.png。

        用 jiangli.png 相同的方式关闭：点击 (20, 20) 附近随机位置。
        快速多轮检测确保弹窗确实出现再关闭。
        """
        from ..vision.utils import random_point_in_circle

        # 等待弹窗出现
        m = await wait_for_template(
            self.adapter,
            self.ui.capture_method,
            self._TPL_POPUP_JINBI,
            timeout=3.0,
            interval=0.2,
            log=self.logger,
            label="对弈竞猜-金币弹窗",
        )
        if not m:
            self.logger.info("[对弈竞猜] 未检测到金币弹窗，跳过关闭")
            return

        # 关闭弹窗：点击 (20, 20) 附近
        close_x, close_y = random_point_in_circle(20, 20, 20)
        await self._tap(close_x, close_y)
        self.logger.info(f"[对弈竞猜] 点击 ({close_x}, {close_y}) 关闭金币弹窗")
        await asyncio.sleep(0.5)

        # 可能有级联弹窗，再检查一次
        if self.popup_handler:
            screenshot = await self._capture()
            if screenshot:
                await self.popup_handler.check_and_dismiss(screenshot)

    # ── 快速多轮检测+点击（移植自 ClimbTowerExecutor） ──

    async def _rapid_click_template(
        self,
        template: str,
        *,
        timeout: float = 8.0,
        settle: float = 0.15,
        post_delay: float = 0.5,
        threshold: float | None = None,
        label: str = "",
        rapid_count: int = 3,
        rapid_interval: float = 0.12,
        wait_interval: float = 0.2,
    ) -> bool:
        """快速多次截图检测+点击模式。

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
        kwargs = {"threshold": threshold} if threshold is not None else {}

        # Phase 1: 等待模板出现
        m = await wait_for_template(
            self.adapter,
            self.ui.capture_method,
            template,
            timeout=timeout,
            interval=wait_interval,
            threshold=threshold,
            log=self.logger,
            label=label,
            popup_handler=self.popup_handler,
        )

        # Phase 2: settle（仅模板找到时）
        if m and settle > 0:
            await asyncio.sleep(settle)

        # Phase 3: 快速连续检测 + 点击
        clicked_count = 0
        for i in range(rapid_count):
            screenshot = await self._capture()
            if screenshot is None:
                await asyncio.sleep(rapid_interval)
                continue

            # 弹窗检查
            if self.popup_handler:
                dismissed = await self.popup_handler.check_and_dismiss(screenshot)
                if dismissed > 0:
                    await asyncio.sleep(rapid_interval)
                    continue

            rm = match_template(
                to_gray(screenshot) if screenshot.ndim != 2 else screenshot,
                template, **kwargs,
            )
            if rm:
                cx, cy = rm.random_point()
                await self._tap(cx, cy)
                clicked_count += 1
                self.logger.info(
                    f"{tag}快速点击 ({cx}, {cy}) "
                    f"(cycle={i + 1}/{rapid_count}, "
                    f"total_clicks={clicked_count}, "
                    f"score={rm.score:.3f})"
                )

            await asyncio.sleep(rapid_interval)

        if clicked_count > 0:
            self.logger.info(f"{tag}快速检测完成, 共点击{clicked_count}次")
        else:
            self.logger.warning(f"{tag}快速检测{rapid_count}次均未找到模板")

        # Phase 4: post_delay（仅点击成功时）
        if clicked_count > 0 and post_delay > 0:
            await asyncio.sleep(post_delay)

        return clicked_count > 0

    # ── 恢复到庭院 ──

    async def _try_back_to_tingyuan(self) -> bool:
        """尝试从当前状态返回庭院。"""
        # 1. 检查是否已在庭院
        detect_result = await self._detect_ui()
        if detect_result and detect_result.ui == "TINGYUAN":
            return True

        # 2. 已知 UI → ensure_ui 导航
        if detect_result and detect_result.ui not in ("UNKNOWN", None):
            ok = await self.ui.ensure_ui("TINGYUAN", max_steps=6, step_timeout=3.0)
            if ok:
                return True

        # 3. 未知界面：连续尝试点击 back / exit
        for i in range(5):
            clicked = await click_template(
                self.adapter,
                self.ui.capture_method,
                "assets/ui/templates/back.png",
                timeout=2.0,
                settle=0.2,
                post_delay=0.8,
                log=self.logger,
                label=f"对弈竞猜-回退({i + 1}/5)",
                popup_handler=self.popup_handler,
            )
            if not clicked:
                await click_template(
                    self.adapter,
                    self.ui.capture_method,
                    "assets/ui/templates/exit.png",
                    timeout=1.5,
                    settle=0.2,
                    post_delay=0.8,
                    log=self.logger,
                    label=f"对弈竞猜-退出({i + 1}/5)",
                    popup_handler=self.popup_handler,
                )
            detect_result = await self._detect_ui()
            if detect_result and detect_result.ui == "TINGYUAN":
                return True

        # 4. 兜底：go_to_tingyuan
        return await self.ui.go_to_tingyuan()

    # ── 辅助方法 ──

    def _fail(self, error: str) -> Dict[str, Any]:
        """构造失败结果。"""
        self.logger.error(f"[对弈竞猜] {error}")
        return {
            "status": TaskStatus.FAILED,
            "error": error,
            "timestamp": datetime.utcnow().isoformat(),
        }
