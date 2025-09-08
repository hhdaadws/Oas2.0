"""
IPC截图实现
"""
import asyncio
from typing import Optional
from .base import BaseCapture, CaptureError
from ....core.logger import logger


class IPCCapture(BaseCapture):
    """IPC截图实现"""
    
    def __init__(self, device_id: str, instance_id: int):
        super().__init__(device_id)
        self.instance_id = instance_id
        self.logger = logger.bind(device=device_id, module="IPCCapture")
    
    async def _capture_raw(self) -> bytes:
        """
        使用IPC截图
        
        Returns:
            PNG图像数据
            
        Raises:
            CaptureError: 截图失败
        """
        try:
            # IPC截图实现（需要根据具体IPC协议实现）
            # 这里提供一个示例框架
            
            # 方案1: 通过IPC命名管道通信
            import win32file
            import win32pipe
            
            pipe_name = f"\\\\.\\pipe\\MuMu_Screenshot_{self.instance_id}"
            
            try:
                # 连接到IPC管道
                handle = win32file.CreateFile(
                    pipe_name,
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0,
                    None,
                    win32file.OPEN_EXISTING,
                    0,
                    None
                )
                
                # 发送截图请求
                request = b"SCREENSHOT"
                win32file.WriteFile(handle, request)
                
                # 读取图像数据
                result = win32file.ReadFile(handle, 1024*1024*5)  # 最大5MB
                image_data = result[1]
                
                win32file.CloseHandle(handle)
                
                if not image_data:
                    raise CaptureError("IPC截图返回空数据")
                
                self.logger.debug(f"IPC截图成功，数据大小: {len(image_data)} bytes")
                return image_data
                
            except FileNotFoundError:
                raise CaptureError(f"IPC管道不存在: {pipe_name}")
            
        except ImportError:
            # Windows API不可用，回退到其他方法
            raise CaptureError("IPC截图需要Windows环境和pywin32库")
        except Exception as e:
            self.logger.error(f"IPC截图异常: {str(e)}")
            raise CaptureError(f"IPC截图异常: {str(e)}")
    
    def is_available(self) -> bool:
        """
        检查IPC截图是否可用
        
        Returns:
            是否可用
        """
        try:
            import win32file
            pipe_name = f"\\\\.\\pipe\\MuMu_Screenshot_{self.instance_id}"
            
            # 尝试连接管道
            handle = win32file.CreateFile(
                pipe_name,
                win32file.GENERIC_READ,
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None
            )
            
            win32file.CloseHandle(handle)
            return True
            
        except:
            return False
    
    async def capture_fast(self) -> bytes:
        """
        快速截图（无缓存）
        
        Returns:
            PNG图像数据
        """
        return await self.capture(use_cache=False)