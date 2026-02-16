"""
起号 - 式神养成执行器
仅限 init 阶段账号。
分支一（觉醒）：检查座敷童子是否已觉醒，未觉醒则导航到式神界面执行觉醒。
分支二（技能升级）：觉醒完成后，进入养成界面，用未觉醒座敷副本升级技能，直到2技能和3技能均达到3级。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

import cv2
import numpy as np

from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus
from ...core.logger import logger
from ...core.timeutils import add_hours_to_beijing_time, format_beijing_time, now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ui.manager import UIManager
from ..vision.template import Match, find_all_templates, match_template
from ..vision.utils import load_image
from .awaken import awaken_shikigami
from .base import BaseExecutor
from .db_logger import emit as db_log
from .helpers import click_template, wait_for_template

PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# 模板路径
_TPL_SHISHEN_R = "assets/ui/templates/shishen_r.png"
_TPL_SHISHEN_LIEBIAO = "assets/ui/templates/shishen_liebiao.png"
_TPL_SHISHEN_XIYOUDU = "assets/ui/templates/shishen_xiyoudu.png"
_TPL_WEIJUEXING_ZUOFU = "assets/ui/shishen/weijuexing_zuofu.png"
_TPL_YIJUEXING_ZUOFU = "assets/ui/shishen/yijuexing_zuofu.png"

# 养成界面模板
_TPL_SHISHEN_YANGCHENG = "assets/ui/templates/shishen_yangcheng.png"
_TPL_TAG_YANGCHENG = "assets/ui/templates/tag_yangcheng.png"
_TPL_YANGCHENG_GEZI = "assets/ui/templates/yangcheng_gezi.png"
_TPL_YANGCHENG_QUEREN = "assets/ui/templates/yangcheng_queren.png"
_TPL_YANGCHENG_CHENGGONG = "assets/ui/templates/yangcheng_chenggong.png"

# ── 滚动常量（960×540 分辨率，式神列表视图）──
_SHISHEN_SWIPE_X = 480          # 式神列表中心 x
_SHISHEN_SWIPE_DUR_MS = 500     # 滑动持续时间（毫秒）
_SHISHEN_SCROLL_SETTLE = 1.0    # 滚动后等待动画结束（秒）
_SHISHEN_MAX_SCROLL = 8         # 最大滚动次数
_SHISHEN_SWIPE_DOWN_Y1 = 380    # 向下滚动：从高 y 拖到低 y
_SHISHEN_SWIPE_DOWN_Y2 = 150
_SHISHEN_SWIPE_UP_Y1 = 150      # 滚动到顶部：从低 y 拖到高 y
_SHISHEN_SWIPE_UP_Y2 = 400
_SHISHEN_ROI_SLICE = (80, 480, 100, 860)  # (y1, y2, x1, x2) 列表主体区域
_SHISHEN_DIFF_THRESHOLD = 3.0   # 像素差异阈值，低于此值认为已到达列表边界


class InitShikigamiTrainExecutor(BaseExecutor):
    """起号 - 式神养成（座敷童子觉醒 + 技能升级）"""

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
        self.logger.info(
            f"[起号_式神养成] 准备: account_id={account.id}, login_id={account.login_id}"
        )

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[起号_式神养成] 复用 shared_adapter，跳过 push 登录数据")
        else:
            if not self.emulator_row:
                with SessionLocal() as db:
                    self.emulator_row = (
                        db.query(Emulator)
                        .filter(Emulator.id == self.emulator_id)
                        .first()
                    )
                    self.system_config = db.query(SystemConfig).first()

            if not self.emulator_row:
                self.logger.error(
                    f"[起号_式神养成] 模拟器不存在: id={self.emulator_id}"
                )
                return False

            self.adapter = self._build_adapter()

            ok = self.adapter.push_login_data(
                account.login_id, data_dir="putonglogindata"
            )
            if not ok:
                self.logger.error(
                    f"[起号_式神养成] push 登录数据失败: {account.login_id}"
                )
                return False
            self.logger.info(
                f"[起号_式神养成] push 登录数据成功: {account.login_id}"
            )

        return True

    async def execute(self) -> Dict[str, Any]:
        account = self.current_account
        account_id = account.id

        # 1. 加载式神配置，判断分支
        shikigami_cfg = self._load_shikigami_config(account_id)
        zuofu_cfg = shikigami_cfg.get("座敷童子", {})

        is_awakened = zuofu_cfg.get("awakened") is True
        skill_2 = zuofu_cfg.get("skill_2_level", 1)
        skill_3 = zuofu_cfg.get("skill_3_level", 1)
        skills_maxed = skill_2 >= 3 and skill_3 >= 3

        if is_awakened and skills_maxed:
            self.logger.info("[起号_式神养成] 座敷童子已觉醒且技能已满级，跳过")
            self._update_next_time(account_id, hours=24)
            return {"status": TaskStatus.SKIPPED, "reason": "座敷童子已觉醒且技能已满级"}

        # 2. 构建 / 复用 UIManager
        if self.shared_ui:
            self.ui = self.shared_ui
        else:
            capture_method = "adb"
            if self.system_config and getattr(self.system_config, "capture_method", None):
                capture_method = self.system_config.capture_method
            self.ui = UIManager(self.adapter, capture_method=capture_method)

        capture_method = self.ui.capture_method

        # 3. 确保游戏就绪
        entered = await self.ui.ensure_game_ready(timeout=90.0)
        if not entered:
            db_log(account_id, "式神养成: 游戏就绪失败", level="ERROR")
            return {"status": TaskStatus.FAILED, "error": "游戏就绪失败"}

        # 4. 导航到式神界面
        in_shishen = await self.ui.ensure_ui("SHISHEN", max_steps=6, step_timeout=3.0)
        if not in_shishen:
            db_log(account_id, "式神养成: 导航到式神界面失败", level="ERROR")
            return {"status": TaskStatus.FAILED, "error": "导航到式神界面失败"}

        await asyncio.sleep(1.0)

        # 5. 确保在列表视图并筛选 R 级
        screenshot = self.adapter.capture(capture_method)
        if screenshot is not None:
            m = match_template(screenshot, _TPL_SHISHEN_R)
            if not m:
                clicked = await click_template(
                    self.adapter, capture_method, _TPL_SHISHEN_LIEBIAO,
                    timeout=5.0, settle=0.5, post_delay=1.0,
                    log=self.logger, label="式神养成-列表视图",
                    popup_handler=self.ui.popup_handler,
                )
                if not clicked:
                    self.logger.warning("[起号_式神养成] 未找到列表视图按钮")

        clicked = await click_template(
            self.adapter, capture_method, _TPL_SHISHEN_XIYOUDU,
            timeout=5.0, settle=0.5, post_delay=1.0,
            log=self.logger, label="式神养成-稀有度筛选",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked:
            self.logger.warning("[起号_式神养成] 未找到稀有度筛选按钮")

        clicked = await click_template(
            self.adapter, capture_method, _TPL_SHISHEN_R,
            timeout=5.0, settle=0.5, post_delay=1.5,
            log=self.logger, label="式神养成-R级筛选",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked:
            db_log(account_id, "式神养成: R级筛选失败", level="WARNING")

        await asyncio.sleep(1.0)

        # 6. 分支执行
        if not is_awakened:
            return await self._run_awaken_branch(account_id, capture_method)
        else:
            return await self._run_skill_upgrade_branch(account_id, capture_method)

    # ---- 觉醒分支 ----

    async def _run_awaken_branch(
        self, account_id: int, capture_method: str,
    ) -> Dict[str, Any]:
        """分支一：搜索并觉醒座敷童子。"""
        # 阶段一：搜索已觉醒座敷童子
        self.logger.info("[起号_式神养成] 觉醒分支 - 阶段一：搜索已觉醒座敷童子")
        await self._scroll_to_top()
        await asyncio.sleep(0.5)

        m_awakened = await self._scroll_find_template(
            _TPL_YIJUEXING_ZUOFU, "搜索已觉醒座敷",
        )

        if m_awakened:
            self.logger.info("[起号_式神养成] 座敷童子已觉醒（视觉确认）")
            self._update_shikigami_field(account_id, "awakened", True)
            self._update_shikigami_field(account_id, "owned", True)
            self._update_next_time(account_id, hours=0)
            db_log(account_id, "式神养成: 座敷童子已觉醒（视觉确认），即将升级技能")
            return {"status": TaskStatus.SUCCEEDED, "reason": "座敷童子已觉醒（视觉确认）"}

        # 阶段二：搜索未觉醒座敷童子
        self.logger.info("[起号_式神养成] 觉醒分支 - 阶段二：搜索未觉醒座敷童子")
        await self._scroll_to_top()
        await asyncio.sleep(0.5)

        m_zuofu = await self._scroll_find_template(
            _TPL_WEIJUEXING_ZUOFU, "搜索未觉醒座敷",
        )

        if not m_zuofu:
            self.logger.warning("[起号_式神养成] 未找到座敷童子（已觉醒/未觉醒均未匹配）")
            self._update_shikigami_field(account_id, "owned", False)
            self._update_next_time(account_id, hours=24)
            db_log(account_id, "式神养成: 未找到座敷童子", level="WARNING")
            return {"status": TaskStatus.FAILED, "error": "未找到座敷童子"}

        self._update_shikigami_field(account_id, "owned", True)
        self.logger.info("[起号_式神养成] 找到未觉醒座敷童子，点击进入详情")

        cx, cy = m_zuofu.random_point()
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, cx, cy)
        await asyncio.sleep(2.0)

        # 执行觉醒
        awaken_ok = await awaken_shikigami(
            self.adapter, capture_method,
            log=self.logger, label="式神养成",
            popup_handler=self.ui.popup_handler,
        )

        if awaken_ok:
            self._update_shikigami_field(account_id, "awakened", True)
            self._update_next_time(account_id, hours=0)
            db_log(account_id, "式神养成: 座敷童子觉醒成功，即将升级技能")
            return {
                "status": TaskStatus.SUCCEEDED,
                "timestamp": datetime.utcnow().isoformat(),
            }
        else:
            self._update_next_time(account_id, hours=1)
            db_log(account_id, "式神养成: 觉醒操作失败", level="WARNING")
            return {"status": TaskStatus.FAILED, "error": "觉醒操作失败"}

    # ---- 技能升级分支 ----

    async def _run_skill_upgrade_branch(
        self, account_id: int, capture_method: str,
    ) -> Dict[str, Any]:
        """分支二：升级座敷童子技能（养成）。

        前置条件：已在式神列表界面，已筛选R级。
        流程：搜索已觉醒座敷 → 进入详情 → 点击养成 → 填充素材 → 确认 → 验证成功。
        """
        addr = self.adapter.cfg.adb_addr

        # 1. 搜索已觉醒座敷童子
        self.logger.info("[起号_式神养成] 技能升级分支 - 搜索已觉醒座敷童子")
        await self._scroll_to_top()
        await asyncio.sleep(0.5)

        m_zuofu = await self._scroll_find_template(
            _TPL_YIJUEXING_ZUOFU, "搜索已觉醒座敷",
        )
        if not m_zuofu:
            self.logger.warning("[起号_式神养成] 技能升级: 未找到已觉醒座敷童子")
            self._update_next_time(account_id, hours=1)
            db_log(account_id, "式神养成-技能升级: 未找到已觉醒座敷童子", level="WARNING")
            return {"status": TaskStatus.FAILED, "error": "未找到已觉醒座敷童子"}

        # 2. 点击进入详情
        cx, cy = m_zuofu.random_point()
        self.adapter.adb.tap(addr, cx, cy)
        self.logger.info(f"[起号_式神养成] 技能升级: 点击已觉醒座敷 ({cx}, {cy})")
        await asyncio.sleep(2.0)

        # 3. 点击养成按钮
        clicked = await click_template(
            self.adapter, capture_method, _TPL_SHISHEN_YANGCHENG,
            timeout=8.0, settle=0.5, post_delay=1.0,
            log=self.logger, label="技能升级-养成按钮",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked:
            self.logger.warning("[起号_式神养成] 技能升级: 未找到养成按钮")
            self._update_next_time(account_id, hours=1)
            db_log(account_id, "式神养成-技能升级: 未找到养成按钮", level="WARNING")
            return {"status": TaskStatus.FAILED, "error": "未找到养成按钮"}

        # 4. 等待养成界面标签出现
        m_tag = await wait_for_template(
            self.adapter, capture_method, _TPL_TAG_YANGCHENG,
            timeout=8.0, interval=0.5,
            log=self.logger, label="技能升级-养成界面",
            popup_handler=self.ui.popup_handler,
        )
        if not m_tag:
            self.logger.warning("[起号_式神养成] 技能升级: 未进入养成界面")
            self._update_next_time(account_id, hours=1)
            db_log(account_id, "式神养成-技能升级: 未进入养成界面", level="WARNING")
            return {"status": TaskStatus.FAILED, "error": "未进入养成界面"}

        # 5. 统计养成格子总数（记录日志用）
        screenshot = self.adapter.capture(capture_method)
        if screenshot is not None:
            all_gezi = find_all_templates(screenshot, _TPL_YANGCHENG_GEZI)
            self.logger.info(
                f"[起号_式神养成] 技能升级: 养成格子总数={len(all_gezi)}"
            )

        # 6. 循环点击未觉醒座敷素材
        click_count = 0
        for _ in range(20):  # 安全上限
            screenshot = self.adapter.capture(capture_method)
            if screenshot is None:
                await asyncio.sleep(0.5)
                continue
            m = match_template(screenshot, _TPL_WEIJUEXING_ZUOFU)
            if not m:
                self.logger.info(
                    f"[起号_式神养成] 技能升级: 无更多未觉醒素材，共点击 {click_count} 次"
                )
                break
            self.adapter.adb.tap(addr, *m.random_point())
            click_count += 1
            self.logger.info(
                f"[起号_式神养成] 技能升级: 点击素材 #{click_count} ({m.center})"
            )
            await asyncio.sleep(1.0)

        if click_count == 0:
            self.logger.warning("[起号_式神养成] 技能升级: 未找到可用的未觉醒座敷素材")
            self._update_next_time(account_id, hours=24)
            db_log(account_id, "式神养成-技能升级: 无可用素材", level="WARNING")
            return {"status": TaskStatus.FAILED, "error": "无可用的未觉醒座敷素材"}

        # 7. 点击确认
        clicked = await click_template(
            self.adapter, capture_method, _TPL_YANGCHENG_QUEREN,
            timeout=8.0, settle=0.5, post_delay=2.0,
            log=self.logger, label="技能升级-确认",
            popup_handler=self.ui.popup_handler,
        )
        if not clicked:
            self.logger.warning("[起号_式神养成] 技能升级: 确认按钮未找到")
            self._update_next_time(account_id, hours=1)
            db_log(account_id, "式神养成-技能升级: 确认按钮未找到", level="WARNING")
            return {"status": TaskStatus.FAILED, "error": "确认按钮未找到"}

        # 8. 验证养成成功
        m_ok = await wait_for_template(
            self.adapter, capture_method, _TPL_YANGCHENG_CHENGGONG,
            timeout=8.0, interval=0.5,
            log=self.logger, label="技能升级-成功",
            popup_handler=self.ui.popup_handler,
        )
        if m_ok:
            # 更新技能等级：优先升级较低的那个
            shikigami_cfg = self._load_shikigami_config(account_id)
            zuofu_cfg = shikigami_cfg.get("座敷童子", {})
            s2 = zuofu_cfg.get("skill_2_level", 1)
            s3 = zuofu_cfg.get("skill_3_level", 1)
            if s2 <= s3:
                new_level = min(s2 + 1, 3)
                self._update_shikigami_field(account_id, "skill_2_level", new_level)
                self.logger.info(f"[起号_式神养成] 技能升级: 2技能 {s2} → {new_level}")
            else:
                new_level = min(s3 + 1, 3)
                self._update_shikigami_field(account_id, "skill_3_level", new_level)
                self.logger.info(f"[起号_式神养成] 技能升级: 3技能 {s3} → {new_level}")

            # 重新检查是否全部满级
            s2_new = zuofu_cfg.get("skill_2_level", s2)
            s3_new = zuofu_cfg.get("skill_3_level", s3)
            if s2 <= s3:
                s2_new = new_level
            else:
                s3_new = new_level

            if s2_new >= 3 and s3_new >= 3:
                self._update_next_time(account_id, hours=24)
                db_log(account_id, "式神养成-技能升级: 全部技能已满级")
            else:
                self._update_next_time(account_id, hours=0)
                db_log(account_id, f"式神养成-技能升级: 成功 (2技能={s2_new}, 3技能={s3_new})，继续升级")

            return {
                "status": TaskStatus.SUCCEEDED,
                "timestamp": datetime.utcnow().isoformat(),
            }
        else:
            self._update_next_time(account_id, hours=1)
            db_log(account_id, "式神养成-技能升级: 未检测到成功提示", level="WARNING")
            return {"status": TaskStatus.FAILED, "error": "养成未检测到成功提示"}

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            # 批次中非最后任务：不关闭游戏，但必须回到庭院，
            # 避免 UI 停留在子页面导致下一个任务检测到 UNKNOWN 而重启游戏
            if self.ui:
                self.logger.info("[起号_式神养成] 批次中非最后任务，尝试回到庭院")
                try:
                    ok = await self.ui.go_to_tingyuan(timeout=15.0)
                    if ok:
                        self.logger.info("[起号_式神养成] 已回到庭院")
                    else:
                        self.logger.warning("[起号_式神养成] 回到庭院超时，下一个任务将通过 ensure_game_ready 处理")
                except Exception as e:
                    self.logger.warning(f"[起号_式神养成] 回到庭院异常: {e}")
            else:
                self.logger.info("[起号_式神养成] 批次中非最后任务，无 UIManager，跳过 cleanup")
            return
        if self.adapter:
            self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)

    # ---- 私有辅助方法 ----

    def _load_shikigami_config(self, account_id: int) -> dict:
        """从数据库加载最新的 shikigami_config。"""
        try:
            with SessionLocal() as db:
                account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
                if account and account.shikigami_config:
                    return account.shikigami_config
        except Exception as e:
            self.logger.error(f"[起号_式神养成] 加载 shikigami_config 失败: {e}")
        return {}

    def _update_shikigami_field(self, account_id: int, field: str, value: Any) -> None:
        """更新 shikigami_config 中座敷童子的指定字段。"""
        try:
            with SessionLocal() as db:
                account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
                if not account:
                    return
                cfg = account.shikigami_config or {}
                zuofu = cfg.get("座敷童子", {})
                zuofu[field] = value
                cfg["座敷童子"] = zuofu
                account.shikigami_config = cfg
                flag_modified(account, "shikigami_config")
                db.commit()
                self.logger.info(
                    f"[起号_式神养成] 更新 座敷童子.{field}={value} (account={account_id})"
                )
        except Exception as e:
            self.logger.error(f"[起号_式神养成] 更新 shikigami_config 失败: {e}")

    def _update_next_time(self, account_id: int, hours: int = 24) -> None:
        """更新任务的 next_time。"""
        bj_now_str = format_beijing_time(now_beijing())
        next_time = add_hours_to_beijing_time(bj_now_str, hours)
        try:
            with SessionLocal() as db:
                account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
                if not account:
                    return
                cfg = account.task_config or {}
                task_cfg = cfg.get("起号_式神养成", {})
                task_cfg["next_time"] = next_time
                cfg["起号_式神养成"] = task_cfg
                account.task_config = cfg
                flag_modified(account, "task_config")
                db.commit()
                self.logger.info(
                    f"[起号_式神养成] next_time 更新为 {next_time} (account={account_id})"
                )
        except Exception as e:
            self.logger.error(f"[起号_式神养成] 更新 next_time 失败: {e}")

    # ---- 滚动搜索辅助方法 ----

    async def _scroll_to_top(self) -> None:
        """将式神列表复位到顶部，通过连续截图比对确认到顶。"""
        capture_method = self.ui.capture_method
        prev_screenshot = None
        for attempt in range(6):
            # 手指从低 y 拖到高 y = 列表向上滚（回到顶部）
            self.adapter.swipe(
                _SHISHEN_SWIPE_X, _SHISHEN_SWIPE_UP_Y1,
                _SHISHEN_SWIPE_X, _SHISHEN_SWIPE_UP_Y2,
                _SHISHEN_SWIPE_DUR_MS,
            )
            await asyncio.sleep(0.6)
            screenshot_raw = self.adapter.capture(capture_method)
            screenshot = load_image(screenshot_raw) if screenshot_raw is not None else None
            if screenshot is not None and prev_screenshot is not None:
                y1, y2, x1, x2 = _SHISHEN_ROI_SLICE
                roi_curr = screenshot[y1:y2, x1:x2]
                roi_prev = prev_screenshot[y1:y2, x1:x2]
                diff = cv2.absdiff(roi_curr, roi_prev)
                if np.mean(diff) < _SHISHEN_DIFF_THRESHOLD:
                    self.logger.info(
                        f"[起号_式神养成] 列表已复位到顶部 (尝试 {attempt + 1} 次)"
                    )
                    return
            prev_screenshot = screenshot
        self.logger.warning("[起号_式神养成] scroll_to_top 达到最大尝试次数")

    async def _scroll_down_once(self) -> bool:
        """向下滚动一页，返回 True 表示列表发生了变化（还未到底）。"""
        capture_method = self.ui.capture_method

        # 滚动前截图
        before_raw = self.adapter.capture(capture_method)
        before = load_image(before_raw) if before_raw is not None else None

        # 手指从高 y 拖到低 y = 列表向下滚
        self.adapter.swipe(
            _SHISHEN_SWIPE_X, _SHISHEN_SWIPE_DOWN_Y1,
            _SHISHEN_SWIPE_X, _SHISHEN_SWIPE_DOWN_Y2,
            _SHISHEN_SWIPE_DUR_MS,
        )
        await asyncio.sleep(_SHISHEN_SCROLL_SETTLE)

        # 滚动后截图对比
        after_raw = self.adapter.capture(capture_method)
        after = load_image(after_raw) if after_raw is not None else None
        if before is not None and after is not None:
            y1, y2, x1, x2 = _SHISHEN_ROI_SLICE
            roi_before = before[y1:y2, x1:x2]
            roi_after = after[y1:y2, x1:x2]
            diff = cv2.absdiff(roi_before, roi_after)
            if np.mean(diff) < _SHISHEN_DIFF_THRESHOLD:
                self.logger.info("[起号_式神养成] 列表已到底部，无法继续滚动")
                return False
        return True

    async def _scroll_find_template(
        self,
        template_path: str,
        label: str,
        *,
        max_scrolls: int = _SHISHEN_MAX_SCROLL,
        threshold: float | None = None,
    ) -> Optional[Match]:
        """从当前位置开始，逐步向下滚动搜索指定模板。

        第 0 次不滚动，直接检查当前画面；之后每次先滚动再检查。
        若列表到底仍未找到，返回 None。
        """
        capture_method = self.ui.capture_method
        kwargs = {"threshold": threshold} if threshold is not None else {}

        for scroll_i in range(max_scrolls + 1):
            # 第 0 次先检查当前画面，后续每次先滚动
            if scroll_i > 0:
                scrolled = await self._scroll_down_once()
                if not scrolled:
                    self.logger.info(
                        f"[起号_式神养成] {label}: 列表到底，未找到模板"
                    )
                    return None

            screenshot = self.adapter.capture(capture_method)
            if screenshot is None:
                continue

            # 弹窗检测
            if self.ui.popup_handler:
                dismissed = await self.ui.popup_handler.check_and_dismiss(screenshot)
                if dismissed > 0:
                    await asyncio.sleep(0.5)
                    screenshot = self.adapter.capture(capture_method)
                    if screenshot is None:
                        continue

            m = match_template(screenshot, template_path, **kwargs)
            if m:
                self.logger.info(
                    f"[起号_式神养成] {label}: 第 {scroll_i} 次滚动后找到模板 "
                    f"(score={m.score:.3f}, center={m.center})"
                )
                return m

        self.logger.info(
            f"[起号_式神养成] {label}: 滚动 {max_scrolls} 次后未找到模板"
        )
        return None
