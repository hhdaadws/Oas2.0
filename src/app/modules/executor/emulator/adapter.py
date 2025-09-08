"""
模拟器适配器
"""
import asyncio
import subprocess
from typing import Optional, Tuple
from ....core.logger import logger
from ..vision.utils import add_random_offset, ensure_point_in_screen, calculate_click_delay


class EmulatorError(Exception):
    """模拟器操作异常"""
    pass


class EmulatorAdapter:
    """模拟器适配器"""
    
    def __init__(self, adb_addr: str, instance_id: int, adb_path: str = "adb"):
        self.adb_addr = adb_addr
        self.instance_id = instance_id
        self.adb_path = adb_path
        self.package_name = "com.netease.onmyoji"  # 阴阳师包名
        self.logger = logger.bind(device=adb_addr, module="EmulatorAdapter")
    
    async def ensure_running(self) -> bool:
        """
        确保模拟器运行
        
        Returns:
            是否成功启动
        """
        try:
            # 检查ADB连接
            if not await self._check_adb_connection():
                return False
            
            # 检查模拟器状态
            if not await self._check_emulator_state():
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"确保模拟器运行失败: {str(e)}")
            return False
    
    async def start_app(self) -> bool:
        """
        启动阴阳师应用
        
        Returns:
            是否启动成功
        """
        try:
            # 检查应用是否已在前台
            if await self._is_app_foreground():
                self.logger.info("阴阳师已在前台运行")
                return True
            
            # 启动应用
            cmd = [
                self.adb_path, "-s", self.adb_addr,
                "shell", "monkey", "-p", self.package_name,
                "-c", "android.intent.category.LAUNCHER", "1"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                self.logger.info("阴阳师启动命令执行成功")
                # 等待应用启动
                await asyncio.sleep(5)
                
                # 验证应用是否启动
                return await self._is_app_foreground()
            else:
                error_msg = stderr.decode('utf-8') if stderr else "未知错误"
                raise EmulatorError(f"启动应用命令失败: {error_msg}")
            
        except Exception as e:
            self.logger.error(f"启动阴阳师失败: {str(e)}")
            return False
    
    async def tap(self, x: int, y: int, add_random: bool = True) -> bool:
        """
        点击指定坐标
        
        Args:
            x: X坐标
            y: Y坐标
            add_random: 是否添加随机偏移
            
        Returns:
            是否点击成功
        """
        try:
            # 添加随机偏移模拟人类操作
            if add_random:
                x, y = add_random_offset(x, y)
            
            # 确保坐标在屏幕范围内
            x, y = ensure_point_in_screen(x, y)
            
            # 执行点击
            cmd = [
                self.adb_path, "-s", self.adb_addr,
                "shell", "input", "tap", str(x), str(y)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            if process.returncode == 0:
                self.logger.debug(f"点击成功: ({x}, {y})")
                
                # 添加随机延迟
                if add_random:
                    delay = calculate_click_delay()
                    await asyncio.sleep(delay)
                
                return True
            else:
                raise EmulatorError("点击命令执行失败")
            
        except Exception as e:
            self.logger.error(f"点击操作失败: ({x}, {y}), 错误: {str(e)}")
            return False
    
    async def tap_random_in_area(self, x: int, y: int, width: int, height: int) -> bool:
        """
        在指定区域内随机点击
        
        Args:
            x: 区域左上角X坐标
            y: 区域左上角Y坐标
            width: 区域宽度
            height: 区域高度
            
        Returns:
            是否点击成功
        """
        from ..vision.utils import random_point_in_rect
        
        random_x, random_y = random_point_in_rect(x, y, width, height)
        return await self.tap(random_x, random_y, add_random=False)  # 已经是随机点了
    
    async def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> bool:
        """
        滑动操作
        
        Args:
            x1: 起始X坐标
            y1: 起始Y坐标
            x2: 结束X坐标
            y2: 结束Y坐标
            duration: 滑动时长（毫秒）
            
        Returns:
            是否滑动成功
        """
        try:
            cmd = [
                self.adb_path, "-s", self.adb_addr,
                "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            if process.returncode == 0:
                self.logger.debug(f"滑动成功: ({x1}, {y1}) -> ({x2}, {y2})")
                return True
            else:
                raise EmulatorError("滑动命令执行失败")
            
        except Exception as e:
            self.logger.error(f"滑动操作失败: {str(e)}")
            return False
    
    async def press_back(self) -> bool:
        """按返回键"""
        try:
            cmd = [
                self.adb_path, "-s", self.adb_addr,
                "shell", "input", "keyevent", "KEYCODE_BACK"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            return process.returncode == 0
            
        except Exception as e:
            self.logger.error(f"按返回键失败: {str(e)}")
            return False
    
    async def _check_adb_connection(self) -> bool:
        """检查ADB连接"""
        try:
            cmd = [self.adb_path, "-s", self.adb_addr, "get-state"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return result.returncode == 0 and result.stdout.strip() == "device"
        except Exception:
            return False
    
    async def _check_emulator_state(self) -> bool:
        """检查模拟器状态"""
        try:
            # 检查屏幕是否亮着
            cmd = [self.adb_path, "-s", self.adb_addr, "shell", "dumpsys", "power"]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, _ = await process.communicate()
            output = stdout.decode('utf-8')
            
            # 检查是否唤醒状态
            return "mWakefulness=Awake" in output
            
        except Exception as e:
            self.logger.error(f"检查模拟器状态失败: {str(e)}")
            return False
    
    async def _is_app_foreground(self) -> bool:
        """检查阴阳师是否在前台"""
        try:
            cmd = [
                self.adb_path, "-s", self.adb_addr,
                "shell", "dumpsys", "activity", "activities"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, _ = await process.communicate()
            output = stdout.decode('utf-8')
            
            # 检查阴阳师是否在前台
            return self.package_name in output and "mResumedActivity" in output
            
        except Exception as e:
            self.logger.error(f"检查应用前台状态失败: {str(e)}")
            return False
    
    async def ensure_app_foreground(self) -> bool:
        """确保阴阳师在前台"""
        if await self._is_app_foreground():
            return True
        
        return await self.start_app()