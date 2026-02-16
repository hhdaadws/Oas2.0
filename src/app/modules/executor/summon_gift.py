"""
召唤礼包执行器 - 导航到召唤界面，检测并领取免费召唤礼包
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import cv2  # type: ignore
import numpy as np
from sqlalchemy.orm.attributes import flag_modified

from ...core.constants import TaskStatus, TaskType
from ...core.timeutils import now_beijing
from ...db.base import SessionLocal
from ...db.models import Emulator, GameAccount, SystemConfig, Task
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..ui.manager import UIManager
from ..vision.template import Match, match_template
from ..vision.utils import ImageLike, load_image, random_point_in_circle
from .base import BaseExecutor

# 渠道包名
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# 最大领取轮次（防无限循环）
_MAX_COLLECT_ROUNDS = 10


def _check_small_red_dot(
    image: ImageLike,
    match: Match,
    *,
    corner: str = "top_right",
    margin: int = 8,
    min_red_pixels: int = 6,
) -> bool:
    """针对小模板的红点检测（纯像素计数，无形态学处理）。

    与通用 detect_red_dot 的区别：
    - 不做形态学开运算（避免腐蚀消除微小红点）
    - 不做轮廓圆度过滤（极小像素块圆度不可靠）
    - 纯红色像素计数判定
    - 默认 margin=8（比通用的 4 更大，更好覆盖小模板的红点区域）
    """
    image = load_image(image)
    img_h, img_w = image.shape[:2]
    half_w = match.w // 2
    half_h = match.h // 2

    if corner == "top_right":
        rx = match.x + half_w - margin
        ry = match.y - margin
    elif corner == "top_left":
        rx = match.x - margin
        ry = match.y - margin
    elif corner == "bottom_right":
        rx = match.x + half_w - margin
        ry = match.y + half_h - margin
    else:
        rx = match.x - margin
        ry = match.y + half_h - margin

    rx = max(0, rx)
    ry = max(0, ry)
    rw = min(half_w + 2 * margin, img_w - rx)
    rh = min(half_h + 2 * margin, img_h - ry)
    if rw <= 0 or rh <= 0:
        return False

    roi = image[ry:ry + rh, rx:rx + rw]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    mask1 = cv2.inRange(hsv, np.array([0, 80, 120]), np.array([10, 255, 255]))
    mask2 = cv2.inRange(hsv, np.array([170, 80, 120]), np.array([180, 255, 255]))
    mask = cv2.bitwise_or(mask1, mask2)

    return cv2.countNonZero(mask) >= min_red_pixels


def _detect_reward_red_dots(
    image: ImageLike,
    *,
    roi: tuple = (150, 270, 780, 230),
    min_area: int = 150,
    max_area: int = 250,
    min_circularity: float = 0.45,
) -> list[tuple[int, int]]:
    """检测召唤礼包界面中可领取奖励的按钮红点。

    算法：
    1. 裁切 ROI（y>270 过滤顶部装饰干扰）
    2. BGR→HSV，双段红色掩码
    3. 无形态学处理（保留小像素红点）
    4. 轮廓检测，按面积 + 圆度过滤
    5. 返回中心点列表（原图坐标），按 x 排序

    参数基于 hongdian_test.png 实测验证：
    - 按钮红点：area≈200, circ≈0.55-0.61 → 通过
    - 通知红点：area≈98 → 被 min_area=150 过滤
    - 杂色元素：area<80 或 circ<0.45 → 被过滤
    """
    img = load_image(image)
    rx, ry, rw, rh = roi
    roi_img = img[ry : ry + rh, rx : rx + rw]

    hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
    mask1 = cv2.inRange(hsv, np.array([0, 80, 120]), np.array([10, 255, 255]))
    mask2 = cv2.inRange(hsv, np.array([170, 80, 120]), np.array([180, 255, 255]))
    mask = cv2.bitwise_or(mask1, mask2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    results: list[tuple[int, int]] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue
        circ = (4.0 * np.pi * area) / (perimeter * perimeter)
        if circ < min_circularity:
            continue
        m = cv2.moments(cnt)
        if m["m00"] == 0:
            continue
        cx = int(m["m10"] / m["m00"]) + rx
        cy = int(m["m01"] / m["m00"]) + ry
        results.append((cx, cy))

    results.sort(key=lambda p: p[0])
    return results


class SummonGiftExecutor(BaseExecutor):
    """召唤礼包执行器"""

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
        self.logger.info(f"[召唤礼包] 准备: account={account.login_id}")

        if self.shared_adapter:
            self.adapter = self.shared_adapter
            self.logger.info("[召唤礼包] 复用 shared_adapter，跳过 push 登录数据")
            return True

        if not self.emulator_row:
            with SessionLocal() as db:
                self.emulator_row = (
                    db.query(Emulator).filter(Emulator.id == self.emulator_id).first()
                )
                self.system_config = db.query(SystemConfig).first()

        if not self.emulator_row:
            self.logger.error("[召唤礼包] 模拟器不存在: id={}", self.emulator_id)
            return False

        self.adapter = self._build_adapter()

        ok = self.adapter.push_login_data(account.login_id, data_dir="putonglogindata")
        if not ok:
            self.logger.error(f"[召唤礼包] push 登录数据失败: {account.login_id}")
            return False

        self.logger.info(f"[召唤礼包] push 登录数据成功: {account.login_id}")
        return True

    async def execute(self) -> Dict[str, Any]:
        self.logger.info(f"[召唤礼包] 执行: account={self.current_account.login_id}")

        # 构造/复用 UIManager
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
            self.logger.error("[召唤礼包] 游戏就绪失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "游戏就绪失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. 导航到召唤界面
        self.logger.info("[召唤礼包] 导航至召唤界面")
        in_zhaohuan = await self.ui.ensure_ui("ZHAOHUAN", max_steps=6, step_timeout=3.0)
        if not in_zhaohuan:
            self.logger.error("[召唤礼包] 导航到召唤界面失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "导航到召唤界面失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        await asyncio.sleep(1.0)

        # 3. 截图，检测 zhaohuan_shangdian.png 及其右上角红点
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            self.logger.error("[召唤礼包] 截图失败")
            return {
                "status": TaskStatus.FAILED,
                "error": "截图失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 弹窗检测
        if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
            await asyncio.sleep(1.0)
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is None:
                return {
                    "status": TaskStatus.FAILED,
                    "error": "截图失败",
                    "timestamp": datetime.utcnow().isoformat(),
                }

        shangdian_match = match_template(
            screenshot, "assets/ui/templates/zhaohuan_shangdian.png"
        )
        if not shangdian_match:
            self.logger.warning("[召唤礼包] 未检测到召唤商店标签")
            self._update_next_time()
            return {
                "status": TaskStatus.SUCCEEDED,
                "message": "未检测到召唤商店标签，跳过",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 4. 检测 zhaohuan_shangdian 右上角红点
        has_red = _check_small_red_dot(screenshot, shangdian_match, corner="top_right")
        if not has_red:
            self.logger.info("[召唤礼包] 召唤商店无红点，无需领取")
            self._update_next_time()
            return {
                "status": TaskStatus.SUCCEEDED,
                "message": "无可领取礼包",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 5. 有红点，点击进入召唤礼包界面
        sx, sy = shangdian_match.random_point()
        self.logger.info(f"[召唤礼包] 检测到红点，点击召唤商店 ({sx}, {sy})")
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, sx, sy)
        await asyncio.sleep(1.5)

        # 6. 确认进入召唤礼包界面
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            return {
                "status": TaskStatus.FAILED,
                "error": "截图失败",
                "timestamp": datetime.utcnow().isoformat(),
            }

        libao_tag = match_template(screenshot, "assets/ui/templates/libao_tag.png")
        if not libao_tag:
            self.logger.warning("[召唤礼包] 未进入召唤礼包界面，重试一次")
            await asyncio.sleep(1.5)
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is not None:
                libao_tag = match_template(
                    screenshot, "assets/ui/templates/libao_tag.png"
                )
            if not libao_tag:
                self.logger.error("[召唤礼包] 无法进入召唤礼包界面")
                self._update_next_time()
                return {
                    "status": TaskStatus.FAILED,
                    "error": "无法进入召唤礼包界面",
                    "timestamp": datetime.utcnow().isoformat(),
                }

        self.logger.info("[召唤礼包] 已进入召唤礼包界面")

        # ====== 7. Phase A: 免费购买（如尚未购买） ======
        collected_count = 0

        await asyncio.sleep(1.0)
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is None:
            self.logger.warning("[召唤礼包] Phase A: 截图失败")
        else:
            # 弹窗检测
            if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
                await asyncio.sleep(1.0)
                screenshot = self.adapter.capture(self.ui.capture_method)

            if screenshot is not None:
                mianfei_match = match_template(
                    screenshot, "assets/ui/templates/zhaohuan_mianfei.png"
                )
                if mianfei_match:
                    # 找到免费按钮，点击购买
                    mx, my = mianfei_match.random_point()
                    self.logger.info(
                        f"[召唤礼包] Phase A: 检测到免费按钮，点击 ({mx}, {my})"
                    )
                    self.adapter.adb.tap(self.adapter.cfg.adb_addr, mx, my)
                    await asyncio.sleep(1.5)

                    # 等待并点击确认按钮 queren_mianfei.png
                    purchase_done = False
                    for retry in range(5):
                        ss = self.adapter.capture(self.ui.capture_method)
                        if ss is None:
                            await asyncio.sleep(0.5)
                            continue
                        queren_match = match_template(
                            ss, "assets/ui/templates/queren_mianfei.png"
                        )
                        if queren_match:
                            qx, qy = queren_match.random_point()
                            self.logger.info(
                                f"[召唤礼包] Phase A: 点击确认购买 ({qx}, {qy})"
                            )
                            self.adapter.adb.tap(
                                self.adapter.cfg.adb_addr, qx, qy
                            )
                            purchase_done = True
                            collected_count += 1
                            await asyncio.sleep(2.0)
                            break
                        await asyncio.sleep(0.5)

                    if not purchase_done:
                        self.logger.warning(
                            "[召唤礼包] Phase A: 未检测到确认按钮，购买可能失败"
                        )

                    # 关闭可能出现的奖励/插画弹窗
                    await self._dismiss_jiangli("Phase A")
                else:
                    self.logger.info(
                        "[召唤礼包] Phase A: 未检测到免费按钮，购买已完成"
                    )

        # ====== 7. Phase B: 红点领取循环 ======
        for round_idx in range(_MAX_COLLECT_ROUNDS):
            await asyncio.sleep(1.0)
            screenshot = self.adapter.capture(self.ui.capture_method)
            if screenshot is None:
                self.logger.warning("[召唤礼包] Phase B: 截图失败，停止扫描")
                break

            # 弹窗检测
            if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
                continue

            # 检测奖励按钮红点（实测验证参数）
            red_dots = _detect_reward_red_dots(screenshot)

            if not red_dots:
                self.logger.info(
                    f"[召唤礼包] Phase B: 第 {round_idx + 1} 轮无红点，领取完毕"
                )
                break

            self.logger.info(
                f"[召唤礼包] Phase B: 第 {round_idx + 1} 轮检测到 "
                f"{len(red_dots)} 个红点"
            )

            # 直接点击第一个按钮红点（红点在奖励按钮本体上）
            dot_x, dot_y = red_dots[0]
            self.logger.info(
                f"[召唤礼包] Phase B: 点击红点 ({dot_x}, {dot_y})"
            )
            self.adapter.adb.tap(self.adapter.cfg.adb_addr, dot_x, dot_y)
            collected_count += 1
            await asyncio.sleep(1.5)

            # 关闭奖励/插画弹窗
            await self._dismiss_jiangli(f"Phase B 第{round_idx + 1}轮")

        # 8. 点击 back 返回召唤界面
        self.logger.info("[召唤礼包] 点击返回召唤界面")
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is not None:
            back_match = match_template(screenshot, "assets/ui/templates/back.png")
            if back_match:
                bx, by = back_match.random_point()
                self.adapter.adb.tap(self.adapter.cfg.adb_addr, bx, by)
                self.logger.info(f"[召唤礼包] 点击返回按钮 ({bx}, {by})")
            else:
                self.logger.warning("[召唤礼包] 未检测到返回按钮")

        self._update_next_time()

        self.logger.info(f"[召唤礼包] 执行完成，领取了 {collected_count} 个免费礼包")
        return {
            "status": TaskStatus.SUCCEEDED,
            "message": f"领取了 {collected_count} 个免费礼包",
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _dismiss_jiangli(self, step_label: str) -> None:
        """关闭 jiangli.png 奖励弹窗，之后可能出现 chahua.png 也一并关闭"""
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is not None:
            if await self.ui.popup_handler.check_and_dismiss(screenshot) > 0:
                await asyncio.sleep(0.5)
                screenshot = self.adapter.capture(self.ui.capture_method)

        if screenshot is not None:
            jiangli_result = match_template(
                screenshot, "assets/ui/templates/jiangli.png"
            )
            if jiangli_result:
                self.logger.info(
                    f"[召唤礼包] {step_label} 检测到奖励弹窗，点击关闭"
                )
            else:
                self.logger.info(
                    f"[召唤礼包] {step_label} 未检测到奖励弹窗，仍尝试点击关闭"
                )

        close_x, close_y = random_point_in_circle(20, 20, 20)
        self.adapter.adb.tap(self.adapter.cfg.adb_addr, close_x, close_y)
        self.logger.info(
            f"[召唤礼包] {step_label} 随机点击 ({close_x}, {close_y}) 关闭弹窗"
        )
        await asyncio.sleep(1.0)

        # 关闭可能出现的插画弹窗 (chahua.png)
        screenshot = self.adapter.capture(self.ui.capture_method)
        if screenshot is not None:
            chahua_result = match_template(
                screenshot, "assets/ui/templates/chahua.png"
            )
            if chahua_result:
                self.logger.info(
                    f"[召唤礼包] {step_label} 检测到插画弹窗，点击关闭"
                )
                cx, cy = random_point_in_circle(20, 20, 20)
                self.adapter.adb.tap(self.adapter.cfg.adb_addr, cx, cy)
                await asyncio.sleep(1.0)

    def _update_next_time(self) -> None:
        """更新召唤礼包的 next_time 为明天 00:01"""
        try:
            bj_now = now_beijing()
            tomorrow = bj_now.date() + timedelta(days=1)
            next_time = f"{tomorrow.isoformat()} 00:01"

            with SessionLocal() as db:
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.id == self.current_account.id)
                    .first()
                )
                if account:
                    cfg = account.task_config or {}
                    gift_cfg = cfg.get("召唤礼包", {})
                    gift_cfg["next_time"] = next_time
                    cfg["召唤礼包"] = gift_cfg
                    account.task_config = cfg
                    flag_modified(account, "task_config")
                    db.commit()
                    self.logger.info(f"[召唤礼包] next_time 更新为 {next_time}")
        except Exception as e:
            self.logger.error(f"[召唤礼包] 更新 next_time 失败: {e}")

    async def cleanup(self) -> None:
        if self.skip_cleanup:
            self.logger.info("[召唤礼包] 批次中非最后任务，跳过 cleanup")
            return
        if self.adapter:
            try:
                self.adapter.adb.force_stop(self.adapter.cfg.adb_addr, PKG_NAME)
                self.logger.info("[召唤礼包] 游戏已停止")
            except Exception as e:
                self.logger.error(f"[召唤礼包] 停止游戏失败: {e}")
