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
    pull_default_zone: str = "樱之华"
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
    pull_default_zone: Optional[str] = None
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
            pull_default_zone=row.pull_default_zone or "樱之华",
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
    if body.pull_default_zone is not None:
        apply["pull_default_zone"] = body.pull_default_zone
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
