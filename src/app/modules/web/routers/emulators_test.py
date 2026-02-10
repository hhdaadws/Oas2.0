"""
模拟器测试 API（截图、点击）
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from starlette.responses import StreamingResponse
import subprocess
import io

from ....db.base import get_db
from ....db.models import Emulator
from ....core.config import settings
from ....core.logger import logger
from ....db.models import SystemConfig
from ...emu.adapter import EmulatorAdapter, AdapterConfig
from ...emu.adb import AdbError
from ...emu.manager import MuMuManagerError
from ...emu.ipc import IpcNotConfigured
import os
import sys


router = APIRouter(prefix="/api/emulators", tags=["emulators"])


class ClickRequest(BaseModel):
    x: int
    y: int


def _get_emulator_or_404(db: Session, emulator_id: int) -> Emulator:
    emu = db.query(Emulator).filter(Emulator.id == emulator_id).first()
    if not emu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模拟器不存在")
    if not emu.adb_addr:
        raise HTTPException(status_code=400, detail="模拟器未配置 ADB 地址")
    return emu


@router.post("/connect")
async def connect_all_emulators(db: Session = Depends(get_db)):
    """使用 adb connect 连接数据库中已配置的所有模拟器。"""
    adb_path = (db.query(SystemConfig).first() or SystemConfig(adb_path=settings.adb_path)).adb_path or settings.adb_path
    emulators = db.query(Emulator).all()
    targets = []
    for e in emulators:
        if e.adb_addr and e.adb_addr not in targets:
            targets.append(e.adb_addr)

    if not targets:
        return {"message": "没有可连接的模拟器", "connected": 0, "total": 0, "details": []}

    details = []
    connected = 0
    for addr in targets:
        cmd = [adb_path, "connect", addr]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            out = (res.stdout or b'').decode(errors='ignore').strip()
            err = (res.stderr or b'').decode(errors='ignore').strip()
            ok = res.returncode == 0 and ("connected" in out or "already" in out.lower())
            if ok:
                connected += 1
            # 更新该地址对应的模拟器状态
            emus = db.query(Emulator).filter(Emulator.adb_addr == addr).all()
            for em in emus:
                em.state = "connected" if ok else "disconnected"
            db.commit()
            details.append({
                "addr": addr,
                "ok": ok,
                "stdout": out,
                "stderr": err,
                "returncode": res.returncode,
            })
        except subprocess.TimeoutExpired:
            details.append({"addr": addr, "ok": False, "error": "timeout"})
        except FileNotFoundError:
            raise HTTPException(status_code=400, detail=f"找不到 ADB 可执行文件，请在系统配置中设置正确的 adb 路径。当前: {cmd[0]}")
        except Exception as e:
            details.append({"addr": addr, "ok": False, "error": str(e)})

    return {"message": "连接完成", "connected": connected, "total": len(targets), "details": details}


@router.post("/refresh")
async def refresh_emulator_status(db: Session = Depends(get_db)):
    """通过 `adb devices` 刷新数据库中模拟器的连接状态。"""
    adb_path = (db.query(SystemConfig).first() or SystemConfig(adb_path=settings.adb_path)).adb_path or settings.adb_path
    try:
        res = subprocess.run([adb_path, "devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="ADB 查询设备超时")
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail=f"找不到 ADB 可执行文件，请在系统配置中设置正确的 adb 路径。当前: {adb_path}")

    out = (res.stdout or b"").decode(errors="ignore")
    connected_set = set()
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        # 格式: <serial> <state>
        parts = line.split()
        if len(parts) >= 2:
            serial, state = parts[0], parts[1]
            if state == "device":
                connected_set.add(serial)

    # 更新数据库状态
    emus = db.query(Emulator).all()
    total = len(emus)
    connected = 0
    for em in emus:
        if em.adb_addr in connected_set:
            em.state = "connected"
            connected += 1
        else:
            em.state = "disconnected"
    db.commit()

    return {
        "message": "状态已刷新",
        "connected": connected,
        "total": total,
        "connected_addrs": sorted(list(connected_set)),
    }


@router.get("/{emulator_id}/screenshot")
async def emulator_screenshot(emulator_id: int, method: str = "adb", db: Session = Depends(get_db)):
    """获取截图（PNG）。支持 method=adb|ipc（ipc 需配置 DLL）。
    按你的要求，不捕获异常，直接将错误抛出，配合 FastAPI debug=True 便于直接看到堆栈。
    同时：如果在 DB 配置了 python_path，则自动追加到 sys.path，方便导入本地 module.base。
    """
    emu = _get_emulator_or_404(db, emulator_id)
    syscfg = db.query(SystemConfig).first()
    # 动态扩展 Python 搜索路径（可在系统配置中填写 D:\multi 等）
    if syscfg and getattr(syscfg, "python_path", None):
        extra_paths = [p.strip() for p in syscfg.python_path.replace(";", ",").split(",") if p.strip()]
        for p in extra_paths:
            if p not in sys.path:
                sys.path.append(p)

    cfg = AdapterConfig(
        adb_path=(syscfg.adb_path if syscfg and syscfg.adb_path else settings.adb_path),
        adb_addr=emu.adb_addr,
        pkg_name=(syscfg.pkg_name if syscfg and syscfg.pkg_name else settings.pkg_name),
        ipc_dll_path=(syscfg.ipc_dll_path if syscfg and syscfg.ipc_dll_path else ""),
        mumu_manager_path=(syscfg.mumu_manager_path if syscfg and syscfg.mumu_manager_path else ""),
        nemu_folder=(syscfg.nemu_folder if syscfg and syscfg.nemu_folder else ""),
        instance_id=getattr(emu, "instance_id", None),
        activity_name=(syscfg.activity_name if syscfg and syscfg.activity_name else settings.activity_name),
    )
    adapter = EmulatorAdapter(cfg)
    out = adapter.capture(method=method)
    return StreamingResponse(io.BytesIO(out), media_type="image/png")


@router.post("/{emulator_id}/click")
async def emulator_click(emulator_id: int, body: ClickRequest, db: Session = Depends(get_db)):
    """通过 ADB 向设备注入点击。"""
    if body.x < 0 or body.y < 0:
        raise HTTPException(status_code=400, detail="坐标必须为非负整数")
    emu = _get_emulator_or_404(db, emulator_id)
    sys = db.query(SystemConfig).first()
    cfg = AdapterConfig(
        adb_path=(sys.adb_path if sys and sys.adb_path else settings.adb_path),
        adb_addr=emu.adb_addr,
        pkg_name=(sys.pkg_name if sys and sys.pkg_name else settings.pkg_name),
        ipc_dll_path=(sys.ipc_dll_path if sys and sys.ipc_dll_path else ""),
        mumu_manager_path=(sys.mumu_manager_path if sys and sys.mumu_manager_path else ""),
        nemu_folder=(sys.nemu_folder if sys and sys.nemu_folder else ""),
        instance_id=getattr(emu, "instance_id", None),
        activity_name=(sys.activity_name if sys and sys.activity_name else settings.activity_name),
    )
    adapter = EmulatorAdapter(cfg)
    try:
        adapter.tap(body.x, body.y)
    except AdbError as e:
        logger.error(f"ADB 点击失败: {e}")
        raise HTTPException(status_code=502, detail="ADB 点击失败")
    return {"message": "点击已发送", "x": body.x, "y": body.y}


class LaunchRequest(BaseModel):
    mode: str | None = None  # adb_monkey|adb_intent|mumu|ipc
    activity: str | None = None


@router.post("/{emulator_id}/launch")
async def emulator_launch(emulator_id: int, body: LaunchRequest, db: Session = Depends(get_db)):
    emu = _get_emulator_or_404(db, emulator_id)
    sys = db.query(SystemConfig).first()
    cfg = AdapterConfig(
        adb_path=(sys.adb_path if sys and sys.adb_path else settings.adb_path),
        adb_addr=emu.adb_addr,
        pkg_name=(sys.pkg_name if sys and sys.pkg_name else settings.pkg_name),
        ipc_dll_path=(sys.ipc_dll_path if sys and sys.ipc_dll_path else ""),
        mumu_manager_path=(sys.mumu_manager_path if sys and sys.mumu_manager_path else ""),
        nemu_folder=(sys.nemu_folder if sys and sys.nemu_folder else ""),
        instance_id=getattr(emu, "instance_id", None),
        activity_name=(sys.activity_name if sys and sys.activity_name else settings.activity_name),
    )
    adapter = EmulatorAdapter(cfg)
    if True:
        mode = body.mode or (sys.launch_mode if sys and sys.launch_mode else settings.launch_mode)
        attempts = []
        # 构造尝试序列
        def attempt(cmd: list[str], label: str):
            cp = adapter.adb._run(cmd, timeout=12.0)  # 使用底层以捕获输出
            out = (cp.stdout or b"").decode(errors='ignore')
            err = (cp.stderr or b"").decode(errors='ignore')
            running = adapter.adb.wait_for_app_running(cfg.adb_addr, cfg.pkg_name, timeout_total=6.0)
            attempts.append({
                "label": label,
                "cmd": " ".join(cmd),
                "returncode": cp.returncode,
                "stdout": out[-800:],
                "stderr": err[-800:],
                "running": running,
            })
            return running

        # 构造统一尝试流程，包含 resolve-activity
        pkgs = [cfg.pkg_name] + [p for p in adapter.adb.list_packages(cfg.adb_addr, pattern="onmyoji") if p != cfg.pkg_name]
        for pkg in pkgs:
            # 1) 偏好方式（monkey / am_start / adb_intent 显式组件）
            if mode == "adb_monkey":
                if attempt([cfg.adb_path, "-s", cfg.adb_addr, "shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"], f"monkey ({pkg})"):
                    cfg.pkg_name = pkg
                    break
            elif mode == "am_start":
                if attempt([cfg.adb_path, "-s", cfg.adb_addr, "shell", "am", "start", "-n", f"{pkg}/{body.activity or cfg.activity_name}"], f"am start component ({pkg})"):
                    cfg.pkg_name = pkg
                    break
            else:  # adb_intent
                if attempt([cfg.adb_path, "-s", cfg.adb_addr, "shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-n", f"{pkg}/{body.activity or cfg.activity_name}"], f"am start component ({pkg})"):
                    cfg.pkg_name = pkg
                    break

            # 2) resolve-activity 解析组件
            comp = adapter.adb.resolve_launcher_component(cfg.adb_addr, pkg)
            if comp:
                if attempt([cfg.adb_path, "-s", cfg.adb_addr, "shell", "am", "start", "-n", comp], f"am start resolved ({comp})"):
                    cfg.pkg_name = pkg
                    break

            # 3) MAIN/LAUNCHER + 包名（不带组件）
            if attempt([cfg.adb_path, "-s", cfg.adb_addr, "shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", pkg], f"am start package ({pkg})"):
                cfg.pkg_name = pkg
                break
            # 4) 反向方式（如果第1步是 monkey 则试 intent；反之亦然）
            if mode == "adb_monkey":
                if attempt([cfg.adb_path, "-s", cfg.adb_addr, "shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-n", f"{pkg}/{body.activity or cfg.activity_name}"], f"am start component ({pkg})"):
                    cfg.pkg_name = pkg
                    break
            elif mode == "am_start":
                if attempt([cfg.adb_path, "-s", cfg.adb_addr, "shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-n", f"{pkg}/{body.activity or cfg.activity_name}"], f"am start (LAUNCHER) ({pkg})"):
                    cfg.pkg_name = pkg
                    break
            else:  # adb_intent
                if attempt([cfg.adb_path, "-s", cfg.adb_addr, "shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"], f"monkey ({pkg})"):
                    cfg.pkg_name = pkg
                    break

        # 判断是否成功
        if attempts and attempts[-1]["running"]:
            emu.state = "connected"
            db.commit()
            return {"message": "启动成功", "mode": mode, "pkg": cfg.pkg_name, "attempts": attempts}
        # 未成功，暴露详细尝试与输出尾部，便于排查
        lines = []
        for a in attempts:
            stderr_tail = (a.get('stderr') or '')[-300:]
            stdout_tail = (a.get('stdout') or '')[-200:]
            lines.append(f"[{a['label']}] rc={a['returncode']} running={a['running']} cmd={a['cmd']} stderr_tail={stderr_tail!r} stdout_tail={stdout_tail!r}")
        detail_msg = "应用未检测到启动（进程未出现）\n" + "\n".join(lines)
        raise HTTPException(status_code=502, detail=detail_msg)


@router.get("/{emulator_id}/ipc/diag")
async def ipc_diagnose(emulator_id: int, db: Session = Depends(get_db)):
    """IPC 截图诊断：检查配置/依赖/文件/连接情况，便于快速排查。"""
    emu = _get_emulator_or_404(db, emulator_id)
    syscfg = db.query(SystemConfig).first()
    nemu_folder = (syscfg.nemu_folder if syscfg and syscfg.nemu_folder else "")
    ipc_dll_path = (syscfg.ipc_dll_path if syscfg and syscfg.ipc_dll_path else "")
    instance_id = getattr(emu, "instance_id", 0) or 0

    diag = {
        "nemu_folder": nemu_folder,
        "ipc_dll_path": ipc_dll_path,
        "instance_id": instance_id,
        "nemu_folder_exists": bool(nemu_folder and os.path.isdir(nemu_folder)),
        "dll_candidates": [],
        "dll_exists": False,
        "import_module_base": False,
        "import_error": None,
        "client_connected": False,
        "sys_path_sample": sys.path[:5],
    }

    # 构造候选 DLL 路径
    candidates = []
    if nemu_folder:
        candidates.extend([
            os.path.abspath(os.path.join(nemu_folder, 'shell', 'sdk', 'external_renderer_ipc.dll')),
            os.path.abspath(os.path.join(nemu_folder, 'nx_device', '12.0', 'shell', 'sdk', 'external_renderer_ipc.dll')),
            os.path.abspath(os.path.join(nemu_folder, 'nx_main', 'sdk', 'external_renderer_ipc.dll')),
        ])
    if ipc_dll_path:
        candidates.append(os.path.abspath(ipc_dll_path))
    diag["dll_candidates"] = candidates
    diag["dll_exists"] = any(os.path.isfile(p) for p in candidates)

    # 尝试导入 IPC 连接池并建立连接
    try:
        from module.base.ipc_connection_pool import get_ipc_client  # type: ignore
        diag["import_module_base"] = True
        if nemu_folder and instance_id is not None:
            client = get_ipc_client(nemu_folder, int(instance_id), None)
            diag["client_connected"] = bool(client)
    except Exception as e:
        diag["import_error"] = str(e)

    return diag


class OcrRequest(BaseModel):
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    method: str = "adb"


@router.post("/{emulator_id}/ocr")
async def emulator_ocr(emulator_id: int, body: OcrRequest, db: Session = Depends(get_db)):
    """对模拟器当前画面（可选区域）执行 OCR 识别。"""
    emu = _get_emulator_or_404(db, emulator_id)
    syscfg = db.query(SystemConfig).first()

    cfg = AdapterConfig(
        adb_path=(syscfg.adb_path if syscfg and syscfg.adb_path else settings.adb_path),
        adb_addr=emu.adb_addr,
        pkg_name=(syscfg.pkg_name if syscfg and syscfg.pkg_name else settings.pkg_name),
        ipc_dll_path=(syscfg.ipc_dll_path if syscfg and syscfg.ipc_dll_path else ""),
        mumu_manager_path=(syscfg.mumu_manager_path if syscfg and syscfg.mumu_manager_path else ""),
        nemu_folder=(syscfg.nemu_folder if syscfg and syscfg.nemu_folder else ""),
        instance_id=getattr(emu, "instance_id", None),
        activity_name=(syscfg.activity_name if syscfg and syscfg.activity_name else settings.activity_name),
    )
    adapter = EmulatorAdapter(cfg)
    screenshot = adapter.capture(method=body.method)

    roi = (body.x, body.y, body.w, body.h) if body.w > 0 and body.h > 0 else None

    from ...ocr import ocr
    result = ocr(screenshot, roi=roi)

    return {
        "full_text": result.text,
        "boxes": [
            {
                "text": b.text,
                "confidence": round(b.confidence, 4),
                "center": list(b.center),
                "box": b.box,
            }
            for b in result.boxes
        ],
    }
