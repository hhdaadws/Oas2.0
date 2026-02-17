"""
IPC 截图/启动 适配器

通过 ctypes 调用 MuMu 模拟器的 external_renderer_ipc.dll，
实现高性能截图（比 ADB 快 5-10 倍）。

优化特性：
- DLL 句柄缓存：只加载一次，后续复用
- 连接持久化：保持 nemu_connect 连接，断线自动重连
- 分辨率缓存：首次查询后缓存，避免重复 DLL 调用
- screencap_ndarray：直接返回 BGR ndarray，跳过 PNG encode/decode 往返
"""
from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2  # type: ignore
import numpy as np

from loguru import logger as _logger


class IpcNotConfigured(RuntimeError):
    pass


@dataclass
class IpcConfig:
    dll_path: str


class IpcAdapter:
    def __init__(self, cfg: Optional[IpcConfig]):
        self.cfg = cfg
        self._lib = None                          # 缓存 DLL 句柄
        self._connect_id: Optional[int] = None    # 持久连接 ID
        self._resolution: Optional[Tuple[int, int]] = None  # 缓存 (w, h)
        self._nemu_folder: Optional[str] = None   # 当前连接参数
        self._instance_id: Optional[int] = None

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

    def _ensure_lib(self) -> ctypes.CDLL:
        """确保 DLL 已加载并设置函数签名（仅首次加载）。"""
        if self._lib is not None:
            return self._lib

        dll_path = self._resolve_dll()
        lib = ctypes.CDLL(dll_path)

        # 设置函数签名
        lib.nemu_connect.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
        lib.nemu_connect.restype = ctypes.c_int
        lib.nemu_disconnect.argtypes = [ctypes.c_int]
        lib.nemu_disconnect.restype = ctypes.c_int
        lib.nemu_capture_display.argtypes = [
            ctypes.c_int,                   # connect_id
            ctypes.c_int,                   # display_id
            ctypes.c_int,                   # length
            ctypes.POINTER(ctypes.c_int),   # width*
            ctypes.POINTER(ctypes.c_int),   # height*
            ctypes.c_void_p,                # pixels*
        ]
        lib.nemu_capture_display.restype = ctypes.c_int

        self._lib = lib
        _logger.debug("IPC DLL 已加载: {}", dll_path)
        return lib

    def _ensure_connected(self, nemu_folder: str, instance_id: Optional[int]) -> int:
        """确保已连接到模拟器（连接持久化 + 参数变化时重连）。"""
        if not nemu_folder:
            raise IpcNotConfigured("未配置 MuMu 安装目录，请在系统配置中填写")
        if instance_id is None:
            raise IpcNotConfigured("未配置实例ID，请在模拟器配置中设置 instance_id")

        # 参数变化时，断开旧连接
        if (self._connect_id is not None
                and (self._nemu_folder != nemu_folder
                     or self._instance_id != instance_id)):
            self._do_disconnect()

        # 已有有效连接，直接复用
        if self._connect_id is not None:
            return self._connect_id

        lib = self._ensure_lib()
        folder_wstr = os.path.abspath(nemu_folder)
        connect_id = lib.nemu_connect(folder_wstr, int(instance_id))
        if connect_id == 0:
            raise IpcNotConfigured(
                f"IPC 连接失败，请检查安装目录与实例ID: "
                f"folder={nemu_folder}, instance={instance_id}"
            )

        self._connect_id = connect_id
        self._nemu_folder = nemu_folder
        self._instance_id = instance_id
        self._resolution = None  # 新连接时重新查询分辨率
        _logger.debug("IPC 连接已建立: cid={}, folder={}, instance={}",
                       connect_id, nemu_folder, instance_id)
        return connect_id

    def _ensure_resolution(self, connect_id: int) -> Tuple[int, int]:
        """确保已查询分辨率（仅首次查询）。"""
        if self._resolution is not None:
            return self._resolution

        lib = self._ensure_lib()
        width = ctypes.c_int(0)
        height = ctypes.c_int(0)
        ret = lib.nemu_capture_display(
            connect_id, 0, 0,
            ctypes.byref(width), ctypes.byref(height), None,
        )
        if ret != 0 or width.value <= 0 or height.value <= 0:
            # 分辨率查询失败，标记连接无效
            self._invalidate_connection()
            raise IpcNotConfigured(
                f"IPC 截图获取分辨率失败 (cid={connect_id}, "
                f"folder='{self._nemu_folder}', instance={self._instance_id})"
            )

        self._resolution = (width.value, height.value)
        _logger.debug("IPC 分辨率: {}x{}", width.value, height.value)
        return self._resolution

    def _invalidate_connection(self) -> None:
        """标记连接为无效（下次调用时自动重连）。"""
        if self._connect_id is not None:
            self._do_disconnect()

    def _do_disconnect(self) -> None:
        """执行实际断开操作。"""
        if self._connect_id is not None and self._lib is not None:
            try:
                self._lib.nemu_disconnect(self._connect_id)
            except Exception:
                pass
        self._connect_id = None
        self._resolution = None

    def disconnect(self) -> None:
        """显式断开连接（供 Worker cleanup 调用）。"""
        self._do_disconnect()

    def screencap_ndarray(self, nemu_folder: str, instance_id: Optional[int]) -> np.ndarray:
        """IPC 截图，直接返回 BGR ndarray（跳过 PNG encode/decode）。

        性能优化：
        - DLL 句柄复用
        - 连接持久化
        - 分辨率缓存
        - 无 PNG 编解码开销
        """
        try:
            connect_id = self._ensure_connected(nemu_folder, instance_id)
            w, h = self._ensure_resolution(connect_id)
        except IpcNotConfigured:
            raise
        except Exception as exc:
            # 未知异常时重置连接状态
            self._invalidate_connection()
            raise IpcNotConfigured(f"IPC 连接异常: {exc}") from exc

        lib = self._lib
        length = w * h * 4
        pixel_array = (ctypes.c_ubyte * length)()

        width_out = ctypes.c_int(w)
        height_out = ctypes.c_int(h)
        ret = lib.nemu_capture_display(
            connect_id, 0, length,
            ctypes.byref(width_out), ctypes.byref(height_out),
            ctypes.byref(pixel_array),
        )
        if ret != 0:
            # 截图失败，可能是连接断开，标记无效让下次重连
            self._invalidate_connection()
            raise IpcNotConfigured(
                f"IPC 截图获取像素失败 (cid={connect_id}, "
                f"folder='{self._nemu_folder}', instance={self._instance_id})"
            )

        # RGBA -> BGR + 垂直翻转
        img_rgba = np.ctypeslib.as_array(pixel_array).reshape((h, w, 4))
        img_bgr = cv2.cvtColor(img_rgba, cv2.COLOR_RGBA2BGR)
        img_bgr = cv2.flip(img_bgr, 0)
        return img_bgr

    def screencap(self, nemu_folder: str, instance_id: Optional[int]) -> bytes:
        """IPC 截图，返回 PNG bytes（兼容 Web API 等需要 bytes 的场景）。"""
        img_bgr = self.screencap_ndarray(nemu_folder, instance_id)
        ok, buf = cv2.imencode('.png', img_bgr)
        if not ok:
            raise IpcNotConfigured("IPC 截图编码 PNG 失败")
        return buf.tobytes()

    def start_app(self, pkg: str) -> None:
        self._ensure()
        # 占位：无通用 IPC 启动接口，通常仍使用 ADB 启动
        raise IpcNotConfigured("未提供 IPC 启动实现，建议使用 ADB(monkey/intent) 模式启动后进行 IPC 截图。")
