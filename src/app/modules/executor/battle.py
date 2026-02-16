"""
通用战斗模块

处理战斗确认、等待战斗结束、判定胜负、领取奖励。
可被地鬼、探索、逢魔等多个执行器复用。
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

from ..vision.template import Match, match_template
from .helpers import click_template, wait_for_template

if TYPE_CHECKING:
    from ..emu.adapter import EmulatorAdapter

# 模板路径
_TPL_SHENGLI = "assets/ui/templates/zhandou_shengli.png"
_TPL_SHIBAI = "assets/ui/templates/zhandou_shibai.png"
_TPL_JIANGLI = "assets/ui/templates/zhandou_jiangli.png"
_TPL_YUSHE = "assets/ui/templates/zhandou_yushe.png"
_TPL_CHUZHAN = "assets/ui/templates/zhandou_chuzhan.png"

# ── 手动阵容配置相关模板和常量 ──
_TPL_TAG_ZHENRONG = "assets/ui/templates/tag_zhenrong.png"
_TPL_ZHENRONG_R = "assets/ui/templates/zhenrong_r.png"

_LINEUP_POS_1 = (127, 281)         # 阵容位置1 坐标（放租借式神）
_LINEUP_POS_2 = (297, 295)         # 阵容位置2 坐标（放座敷童子）
_LINEUP_CONFIG_BTN = (462, 446)    # 进入阵容配置界面的点击坐标
_ZUOFU_SEARCH_START = (517, 448)   # 座敷童子搜索起点
_DRAG_DUR_MS = 800                 # 拖拽持续时间（ms）
_ZUOFU_SWIPE_DUR_MS = 600         # 搜索滑动持续时间（ms）
_ZUOFU_SWIPE_DIST = 200           # 每次左滑距离（px）
_ZUOFU_MAX_SWIPES = 5             # 最大搜索滑动次数


@dataclass
class ManualLineupInfo:
    """手动阵容配置信息（由 executor 从数据库加载后构建）。

    Attributes:
        rental_shikigami: 租借式神列表，已按优先级排序。
            每项为 (template_path, name, star)。
        zuofu_template: 座敷童子模板路径（根据觉醒状态选择）。
            None 表示不配置座敷童子。
        config_btn: 进入阵容配置界面的点击坐标覆盖。
            None 使用默认值 (462, 446)。探索场景使用 (165, 390)。
        lineup_pos_1: 阵容位置1 坐标覆盖（放租借式神）。
            None 使用默认值 (127, 281)。
        lineup_pos_2: 阵容位置2 坐标覆盖（放座敷童子）。
            None 使用默认值 (297, 295)。
    """
    rental_shikigami: List[Tuple[str, str, int]] = field(default_factory=list)
    zuofu_template: str | None = None
    config_btn: Tuple[int, int] | None = None
    lineup_pos_1: Tuple[int, int] | None = None
    lineup_pos_2: Tuple[int, int] | None = None


def _discover_templates(pattern: str) -> List[str]:
    """自动发现匹配 pattern 的模板文件。"""
    paths = sorted(Path("assets/ui/templates").glob(pattern))
    return [p.as_posix() for p in paths]


_TPL_ZIDONG_LIST = _discover_templates("zhandou_zidong_*.png")
_TPL_ZHUNBEI_LIST = _discover_templates("zhandou_zhunbei_*.png")

# 战斗结果常量
VICTORY = "victory"
DEFEAT = "defeat"
TIMEOUT = "timeout"
ERROR = "error"


async def _wait_for_any_template(
    adapter: EmulatorAdapter,
    capture_method: str,
    templates: List[str],
    *,
    timeout: float = 8.0,
    interval: float = 1.0,
    threshold: float | None = None,
    log: Any = None,
    label: str = "",
    popup_handler: Any = None,
) -> Optional[Match]:
    """轮询截图直到任一模板出现。

    Args:
        templates: 模板路径列表，任一匹配即返回。

    Returns:
        Match 对象，超时返回 None。
    """
    tag = f"[{label}] " if label else ""
    elapsed = 0.0
    kwargs = {"threshold": threshold} if threshold is not None else {}

    while elapsed < timeout:
        screenshot = adapter.capture(capture_method)
        if screenshot is not None:
            for tpl in templates:
                m = match_template(screenshot, tpl, **kwargs)
                if m:
                    if log:
                        log.info(
                            f"{tag}检测到模板 {Path(tpl).name}"
                            f" (score={m.score:.3f}, elapsed={elapsed:.1f}s)"
                        )
                    return m
            # 模板未找到时检查弹窗
            if popup_handler is not None:
                dismissed = await popup_handler.check_and_dismiss(screenshot)
                if dismissed > 0:
                    continue
        await asyncio.sleep(interval)
        elapsed += interval

    if log:
        log.warning(f"{tag}等待模板超时 ({timeout:.0f}s)")
    return None


async def _switch_battle_lineup(
    adapter: EmulatorAdapter,
    capture_method: str,
    *,
    group: int,
    position: int,
    log: Any = None,
    popup_handler: Any = None,
) -> bool:
    """在战斗准备界面通过预设面板切换阵容。

    前置条件: 已确认在战斗准备界面（由调用方保证）。

    流程:
        1. 等待准备按钮出现（确认在战斗准备界面）
        2. 点击预设按钮 (yushe)
        3. 截图 → 检测分组格子 → 点击目标分组
        4. 等待刷新 → 截图 → 检测阵容格子 → 点击目标阵容
        5. 点击出战按钮 (chuzhan)

    Returns:
        True 切换成功，False 失败（不中断战斗流程）
    """
    from ..vision.battle_lineup_detect import detect_battle_groups, detect_battle_lineups

    tag = "[阵容切换]"
    addr = adapter.cfg.adb_addr

    # 1. 等待准备按钮确认在战斗准备界面
    zhunbei = await _wait_for_any_template(
        adapter, capture_method, _TPL_ZHUNBEI_LIST,
        timeout=15.0, interval=1.0,
        log=log, label="阵容-等待准备界面",
        popup_handler=popup_handler,
    )
    if not zhunbei:
        if log:
            log.warning(f"{tag} 等待准备界面超时")
        return False

    # 2. 点击预设按钮
    clicked = await click_template(
        adapter, capture_method, _TPL_YUSHE,
        timeout=8.0, settle=0.5, post_delay=1.0,
        log=log, label="阵容-预设",
        popup_handler=popup_handler,
    )
    if not clicked:
        if log:
            log.warning(f"{tag} 未找到预设按钮")
        return False

    # 3. 截图 → 检测分组 → 点击目标分组（3 次截图重试）
    await asyncio.sleep(0.8)
    groups = []
    for attempt in range(1, 4):
        screenshot = adapter.capture(capture_method)
        if screenshot is None:
            if log:
                log.warning(f"{tag} 截图失败 (attempt={attempt}/3)")
            await asyncio.sleep(0.5)
            continue

        groups = detect_battle_groups(screenshot)
        if log:
            log.info(
                f"{tag} 检测到 {len(groups)} 个分组 (attempt={attempt}/3)"
            )
        if groups and group <= len(groups):
            break
        await asyncio.sleep(0.5)

    if not groups or group > len(groups):
        if log:
            log.warning(f"{tag} 分组 {group} 超出范围 (检测到 {len(groups)} 个)")
        return False

    target_group = groups[group - 1]
    cx, cy = target_group.random_point()
    adapter.adb.tap(addr, cx, cy)
    if log:
        log.info(f"{tag} 点击分组 {group} ({cx}, {cy})")

    # 4. 等待阵容列表更新 → 截图 → 检测阵容 → 点击目标阵容（3 次截图重试）
    await asyncio.sleep(1.0)
    lineups = []
    for attempt in range(1, 4):
        screenshot = adapter.capture(capture_method)
        if screenshot is None:
            if log:
                log.warning(f"{tag} 截图失败 (attempt={attempt}/3)")
            await asyncio.sleep(0.5)
            continue

        lineups = detect_battle_lineups(screenshot)
        if log:
            log.info(
                f"{tag} 检测到 {len(lineups)} 个阵容 (attempt={attempt}/3)"
            )
        if lineups and position <= len(lineups):
            break
        await asyncio.sleep(0.5)

    if not lineups or position > len(lineups):
        if log:
            log.warning(f"{tag} 阵容 {position} 超出范围 (检测到 {len(lineups)} 个)")
        return False

    target_lineup = lineups[position - 1]
    cx, cy = target_lineup.random_point()
    adapter.adb.tap(addr, cx, cy)
    if log:
        log.info(f"{tag} 点击阵容 {position} ({cx}, {cy})")

    # 5. 点击出战
    await asyncio.sleep(1.0)
    clicked = await click_template(
        adapter, capture_method, _TPL_CHUZHAN,
        timeout=8.0, settle=0.5, post_delay=1.0,
        log=log, label="阵容-出战",
        popup_handler=popup_handler,
    )
    if not clicked:
        if log:
            log.warning(f"{tag} 未找到出战按钮")
        return False

    if log:
        log.info(f"{tag} 阵容切换完成 (分组={group}, 阵容={position})")
    return True


async def _manual_setup_lineup(
    adapter: EmulatorAdapter,
    capture_method: str,
    manual_lineup: ManualLineupInfo,
    *,
    log: Any = None,
    popup_handler: Any = None,
) -> bool:
    """在战斗准备界面手动配置阵容（无预设时使用）。

    前置条件: 已确认在战斗准备界面（由调用方保证）。

    流程:
        1. 等待准备按钮出现（确认在战斗准备界面）
        2. 点击 (462, 446) 进入阵容配置界面
        3. 等待 tag_zhenrong.png 确认界面加载
        4. 在底部式神列表中找到优先级最高的租借式神，长按拖动到位置1
        5. 点击 tag_zhenrong.png（切换标签）
        6. 点击 zhenrong_r.png（筛选R级式神）
        7. 从 (517, 448) 向左缓慢滑动搜索座敷童子
        8. 找到座敷童子后，长按拖动到位置2

    注意: 不点击准备按钮，返回后由 run_battle() 主循环自动点击。

    Returns:
        True 配置成功，False 失败（不中断战斗流程）
    """
    tag = "[手动阵容]"
    addr = adapter.cfg.adb_addr

    # 1. 等待准备按钮确认在战斗准备界面
    zhunbei = await _wait_for_any_template(
        adapter, capture_method, _TPL_ZHUNBEI_LIST,
        timeout=15.0, interval=1.0,
        log=log, label="手动阵容-等待准备界面",
        popup_handler=popup_handler,
    )
    if not zhunbei:
        if log:
            log.warning(f"{tag} 等待准备界面超时")
        return False

    # 2+3. 点击进入阵容配置界面 + 等待加载（持续重试最多 20 次）
    config_btn = manual_lineup.config_btn or _LINEUP_CONFIG_BTN
    zhenrong_ready = False
    for attempt in range(1, 21):
        adapter.adb.tap(addr, *config_btn)
        if log:
            log.info(
                f"{tag} 点击进入阵容配置 {config_btn} (attempt={attempt}/20)"
            )
        await asyncio.sleep(1.5)

        m = await wait_for_template(
            adapter, capture_method, _TPL_TAG_ZHENRONG,
            timeout=3.0, interval=0.5,
            log=log, label=f"手动阵容-等待阵容界面(attempt={attempt}/20)",
            popup_handler=popup_handler,
        )
        if m:
            zhenrong_ready = True
            break
        if log:
            log.warning(
                f"{tag} 阵容配置界面未加载 (attempt={attempt}/20)"
            )

    if not zhenrong_ready:
        if log:
            log.warning(f"{tag} 阵容配置界面加载失败，已重试 20 次")
        return False

    # 4. 在底部式神列表中找到并拖动租借式神到位置1
    rental_placed = False
    if manual_lineup.rental_shikigami:
        for tpl_path, name, star in manual_lineup.rental_shikigami:
            found = False
            for cap_attempt in range(1, 11):  # 每个式神 10 次截图重试
                screenshot = adapter.capture(capture_method)
                if screenshot is None:
                    await asyncio.sleep(0.3)
                    continue
                m = match_template(screenshot, tpl_path, threshold=0.80)
                if m:
                    cx, cy = m.center
                    tx, ty = manual_lineup.lineup_pos_1 or _LINEUP_POS_1
                    try:
                        adapter.swipe(cx, cy, tx, ty, _DRAG_DUR_MS)
                    except Exception as e:
                        if log:
                            log.warning(f"{tag} 拖动式神 swipe 失败: {e}")
                        break
                    if log:
                        log.info(
                            f"{tag} 拖动 {name}({star}★) "
                            f"({cx},{cy}) → ({tx},{ty})"
                        )
                    await asyncio.sleep(1.0)
                    rental_placed = True
                    found = True
                    break
                if cap_attempt < 10:
                    await asyncio.sleep(0.5)
            if found:
                break
            if log:
                log.info(f"{tag} 未在列表中找到 {name}({star}★)")

    if not rental_placed and log:
        log.warning(f"{tag} 未能放置任何租借式神")

    # 5. 配置座敷童子
    if manual_lineup.zuofu_template:
        # 5a. 点击阵容标签
        clicked = await click_template(
            adapter, capture_method, _TPL_TAG_ZHENRONG,
            timeout=5.0, settle=0.3, post_delay=0.8,
            log=log, label="手动阵容-点击阵容标签",
            popup_handler=popup_handler,
        )
        if not clicked and log:
            log.warning(f"{tag} 未找到阵容标签")

        # 5b. 点击 R 级筛选
        clicked = await click_template(
            adapter, capture_method, _TPL_ZHENRONG_R,
            timeout=5.0, settle=0.3, post_delay=0.8,
            log=log, label="手动阵容-R级筛选",
            popup_handler=popup_handler,
        )
        if not clicked and log:
            log.warning(f"{tag} 未找到R级筛选按钮")

        # 5c. 从右向左滑动搜索座敷童子
        zuofu_found = False
        for swipe_idx in range(_ZUOFU_MAX_SWIPES):
            screenshot = adapter.capture(capture_method)
            if screenshot is None:
                await asyncio.sleep(0.5)
                continue

            m = match_template(
                screenshot, manual_lineup.zuofu_template, threshold=0.80,
            )
            if m:
                cx, cy = m.center
                tx, ty = manual_lineup.lineup_pos_2 or _LINEUP_POS_2
                try:
                    adapter.swipe(cx, cy, tx, ty, _DRAG_DUR_MS)
                except Exception as e:
                    if log:
                        log.warning(f"{tag} 拖动座敷童子 swipe 失败: {e}")
                    break
                if log:
                    log.info(
                        f"{tag} 拖动座敷童子 ({cx},{cy}) → ({tx},{ty})"
                    )
                zuofu_found = True
                await asyncio.sleep(1.0)
                break

            # 向左滑动搜索
            sx, sy = _ZUOFU_SEARCH_START
            try:
                adapter.swipe(sx, sy, sx - _ZUOFU_SWIPE_DIST, sy, _ZUOFU_SWIPE_DUR_MS)
            except Exception as e:
                if log:
                    log.warning(f"{tag} 搜索座敷童子 swipe 失败: {e}")
                break
            if log:
                log.info(
                    f"{tag} 向左滑动搜索座敷童子 (第{swipe_idx + 1}次)"
                )
            await asyncio.sleep(0.8)

        if not zuofu_found and log:
            log.warning(f"{tag} 未找到座敷童子")

    if log:
        log.info(f"{tag} 手动阵容配置完成")
    return True


async def run_battle(
    adapter: EmulatorAdapter,
    capture_method: str,
    *,
    confirm_template: str | None = None,
    battle_timeout: float = 120.0,
    log: Any = None,
    popup_handler: Any = None,
    lineup: dict | None = None,
    manual_lineup: ManualLineupInfo | None = None,
    reward_exit_template: str | None = None,
) -> str:
    """执行一场完整战斗并返回结果。

    从确认按钮出现时接管，处理整个战斗流程直到奖励领取完毕。

    Args:
        adapter: 模拟器适配器
        capture_method: 截图方式 ("adb" / "ipc")
        confirm_template: 战斗确认按钮模板路径（如 digui_tiaozhan_sure.png），
                          为 None 则跳过确认步骤
        battle_timeout: 战斗阶段最大等待秒数
        log: 日志对象
        popup_handler: 弹窗处理器
        lineup: 阵容配置 {"group": int, "position": int}，
                group/position > 0 时在战斗准备界面通过预设面板切换阵容。
                为 None 或 group/position 为 0 时跳过切换。
        manual_lineup: 手动阵容配置信息。当无预设阵容时，根据租借式神和
                       座敷童子数据在战斗准备界面拖拽配置阵容。
                       优先级：lineup > manual_lineup > 默认阵容。
        reward_exit_template: 奖励退出模板路径。指定后，胜利时持续点击奖励区域
                              直到该模板出现（用于探索等需要多次点击奖励的场景）。
                              为 None 时使用默认的 verify_gone 逻辑。

    Returns:
        "victory" | "defeat" | "timeout" | "error"
    """
    tag = "[战斗]"

    # 1. 点击确认按钮（如 digui_tiaozhan_sure.png）（2 次重试）
    if confirm_template:
        confirm_clicked = False
        for attempt in range(1, 3):
            clicked = await click_template(
                adapter, capture_method, confirm_template,
                timeout=10.0, settle=0.5, post_delay=1.5,
                log=log, label=f"战斗-确认(attempt={attempt}/2)",
                popup_handler=popup_handler,
            )
            if clicked:
                confirm_clicked = True
                break
            if log:
                log.warning(
                    f"{tag} 未检测到确认按钮 (attempt={attempt}/2)"
                )
            await asyncio.sleep(1.5)
        if not confirm_clicked:
            if log:
                log.error(f"{tag} 确认按钮重试 2 次均失败")
            return ERROR

    # 1.5 战斗内阵容切换（预设面板）
    if lineup and lineup.get("group", 0) > 0 and lineup.get("position", 0) > 0:
        switched = await _switch_battle_lineup(
            adapter, capture_method,
            group=lineup["group"],
            position=lineup["position"],
            log=log,
            popup_handler=popup_handler,
        )
        if not switched and log:
            log.warning(f"{tag} 战斗阵容切换失败，继续使用当前阵容")
    # 1.6 手动阵容配置（无预设时的备选方案）
    elif manual_lineup and (
        manual_lineup.rental_shikigami or manual_lineup.zuofu_template
    ):
        setup_ok = await _manual_setup_lineup(
            adapter, capture_method, manual_lineup,
            log=log,
            popup_handler=popup_handler,
        )
        if not setup_ok and log:
            log.warning(f"{tag} 手动阵容配置失败，继续使用当前阵容")

    # 2+3. 点击准备并等待进入战斗（自动按钮出现）
    #      准备按钮点击可能失败，循环重试直到准备消失且自动出现
    battle_entered = False
    enter_elapsed = 0.0
    enter_timeout = 20.0
    enter_interval = 1.5

    while enter_elapsed < enter_timeout:
        screenshot = adapter.capture(capture_method)
        if screenshot is None:
            await asyncio.sleep(enter_interval)
            enter_elapsed += enter_interval
            continue

        # 优先检查是否已进入战斗（自动按钮出现）
        best_zidong_score = 0.0
        for tpl in _TPL_ZIDONG_LIST:
            m = match_template(screenshot, tpl)
            if m:
                if m.score > best_zidong_score:
                    best_zidong_score = m.score
                if log:
                    log.info(
                        f"{tag} 检测到自动按钮 {Path(tpl).name}，已进入战斗"
                        f" (score={m.score:.3f}, elapsed={enter_elapsed:.1f}s)"
                    )
                battle_entered = True
                break
        if battle_entered:
            break
        if best_zidong_score > 0 and log:
            log.debug(
                f"{tag} 自动按钮最佳分数: {best_zidong_score:.3f} (未达阈值)"
            )

        # 检查弹窗
        if popup_handler is not None:
            dismissed = await popup_handler.check_and_dismiss(screenshot)
            if dismissed > 0:
                continue

        # 准备按钮检测（多模板）
        zhunbei_clicked = False
        for tpl in _TPL_ZHUNBEI_LIST:
            m_zhunbei = match_template(screenshot, tpl)
            if m_zhunbei:
                cx, cy = m_zhunbei.random_point()
                if log:
                    log.info(
                        f"{tag} 检测到准备按钮 {Path(tpl).name}，"
                        f"点击 ({cx}, {cy}) (score={m_zhunbei.score:.3f})"
                    )
                adapter.adb.tap(adapter.cfg.adb_addr, cx, cy)
                zhunbei_clicked = True
                break
        if not zhunbei_clicked and log:
            log.debug(f"{tag} 未检测到准备按钮 (模板数={len(_TPL_ZHUNBEI_LIST)})")

        await asyncio.sleep(enter_interval)
        enter_elapsed += enter_interval

    if not battle_entered:
        if log:
            log.error(f"{tag} 未检测到战斗界面 (准备/自动超时)")
        return ERROR

    if log:
        log.info(f"{tag} 已进入战斗，等待战斗结束 (timeout={battle_timeout}s)")

    # 4. 轮询等待战斗结束（胜利 / 失败 / 奖励界面直接出现）
    end_match = await _wait_for_any_template(
        adapter, capture_method,
        [_TPL_SHENGLI, _TPL_SHIBAI, _TPL_JIANGLI],
        timeout=battle_timeout, interval=2.0,
        log=log, label="战斗-结果",
        popup_handler=popup_handler,
    )
    if not end_match:
        if log:
            log.warning(f"{tag} 等待战斗结果超时")
        return TIMEOUT

    # 再次截图确认状态
    await asyncio.sleep(0.5)
    screenshot = adapter.capture(capture_method)
    is_victory = True  # 默认视为胜利
    is_jiangli = False
    if screenshot is not None:
        m_shibai = match_template(screenshot, _TPL_SHIBAI)
        if m_shibai:
            is_victory = False
        m_jiangli_check = match_template(screenshot, _TPL_JIANGLI)
        if m_jiangli_check:
            is_jiangli = True

    if is_victory or is_jiangli:
        if not is_jiangli:
            # 5. 点击胜利（奖励界面已出现时跳过此步骤）
            if log:
                log.info(f"{tag} 战斗胜利，点击")
            await click_template(
                adapter, capture_method, _TPL_SHENGLI,
                timeout=5.0, settle=0.5, post_delay=1.5,
                log=log, label="战斗-点击胜利",
                popup_handler=popup_handler,
            )
        else:
            if log:
                log.info(f"{tag} 战斗胜利，奖励界面已出现，跳过点击胜利")

        # 6. 奖励处理
        if reward_exit_template:
            # 探索模式：持续点击奖励区域直到 tansuo_shezhi 出现
            _TPL_TANSUO_SHEZHI = "assets/ui/templates/tansuo_shezhi.png"
            if is_jiangli:
                # 奖励界面已出现，直接获取坐标开始点击
                click_x, click_y = m_jiangli_check.random_point()
                click_x += 100  # 偏右点击，避免点到奖励图标本身
            else:
                # 等待奖励界面出现
                m_jiangli = await wait_for_template(
                    adapter, capture_method, _TPL_JIANGLI,
                    timeout=8.0, interval=0.5,
                    log=log, label="战斗-等待奖励",
                    popup_handler=popup_handler,
                )
                if m_jiangli:
                    click_x, click_y = m_jiangli.random_point()
                    click_x += 100  # 偏右点击，避免点到奖励图标本身
                else:
                    if log:
                        log.warning(f"{tag} 未检测到奖励界面，但战斗已胜利，尝试恢复")
                    # 检测是否已回到探索地图
                    screenshot = adapter.capture(capture_method)
                    already_back = False
                    if screenshot is not None:
                        m_exit_check = match_template(screenshot, _TPL_TANSUO_SHEZHI)
                        if m_exit_check:
                            if log:
                                log.info(f"{tag} 已检测到 tansuo_shezhi，无需恢复")
                            already_back = True
                    if not already_back:
                        # 点击右上角随机坐标尝试恢复
                        max_recovery_clicks = 15
                        recovery_ok = False
                        for rc_idx in range(max_recovery_clicks):
                            rx = random.randint(920, 940)
                            ry = random.randint(10, 30)
                            adapter.adb.tap(adapter.cfg.adb_addr, rx, ry)
                            if log:
                                log.info(
                                    f"{tag} 恢复点击 ({rx}, {ry}) "
                                    f"(第{rc_idx + 1}/{max_recovery_clicks}次)"
                                )
                            await asyncio.sleep(1.0)
                            screenshot = adapter.capture(capture_method)
                            if screenshot is not None:
                                m_exit_recover = match_template(
                                    screenshot, _TPL_TANSUO_SHEZHI
                                )
                                if m_exit_recover:
                                    if log:
                                        log.info(
                                            f"{tag} 恢复成功，检测到 tansuo_shezhi "
                                            f"(第{rc_idx + 1}次点击)"
                                        )
                                    recovery_ok = True
                                    break
                        if not recovery_ok:
                            if log:
                                log.error(
                                    f"{tag} 恢复点击 {max_recovery_clicks} 次"
                                    f"仍未检测到 tansuo_shezhi"
                                )
                            return ERROR
                    click_x, click_y = None, None  # 跳过原有点击循环

            if click_x is not None:
                max_clicks = 30
                click_interval = 1.0
                found_exit = False
                for i in range(max_clicks):
                    adapter.adb.tap(adapter.cfg.adb_addr, click_x, click_y)
                    await asyncio.sleep(click_interval)
                    screenshot = adapter.capture(capture_method)
                    if screenshot is not None:
                        m_exit = match_template(screenshot, _TPL_TANSUO_SHEZHI)
                        if m_exit:
                            if log:
                                log.info(
                                    f"{tag} 检测到 tansuo_shezhi，"
                                    f"奖励处理完成 (第{i + 1}次点击)"
                                )
                            found_exit = True
                            break
                if not found_exit:
                    if log:
                        log.error(
                            f"{tag} 点击奖励 {max_clicks} 次"
                            f"仍未检测到 tansuo_shezhi，退出任务"
                        )
                    return ERROR
        else:
            # 通用模式：verify_gone 确保奖励界面真正关闭
            clicked = await click_template(
                adapter, capture_method, _TPL_JIANGLI,
                timeout=8.0, settle=0.5, post_delay=1.5,
                verify_gone=True, max_clicks=3, gone_interval=1.0,
                log=log, label="战斗-奖励",
                popup_handler=popup_handler,
            )
            if not clicked:
                if log:
                    log.warning(f"{tag} 未检测到奖励界面，但战斗已胜利")

        if log:
            log.info(f"{tag} 战斗流程完成")
        return VICTORY
    else:
        # 战斗失败：点击失败画面关闭
        if log:
            log.info(f"{tag} 战斗失败")
        await click_template(
            adapter, capture_method, _TPL_SHIBAI,
            timeout=5.0, settle=0.5, post_delay=1.5,
            log=log, label="战斗-点击失败",
            popup_handler=popup_handler,
        )
        if log:
            log.info(f"{tag} 战斗失败流程完成")
        return DEFEAT


__all__ = ["run_battle", "ManualLineupInfo", "VICTORY", "DEFEAT", "TIMEOUT", "ERROR"]
