"""
截图模块
"""
from .base import BaseCapture
from .adb_capture import ADBCapture  
from .ipc_capture import IPCCapture

__all__ = ["BaseCapture", "ADBCapture", "IPCCapture"]