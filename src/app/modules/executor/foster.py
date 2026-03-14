"""
寄养执行器 - 导航到结界养成界面，检查寄养状态，选择最佳结界卡进行寄养
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus, TaskType
from ...core.logger import logger
from ...core.timeutils import format_beijing_time, now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..emu.adb import AdbError
from ..ui.manager import UIManager
from ..vision.template import Match, match_template
from .base import BaseExecutor
from .helpers import click_template, discover_template_paths, wait_for_template
from ..ocr.async_recognize import async_ocr_digits
import cv2
import numpy as np

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# ---------------------------------------------------------------------------
# 模板路径常量
# ---------------------------------------------------------------------------
_TPL_BLANK = "assets/ui/templates/jy_blank.png"
_TPL_KUAQU = "assets/ui/templates/jy_kuaqu.png"
_TPL_HAOYOU = "assets/ui/templates/jy_haoyou.png"
_TPL_JINRUJIEJIE = "assets/ui/templates/jy_jinrujiejie.png"
_TPL_DAODI = "assets/ui/templates/jy_daodi.png"
_TPL_WFXL = "assets/ui/templates/jy_wfxl.png"

# 自动同意好友申请用模板
_TPL_TIANJIA = discover_template_paths("tianjia")
_TPL_FRIEND_TONGYI = "assets/ui/templates/friend_tongyi.png"

# 领取饭盒用模板
_TPL_FANHE_QUCHU = "assets/ui/templates/fanhe_quchu.png"
_TPL_JIANGLI = "assets/ui/templates/jiangli.png"

# 寄养确认用模板
_TPL_QUEDING = "assets/ui/templates/jy_queding.png"
_TPL_BACK = "assets/ui/templates/back.png"
_TPL_EXIT_DARK = "assets/ui/templates/exit_dark.png"
_TPL_TAG_JIEJIE = "assets/ui/templates/tag_jiejie.png"

# 进入结界后放置式神的固定坐标
_FOSTER_PLACE_X = 153
_FOSTER_PLACE_Y = 434

# 自动同意好友申请最大循环次数
_MAX_ACCEPT_FRIEND_LOOPS = 30

# 奖励模板 {key: path}
_REWARD_TEMPLATES: Dict[str, str] = {
    "6xtg": "assets/ui/templates/jy_6xtg.png",
    "6xdy": "assets/ui/templates/jy_6xdy.png",
    "5xtg": "assets/ui/templates/jy_5xtg.png",
    "5xdy": "assets/ui/templates/jy_5xdy.png",
    "4xtg": "assets/ui/templates/jy_4xtg.png",
    "4xdy": "assets/ui/templates/jy_4xdy.png",
}

# 低星奖励模板（1x-3x），仅当 foster_low_star 启用时使用
_LOW_STAR_REWARD_TEMPLATES: Dict[str, str] = {
    "3xtg": "assets/ui/templates/jy_3xtg.png",
    "3xdy": "assets/ui/templates/jy_3xdy.png",
    "2xtg": "assets/ui/templates/jy_2xtg.png",
    "2xdy": "assets/ui/templates/jy_2xdy.png",
    "1xtg": "assets/ui/templates/jy_1xtg.png",
    "1xdy": "assets/ui/templates/jy_1xdy.png",
}

# 仅用于"存在感知"的模板（阻止无奖励早停，但不加入备选池）
_PRESENCE_TEMPLATES: Dict[str, str] = {
    "6xty": "assets/ui/templates/jy_6xty.png",   # 太阴
}

# 预设优先级排序
_GOUYU_PRIORITY = ["6xtg", "5xtg", "4xtg"]  # 勾玉优先：只寄养太鼓
_TILI_PRIORITY = ["6xdy", "5xdy", "4xdy"]   # 体力优先：只寄养斗鱼
_DEFAULT_CUSTOM_PRIORITY = ["6xtg", "6xdy", "5xtg", "5xdy", "4xtg", "4xdy"]

# 低星扩展追加项
_GOUYU_LOW_STAR_EXT = ["3xtg", "2xtg", "1xtg"]
_TILI_LOW_STAR_EXT = ["3xdy", "2xdy", "1xdy"]

# 预设模式的"立即寄养"目标集合
_GOUYU_IMMEDIATE: Set[str] = {"6xtg"}
_TILI_IMMEDIATE: Set[str] = {"6xdy"}

# 奖励代码→中文可读标签
_REWARD_LABELS: Dict[str, str] = {
    "6xtg": "6x太鼓",
    "5xtg": "5x太鼓",
    "4xtg": "4x太鼓",
    "6xdy": "6x斗鱼",
    "5xdy": "5x斗鱼",
    "4xdy": "4x斗鱼",
    "3xtg": "3x太鼓",
    "2xtg": "2x太鼓",
    "1xtg": "1x太鼓",
    "3xdy": "3x斗鱼",
    "2xdy": "2x斗鱼",
    "1xdy": "1x斗鱼",
}


def _reward_label(code: str) -> str:
    """将奖励代码转为中文可读标签，如 '6xtg' → '6x太鼓'"""
    return _REWARD_LABELS.get(code, code)

# 滚动参数
_SCROLL_X = 306
_SCROLL_Y_FROM = 440
_SCROLL_Y_TO = 290   # 向上 ~150px
_SCROLL_DUR_MS = 400

# 到底检测区域 (x, y, w, h)
_DAODI_ROI = (136, 389, 17, 9)

# 无法下拉检测区域 (x, y, w, h) — 左上角(135,141) 右下角(145,151)
_WFXL_ROI = (135, 141, 10, 10)

# 4xtg/5xtg 区分：底部灰色图标段数
# 4xtg底部：4心 + 2灰图标 → 灰色列段数 = 3（含边缘噪声）
# 5xtg底部：5心 + 1灰图标 → 灰色列段数 = 2
# 规则：gray_segments >= 3 → 4xtg，否则 → 5xtg
_TG_GRAY_S_MAX = 60    # 灰色饱和度上限
_TG_GRAY_V_MIN = 60    # 灰色亮度下限
_TG_STRIP_ROWS = 10    # 取底部行数
_TG_COL_THR = 0.3      # 列灰色像素占比阈值
_TG_SEG_THR = 3        # 段数 >= 此值 → 4xtg

# 寄养倒计时 OCR 区域 (x, y, w, h)
_FOSTER_TIME_ROI = (863, 93, 61, 14)  # 左上角(863,93) 右下角(924,107)

# 寄养位固定坐标
_FOSTER_SLOT_X = 458
_FOSTER_SLOT_Y = 256


@dataclass
class FosterCandidate:
    """扫描发现的候选寄养位"""
    reward_type: str      # "6xtg", "5xdy" 等
    list_type: str        # "kuaqu" 或 "haoyou"
    match_x: int          # 匹配位置 x
    match_y: int          # 匹配位置 y
    scroll_count: int     # 到达该位置的滚动次数


class FosterExecutor(BaseExecutor):
    """寄养执行器"""

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
        # 可用奖励模板（过滤掉磁盘上不存在的）
        self._available_rewards: Dict[str, str] = {}
        # 存在感知模板（阻止无奖励早停，但不加入备选池）
        self._available_presence: Dict[str, str] = {}
        self._missing_logged: bool = False

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
            activity_name=syscfg.activity_name or ".MainActivity"
            if syscfg
            else ".MainActivity",
        )
        return EmulatorAdapter(cfg)

    def _init_available_rewards(self, foster_low_star: bool = False) -> None:
        """初始化可用奖励模板，跳过磁盘上不存在的文件"""
        available = {}
        missing = []
        for key, path in _REWARD_TEMPLATES.items():
            if Path(path).exists():
                available[key] = path
            else:
                missing.append(key)
        # 低星模板（仅当启用时加载）
        if foster_low_star:
            for key, path in _LOW_STAR_REWARD_TEMPLATES.items():
                if Path(path).exists():
                    available[key] = path
                else:
                    missing.append(key)
        self._available_rewards = available
        if missing and not self._missing_logged:
            self._missing_logged = True
            self.logger.warning(
                f"[寄养] 缺失奖励模板: {', '.join(missing)}，对应类型将无法识别"
            )
        # 初始化存在感知模板
        presence = {}
        for key, path in _PRESENCE_TEMPLATES.items():
            if Path(path).exists():
                presence[key] = path
            else:
                self.logger.debug(f"[寄养] 存在感知模板不存在，跳过: {key} ({path})")
        self._available_presence = presence

    # ------------------------------------------------------------------
    # 优先级配置
    # ------------------------------------------------------------------

    def _get_foster_config(self) -> Tuple[str, List[str]]:
        """从账号 task_config 读取寄养优先级配置

        Returns:
            (mode, priority_list)
        """
        cfg = (self.current_account.task_config or {}).get("寄养", {})
        mode = cfg.get("foster_priority", "gouyu")
        custom_list = cfg.get("custom_priority", list(_DEFAULT_CUSTOM_PRIORITY))
        # 刷卡账号强制体力优先
        if getattr(self.current_account, "progress", None) == "init":
            mode = "tili"
        return mode, custom_list

    def _get_priority_list(self, mode: str, custom_list: List[str], foster_low_star: bool = False) -> List[str]:
        """根据模式返回有效的优先级列表（仅包含可用模板）"""
        if mode == "tili":
            base = list(_TILI_PRIORITY)
            if foster_low_star:
                base.extend(_TILI_LOW_STAR_EXT)
        elif mode == "custom":
            base = list(custom_list) if custom_list else list(_DEFAULT_CUSTOM_PRIORITY)
        else:
            base = list(_GOUYU_PRIORITY)
            if foster_low_star:
                base.extend(_GOUYU_LOW_STAR_EXT)
        # 过滤为仅包含可用模板
        return [r for r in base if r in self._available_rewards]

    def _get_immediate_set(self, mode: str, custom_list: List[str]) -> Set[str]:
        """根据模式返回"立即寄养"目标集合"""
        if mode == "tili":
            return {r for r in _TILI_IMMEDIATE if r in self._available_rewards}
        elif mode == "custom":
            # 自定义模式：第一优先级为立即目标
            if custom_list and custom_list[0] in self._available_rewards:
                return {custom_list[0]}
            return set()
        else:
            return {r for r in _GOUYU_IMMEDIATE if r in self._available_rewards}

    def _get_extension_config(self) -> Tuple[bool, bool, bool]:
        """从账号 task_config 读取寄养扩展配置

        Returns:
            (auto_accept_friend, collect_fanhe, foster_low_star)
        """
        cfg = (self.current_account.task_config or {}).get("寄养", {})
        auto_accept = cfg.get("auto_accept_friend", False) is True
        collect_fanhe = cfg.get("collect_fanhe", False) is True
        foster_low_star = cfg.get("foster_low_star", False) is True
        # 刷卡账号强制启用低星
        if getattr(self.current_account, "progress", None) == "init":
            foster_low_star = True
        return auto_accept, collect_fanhe, foster_low_star

    # ------------------------------------------------------------------
    # 3-phase: prepare / execute / cleanup
    # ------------------------------------------------------------------

    async def prepare(self, task: Task, account: GameAccount) -> bool:
        """准备阶段：构造 adapter，push 登录数据"""
        self.logger.info(f"[寄养] 准备: account={account.login_id}")

        # 批次复用
        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[寄养] 复用 shared_adapter，跳过 push 登录数据")
            return True

        # 加载 emulator_row
        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error(f"[寄养] 模拟器不存在: id={self.emulator_id}")
            return False

        self.adapter = self._build_adapter()

        ok = await self._push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[寄养] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[寄养] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        """执行寄养流程"""
        self.logger.info(f"[寄养] 执行: account={self.current_account.login_id}")

        # 读取低星配置，用于模板初始化
        foster_cfg = (self.current_account.task_config or {}).get("寄养", {})
        foster_low_star = foster_cfg.get("foster_low_star", False) is True

        # 初始化可用模板
        self._init_available_rewards(foster_low_star=foster_low_star)

        # 构造 UIManager（或复用）
        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = (
                self.system_config.capture_method if self.system_config else None
            ) or "adb"
            self.ui = UIManager(
                self.adapter,
                capture_method=capture_method,
                cross_emulator_cache_enabled=self._cross_emulator_cache_enabled(),
            )

        # Phase 1: 导航到结界养成
        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            self.logger.error("[寄养] 游戏就绪失败")
            return self._fail("游戏就绪失败")

        # Phase 1a: 扩展操作（在进入结界前执行）
        auto_accept_friend, collect_fanhe, _ = self._get_extension_config()

        if auto_accept_friend:
            await self._auto_accept_friends()

        if collect_fanhe:
            await self._collect_fanhe_only()

        in_jiejie = await self.ui.ensure_ui(
            "JIEJIE_YANGCHENG", max_steps=10, step_timeout=3.0
        )
        if not in_jiejie:
            self.logger.error("[寄养] 导航到结界养成失败")
            return self._fail("导航结界养成失败")

        self.logger.info("[寄养] 已到达结界养成界面")

        # Phase 2: 检查寄养状态
        await self._tap(_FOSTER_SLOT_X, _FOSTER_SLOT_Y)
        self.logger.info("[寄养] 点击寄养位")
        await asyncio.sleep(1.5)

        screenshot = await self._capture()
        if screenshot is None:
            return self._fail("截图失败")

        # 弹窗检查
        if self.ui and self.ui.popup_handler:
            dismissed = await self.ui.popup_handler.check_and_dismiss(screenshot)
            if dismissed > 0:
                screenshot = await self._capture()
                if screenshot is None:
                    return self._fail("截图失败")

        blank_match = match_template(screenshot, _TPL_BLANK)
        if not blank_match:
            # 已在寄养中 → OCR 识别剩余寄养时间
            self.logger.info("[寄养] 当前已在寄养中")
            delta = timedelta(hours=6)  # fallback
            try:
                ocr_result = await async_ocr_digits(screenshot, roi=_FOSTER_TIME_ROI)
                raw = ocr_result.text.strip()
                self.logger.info(f"[寄养] OCR 原始结果: {raw}")
                # 去除非数字字符（ddddocr 可能把 ':' 识别为 's'、'g'、'8' 等）
                parsed = None
                # 策略1: 长度8 → XX?XX?XX 格式，取位置0,1,3,4,6,7
                if len(raw) == 8:
                    d = raw[0:2] + raw[3:5] + raw[6:8]
                    if d.isdigit():
                        parsed = d
                # 策略2: 去除非数字后恰好6位
                if parsed is None:
                    d = re.sub(r"\D", "", raw)
                    if len(d) == 6:
                        parsed = d
                # 解析时间
                if parsed:
                    h, m, s = int(parsed[0:2]), int(parsed[2:4]), int(parsed[4:6])
                    if h <= 23 and m <= 59 and s <= 59:
                        time_str = f"{parsed[0:2]}:{parsed[2:4]}:{parsed[4:6]}"
                        delta = timedelta(hours=h, minutes=m, seconds=s)
                        self.logger.info(f"[寄养] 识别剩余时间: {time_str} → delta={delta}")
                    else:
                        self.logger.warning(f"[寄养] OCR 时间值超范围: '{parsed}'，使用默认 6h")
                else:
                    self.logger.warning(f"[寄养] OCR 无法解析: '{raw}'，使用默认 6h")
            except Exception as e:
                self.logger.warning(f"[寄养] OCR 识别失败: {e}，使用默认 6h")
            self._update_next_time(delta)
            total_sec = int(delta.total_seconds())
            hh, mm = total_sec // 3600, (total_sec % 3600) // 60
            remain_str = f"{hh}h{mm:02d}m"
            return self._success(f"已在寄养中, 剩余{remain_str}")

        # Phase 3: 进入选卡界面
        self.logger.info("[寄养] 检测到空位，点击进入选卡")
        bx, by = blank_match.random_point()
        await self._tap(bx, by)
        await asyncio.sleep(2.0)

        # 等待 jy_jinrujiejie.png 出现
        jin_match = await wait_for_template(
            self.adapter,
            self.ui.capture_method,
            _TPL_JINRUJIEJIE,
            timeout=8.0,
            interval=0.5,
            log=self.logger,
            label="寄养-等待选卡界面",
            popup_handler=self.popup_handler,
        )
        if not jin_match:
            self.logger.error("[寄养] 未进入选卡界面")
            await self._return_to_jiejie()
            return self._fail("未进入选卡界面")

        self.logger.info("[寄养] 已进入选卡界面")

        # 读取优先级配置
        mode, custom_list = self._get_foster_config()
        priority_list = self._get_priority_list(mode, custom_list, foster_low_star=foster_low_star)
        immediate_set = self._get_immediate_set(mode, custom_list)

        self.logger.info(
            f"[寄养] 模式={mode}, 优先级={priority_list}, 立即目标={immediate_set}"
        )

        # -- Phase 3.5: 快速预检 — 初始界面立即目标检测 --
        if immediate_set:
            self.logger.info("[寄养] 快速预检：检测初始界面是否存在立即目标")
            pre_screenshot = await self._capture()
            if pre_screenshot is not None:
                if self.ui and self.ui.popup_handler:
                    dismissed = await self.ui.popup_handler.check_and_dismiss(pre_screenshot)
                    if dismissed > 0:
                        pre_screenshot = await self._capture()

                if pre_screenshot is not None:
                    pre_rewards = self._detect_rewards(pre_screenshot)
                    for reward_type, m in pre_rewards:
                        if reward_type in immediate_set:
                            self.logger.info(
                                f"[寄养] 快速预检命中立即目标: {_reward_label(reward_type)} "
                                f"at ({m.center[0]}, {m.center[1]})"
                            )
                            cand = FosterCandidate(
                                reward_type=reward_type,
                                list_type="initial",
                                match_x=m.center[0],
                                match_y=m.center[1],
                                scroll_count=0,
                            )
                            ok = await self._do_foster(cand)
                            if ok:
                                self._update_next_time(timedelta(hours=6))
                                return self._success(
                                    f"寄养成功(快速预检): {_reward_label(reward_type)}"
                                )
                            else:
                                self.logger.warning(
                                    f"[寄养] 快速预检寄养失败: {_reward_label(reward_type)}, 继续正常扫描"
                                )
                            break
                    else:
                        self.logger.info("[寄养] 快速预检未发现立即目标，继续正常扫描")

        if not priority_list:
            self.logger.warning("[寄养] 无可用奖励模板，无法执行")
            await self._return_to_jiejie()
            return self._fail("无可用奖励模板")

        # 读取扫描间隔配置
        kuaqu_first_interval = float(
            getattr(self.system_config, "foster_kuaqu_first_interval", None) or 0.8
        )
        scan_interval = float(
            getattr(self.system_config, "foster_scan_interval", None) or 0.8
        )

        # Phase 4a: 跨区第一次扫描（只识别顶级目标，不记录候选）
        self.logger.info("[寄养] 切换到跨区列表（第一次扫描）")
        kuaqu_clicked = await click_template(
            self.adapter,
            self.ui.capture_method,
            _TPL_KUAQU,
            timeout=5.0,
            settle=0.5,
            post_delay=1.5,
            log=self.logger,
            label="寄养-跨区",
            popup_handler=self.popup_handler,
        )
        if not kuaqu_clicked:
            self.logger.warning("[寄养] 未找到跨区按钮，可能已在跨区列表")

        immediate_cand, _ = await self._scan_list(
            "kuaqu", priority_list, immediate_set,
            record_candidates=False,
            sleep_interval=kuaqu_first_interval,
        )

        if immediate_cand:
            ok = await self._do_foster(immediate_cand)
            if ok:
                self._update_next_time(timedelta(hours=6))
                return self._success(
                    f"寄养成功: {_reward_label(immediate_cand.reward_type)}"
                )

        # 重置跨区到顶部：先切好友，再切回跨区
        self.logger.info("[寄养] 重置跨区列表到顶部")
        await click_template(
            self.adapter,
            self.ui.capture_method,
            _TPL_HAOYOU,
            timeout=5.0,
            settle=0.5,
            post_delay=1.0,
            log=self.logger,
            label="寄养-切好友重置跨区",
            popup_handler=self.popup_handler,
        )
        await click_template(
            self.adapter,
            self.ui.capture_method,
            _TPL_KUAQU,
            timeout=5.0,
            settle=0.5,
            post_delay=1.5,
            log=self.logger,
            label="寄养-切跨区顶部",
            popup_handler=self.popup_handler,
        )

        # Phase 4b: 跨区第二次扫描（记录全部候选 + 无奖励早停）
        self.logger.info("[寄养] 跨区列表第二次扫描（记录候选）")
        immediate_cand, kuaqu_candidates = await self._scan_list(
            "kuaqu", priority_list, immediate_set,
            early_stop_on_no_rewards=True,
            sleep_interval=scan_interval,
        )

        if immediate_cand:
            ok = await self._do_foster(immediate_cand)
            if ok:
                self._update_next_time(timedelta(hours=6))
                return self._success(
                    f"寄养成功: {_reward_label(immediate_cand.reward_type)}"
                )

        # Phase 5: 扫描好友列表（记录全部候选 + 无奖励早停）
        self.logger.info("[寄养] 切换到好友列表")
        haoyou_clicked = await click_template(
            self.adapter,
            self.ui.capture_method,
            _TPL_HAOYOU,
            timeout=5.0,
            settle=0.5,
            post_delay=1.5,
            log=self.logger,
            label="寄养-好友",
            popup_handler=self.popup_handler,
        )
        if not haoyou_clicked:
            self.logger.warning("[寄养] 未找到好友按钮")

        immediate_cand, haoyou_candidates = await self._scan_list(
            "haoyou", priority_list, immediate_set,
            early_stop_on_no_rewards=True,
            sleep_interval=scan_interval,
        )

        if immediate_cand:
            ok = await self._do_foster(immediate_cand)
            if ok:
                self._update_next_time(timedelta(hours=6))
                return self._success(
                    f"寄养成功: {_reward_label(immediate_cand.reward_type)}"
                )

        # Phase 6: 从备选池选择最佳
        all_candidates = kuaqu_candidates + haoyou_candidates
        if not all_candidates:
            self.logger.warning("[寄养] 跨区和好友列表均未发现可用寄养位")
            await self._return_to_jiejie()
            return self._fail("未找到可用寄养位")

        # 按优先级排序
        def _sort_key(c: FosterCandidate) -> int:
            try:
                return priority_list.index(c.reward_type)
            except ValueError:
                return len(priority_list)

        all_candidates.sort(key=_sort_key)

        self.logger.info(
            f"[寄养] 备选池共 {len(all_candidates)} 个候选，"
            f"最佳: {all_candidates[0].reward_type} ({all_candidates[0].list_type})"
        )

        # 尝试寄养最佳候选
        for candidate in all_candidates[:3]:  # 最多尝试 3 个
            ok = await self._foster_best_candidate(candidate, priority_list)
            if ok:
                self._update_next_time(timedelta(hours=6))
                return self._success(
                    f"寄养成功: {_reward_label(candidate.reward_type)}"
                )

        await self._return_to_jiejie()
        return self._fail("寄养失败，所有候选均无法完成")

    async def cleanup(self) -> None:
        """停止游戏（批次中非最后一个任务跳过）"""
        if self.skip_cleanup:
            self.logger.info("[寄养] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                await self._adb_force_stop(PKG_NAME)
                self.logger.info("[寄养] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[寄养] 停止游戏失败: {e}")

    async def _return_to_jiejie(self) -> None:
        """点击 back / exit_dark 返回结界界面"""
        for i in range(10):
            await asyncio.sleep(1.0)
            screenshot = await self._capture()
            if screenshot is None:
                continue

            if self.ui and self.ui.popup_handler:
                dismissed = await self.ui.popup_handler.check_and_dismiss(screenshot)
                if dismissed > 0:
                    screenshot = await self._capture()
                    if screenshot is None:
                        continue

            if match_template(screenshot, _TPL_TAG_JIEJIE):
                self.logger.info(f"[寄养] 已回到结界界面 (第 {i + 1} 次检测)")
                return

            back_match = match_template(screenshot, _TPL_BACK)
            if back_match:
                bx, by = back_match.random_point()
                await self._tap(bx, by)
                self.logger.info(f"[寄养] 点击返回 back: ({bx}, {by}) (第 {i + 1} 次)")
                continue

            exit_match = match_template(screenshot, _TPL_EXIT_DARK)
            if exit_match:
                ex, ey = exit_match.random_point()
                await self._tap(ex, ey)
                self.logger.info(f"[寄养] 点击返回 exit_dark: ({ex}, {ey}) (第 {i + 1} 次)")
                continue

            self.logger.info(f"[寄养] 未检测到返回按钮，可能已回到结界 (第 {i + 1} 次)")
            break

    # ------------------------------------------------------------------
    # 扫描逻辑
    # ------------------------------------------------------------------

    async def _scan_list(
        self,
        list_type: str,
        priority_list: List[str],
        immediate_set: Set[str],
        *,
        record_candidates: bool = True,
        early_stop_on_no_rewards: bool = False,
        sleep_interval: float = 0.8,
    ) -> Tuple[Optional[FosterCandidate], List[FosterCandidate]]:
        """扫描一个列表（跨区或好友）查找奖励候选

        Args:
            record_candidates: False 时只检测立即目标，不记录普通候选
            early_stop_on_no_rewards: True 时若未识别到任何奖励则提前结束扫描
            sleep_interval: 每帧截图前等待时间（秒）

        Returns:
            (immediate_candidate, all_candidates)
            如果 immediate_candidate 不为 None，调用方应立即寄养。
        """
        candidates: List[FosterCandidate] = []
        scroll_count = 0

        while True:
            await asyncio.sleep(sleep_interval)

            screenshot = await self._capture()
            if screenshot is None:
                continue

            # 弹窗检查
            if self.ui and self.ui.popup_handler:
                dismissed = await self.ui.popup_handler.check_and_dismiss(screenshot)
                if dismissed > 0:
                    screenshot = await self._capture()
                    if screenshot is None:
                        continue

            # 识别奖励
            rewards = self._detect_rewards(screenshot)
            for reward_type, m in rewards:
                cand = FosterCandidate(
                    reward_type=reward_type,
                    list_type=list_type,
                    match_x=m.center[0],
                    match_y=m.center[1],
                    scroll_count=scroll_count,
                )

                if reward_type in immediate_set:
                    self.logger.info(
                        f"[寄养] 发现立即寄养目标: {reward_type} "
                        f"({list_type}, scroll={scroll_count})"
                    )
                    return cand, candidates

                if record_candidates:
                    candidates.append(cand)
                    self.logger.info(
                        f"[寄养] 记录候选: {reward_type} "
                        f"({list_type}, y={m.center[1]}, scroll={scroll_count})"
                    )

            # 无奖励早停（仅在 record_candidates 阶段启用）
            if early_stop_on_no_rewards and not rewards:
                if self._detect_any_presence(screenshot):
                    self.logger.debug(
                        f"[寄养] {list_type}未识别到可寄养奖励，但检测到存在感知模板（如太阴），继续扫描"
                    )
                else:
                    self.logger.info(
                        f"[寄养] {list_type}未识别到任何奖励，提前结束扫描 (scroll={scroll_count})"
                    )
                    break

            # 到底检测
            if self._is_at_bottom(screenshot):
                self.logger.info(f"[寄养] {list_type}列表已到底部 (scroll={scroll_count})")
                break

            # 无法下拉检测：每下拉3次检测一次
            if scroll_count > 0 and scroll_count % 3 == 0:
                if self._is_unable_to_scroll(screenshot):
                    self.logger.info(f"[寄养] {list_type}列表无法下拉 (scroll={scroll_count})")
                    break

            # 下滑
            try:
                await self._swipe(
                    _SCROLL_X, _SCROLL_Y_FROM, _SCROLL_X, _SCROLL_Y_TO, _SCROLL_DUR_MS
                )
            except AdbError as e:
                self.logger.warning(f"[寄养] {list_type}列表下滑失败，跳过本次滚动: {e}")
                continue
            scroll_count += 1

        self.logger.info(
            f"[寄养] {list_type}列表扫描完成, 发现 {len(candidates)} 个候选"
        )
        return None, candidates

    def _detect_any_presence(self, screenshot) -> bool:
        """检测截图中是否存在任意"存在感知"模板（如太阴）。

        仅用于阻止无奖励早停，不产生候选寄养位。
        """
        for key, tpl_path in self._available_presence.items():
            m = match_template(screenshot, tpl_path, threshold=0.8)
            if m:
                self.logger.debug(f"[寄养] 存在感知模板命中: {key}")
                return True
        return False

    def _detect_rewards(self, screenshot) -> List[Tuple[str, Match]]:
        """识别截图中的所有奖励模板，对 4xtg/5xtg 用右侧橙色占比校验区分"""
        results: List[Tuple[str, Match]] = []
        tg_done = False  # 4xtg/5xtg 合并判断，只处理一次

        for reward_type, tpl_path in self._available_rewards.items():
            if reward_type in ("4xtg", "5xtg"):
                if tg_done:
                    continue
                tg_done = True
                # 两个模板灰度极相似，各自匹配取更高分者
                m4 = match_template(screenshot, self._available_rewards.get("4xtg", ""), threshold=0.8) \
                    if "4xtg" in self._available_rewards else None
                m5 = match_template(screenshot, self._available_rewards.get("5xtg", ""), threshold=0.8) \
                    if "5xtg" in self._available_rewards else None
                m = m4 if (m4 and (not m5 or m4.score >= m5.score)) else m5
                if not m:
                    continue
                classified = self._classify_4xtg_5xtg(screenshot, m)
                self.logger.debug(f"[寄养] 4xtg/5xtg 判定为 {classified} (match score={m.score:.3f})")
                results.append((classified, m))
                continue

            m = match_template(screenshot, tpl_path, threshold=0.8)
            if not m:
                continue
            results.append((reward_type, m))
        return results

    def _classify_4xtg_5xtg(self, screenshot, match: Match) -> str:
        """通过底部灰色图标段数区分 4xtg / 5xtg。

        4xtg底部：4心 + 2灰图标 → 灰色列段数 = 3
        5xtg底部：5心 + 1灰图标 → 灰色列段数 = 2
        阈值 _TG_SEG_THR=3：段数 >= 3 → 4xtg，否则 → 5xtg
        """
        img_h, img_w = screenshot.shape[:2]
        y1 = max(0, match.y + match.h - _TG_STRIP_ROWS)
        y2 = min(img_h, match.y + match.h)
        x1 = max(0, match.x)
        x2 = min(img_w, match.x + match.w)
        strip = screenshot[y1:y2, x1:x2]
        if strip.size == 0:
            return "4xtg"
        hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
        S = hsv[:, :, 1]
        V = hsv[:, :, 2]
        gray_mask = (S < _TG_GRAY_S_MAX) & (V > _TG_GRAY_V_MIN)
        gray_col = gray_mask.mean(axis=0)
        segments = 0
        in_seg = False
        for v in gray_col:
            if v > _TG_COL_THR and not in_seg:
                segments += 1
                in_seg = True
            elif v <= _TG_COL_THR:
                in_seg = False
        self.logger.debug(f"[寄养] 4xtg/5xtg 底部灰色段数={segments} (阈值{_TG_SEG_THR})")
        return "4xtg" if segments >= _TG_SEG_THR else "5xtg"

    def _is_at_bottom(self, screenshot) -> bool:
        """检查 ROI 区域是否出现到底指示"""
        x, y, w, h = _DAODI_ROI
        roi_img = screenshot[y : y + h, x : x + w]
        m = match_template(roi_img, _TPL_DAODI, threshold=0.8)
        return m is not None

    def _is_unable_to_scroll(self, screenshot) -> bool:
        """检查 ROI 区域是否出现无法下拉指示"""
        x, y, w, h = _WFXL_ROI
        roi_img = screenshot[y : y + h, x : x + w]
        m = match_template(roi_img, _TPL_WFXL, threshold=0.8)
        return m is not None

    # ------------------------------------------------------------------
    # 寄养操作
    # ------------------------------------------------------------------

    async def _do_foster(self, candidate: FosterCandidate) -> bool:
        """对当前画面中已识别到的候选执行寄养

        点击奖励位置 → 点击进入结界 → 放置式神 → 确认 → 返回验证
        """
        self.logger.info(
            f"[寄养] 执行寄养: {candidate.reward_type} "
            f"({candidate.match_x}, {candidate.match_y})"
        )
        await self._tap(candidate.match_x, candidate.match_y)
        await asyncio.sleep(1.5)

        # 点击进入结界确认
        ok = await click_template(
            self.adapter,
            self.ui.capture_method,
            _TPL_JINRUJIEJIE,
            timeout=5.0,
            settle=0.5,
            post_delay=2.0,
            log=self.logger,
            label="寄养-确认进入结界",
            popup_handler=self.popup_handler,
        )
        if not ok:
            self.logger.warning(f"[寄养] 点击进入结界失败: {candidate.reward_type}")
            return False

        # 进入结界后完成放置、确认、返回验证
        return await self._confirm_and_verify_foster(candidate.reward_type)

    async def _confirm_and_verify_foster(self, reward_type: str) -> bool:
        """进入他人结界后，放置式神、确认、返回结界养成并验证寄养成功

        1. 点击 (153, 434) 放置式神
        2. 等待并点击 jy_queding.png 确认
        3. 返回结界养成界面
        4. 点击寄养位 (458, 256) 并检测 jy_blank.png
        5. 没有空位 → 成功，有空位 → 失败
        """
        # 1. 点击放置式神位置
        self.logger.info(f"[寄养] 点击放置式神: ({_FOSTER_PLACE_X}, {_FOSTER_PLACE_Y})")
        await self._tap(_FOSTER_PLACE_X, _FOSTER_PLACE_Y)
        await asyncio.sleep(2.0)

        # 2. 等待并点击确认按钮
        queding_clicked = await click_template(
            self.adapter,
            self.ui.capture_method,
            _TPL_QUEDING,
            timeout=5.0,
            settle=0.5,
            post_delay=2.0,
            log=self.logger,
            label="寄养-确定",
            popup_handler=self.popup_handler,
        )
        if not queding_clicked:
            self.logger.warning(f"[寄养] 未检测到确定按钮: {reward_type}")
            return False

        self.logger.info(f"[寄养] 已点击确定: {reward_type}")

        # 3. 点击 back / exit_dark 返回结界界面
        await self._return_to_jiejie()

        # 确保回到结界养成界面
        in_yangcheng = await self.ui.ensure_ui(
            "JIEJIE_YANGCHENG", max_steps=6, step_timeout=3.0
        )
        if not in_yangcheng:
            self.logger.warning("[寄养] 返回结界养成界面失败")
            return False

        await asyncio.sleep(1.0)

        # 4. 点击寄养位固定坐标
        self.logger.info(f"[寄养] 点击寄养位验证: ({_FOSTER_SLOT_X}, {_FOSTER_SLOT_Y})")
        await self._tap(_FOSTER_SLOT_X, _FOSTER_SLOT_Y)
        await asyncio.sleep(1.5)

        # 5. 检测 jy_blank.png 判断是否寄养成功
        screenshot = await self._capture()
        if screenshot is None:
            self.logger.warning("[寄养] 验证截图失败")
            return False

        # 弹窗检查
        if self.ui and self.ui.popup_handler:
            dismissed = await self.ui.popup_handler.check_and_dismiss(screenshot)
            if dismissed > 0:
                screenshot = await self._capture()
                if screenshot is None:
                    return False

        blank_match = match_template(screenshot, _TPL_BLANK)
        if blank_match:
            self.logger.warning(f"[寄养] 验证失败：仍检测到空位，寄养未成功: {reward_type}")
            return False

        self.logger.info(f"[寄养] 验证成功：未检测到空位，寄养已完成: {reward_type}")
        return True

    async def _foster_best_candidate(
        self, candidate: FosterCandidate, priority_list: List[str]
    ) -> bool:
        """回溯导航到候选位置并执行寄养

        1. 切换到候选所在列表
        2. 滚动到大致位置
        3. 重新识别并点击
        4. 确认寄养
        """
        self.logger.info(
            f"[寄养] 回溯寄养候选: {candidate.reward_type} "
            f"(list={candidate.list_type}, scroll={candidate.scroll_count})"
        )

        # 1. 先切换到对立标签（使目标标签重置到顶部），再切回目标标签
        if candidate.list_type == "kuaqu":
            tpl_opposite = _TPL_HAOYOU
            tpl_target = _TPL_KUAQU
        else:
            tpl_opposite = _TPL_KUAQU
            tpl_target = _TPL_HAOYOU

        await click_template(
            self.adapter,
            self.ui.capture_method,
            tpl_opposite,
            timeout=5.0,
            settle=0.5,
            post_delay=1.0,
            log=self.logger,
            label=f"寄养-切换对立标签（重置{candidate.list_type}）",
            popup_handler=self.popup_handler,
        )

        clicked = await click_template(
            self.adapter,
            self.ui.capture_method,
            tpl_target,
            timeout=5.0,
            settle=0.5,
            post_delay=1.5,
            log=self.logger,
            label=f"寄养-切换{candidate.list_type}（从顶部）",
            popup_handler=self.popup_handler,
        )
        if not clicked:
            self.logger.warning(
                f"[寄养] 切换到 {candidate.list_type} 列表失败"
            )

        # 2. 滚动到大致位置
        for i in range(candidate.scroll_count):
            try:
                await self._swipe(
                    _SCROLL_X, _SCROLL_Y_FROM, _SCROLL_X, _SCROLL_Y_TO, _SCROLL_DUR_MS
                )
            except AdbError as e:
                self.logger.warning(f"[寄养] 回滚到候选位置时下滑失败，继续: {e}")
                continue
            await asyncio.sleep(0.6)

        # 3. 扫描当前画面 + 额外 2 次滚动范围寻找目标
        for attempt in range(3):
            await asyncio.sleep(0.8)
            screenshot = await self._capture()
            if screenshot is None:
                continue

            # 弹窗检查
            if self.ui and self.ui.popup_handler:
                dismissed = await self.ui.popup_handler.check_and_dismiss(screenshot)
                if dismissed > 0:
                    screenshot = await self._capture()
                    if screenshot is None:
                        continue

            # 查找目标奖励（优先找原候选类型，其次找更高优先级）
            best_match: Optional[Tuple[str, Match]] = None
            best_priority = len(priority_list)
            for reward_type, m in self._detect_rewards(screenshot):
                try:
                    idx = priority_list.index(reward_type)
                except ValueError:
                    idx = len(priority_list)
                if idx < best_priority:
                    best_priority = idx
                    best_match = (reward_type, m)

            if best_match:
                reward_type, m = best_match
                cx, cy = m.random_point()
                self.logger.info(
                    f"[寄养] 重新定位到 {reward_type} ({cx}, {cy})"
                )
                await self._tap(cx, cy)
                await asyncio.sleep(1.5)

                ok = await click_template(
                    self.adapter,
                    self.ui.capture_method,
                    _TPL_JINRUJIEJIE,
                    timeout=5.0,
                    settle=0.5,
                    post_delay=2.0,
                    log=self.logger,
                    label="寄养-确认进入结界",
                    popup_handler=self.popup_handler,
                )
                if not ok:
                    self.logger.warning(f"[寄养] 点击进入结界失败: {reward_type}")
                    return False

                # 进入结界后完成放置、确认、返回验证
                verified = await self._confirm_and_verify_foster(reward_type)
                if verified:
                    self.logger.info(f"[寄养] 备选池寄养成功: {reward_type}")
                    return True
                else:
                    self.logger.warning(f"[寄养] 备选池寄养验证失败: {reward_type}")
                    return False

            # 未找到，继续滚动
            try:
                await self._swipe(
                    _SCROLL_X, _SCROLL_Y_FROM, _SCROLL_X, _SCROLL_Y_TO, _SCROLL_DUR_MS
                )
            except AdbError as e:
                self.logger.warning(f"[寄养] 精确定位时下滑失败，跳过本次滚动: {e}")

        self.logger.warning("[寄养] 无法重新定位到候选寄养位")
        return False

    # ------------------------------------------------------------------
    # 扩展操作
    # ------------------------------------------------------------------

    async def _auto_accept_friends(self) -> None:
        """导航到好友界面，自动同意所有待处理的好友申请"""
        self.logger.info("[寄养] 开始自动同意好友申请")

        # 1. 导航到好友界面
        in_haoyou = await self.ui.ensure_ui("HAOYOU", max_steps=6, step_timeout=3.0)
        if not in_haoyou:
            self.logger.warning("[寄养] 导航到好友界面失败，跳过自动同意好友申请")
            return

        await asyncio.sleep(1.0)

        # 2. 点击"添加"按钮进入推荐/申请界面
        clicked_tianjia = await click_template(
            self.adapter,
            self.ui.capture_method,
            _TPL_TIANJIA,
            timeout=5.0,
            interval=1.0,
            settle=0.5,
            post_delay=2.0,
            log=self.logger,
            label="寄养-添加好友",
            popup_handler=self.popup_handler,
        )
        if not clicked_tianjia:
            self.logger.warning("[寄养] 未检测到添加按钮，跳过自动同意好友申请")
            return

        # 3. 循环点击 friend_tongyi.png 直到没有为止
        accepted_count = 0
        for i in range(_MAX_ACCEPT_FRIEND_LOOPS):
            screenshot = await self._capture()
            if screenshot is None:
                self.logger.warning("[寄养] 截图失败，中断同意好友循环")
                break

            # 弹窗检查
            if self.ui and self.ui.popup_handler:
                dismissed = await self.ui.popup_handler.check_and_dismiss(screenshot)
                if dismissed > 0:
                    screenshot = await self._capture()
                    if screenshot is None:
                        break

            tongyi_match = match_template(screenshot, _TPL_FRIEND_TONGYI)
            if not tongyi_match:
                self.logger.info(
                    f"[寄养] 未检测到同意按钮，好友申请处理完毕 (已同意 {accepted_count} 个)"
                )
                break

            tx, ty = tongyi_match.random_point()
            await self._tap(tx, ty)
            accepted_count += 1
            self.logger.info(f"[寄养] 点击同意好友申请: ({tx}, {ty}) (第 {i + 1} 次)")
            await asyncio.sleep(1.5)

        self.logger.info(f"[寄养] 自动同意好友申请完成，共同意 {accepted_count} 个")

    async def _collect_fanhe_only(self) -> None:
        """导航到饭盒界面，领取饭盒产出（不领酒壶）"""
        self.logger.info("[寄养] 开始领取饭盒")

        in_fanhe = await self.ui.ensure_ui("FANHE", max_steps=6, step_timeout=3.0)
        if not in_fanhe:
            self.logger.warning("[寄养] 导航到饭盒界面失败，跳过领取饭盒")
            return

        # 点击 fanhe_quchu.png
        clicked = await click_template(
            self.adapter,
            self.ui.capture_method,
            _TPL_FANHE_QUCHU,
            timeout=5.0,
            settle=0.5,
            post_delay=2.0,
            log=self.logger,
            label="寄养-饭盒取出",
            popup_handler=self.popup_handler,
        )
        if not clicked:
            self.logger.warning("[寄养] 未检测到饭盒取出按钮，可能无产出")
        else:
            # 关闭 jiangli 奖励弹窗
            await asyncio.sleep(1.5)
            screenshot = await self._capture()
            if screenshot is not None:
                if self.ui and self.ui.popup_handler:
                    if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
                        screenshot = await self._capture()

                if screenshot is not None:
                    jiangli = match_template(screenshot, _TPL_JIANGLI)
                    if jiangli:
                        self.logger.info("[寄养] 检测到奖励弹窗，点击关闭")

                # 点击屏幕空白处关闭弹窗
                from ..vision.utils import random_point_in_circle

                close_x, close_y = random_point_in_circle(20, 20, 20)
                await self._tap(close_x, close_y)
                self.logger.info(f"[寄养] 点击 ({close_x}, {close_y}) 关闭弹窗")
                await asyncio.sleep(1.0)

        self.logger.info("[寄养] 领取饭盒完成")

    # ------------------------------------------------------------------
    # next_time 管理
    # ------------------------------------------------------------------

    def _update_next_time(self, delta: timedelta = timedelta(hours=6)) -> None:
        """更新寄养 next_time 为当前时间 + delta"""
        try:
            bj_now = now_beijing()
            next_time = format_beijing_time(bj_now + delta)

            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    cfg = account.task_config or {}
                    foster = cfg.get("寄养", {})
                    foster["next_time"] = next_time
                    cfg["寄养"] = foster
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(f"[寄养] next_time 更新为 {next_time}")
        except Exception as e:
            self.logger.error(f"[寄养] 更新 next_time 失败: {e}")

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _fail(self, error: str) -> Dict[str, Any]:
        """构造失败返回"""
        return {
            "status": TaskStatus.FAILED,
            "error": error,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _success(self, message: str) -> Dict[str, Any]:
        """构造成功返回"""
        return {
            "status": TaskStatus.SUCCEEDED,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }
