"""
统一适配器：封装 ADB / IPC / MuMu 管理器，对外暴露统一方法

接口（参考设计文档）：
- ensure_running() -> bool
- start_app(mode: str = 'adb') -> None
- stop_app() -> None
- capture(method: str = 'adb') -> bytes
- tap(x, y)
- swipe(x1, y1, x2, y2, dur_ms=300)
- foreground()  # 预留
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .adb import Adb, AdbError
from .ipc import IpcAdapter, IpcConfig, IpcNotConfigured
from .manager import MuMuManager, MuMuManagerError


@dataclass
class AdapterConfig:
    adb_path: str
    adb_addr: str
    pkg_name: str
    ipc_dll_path: str = ""
    mumu_manager_path: str = ""
    nemu_folder: str = ""
    instance_id: Optional[int] = None
    activity_name: str = ".MainActivity"


class EmulatorAdapter:
    def __init__(self, cfg: AdapterConfig) -> None:
        self.cfg = cfg
        self.adb = Adb(cfg.adb_path)
        self.ipc = IpcAdapter(IpcConfig(cfg.ipc_dll_path) if cfg.ipc_dll_path else None)
        self.mumu = MuMuManager(cfg.mumu_manager_path) if cfg.mumu_manager_path else None

    # 运行状态保障（示例：若使用 MuMu，可确保实例已启动并连接）
    def ensure_running(self) -> bool:
        if self.mumu and self.cfg.instance_id is not None:
            try:
                self.mumu.launch(self.cfg.instance_id)
            except MuMuManagerError:
                return False
        # adb connect 尝试（可选）
        try:
            self.adb.connect(self.cfg.adb_addr)
        except AdbError:
            return False
        return True

    # 启动应用
    def start_app(self, mode: str = "adb_monkey", activity: Optional[str] = None) -> None:
        if mode == "adb_monkey":
            self.adb.start_app_monkey(self.cfg.adb_addr, self.cfg.pkg_name, fallback_activity=self.cfg.activity_name)
        elif mode == "adb_intent":
            act = activity or self.cfg.activity_name
            self.adb.start_app_intent(self.cfg.adb_addr, self.cfg.pkg_name, activity=act)
        elif mode == "am_start":
            act = activity or self.cfg.activity_name
            self.adb.start_app_am_component(self.cfg.adb_addr, self.cfg.pkg_name, activity=act)
        elif mode == "mumu":
            if not self.mumu or self.cfg.instance_id is None:
                raise MuMuManagerError("未配置 MuMu 管理器或实例ID")
            self.mumu.launch(self.cfg.instance_id)
            # 启动后再通过 adb 启动目标应用
            self.adb.start_app_monkey(self.cfg.adb_addr, self.cfg.pkg_name)
        elif mode == "ipc":
            # 交由 IPC 侧启动
            self.ipc.start_app(self.cfg.pkg_name)
        else:
            raise ValueError("未知启动方式：%s" % mode)

    def stop_app(self) -> None:
        self.adb.force_stop(self.cfg.adb_addr, self.cfg.pkg_name)

    def capture(self, method: str = "adb") -> bytes:
        if method == "adb":
            return self.adb.screencap(self.cfg.adb_addr)
        elif method == "ipc":
            return self.ipc.screencap(nemu_folder=self.cfg.nemu_folder, instance_id=self.cfg.instance_id)
        else:
            raise ValueError("未知截图方式：%s" % method)

    def tap(self, x: int, y: int) -> None:
        self.adb.tap(self.cfg.adb_addr, x, y)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, dur_ms: int = 300) -> None:
        self.adb.swipe(self.cfg.adb_addr, x1, y1, x2, y2, dur_ms)

    def foreground(self) -> bool:
        # 预留：可通过 dumpsys activity/top 解析当前前台 activity
        return True
