"""
系统配置 API
"""
import time
from typing import Optional, Dict

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ....core.config import settings
from ....core.logger import logger
from ....core.timeutils import now_beijing
from ....db.base import get_db
from ....db.models import SystemConfig


router = APIRouter(prefix="/api/system", tags=["system"])


class SystemSettings(BaseModel):
    adb_path: Optional[str] = None
    mumu_manager_path: Optional[str] = None
    nemu_folder: Optional[str] = None
    pkg_name: Optional[str] = None
    launch_mode: Optional[str] = None
    capture_method: Optional[str] = None
    ipc_dll_path: Optional[str] = None
    activity_name: Optional[str] = None
    python_path: Optional[str] = None
    pull_post_mode: str = "none"
    save_fail_screenshot: bool = False


class SystemSettingsUpdate(BaseModel):
    adb_path: Optional[str] = None
    mumu_manager_path: Optional[str] = None
    nemu_folder: Optional[str] = None
    pkg_name: Optional[str] = None
    launch_mode: Optional[str] = None
    capture_method: Optional[str] = None
    ipc_dll_path: Optional[str] = None
    activity_name: Optional[str] = None
    python_path: Optional[str] = None
    pull_post_mode: Optional[str] = None
    save_fail_screenshot: Optional[bool] = None


class CaptureBenchmarkRequest(BaseModel):
    emulator_id: int
    rounds: int = 5


def _serialize_settings() -> Dict[str, str]:
    return {
        "adb_path": settings.adb_path,
        "mumu_manager_path": settings.mumu_manager_path,
        "nemu_folder": settings.nemu_folder,
        "pkg_name": settings.pkg_name,
        "launch_mode": settings.launch_mode,
        "capture_method": settings.capture_method,
        "ipc_dll_path": settings.ipc_dll_path,
        "activity_name": settings.activity_name,
        "python_path": None,
        "save_fail_screenshot": False,
    }


@router.get("/settings")
async def get_settings(db: Session = Depends(get_db)) -> SystemSettings:
    """获取系统配置：优先数据库，缺省回退到运行配置。"""
    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    if row:
        return SystemSettings(
            adb_path=row.adb_path or settings.adb_path,
            mumu_manager_path=row.mumu_manager_path or settings.mumu_manager_path,
            nemu_folder=row.nemu_folder or settings.nemu_folder,
            pkg_name=row.pkg_name or settings.pkg_name,
            launch_mode=row.launch_mode or settings.launch_mode,
            capture_method=(row.capture_method or settings.capture_method or "adb"),
            ipc_dll_path=row.ipc_dll_path or settings.ipc_dll_path,
            activity_name=row.activity_name or settings.activity_name,
            python_path=row.python_path or None,
            pull_post_mode=row.pull_post_mode or "none",
            save_fail_screenshot=bool(row.save_fail_screenshot) if row.save_fail_screenshot is not None else False,
        )
    return SystemSettings(**_serialize_settings())


def _upsert_system_config(db: Session, data: Dict[str, str]) -> SystemConfig:
    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    if not row:
        row = SystemConfig()
        db.add(row)
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.put("/settings")
async def update_settings(body: SystemSettingsUpdate, db: Session = Depends(get_db)):
    """更新系统配置（写入数据库）。"""
    apply: Dict[str, str] = {}
    if body.adb_path is not None:
        apply["adb_path"] = body.adb_path
    if body.mumu_manager_path is not None:
        apply["mumu_manager_path"] = body.mumu_manager_path
    if body.nemu_folder is not None:
        apply["nemu_folder"] = body.nemu_folder
    if body.pkg_name is not None:
        apply["pkg_name"] = body.pkg_name
    if body.launch_mode is not None:
        if body.launch_mode not in {"adb_monkey", "adb_intent", "am_start"}:
            raise HTTPException(status_code=400, detail="launch_mode 必须是 adb_monkey|adb_intent|am_start 之一")
        apply["launch_mode"] = body.launch_mode
    if body.capture_method is not None:
        if body.capture_method not in {"adb", "ipc"}:
            raise HTTPException(status_code=400, detail="capture_method 必须是 adb|ipc 之一")
        apply["capture_method"] = body.capture_method
    if body.ipc_dll_path is not None:
        apply["ipc_dll_path"] = body.ipc_dll_path
    if body.activity_name is not None:
        apply["activity_name"] = body.activity_name
    if body.python_path is not None:
        apply["python_path"] = body.python_path
    if body.pull_post_mode is not None:
        if body.pull_post_mode not in {"none", "auto", "confirm"}:
            raise HTTPException(status_code=400, detail="pull_post_mode 必须是 none|auto|confirm 之一")
        apply["pull_post_mode"] = body.pull_post_mode
    if body.save_fail_screenshot is not None:
        apply["save_fail_screenshot"] = body.save_fail_screenshot

    if not apply:
        return {"message": "未提供任何需要更新的配置"}

    row = _upsert_system_config(db, apply)
    logger.info("系统配置已更新到数据库")
    return {
        "message": "配置已保存",
        "settings": {
            "adb_path": row.adb_path,
            "mumu_manager_path": row.mumu_manager_path,
            "nemu_folder": row.nemu_folder,
            "pkg_name": row.pkg_name,
            "launch_mode": row.launch_mode,
            "capture_method": row.capture_method,
            "ipc_dll_path": row.ipc_dll_path,
            "activity_name": row.activity_name,
            "python_path": row.python_path,
            "save_fail_screenshot": row.save_fail_screenshot,
        },
    }


@router.post("/capture/benchmark")
async def benchmark_capture_method(body: CaptureBenchmarkRequest, db: Session = Depends(get_db)):
    """检测选中模拟器截图延迟并自动选择最优方式（全局）。"""
    from ....db.models import Emulator
    from ...emu.adapter import AdapterConfig, EmulatorAdapter

    emulator = db.query(Emulator).filter(Emulator.id == body.emulator_id).first()
    if not emulator:
        raise HTTPException(status_code=404, detail="模拟器不存在")
    if not emulator.adb_addr:
        raise HTTPException(status_code=400, detail="模拟器未配置 ADB 地址")

    rounds = max(1, min(20, int(body.rounds or 5)))
    syscfg = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()

    cfg = AdapterConfig(
        adb_path=(syscfg.adb_path if syscfg and syscfg.adb_path else settings.adb_path),
        adb_addr=emulator.adb_addr,
        pkg_name=(syscfg.pkg_name if syscfg and syscfg.pkg_name else settings.pkg_name),
        ipc_dll_path=(syscfg.ipc_dll_path if syscfg and syscfg.ipc_dll_path else settings.ipc_dll_path),
        mumu_manager_path=(syscfg.mumu_manager_path if syscfg and syscfg.mumu_manager_path else settings.mumu_manager_path),
        nemu_folder=(syscfg.nemu_folder if syscfg and syscfg.nemu_folder else settings.nemu_folder),
        instance_id=getattr(emulator, "instance_id", None),
        activity_name=(syscfg.activity_name if syscfg and syscfg.activity_name else settings.activity_name),
    )
    adapter = EmulatorAdapter(cfg)

    candidates = ["adb"]
    if cfg.ipc_dll_path and cfg.nemu_folder and cfg.instance_id is not None:
        candidates.append("ipc")

    metrics = {}
    for method in candidates:
        latencies = []
        errors = []
        for _ in range(rounds):
            t0 = time.perf_counter()
            try:
                data = adapter.capture(method=method)
                if not data:
                    raise RuntimeError("empty image")
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                latencies.append(elapsed_ms)
            except Exception as e:
                errors.append(str(e))

        sorted_l = sorted(latencies)
        p50 = sorted_l[int(0.5 * (len(sorted_l) - 1))] if sorted_l else None
        p95 = sorted_l[int(0.95 * (len(sorted_l) - 1))] if sorted_l else None
        metrics[method] = {
            "success": len(latencies),
            "failed": len(errors),
            "success_rate": (len(latencies) / rounds) if rounds else 0.0,
            "p50_ms": round(p50, 2) if p50 is not None else None,
            "p95_ms": round(p95, 2) if p95 is not None else None,
            "errors": errors[:3],
        }

    ranked = sorted(
        candidates,
        key=lambda m: (
            -(metrics[m]["success_rate"]),
            metrics[m]["p50_ms"] if metrics[m]["p50_ms"] is not None else 10**9,
        ),
    )
    best_method = ranked[0] if ranked else "adb"

    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    if not row:
        row = SystemConfig()
        db.add(row)
    row.capture_method = best_method
    db.commit()

    return {
        "message": f"截图方式自动检测完成，已设置为 {best_method}",
        "best_method": best_method,
        "rounds": rounds,
        "metrics": metrics,
    }


# --------------- 全局默认失败延迟 ---------------

class FailDelayConfig(BaseModel):
    delays: Dict[str, int]  # {"寄养": 30, "悬赏": 60, ...}


@router.get("/fail-delays")
async def get_fail_delays(db: Session = Depends(get_db)):
    """获取全局默认失败延迟配置。"""
    from ....core.constants import TASK_TYPES_WITH_FAIL_DELAY, DEFAULT_TASK_CONFIG

    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    saved = (row.default_fail_delays or {}) if row else {}
    result = {}
    for task_name in TASK_TYPES_WITH_FAIL_DELAY:
        if task_name in saved and isinstance(saved[task_name], (int, float)):
            result[task_name] = int(saved[task_name])
        else:
            result[task_name] = DEFAULT_TASK_CONFIG.get(task_name, {}).get("fail_delay", 30)
    return {"delays": result}


@router.put("/fail-delays")
async def update_fail_delays(body: FailDelayConfig, db: Session = Depends(get_db)):
    """更新全局默认失败延迟配置。"""
    from ....core.constants import TASK_TYPES_WITH_FAIL_DELAY

    validated = {}
    for task_name, delay in body.delays.items():
        if task_name not in TASK_TYPES_WITH_FAIL_DELAY:
            continue
        if not isinstance(delay, (int, float)) or delay <= 0:
            raise HTTPException(status_code=400, detail=f"{task_name} 的 fail_delay 必须为正整数")
        validated[task_name] = int(delay)

    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    if not row:
        row = SystemConfig()
        db.add(row)
    row.default_fail_delays = validated
    db.commit()
    db.refresh(row)

    logger.info("全局默认失败延迟配置已更新")
    return {"message": "保存成功", "delays": validated}


# --------------- 全局任务开关 ---------------

class TaskSwitchesUpdate(BaseModel):
    switches: Dict[str, bool]  # {"召唤礼包": true/false}


@router.get("/task-switches")
async def get_task_switches(db: Session = Depends(get_db)):
    """获取全局任务开关。"""
    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    switches = (row.global_task_switches or {}) if row else {}
    return {"switches": switches}


@router.put("/task-switches")
async def update_task_switches(body: TaskSwitchesUpdate, db: Session = Depends(get_db)):
    """更新全局任务开关。"""
    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    if not row:
        row = SystemConfig()
        db.add(row)
    row.global_task_switches = body.switches
    db.commit()
    db.refresh(row)

    logger.info("全局任务开关已更新")
    return {"message": "保存成功", "switches": row.global_task_switches}


# --------------- 新建账号默认任务启用 ---------------

class TaskEnabledConfig(BaseModel):
    enabled: Dict[str, bool]  # {"签到": false, "御魂": false, ...}


@router.get("/task-enabled-defaults")
async def get_task_enabled_defaults(db: Session = Depends(get_db)):
    """获取新建账号时各任务的默认启用状态。"""
    from ....core.constants import TASK_TYPES_WITH_ENABLED, DEFAULT_TASK_CONFIG

    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    saved = (row.default_task_enabled or {}) if row else {}
    result = {}
    for task_name in TASK_TYPES_WITH_ENABLED:
        if task_name in saved and isinstance(saved[task_name], bool):
            result[task_name] = saved[task_name]
        else:
            result[task_name] = DEFAULT_TASK_CONFIG.get(task_name, {}).get("enabled", True)
    return {"enabled": result}


@router.put("/task-enabled-defaults")
async def update_task_enabled_defaults(body: TaskEnabledConfig, db: Session = Depends(get_db)):
    """更新新建账号时各任务的默认启用状态。"""
    from ....core.constants import TASK_TYPES_WITH_ENABLED

    validated = {}
    for task_name, enabled in body.enabled.items():
        if task_name not in TASK_TYPES_WITH_ENABLED:
            continue
        if not isinstance(enabled, bool):
            raise HTTPException(status_code=400, detail=f"{task_name} 的 enabled 必须为布尔值")
        validated[task_name] = enabled

    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    if not row:
        row = SystemConfig()
        db.add(row)
    row.default_task_enabled = validated
    db.commit()
    db.refresh(row)

    logger.info("新建账号默认任务启用配置已更新")
    return {"message": "保存成功", "enabled": validated}


# --------------- 全局休息开关 ---------------

class GlobalRestUpdate(BaseModel):
    enabled: bool


@router.get("/global-rest")
async def get_global_rest(db: Session = Depends(get_db)):
    """获取全局休息开关状态。"""
    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    enabled = bool(row.global_rest_enabled) if row and row.global_rest_enabled is not None else True
    return {"enabled": enabled}


@router.put("/global-rest")
async def update_global_rest(body: GlobalRestUpdate, db: Session = Depends(get_db)):
    """更新全局休息开关。"""
    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    if not row:
        row = SystemConfig()
        db.add(row)
    row.global_rest_enabled = body.enabled
    db.commit()
    db.refresh(row)

    logger.info(f"全局休息开关已更新: {'开启' if body.enabled else '关闭'}")
    return {"message": "保存成功", "enabled": bool(row.global_rest_enabled)}


# --------------- 新建账号默认休息配置 ---------------

class DefaultRestConfigUpdate(BaseModel):
    enabled: bool = False
    mode: str = "random"  # random|custom
    start_time: Optional[str] = None  # HH:MM
    duration: int = 2  # 小时数


@router.get("/default-rest-config")
async def get_default_rest_config(db: Session = Depends(get_db)):
    """获取新建账号的默认休息配置。"""
    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    saved = (row.default_rest_config or {}) if row else {}
    return {
        "enabled": saved.get("enabled", False),
        "mode": saved.get("mode", "random"),
        "start_time": saved.get("start_time", None),
        "duration": saved.get("duration", 2),
    }


@router.put("/default-rest-config")
async def update_default_rest_config(body: DefaultRestConfigUpdate, db: Session = Depends(get_db)):
    """更新新建账号的默认休息配置。"""
    if body.mode not in {"random", "custom"}:
        raise HTTPException(status_code=400, detail="mode 必须是 random|custom 之一")
    if body.duration < 1 or body.duration > 5:
        raise HTTPException(status_code=400, detail="duration 必须在 1-5 之间")

    config = {
        "enabled": body.enabled,
        "mode": body.mode,
        "start_time": body.start_time,
        "duration": body.duration,
    }

    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    if not row:
        row = SystemConfig()
        db.add(row)
    row.default_rest_config = config
    db.commit()
    db.refresh(row)

    logger.info("新建账号默认休息配置已更新")
    return {"message": "保存成功", "config": config}


# --------------- 对弈竞猜答案配置 ---------------

_DUIYI_WINDOWS = ["10:00", "12:00", "14:00", "16:00", "18:00", "20:00", "22:00"]


class DuiyiAnswersUpdate(BaseModel):
    answers: Dict[str, Optional[str]]  # {"10:00": "左", "12:00": "右", "14:00": null, ...}


@router.get("/duiyi-answers")
async def get_duiyi_answers(db: Session = Depends(get_db)):
    """获取对弈竞猜每个时间窗口的全局答案配置（仅当天有效）。"""
    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    saved = (row.duiyi_jingcai_answers or {}) if row else {}
    today_str = now_beijing().strftime("%Y-%m-%d")
    saved_date = saved.get("date")
    is_today = saved_date == today_str

    result = {}
    for window in _DUIYI_WINDOWS:
        if is_today:
            val = saved.get(window)
            result[window] = val if val in ("左", "右") else None
        else:
            result[window] = None
    return {"date": saved_date if is_today else None, "answers": result}


@router.put("/duiyi-answers")
async def update_duiyi_answers(body: DuiyiAnswersUpdate, db: Session = Depends(get_db)):
    """更新对弈竞猜每个时间窗口的全局答案配置（自动打上当天日期戳）。"""
    today_str = now_beijing().strftime("%Y-%m-%d")
    validated = {"date": today_str}
    for window, answer in body.answers.items():
        if window not in _DUIYI_WINDOWS:
            raise HTTPException(status_code=400, detail=f"无效的时间窗口: {window}")
        if answer is not None and answer not in ("左", "右"):
            raise HTTPException(status_code=400, detail=f"{window} 的答案必须是 '左' 或 '右' 或 null")
        validated[window] = answer

    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    if not row:
        row = SystemConfig()
        db.add(row)
    row.duiyi_jingcai_answers = validated
    db.commit()
    db.refresh(row)

    logger.info(f"对弈竞猜答案配置已更新 (date={today_str})")
    return {"message": "保存成功", "date": today_str, "answers": {k: v for k, v in validated.items() if k != "date"}}


# --------------- 对弈竞猜领奖点击区域 ---------------


class DuiyiRewardCoordUpdate(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int


@router.get("/duiyi-reward-coord")
async def get_duiyi_reward_coord(db: Session = Depends(get_db)):
    """获取对弈竞猜领取奖励的点击区域坐标。"""
    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    coord = (row.duiyi_reward_coord or {}) if row else {}
    return {
        "x1": coord.get("x1"),
        "y1": coord.get("y1"),
        "x2": coord.get("x2"),
        "y2": coord.get("y2"),
    }


@router.put("/duiyi-reward-coord")
async def update_duiyi_reward_coord(body: DuiyiRewardCoordUpdate, db: Session = Depends(get_db)):
    """更新对弈竞猜领取奖励的点击区域坐标。"""
    # 验证范围: x ∈ [0, 960), y ∈ [0, 540)
    if not (0 <= body.x1 < 960 and 0 <= body.x2 < 960):
        raise HTTPException(status_code=400, detail="x 坐标必须在 0-959 范围内")
    if not (0 <= body.y1 < 540 and 0 <= body.y2 < 540):
        raise HTTPException(status_code=400, detail="y 坐标必须在 0-539 范围内")
    if body.x1 >= body.x2:
        raise HTTPException(status_code=400, detail="x1 必须小于 x2")
    if body.y1 >= body.y2:
        raise HTTPException(status_code=400, detail="y1 必须小于 y2")

    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    if not row:
        row = SystemConfig()
        db.add(row)
    row.duiyi_reward_coord = {"x1": body.x1, "y1": body.y1, "x2": body.x2, "y2": body.y2}
    db.commit()
    db.refresh(row)

    logger.info(f"对弈竞猜领奖坐标已更新: ({body.x1},{body.y1})-({body.x2},{body.y2})")
    return {"message": "保存成功", "x1": body.x1, "y1": body.y1, "x2": body.x2, "y2": body.y2}
