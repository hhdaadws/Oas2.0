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

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger as _logger

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
    # 活动心跳注册表：adb_addr -> monotonic timestamp
    # Worker 的 watchdog 通过此注册表检测任务是否卡死
    _heartbeat: dict[str, float] = {}

    @staticmethod
    def touch_heartbeat(adb_addr: str) -> None:
        EmulatorAdapter._heartbeat[adb_addr] = time.monotonic()

    @staticmethod
    def get_heartbeat(adb_addr: str) -> float:
        return EmulatorAdapter._heartbeat.get(adb_addr, 0.0)

    def __init__(self, cfg: AdapterConfig) -> None:
        self.cfg = cfg
        self.adb = Adb(cfg.adb_path)
        self.ipc = IpcAdapter(IpcConfig(cfg.ipc_dll_path) if cfg.ipc_dll_path else None)
        EmulatorAdapter._heartbeat[cfg.adb_addr] = time.monotonic()

        manager_path = (cfg.mumu_manager_path or "").strip()
        if manager_path and Path(manager_path).exists():
            self.mumu = MuMuManager(manager_path)
        else:
            self.mumu = None
            if manager_path:
                _logger.warning(
                    "MuMuManager 路径不可用，降级为 ADB 连接模式: {}",
                    manager_path,
                )

    # 运行状态保障（示例：若使用 MuMu，可确保实例已启动并连接）
    def ensure_running(self) -> bool:
        launch_ok = False

        if self.mumu and self.cfg.instance_id is not None:
            try:
                self.mumu.launch(self.cfg.instance_id)
                launch_ok = True
            except MuMuManagerError as exc:
                _logger.warning("MuMu 启动失败，继续尝试 ADB 连接: {}", exc)

        retry_count = 3 if launch_ok else 2
        for _ in range(retry_count):
            try:
                if self.adb.connect(self.cfg.adb_addr):
                    return True
                if self.cfg.adb_addr in self.adb.devices():
                    return True
            except AdbError:
                pass

        return False

    # 启动应用
    def start_app(
        self, mode: str = "adb_monkey", activity: Optional[str] = None
    ) -> None:
        if mode == "adb_monkey":
            self.adb.start_app_monkey(
                self.cfg.adb_addr,
                self.cfg.pkg_name,
                fallback_activity=self.cfg.activity_name,
            )
        elif mode == "adb_intent":
            act = activity or self.cfg.activity_name
            self.adb.start_app_intent(
                self.cfg.adb_addr, self.cfg.pkg_name, activity=act
            )
        elif mode == "am_start":
            act = activity or self.cfg.activity_name
            self.adb.start_app_am_component(
                self.cfg.adb_addr, self.cfg.pkg_name, activity=act
            )
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
        EmulatorAdapter._heartbeat[self.cfg.adb_addr] = time.monotonic()
        if method == "adb":
            return self.adb.screencap(self.cfg.adb_addr)
        elif method == "ipc":
            return self.ipc.screencap(
                nemu_folder=self.cfg.nemu_folder, instance_id=self.cfg.instance_id
            )
        else:
            raise ValueError("未知截图方式：%s" % method)

    def tap(self, x: int, y: int) -> None:
        EmulatorAdapter._heartbeat[self.cfg.adb_addr] = time.monotonic()
        self.adb.tap(self.cfg.adb_addr, x, y)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, dur_ms: int = 300) -> None:
        self.adb.swipe(self.cfg.adb_addr, x1, y1, x2, y2, dur_ms)

    def foreground(self) -> bool:
        # 预留：可通过 dumpsys activity/top 解析当前前台 activity
        return True

    def push_login_data(self, login_id: str, data_dir: str = "putonglogindata") -> bool:
        """Push 账号登录数据到模拟器（shared_prefs + clientconfig）"""
        PKG = "com.netease.onmyoji.wyzymnqsd_cps"
        local_base = Path(data_dir) / login_id
        addr = self.cfg.adb_addr

        if not local_base.exists():
            _logger.error("push_login_data: 本地数据目录不存在: {}", local_base)
            return False

        if not self.ensure_running():
            _logger.error("push_login_data: 设备不可用，ADB 未连接: {}", addr)
            return False

        # 1. adb root
        self.adb.root(addr)

        # 2. 清理旧 shared_prefs
        remote_prefs = f"/data/user/0/{PKG}/shared_prefs"
        self.adb.shell(addr, f"rm -rf {remote_prefs}")

        # 2.5 清理旧 clientconfig
        remote_cc_del = f"/sdcard/Android/data/{PKG}/files/netease/onmyoji/Documents/clientconfig"
        self.adb.shell(addr, f"rm -rf {remote_cc_del}")

        # 3. 确保目标目录权限
        self.adb.shell(addr, f"chmod 777 /data/user/0/{PKG}/")

        # 4. push shared_prefs
        local_prefs = local_base / "shared_prefs"
        if local_prefs.exists():
            ok, msg = self.adb.push(addr, str(local_prefs), remote_prefs)
            if not ok:
                _logger.error("push shared_prefs 失败: {}", msg)
                return False
            _logger.info("push shared_prefs 成功")
        else:
            _logger.warning("shared_prefs 目录不存在: {}", local_prefs)

        # 5. push clientconfig
        local_cc = local_base / "clientconfig"
        remote_cc = (
            f"/sdcard/Android/data/{PKG}/files/netease/onmyoji/Documents/clientconfig"
        )
        if local_cc.exists():
            ok, msg = self.adb.push(addr, str(local_cc), remote_cc)
            if not ok:
                _logger.error("push clientconfig 失败: {}", msg)
                return False
            _logger.info("push clientconfig 成功")
        else:
            _logger.warning("clientconfig 文件不存在: {}", local_cc)

        return True
