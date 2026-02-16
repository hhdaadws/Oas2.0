"""
探索章节战斗模块

提供可复用的 run_explore_chapter() 函数，在探索地图中检测标记并逐个战斗。
支持 "all"（全打）和 "glowing_only"（只打发光标记）两种模式。

前置条件：调用方已导航到 TANSUO 界面。
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from ..vision.color_detect import detect_explore_lock
from ..vision.explore_detect import (
    ChallengeGlowState,
    detect_challenge_markers,
)
from ..vision.template import match_template
from .battle import ManualLineupInfo, run_battle, VICTORY, DEFEAT
from .helpers import click_template, wait_for_template

if TYPE_CHECKING:
    from ..emu.adapter import EmulatorAdapter

# ── 模板路径 ──
_TPL_NANDU_PUTONG = "assets/ui/templates/nandu_putong.png"
_TPL_NANDU_KUNNAN_LOCK = "assets/ui/templates/nandu_kunnan_lock.png"
_TPL_TANSUO_TANSUO = "assets/ui/templates/tansuo_tansuo.png"
_TPL_TIAOZHAN = "assets/ui/templates/tiaozhan.png"
_TPL_TANSUO_QUEREN = "assets/ui/templates/tansuo_queren.png"
_TPL_TANSUO_BOSS = "assets/ui/templates/tansuo_boss.png"
_TPL_TANSUO_SHEZHI = "assets/ui/templates/tansuo_shezhi.png"
_TPL_BACK = "assets/ui/templates/back.png"

# ── 坐标常量 ──
_ENTER_EXPLORE_BTN = (870, 402)          # TANSUO 界面进入探索按钮
_EXPLORE_LOCK_TOGGLE = (682, 498)        # 探索界面锁定切换坐标

# ── 探索战斗最大轮次 ──
_MAX_FIGHT_ROUNDS = 20

# ── 地图移动点击区域常量 ──
_MAP_CLICK_LEFT = 656
_MAP_CLICK_TOP = 380
_MAP_CLICK_RIGHT = 942
_MAP_CLICK_BOTTOM = 433
_MAP_CLICK_SETTLE = 1.5
_MAX_MAP_CLICKS = 6


@dataclass
class ExploreChapterResult:
    """探索章节执行结果"""
    victories: int = 0
    defeats: int = 0
    markers_found: int = 0


async def _ensure_explore_lock_state(
    adapter: "EmulatorAdapter",
    capture_method: str,
    should_lock: bool,
    *,
    log: Any = None,
) -> bool:
    """确保探索界面的阵容锁定状态与期望一致。

    使用探索专用模板 zhenrong_lock.png 和 ROI 检测锁定状态，
    通过固定坐标 (682, 498) 切换。

    Args:
        should_lock: True=需要锁定, False=需要解锁

    Returns:
        True 表示状态已正确
    """
    tag = "[探索-锁定]"
    screenshot = adapter.capture(capture_method)
    if screenshot is None:
        if log:
            log.warning(f"{tag} 截图失败")
        return False

    lock_state = detect_explore_lock(screenshot)
    if log:
        log.info(
            f"{tag} locked={lock_state.locked}, score={lock_state.score:.2f}, "
            f"期望={'锁定' if should_lock else '解锁'}"
        )

    if lock_state.locked == should_lock:
        return True

    # 需要切换：重试最多 3 次
    for attempt in range(1, 4):
        lx, ly = _EXPLORE_LOCK_TOGGLE
        adapter.adb.tap(adapter.cfg.adb_addr, lx, ly)
        if log:
            log.info(f"{tag} 点击 ({lx}, {ly}) 切换 (attempt={attempt})")
        await asyncio.sleep(1.0)

        screenshot = adapter.capture(capture_method)
        if screenshot is not None:
            new_state = detect_explore_lock(screenshot)
            if new_state.locked == should_lock:
                if log:
                    log.info(
                        f"{tag} 切换成功: {'锁定' if should_lock else '解锁'}"
                    )
                return True
            lock_state = new_state

    if log:
        log.warning(f"{tag} 切换失败，已重试 3 次")
    return False


async def run_explore_chapter(
    adapter: "EmulatorAdapter",
    capture_method: str,
    *,
    mode: str = "all",
    difficulty: str = "normal",
    manual_lineup: Optional[ManualLineupInfo] = None,
    first_fight: bool = True,
    log: Any = None,
    popup_handler: Any = None,
) -> ExploreChapterResult:
    """在探索地图中检测标记并逐个战斗。

    前置条件：调用方已导航到 TANSUO 界面。

    Args:
        adapter: 模拟器适配器
        capture_method: 截图方式
        mode: "all"（全打）| "glowing_only"（只打发光标记）
        difficulty: "normal" | "hard"
        manual_lineup: 手动阵容配置（首次战斗时使用）
        log: 日志对象
        popup_handler: 弹窗处理器

    Returns:
        ExploreChapterResult
    """
    tag = "[探索章节]"
    result = ExploreChapterResult()

    # ── 1+2. 点击进入探索 + 等待难度面板（3 次重试）──
    m = None
    for attempt in range(1, 4):
        ex, ey = _ENTER_EXPLORE_BTN
        adapter.adb.tap(adapter.cfg.adb_addr, ex, ey)
        if log:
            log.info(
                f"{tag} 点击进入探索 ({ex}, {ey}) (attempt={attempt}/3)"
            )
        await asyncio.sleep(1.5)

        m = await wait_for_template(
            adapter, capture_method, _TPL_NANDU_PUTONG,
            timeout=8.0, interval=0.5,
            log=log, label=f"探索-难度面板(attempt={attempt}/3)",
            popup_handler=popup_handler,
        )
        if m:
            break
        if log:
            log.warning(
                f"{tag} 难度面板未出现 (attempt={attempt}/3)"
            )

    if not m:
        if log:
            log.warning(f"{tag} 难度面板 3 次重试均未出现，尝试直接进入")

    # ── 3. 难度处理 ──
    if difficulty == "hard" and m:
        # 检测困难是否锁定
        screenshot = adapter.capture(capture_method)
        if screenshot is not None:
            lock_m = match_template(screenshot, _TPL_NANDU_KUNNAN_LOCK)
            if lock_m:
                if log:
                    log.warning(f"{tag} 困难难度已锁定，回退到普通")
                difficulty = "normal"
            else:
                # 困难未锁定 — 但 nandu_kunnan.png 模板可能不存在
                # 点击屏幕右侧（困难按钮大致位置）切换到困难
                # TODO: 补充 nandu_kunnan.png 模板后改为 click_template
                try:
                    kunnan_m = match_template(screenshot, "assets/ui/templates/nandu_kunnan.png")
                    if kunnan_m:
                        cx, cy = kunnan_m.random_point()
                        adapter.adb.tap(adapter.cfg.adb_addr, cx, cy)
                        if log:
                            log.info(f"{tag} 切换到困难难度 ({cx}, {cy})")
                        await asyncio.sleep(0.8)
                    else:
                        if log:
                            log.warning(
                                f"{tag} nandu_kunnan.png 模板未匹配，"
                                f"保持普通难度"
                            )
                        difficulty = "normal"
                except Exception:
                    if log:
                        log.warning(f"{tag} 困难模板不可用，保持普通难度")
                    difficulty = "normal"

    # ── 4. 点击探索按钮进入地图（3 次重试）──
    map_entered = False
    for attempt in range(1, 4):
        clicked = await click_template(
            adapter, capture_method, _TPL_TANSUO_TANSUO,
            timeout=8.0, settle=0.5, post_delay=2.0,
            log=log, label=f"探索-进入地图(attempt={attempt}/3)",
            popup_handler=popup_handler,
        )
        if clicked:
            map_entered = True
            break
        if log:
            log.warning(
                f"{tag} 未检测到探索按钮 (attempt={attempt}/3)"
            )
        await asyncio.sleep(2.0)
    if not map_entered:
        if log:
            log.warning(f"{tag} 探索按钮重试 3 次均失败")
        return result

    # ── 5. 等待地图加载（挑战标志或 BOSS 标志出现，2 次重试）──
    _MAP_TEMPLATES = [_TPL_TANSUO_SHEZHI]
    m = None
    for attempt in range(1, 3):
        m = await wait_for_template(
            adapter, capture_method, _MAP_TEMPLATES,
            timeout=20.0, interval=1.0,
            log=log, label=f"探索-等待地图加载(attempt={attempt}/2)",
            popup_handler=popup_handler,
        )
        if m:
            break
        if log:
            log.warning(
                f"{tag} 地图加载超时 (attempt={attempt}/2)"
            )
    if not m:
        if log:
            log.warning(f"{tag} 地图加载 2 次重试均超时")
        return result

    # ── 6. 战斗循环（first_fight 由调用方参数控制）──
    move_count = 0

    for round_idx in range(_MAX_FIGHT_ROUNDS):
        await asyncio.sleep(1.0)

        # 截图检测标记
        screenshot = adapter.capture(capture_method)
        if screenshot is None:
            if log:
                log.warning(f"{tag} 截图失败，结束战斗循环")
            break

        detect_result = detect_challenge_markers(screenshot)
        markers = detect_result.markers

        if log:
            log.info(
                f"{tag} 第{round_idx + 1}轮: "
                f"检测到 {len(markers)} 个标记 "
                f"(发光={detect_result.glowing_count}, "
                f"普通={detect_result.normal_count})"
            )

        # 根据模式筛选
        if mode == "glowing_only":
            targets = detect_result.get_glowing()
        else:
            targets = list(markers)

        if not targets:
            # 回退检测 BOSS 标记
            boss_m = match_template(screenshot, _TPL_TANSUO_BOSS)
            if boss_m:
                if log:
                    log.info(
                        f"{tag} 发现 BOSS 标记 ({boss_m.center[0]}, {boss_m.center[1]}), "
                        f"score={boss_m.score:.3f}"
                    )
                result.markers_found += 1

                # 锁定管理
                if first_fight:
                    await _ensure_explore_lock_state(
                        adapter, capture_method, should_lock=False, log=log
                    )
                else:
                    await _ensure_explore_lock_state(
                        adapter, capture_method, should_lock=True, log=log
                    )

                # 点击 BOSS
                bx, by = boss_m.random_point()
                adapter.adb.tap(adapter.cfg.adb_addr, bx, by)
                if log:
                    log.info(f"{tag} 点击 BOSS ({bx}, {by})")
                await asyncio.sleep(1.5)

                # 执行战斗
                battle_result = await run_battle(
                    adapter, capture_method,
                    confirm_template=None,
                    battle_timeout=120.0,
                    log=log,
                    popup_handler=popup_handler,
                    manual_lineup=manual_lineup if first_fight else None,
                    reward_exit_template=_TPL_TANSUO_SHEZHI,
                )
                first_fight = False

                if battle_result == VICTORY:
                    result.victories += 1
                    if log:
                        log.info(
                            f"{tag} BOSS 战斗胜利 "
                            f"(累计: {result.victories}胜 {result.defeats}负)"
                        )
                elif battle_result == DEFEAT:
                    result.defeats += 1
                    if log:
                        log.warning(
                            f"{tag} BOSS 战斗失败 "
                            f"(累计: {result.victories}胜 {result.defeats}负)"
                        )

                # BOSS 战斗完成，等待判断是否需要手动退出
                if log:
                    log.info(f"{tag} BOSS 战斗完成，等待判断退出方式")
                await asyncio.sleep(3.0)

                still_on_map = await wait_for_template(
                    adapter, capture_method, _MAP_TEMPLATES,
                    timeout=5.0, interval=1.0,
                    log=log, label="探索-BOSS后检测地图",
                    popup_handler=popup_handler,
                )
                if not still_on_map:
                    if log:
                        log.info(f"{tag} BOSS 战后已自动退出探索")
                    return result
                if log:
                    log.info(f"{tag} BOSS 战后仍在地图，执行手动退出")
                break

            # 未检测到 BOSS，在指定区域点击移动
            if move_count < _MAX_MAP_CLICKS:
                move_count += 1
                cx = random.randint(_MAP_CLICK_LEFT, _MAP_CLICK_RIGHT)
                cy = random.randint(_MAP_CLICK_TOP, _MAP_CLICK_BOTTOM)
                if log:
                    log.info(f"{tag} 无可战斗标记，点击 ({cx}, {cy}) 移动 (第{move_count}/{_MAX_MAP_CLICKS}次)")
                adapter.adb.tap(adapter.cfg.adb_addr, cx, cy)
                await asyncio.sleep(_MAP_CLICK_SETTLE)
                continue
            else:
                if log:
                    log.info(f"{tag} 无可战斗标记且已移动 {_MAX_MAP_CLICKS} 次，结束循环")
                break

        result.markers_found += len(targets)

        # 取第一个目标
        target = targets[0]

        # 锁定管理
        if first_fight:
            await _ensure_explore_lock_state(
                adapter, capture_method, should_lock=False, log=log
            )
        else:
            await _ensure_explore_lock_state(
                adapter, capture_method, should_lock=True, log=log
            )

        # 点击标记（含重试验证）
        _MAX_MARKER_CLICK_RETRIES = 3
        marker_click_ok = False

        tx, ty = target.random_point()
        adapter.adb.tap(adapter.cfg.adb_addr, tx, ty)
        if log:
            log.info(
                f"{tag} 点击标记 #{target.index} ({tx}, {ty}) "
                f"[{target.state.value}]"
            )
        await asyncio.sleep(1.5)

        # 验证点击是否生效（tansuo_shezhi 消失表示已进入战斗准备）
        for click_retry in range(_MAX_MARKER_CLICK_RETRIES):
            verify_shot = adapter.capture(capture_method)
            if verify_shot is None:
                if log:
                    log.warning(f"{tag} 点击验证截图失败")
                break

            still_on_map = match_template(verify_shot, _TPL_TANSUO_SHEZHI)
            if not still_on_map:
                if log:
                    log.info(f"{tag} 点击验证通过，已离开探索地图")
                marker_click_ok = True
                break

            # 仍在地图上，点击未生效
            if log:
                log.warning(
                    f"{tag} 点击未生效（tansuo_shezhi 仍可见），"
                    f"重试 {click_retry + 1}/{_MAX_MARKER_CLICK_RETRIES}"
                )

            # 重新检测标记并点击
            retry_detect = detect_challenge_markers(verify_shot)
            if mode == "glowing_only":
                retry_targets = retry_detect.get_glowing()
            else:
                retry_targets = list(retry_detect.markers)

            if not retry_targets:
                if log:
                    log.warning(f"{tag} 重试时未检测到标记，放弃本轮战斗")
                break

            retry_target = retry_targets[0]
            tx, ty = retry_target.random_point()
            adapter.adb.tap(adapter.cfg.adb_addr, tx, ty)
            if log:
                log.info(
                    f"{tag} 重新点击标记 #{retry_target.index} ({tx}, {ty}) "
                    f"[{retry_target.state.value}]"
                )
            await asyncio.sleep(1.5)
        else:
            # for 正常结束（未 break），做最终验证
            final_shot = adapter.capture(capture_method)
            if final_shot is not None:
                still_on_map = match_template(final_shot, _TPL_TANSUO_SHEZHI)
                if not still_on_map:
                    marker_click_ok = True
                    if log:
                        log.info(f"{tag} 最终验证通过，已离开探索地图")

        if not marker_click_ok:
            if log:
                log.warning(
                    f"{tag} 点击标记重试 {_MAX_MARKER_CLICK_RETRIES} 次仍未生效，"
                    f"跳过本轮战斗"
                )
            continue

        # 执行战斗
        battle_result = await run_battle(
            adapter, capture_method,
            confirm_template=None,  # 探索战斗无额外确认按钮
            battle_timeout=120.0,
            log=log,
            popup_handler=popup_handler,
            manual_lineup=manual_lineup if first_fight else None,
            reward_exit_template=_TPL_TANSUO_SHEZHI,
        )

        first_fight = False

        if battle_result == VICTORY:
            result.victories += 1
            if log:
                log.info(
                    f"{tag} 战斗胜利 "
                    f"(累计: {result.victories}胜 {result.defeats}负)"
                )
        elif battle_result == DEFEAT:
            result.defeats += 1
            if log:
                log.warning(
                    f"{tag} 战斗失败 "
                    f"(累计: {result.victories}胜 {result.defeats}负)"
                )
        else:
            if log:
                log.error(f"{tag} 战斗异常: {battle_result}")
            # 等待 3s 后尝试检测是否回到地图
            await asyncio.sleep(3.0)
            recover_m = await wait_for_template(
                adapter, capture_method, _MAP_TEMPLATES,
                timeout=10.0, interval=1.0,
                log=log, label="探索-战斗异常恢复",
                popup_handler=popup_handler,
            )
            if recover_m:
                if log:
                    log.info(f"{tag} 战斗异常后已恢复到地图，继续战斗")
                continue
            else:
                if log:
                    log.warning(f"{tag} 战斗异常后未恢复到地图，结束循环")
                break

        # 等待回到地图（tiaozhan.png 重新出现或超时，2 次重试）
        map_recovered = False
        for recover_attempt in range(1, 3):
            m = await wait_for_template(
                adapter, capture_method, _MAP_TEMPLATES,
                timeout=20.0, interval=1.0,
                log=log, label=f"探索-等待地图恢复(attempt={recover_attempt}/2)",
                popup_handler=popup_handler,
            )
            if m:
                map_recovered = True
                break
            # 重试前点击屏幕中央尝试关闭残留弹窗
            adapter.adb.tap(adapter.cfg.adb_addr, 480, 270)
            if log:
                log.warning(
                    f"{tag} 地图未恢复，点击屏幕中央后重试 "
                    f"(attempt={recover_attempt}/2)"
                )
            await asyncio.sleep(1.0)
        if not map_recovered:
            if log:
                log.warning(f"{tag} 地图恢复 2 次重试均失败，结束战斗循环")
            break

    # ── 7. 退出探索（2 次重试）──
    if log:
        log.info(
            f"{tag} 探索完成，退出地图 "
            f"({result.victories}胜 {result.defeats}负)"
        )

    exit_ok = False
    for exit_attempt in range(1, 3):
        clicked = await click_template(
            adapter, capture_method, _TPL_BACK,
            timeout=8.0, settle=0.3, post_delay=1.0,
            log=log, label=f"探索-返回(attempt={exit_attempt}/2)",
            popup_handler=popup_handler,
        )

        if clicked:
            confirmed = await click_template(
                adapter, capture_method, _TPL_TANSUO_QUEREN,
                timeout=8.0, settle=0.3, post_delay=1.5,
                log=log, label=f"探索-确认退出(attempt={exit_attempt}/2)",
                popup_handler=popup_handler,
            )
            if confirmed:
                exit_ok = True
                break
        if log:
            log.warning(
                f"{tag} 退出探索失败 (attempt={exit_attempt}/2)"
            )
        await asyncio.sleep(1.0)

    if not exit_ok and log:
        log.warning(f"{tag} 退出探索重试 2 次均失败")

    return result


__all__ = ["ExploreChapterResult", "run_explore_chapter"]
