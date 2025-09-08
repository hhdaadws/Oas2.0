"""
阴阳师游戏执行器 - 整合所有基础功能
"""
import asyncio
import os
from typing import Optional, Tuple, List
from .capture.adb_capture import ADBCapture
from .capture.ipc_capture import IPCCapture
from .vision.template import TemplateEngine, MatchResult
from .vision.utils import random_point_in_match_result
from .emulator.adapter import EmulatorAdapter
from ...core.logger import logger


class GameExecutor:
    """阴阳师游戏执行器"""
    
    def __init__(self, adb_addr: str, instance_id: int, use_ipc: bool = False):
        self.adb_addr = adb_addr
        self.instance_id = instance_id
        self.logger = logger.bind(device=adb_addr, module="GameExecutor")
        
        # 初始化模块
        self.emulator = EmulatorAdapter(adb_addr, instance_id)
        self.template_engine = TemplateEngine()
        
        # 选择截图方式
        if use_ipc:
            self.capture = IPCCapture(adb_addr, instance_id)
        else:
            self.capture = ADBCapture(adb_addr)
    
    async def initialize(self) -> bool:
        """
        初始化执行器
        
        Returns:
            是否初始化成功
        """
        try:
            self.logger.info("初始化游戏执行器...")
            
            # 检查模拟器状态
            if not await self.emulator.ensure_running():
                self.logger.error("模拟器未运行或连接失败")
                return False
            
            # 检查截图功能
            if not self.capture.is_available():
                self.logger.error("截图功能不可用")
                return False
            
            # 启动阴阳师
            if not await self.emulator.start_app():
                self.logger.error("启动阴阳师失败")
                return False
            
            self.logger.info("游戏执行器初始化成功")
            return True
            
        except Exception as e:
            self.logger.error(f"初始化执行器失败: {str(e)}")
            return False
    
    async def take_screenshot(self, save_path: Optional[str] = None) -> bytes:
        """
        截图
        
        Args:
            save_path: 保存路径（可选）
            
        Returns:
            图像数据
        """
        try:
            image_data = await self.capture.capture()
            
            if save_path:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, 'wb') as f:
                    f.write(image_data)
                self.logger.debug(f"截图已保存: {save_path}")
            
            return image_data
            
        except Exception as e:
            self.logger.error(f"截图失败: {str(e)}")
            raise
    
    async def find_and_click_template(self, template_name: str, threshold: float = 0.8, 
                                    use_random: bool = True) -> bool:
        """
        查找模板并点击
        
        Args:
            template_name: 模板文件名
            threshold: 匹配阈值
            use_random: 是否在匹配区域内随机点击
            
        Returns:
            是否找到并点击成功
        """
        try:
            # 截图
            screenshot = await self.take_screenshot()
            
            # 模板匹配
            match_result = self.template_engine.match_template(
                screenshot, template_name, threshold
            )
            
            if match_result.found:
                if use_random:
                    # 在匹配区域内随机点击
                    click_x, click_y = random_point_in_match_result(match_result)
                else:
                    # 点击中心点
                    click_x, click_y = match_result.center_x, match_result.center_y
                
                success = await self.emulator.tap(click_x, click_y)
                
                if success:
                    self.logger.info(
                        f"模板点击成功: {template_name}, "
                        f"匹配置信度: {match_result.confidence:.3f}, "
                        f"点击位置: ({click_x}, {click_y})"
                    )
                return success
            else:
                self.logger.debug(f"未找到模板: {template_name}")
                return False
            
        except Exception as e:
            self.logger.error(f"模板点击失败: {template_name}, 错误: {str(e)}")
            return False
    
    async def wait_for_template(self, template_name: str, timeout: int = 30, 
                              check_interval: float = 1.0) -> Optional[MatchResult]:
        """
        等待模板出现
        
        Args:
            template_name: 模板文件名
            timeout: 超时时间（秒）
            check_interval: 检查间隔（秒）
            
        Returns:
            匹配结果，超时返回None
        """
        try:
            start_time = asyncio.get_event_loop().time()
            
            while True:
                # 检查是否超时
                if asyncio.get_event_loop().time() - start_time > timeout:
                    self.logger.debug(f"等待模板超时: {template_name}")
                    return None
                
                # 截图并检查
                screenshot = await self.take_screenshot()
                match_result = self.template_engine.match_template(
                    screenshot, template_name, 0.8
                )
                
                if match_result.found:
                    self.logger.debug(f"模板出现: {template_name}")
                    return match_result
                
                await asyncio.sleep(check_interval)
            
        except Exception as e:
            self.logger.error(f"等待模板失败: {template_name}, 错误: {str(e)}")
            return None
    
    async def click_random_in_area(self, x: int, y: int, width: int, height: int) -> bool:
        """
        在指定区域内随机点击
        
        Args:
            x: 区域左上角X
            y: 区域左上角Y
            width: 区域宽度
            height: 区域高度
            
        Returns:
            是否点击成功
        """
        return await self.emulator.tap_random_in_area(x, y, width, height)
    
    async def find_templates_and_click_best(self, template_names: List[str], 
                                          threshold: float = 0.8) -> bool:
        """
        查找多个模板并点击最佳匹配
        
        Args:
            template_names: 模板名称列表
            threshold: 匹配阈值
            
        Returns:
            是否找到并点击成功
        """
        try:
            screenshot = await self.take_screenshot()
            
            best_template, best_result = self.template_engine.find_best_match(
                screenshot, template_names, threshold
            )
            
            if best_template and best_result:
                # 在最佳匹配区域内随机点击
                click_x, click_y = random_point_in_match_result(best_result)
                success = await self.emulator.tap(click_x, click_y)
                
                if success:
                    self.logger.info(f"最佳模板点击成功: {best_template}")
                
                return success
            
            return False
            
        except Exception as e:
            self.logger.error(f"多模板匹配点击失败: {str(e)}")
            return False
    
    async def stop_onmyoji_game(self) -> bool:
        """
        关闭阴阳师游戏
        
        Returns:
            是否关闭成功
        """
        try:
            self.logger.info("关闭阴阳师游戏...")
            return await self.emulator.stop_app()
            
        except Exception as e:
            self.logger.error(f"关闭阴阳师失败: {str(e)}")
            return False
    
    async def restart_onmyoji_game(self) -> bool:
        """
        重启阴阳师游戏
        
        Returns:
            是否重启成功
        """
        try:
            self.logger.info("重启阴阳师游戏...")
            return await self.emulator.restart_app()
            
        except Exception as e:
            self.logger.error(f"重启阴阳师失败: {str(e)}")
            return False
    
    async def is_onmyoji_running(self) -> bool:
        """
        检查阴阳师是否在运行
        
        Returns:
            是否在前台运行
        """
        return await self.emulator._is_app_foreground()
    
    async def start_onmyoji_game(self) -> bool:
        """
        启动阴阳师游戏并等待进入主界面
        
        Returns:
            是否启动成功
        """
        try:
            self.logger.info("启动阴阳师游戏...")
            
            # 启动应用
            if not await self.emulator.start_app():
                return False
            
            # 等待游戏加载完成（检查主界面标识）
            main_screen = await self.wait_for_template("main_screen.png", timeout=60)
            
            if main_screen:
                self.logger.info("阴阳师主界面加载完成")
                return True
            else:
                self.logger.warning("等待主界面超时")
                return False
            
        except Exception as e:
            self.logger.error(f"启动阴阳师失败: {str(e)}")
            return False
    
    def cleanup(self):
        """清理资源"""
        try:
            if hasattr(self.capture, 'clear_cache'):
                self.capture.clear_cache()
            
            self.logger.debug("执行器资源清理完成")
            
        except Exception as e:
            self.logger.error(f"清理资源失败: {str(e)}")