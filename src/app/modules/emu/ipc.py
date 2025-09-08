"""
IPC 截图/启动 占位适配器

按照设计文档预留接口；实际实现需要加载用户提供的 DLL。
当前实现：当未配置 ipc_dll_path 或 DLL 调用未实现时，抛出明确异常。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import os
import ctypes


class IpcNotConfigured(RuntimeError):
    pass


@dataclass
class IpcConfig:
    dll_path: str


class IpcAdapter:
    def __init__(self, cfg: Optional[IpcConfig]):
        self.cfg = cfg

    def _ensure(self):
        if not self.cfg or not self.cfg.dll_path:
            raise IpcNotConfigured("未配置 IPC DLL 路径，无法使用 IPC 截图/启动。")

    def _resolve_dll(self) -> str:
        """仅使用系统配置中的 IPC DLL 路径，不做多路径探测。"""
        if not self.cfg or not self.cfg.dll_path:
            raise IpcNotConfigured("未配置 IPC DLL 路径，请在系统配置中填写 external_renderer_ipc.dll 的完整路径")
        if not os.path.isfile(self.cfg.dll_path):
            raise IpcNotConfigured(f"IPC DLL 路径不存在: {self.cfg.dll_path}")
        return self.cfg.dll_path

    def screencap(self, nemu_folder: str, instance_id: Optional[int]) -> bytes:
        # 直接使用 ctypes 调用 DLL：仅使用配置的 DLL 路径与实例ID
        if not nemu_folder:
            raise IpcNotConfigured("未配置 MuMu 安装目录，请在系统配置中填写")
        if instance_id is None:
            raise IpcNotConfigured("未配置实例ID，请在模拟器配置中设置 instance_id")
        dll_path = self._resolve_dll()

        # 延迟导入依赖
        import numpy as np  # type: ignore
        import cv2  # type: ignore

        lib = ctypes.CDLL(dll_path)
        # 函数签名声明（按 multi 实现，传入 Python 字符串）
        lib.nemu_connect.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
        lib.nemu_connect.restype = ctypes.c_int
        lib.nemu_disconnect.argtypes = [ctypes.c_int]
        lib.nemu_disconnect.restype = ctypes.c_int
        lib.nemu_capture_display.argtypes = [
            ctypes.c_int,  # connect_id
            ctypes.c_int,  # display_id
            ctypes.c_int,  # length
            ctypes.POINTER(ctypes.c_int),  # width*
            ctypes.POINTER(ctypes.c_int),  # height*
            ctypes.c_void_p,  # pixels*
        ]
        lib.nemu_capture_display.restype = ctypes.c_int

        # 使用系统配置值进行连接
        folder_wstr = os.path.abspath(nemu_folder)
        connect_id = lib.nemu_connect(folder_wstr, int(instance_id))
        if connect_id == 0:
            raise IpcNotConfigured(f"IPC 连接失败，请检查安装目录与实例ID: folder={nemu_folder}, instance={instance_id}")
        try:
            # 第一次调用，获取分辨率
            width = ctypes.c_int(0)
            height = ctypes.c_int(0)
            ret = lib.nemu_capture_display(connect_id, 0, 0, ctypes.byref(width), ctypes.byref(height), None)
            if ret != 0 or width.value <= 0 or height.value <= 0:
                raise IpcNotConfigured(f"IPC 截图获取分辨率失败 (cid={connect_id}, folder='{nemu_folder}', instance={instance_id})")

            w, h = width.value, height.value
            length = w * h * 4
            pixel_array = (ctypes.c_ubyte * length)()
            ret2 = lib.nemu_capture_display(connect_id, 0, length, ctypes.byref(width), ctypes.byref(height), ctypes.byref(pixel_array))
            if ret2 != 0:
                raise IpcNotConfigured(f"IPC 截图获取像素失败 (cid={connect_id}, folder='{nemu_folder}', instance={instance_id})")

            # 转换为 PNG bytes
            img_rgba = np.ctypeslib.as_array(pixel_array).reshape((h, w, 4))
            img_bgr = cv2.cvtColor(img_rgba, cv2.COLOR_RGBA2BGR)
            img_bgr = cv2.flip(img_bgr, 0)
            ok, buf = cv2.imencode('.png', img_bgr)
            if not ok:
                raise IpcNotConfigured(f"IPC 截图编码 PNG 失败 (cid={connect_id}, folder='{nemu_folder}', instance={instance_id})")
            return buf.tobytes()
        finally:
            try:
                lib.nemu_disconnect(connect_id)
            except Exception:
                pass

    def start_app(self, pkg: str) -> None:
        self._ensure()
        # 占位：无通用 IPC 启动接口，通常仍使用 ADB 启动
        raise IpcNotConfigured("未提供 IPC 启动实现，建议使用 ADB(monkey/intent) 模式启动后进行 IPC 截图。")
