"""
ADB截图实现
"""
import asyncio
import subprocess
from typing import Optional
from .base import BaseCapture, CaptureError
from ....core.logger import logger


class ADBCapture(BaseCapture):
    """ADB截图实现"""
    
    def __init__(self, device_id: str, adb_path: str = "adb"):
        super().__init__(device_id)
        self.adb_path = adb_path
        self.logger = logger.bind(device=device_id, module="ADBCapture")
    
    async def _capture_raw(self) -> bytes:
        """
        使用ADB截图
        
        Returns:
            PNG图像数据
            
        Raises:
            CaptureError: 截图失败
        """
        try:
            # 构建ADB命令
            cmd = [
                self.adb_path,
                "-s", self.device_id,
                "exec-out",
                "screencap", "-p"
            ]
            
            # 执行截图命令
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10.0
            )
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8') if stderr else "未知错误"
                raise CaptureError(f"ADB截图命令失败: {error_msg}")
            
            if not stdout:
                raise CaptureError("ADB截图返回空数据")
            
            self.logger.debug(f"ADB截图成功，数据大小: {len(stdout)} bytes")
            return stdout
            
        except asyncio.TimeoutError:
            raise CaptureError("ADB截图超时")
        except Exception as e:
            self.logger.error(f"ADB截图异常: {str(e)}")
            raise CaptureError(f"ADB截图异常: {str(e)}")
    
    def is_available(self) -> bool:
        """
        检查ADB是否可用
        
        Returns:
            是否可用
        """
        try:
            # 检查ADB连接
            cmd = [self.adb_path, "-s", self.device_id, "get-state"]
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            return result.returncode == 0 and result.stdout.strip() == "device"
        except Exception as e:
            self.logger.error(f"检查ADB连接失败: {str(e)}")
            return False
    
    async def ensure_connected(self) -> bool:
        """
        确保ADB连接
        
        Returns:
            是否连接成功
        """
        try:
            # 尝试连接设备
            if ":" in self.device_id:
                # 网络设备，需要先连接
                host_port = self.device_id
                cmd = [self.adb_path, "connect", host_port]
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                await process.communicate()
            
            # 检查连接状态
            return self.is_available()
            
        except Exception as e:
            self.logger.error(f"ADB连接失败: {str(e)}")
            return False