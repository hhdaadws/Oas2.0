"""
签到状态处理：
- 到庭院后检测签到弹窗并执行点击操作
- 两种签到流程：qiandao.png → qiandao_sure → exit 或 qiandao_1.png → jiangli → 关闭
- 每日跨天重置签到状态
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm.attributes import flag_modified

from ...core.timeutils import now_beijing
from ...db.models import GameAccount

if TYPE_CHECKING:
    from ..emu.adapter import EmulatorAdapter

# 模板路径
_QIANDAO = "assets/ui/templates/qiandao.png"
_QIANDAO_X_TEMPLATES: list[str] = sorted(
    p.as_posix() for p in Path("assets/ui/templates").glob("qiandao_[0-9]*.png")
) or ["assets/ui/templates/qiandao_1.png"]
_QIANDAO_SURE_TEMPLATES: list[str] = sorted(
    p.as_posix() for p in Path("assets/ui/templates").glob("qiandao_sure_*.png")
) or ["assets/ui/templates/qiandao_sure_1.png"]
_EXIT = "assets/ui/templates/exit.png"
_JIANGLI = "assets/ui/templates/jiangli.png"

# 关闭奖励弹窗的固定坐标中心和随机半径
_CLOSE_CX, _CLOSE_CY, _CLOSE_RADIUS = 20, 20, 20


def _get_today_str() -> str:
    return now_beijing().date().isoformat()


def refresh_signin_status_if_new_day(account: GameAccount) -> bool:
    """跨天重置：若不是今天，签到状态自动重置为未签到。"""
    cfg = account.task_config or {}
    signin = cfg.get("签到") if isinstance(cfg, dict) else None
    if not isinstance(signin, dict):
        return False

    signed_date = signin.get("signed_date")
    today = _get_today_str()
    if signed_date == today:
        return False

    changed = False
    if signin.get("status") != "未签到":
        signin["status"] = "未签到"
        changed = True
    if signin.get("signed_date") is not None:
        signin["signed_date"] = None
        changed = True

    if changed:
        cfg["签到"] = signin
        account.task_config = cfg
    return changed


def should_signin(account: GameAccount) -> bool:
    """检查是否需要签到：已启用且今天尚未签到。"""
    cfg = account.task_config or {}
    if not isinstance(cfg, dict):
        return False

    signin = cfg.get("签到")
    if not isinstance(signin, dict):
        return False

    if signin.get("enabled") is not True:
        return False

    today = _get_today_str()
    if signin.get("status") == "已签到" and signin.get("signed_date") == today:
        return False

    return True


def mark_signin_done(account: GameAccount, *, log: Any = None) -> bool:
    """标记今天签到完成，写回 task_config。"""
    cfg = account.task_config or {}
    if not isinstance(cfg, dict):
        return False

    signin = cfg.get("签到")
    if not isinstance(signin, dict):
        return False

    today = _get_today_str()
    signin["status"] = "已签到"
    signin["signed_date"] = today
    cfg["签到"] = signin
    account.task_config = cfg

    if log:
        try:
            log.info(f"[签到] 签到完成: account={account.login_id}, date={today}")
        except Exception:
            pass
    return True


async def perform_signin(
    adapter: EmulatorAdapter,
    capture_method: str = "adb",
    *,
    log: Any = None,
    poll_timeout: float = 10.0,
    poll_interval: float = 1.5,
) -> bool:
    """在庭院中执行实际的签到 UI 操作。

    轮询检测签到弹窗（最多 poll_timeout 秒），找到后执行对应点击流程。
    返回 True 表示签到成功，False 表示超时未检测到签到弹窗（已签过或无弹窗）。
    """
    from ..vision.template import match_template
    from ..vision.utils import random_point_in_circle

    addr = adapter.cfg.adb_addr
    elapsed = 0.0

    while elapsed < poll_timeout:
        screenshot = adapter.capture(capture_method)
        if screenshot is None:
            if log:
                log.warning("[签到] 截图失败，稍后重试")
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            continue

        # Flow A: 检测 qiandao.png
        m = match_template(screenshot, _QIANDAO)
        if m:
            if log:
                log.info("[签到] 检测到签到弹窗 (qiandao.png)")
            adapter.adb.tap(addr, *m.center)
            await asyncio.sleep(2.0)

            # 等待 qiandao_sure_x.png
            for _ in range(3):
                ss = adapter.capture(capture_method)
                if ss is not None:
                    for tpl in _QIANDAO_SURE_TEMPLATES:
                        ms = match_template(ss, tpl)
                        if ms:
                            adapter.adb.tap(addr, *ms.center)
                            if log:
                                tpl_name = Path(tpl).name
                                log.info(f"[签到] 点击确认签到 ({tpl_name})")
                            break
                    else:
                        await asyncio.sleep(1.0)
                        continue
                    break
                await asyncio.sleep(1.0)

            await asyncio.sleep(2.0)

            # 等待 exit.png
            for _ in range(3):
                ss = adapter.capture(capture_method)
                if ss is not None:
                    me = match_template(ss, _EXIT)
                    if me:
                        adapter.adb.tap(addr, *me.center)
                        if log:
                            log.info("[签到] 点击退出 (exit.png)，回到庭院")
                        break
                await asyncio.sleep(1.0)

            return True

        # Flow B: 检测 qiandao_x.png
        m1 = None
        matched_tpl = None
        for tpl in _QIANDAO_X_TEMPLATES:
            m1 = match_template(screenshot, tpl)
            if m1:
                matched_tpl = Path(tpl).name
                break
        if m1:
            if log:
                log.info(f"[签到] 检测到签到弹窗 ({matched_tpl})")
            adapter.adb.tap(addr, *m1.center)
            await asyncio.sleep(2.0)

            # 检测 jiangli.png 然后随机点击关闭
            ss = adapter.capture(capture_method)
            if ss is not None:
                mj = match_template(ss, _JIANGLI)
                if mj and log:
                    log.info("[签到] 检测到奖励弹窗 (jiangli.png)")

            rx, ry = random_point_in_circle(_CLOSE_CX, _CLOSE_CY, _CLOSE_RADIUS)
            adapter.adb.tap(addr, rx, ry)
            if log:
                log.info(f"[签到] 随机点击 ({rx}, {ry}) 关闭奖励弹窗")
            return True

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    if log:
        log.info("[签到] 超时未检测到签到弹窗，跳过")
    return False


def try_signin_if_needed(account: GameAccount, *, log: Any = None) -> bool:
    """向后兼容：同步标记签到完成（不含 UI 操作）。

    若需要实际 UI 签到，请改用 should_signin() + perform_signin() + mark_signin_done() 组合。
    """
    if not should_signin(account):
        return False
    return mark_signin_done(account, log=log)


def mark_task_config_modified(account: GameAccount) -> None:
    """标记 task_config 为脏字段，确保 SQLAlchemy 提交 JSON 修改。"""
    flag_modified(account, "task_config")


__all__ = [
    "refresh_signin_status_if_new_day",
    "should_signin",
    "perform_signin",
    "mark_signin_done",
    "try_signin_if_needed",
    "mark_task_config_modified",
]
