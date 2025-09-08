"""
寄养任务实现
"""
import asyncio
from typing import List, Tuple
from .base_task import BaseTask, TaskContext, TaskResult, TaskStatus
from ....core.logger import logger


class FosterTask(BaseTask):
    """寄养任务"""
    
    def __init__(self):
        super().__init__()
        self.name = "寄养任务"
        self.timeout = 120  # 2分钟超时
        self.logger = logger.bind(task="foster")
    
    async def execute(self, context: TaskContext) -> TaskResult:
        """
        执行寄养任务
        
        流程：
        1. 截图检查当前界面
        2. 导航到寄养界面
        3. 检查可寄养的式神
        4. 执行寄养操作
        5. 确认寄养成功
        """
        start_time = datetime.now()
        screenshots = []
        ocr_results = []
        template_results = []
        
        try:
            self.logger.info(f"开始执行寄养任务: 账号={context.account_login_id}")
            
            # 步骤1: 截图检查当前界面
            screenshot = await context.capture_engine.capture()
            screenshots.append(self._save_screenshot(screenshot, "initial"))
            
            # 步骤2: 导航到寄养界面
            nav_result = await self._navigate_to_foster_page(context)
            if not nav_result:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="无法导航到寄养界面",
                    duration=(datetime.now() - start_time).total_seconds(),
                    screenshots=screenshots
                )
            
            # 步骤3: 检查可寄养的式神
            foster_available = await self._check_foster_available(context)
            if not foster_available:
                return TaskResult(
                    status=TaskStatus.SUCCESS,
                    message="暂无可寄养的式神，跳过",
                    duration=(datetime.now() - start_time).total_seconds(),
                    screenshots=screenshots
                )
            
            # 步骤4: 执行寄养操作
            foster_result = await self._execute_foster(context)
            if not foster_result:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="寄养操作失败",
                    duration=(datetime.now() - start_time).total_seconds(),
                    screenshots=screenshots
                )
            
            # 步骤5: 确认寄养成功
            success = await self._confirm_foster_success(context)
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if success:
                self.logger.info(f"寄养任务完成: 账号={context.account_login_id}")
                return TaskResult(
                    status=TaskStatus.SUCCESS,
                    message="寄养任务执行成功",
                    duration=duration,
                    screenshots=screenshots,
                    ocr_results=ocr_results,
                    template_results=template_results
                )
            else:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="寄养结果确认失败",
                    duration=duration,
                    screenshots=screenshots
                )
            
        except Exception as e:
            self.logger.error(f"寄养任务异常: {str(e)}")
            duration = (datetime.now() - start_time).total_seconds()
            return TaskResult(
                status=TaskStatus.FAILED,
                message=f"任务异常: {str(e)}",
                duration=duration,
                screenshots=screenshots,
                error=str(e)
            )
    
    async def _navigate_to_foster_page(self, context: TaskContext) -> bool:
        """导航到寄养界面"""
        try:
            # 模板匹配寻找寄养入口
            screenshot = await context.capture_engine.capture()
            
            foster_entrance = await context.vision_engine.match_template(
                screenshot, 
                "foster_entrance",
                threshold=0.8
            )
            
            if foster_entrance.found:
                # 点击寄养入口
                await context.emulator_adapter.tap(
                    foster_entrance.center_x,
                    foster_entrance.center_y
                )
                await asyncio.sleep(2)  # 等待界面加载
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"导航失败: {str(e)}")
            return False
    
    async def _check_foster_available(self, context: TaskContext) -> bool:
        """检查是否有可寄养的式神"""
        try:
            screenshot = await context.capture_engine.capture()
            
            # 模板匹配寻找可寄养标识
            available_mark = await context.vision_engine.match_template(
                screenshot,
                "foster_available",
                threshold=0.7
            )
            
            return available_mark.found
            
        except Exception as e:
            self.logger.error(f"检查寄养可用性失败: {str(e)}")
            return False
    
    async def _execute_foster(self, context: TaskContext) -> bool:
        """执行寄养操作"""
        try:
            # 找到并点击寄养按钮
            screenshot = await context.capture_engine.capture()
            
            foster_button = await context.vision_engine.match_template(
                screenshot,
                "foster_button",
                threshold=0.8
            )
            
            if foster_button.found:
                await context.emulator_adapter.tap(
                    foster_button.center_x,
                    foster_button.center_y
                )
                await asyncio.sleep(1)
                
                # 确认寄养
                confirm_button = await context.vision_engine.match_template(
                    screenshot,
                    "confirm_button",
                    threshold=0.8
                )
                
                if confirm_button.found:
                    await context.emulator_adapter.tap(
                        confirm_button.center_x,
                        confirm_button.center_y
                    )
                    await asyncio.sleep(2)
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"寄养操作失败: {str(e)}")
            return False
    
    async def _confirm_foster_success(self, context: TaskContext) -> bool:
        """确认寄养成功"""
        try:
            screenshot = await context.capture_engine.capture()
            
            # OCR识别成功提示文字
            success_text = await context.vision_engine.ocr_text(
                screenshot,
                roi=(400, 300, 200, 100)  # 成功提示区域
            )
            
            # 检查是否包含成功关键词
            for text_result in success_text:
                if "成功" in text_result.text or "寄养" in text_result.text:
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"确认寄养结果失败: {str(e)}")
            return False
    
    def get_required_templates(self) -> List[str]:
        """获取所需模板"""
        return [
            "foster_entrance.png",    # 寄养入口
            "foster_available.png",   # 可寄养标识
            "foster_button.png",      # 寄养按钮
            "confirm_button.png"      # 确认按钮
        ]
    
    def get_ocr_regions(self) -> List[Tuple[int, int, int, int]]:
        """获取OCR区域"""
        return [
            (400, 300, 200, 100),  # 成功提示区域
            (50, 50, 150, 50)      # 体力显示区域
        ]
    
    def _save_screenshot(self, image_data: bytes, suffix: str) -> str:
        """保存截图文件"""
        import os
        from datetime import datetime
        
        # 创建截图目录
        screenshot_dir = "screenshots"
        os.makedirs(screenshot_dir, exist_ok=True)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"foster_{suffix}_{timestamp}.png"
        filepath = os.path.join(screenshot_dir, filename)
        
        # 保存文件
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        return filepath