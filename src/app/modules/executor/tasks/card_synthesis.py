"""
结界卡合成任务实现
"""
import asyncio
from typing import List, Tuple
from .base_task import BaseTask, TaskContext, TaskResult, TaskStatus
from ....core.logger import logger


class CardSynthesisTask(BaseTask):
    """结界卡合成任务"""
    
    def __init__(self):
        super().__init__()
        self.name = "结界卡合成任务"
        self.timeout = 180  # 3分钟超时
        self.logger = logger.bind(task="card_synthesis")
    
    async def execute(self, context: TaskContext) -> TaskResult:
        """
        执行结界卡合成任务
        
        流程：
        1. 导航到结界卡界面
        2. 检查可合成的卡片
        3. 执行合成操作
        4. 确认合成结果
        """
        start_time = datetime.now()
        screenshots = []
        synthesis_count = 0
        
        try:
            self.logger.info(f"开始执行结界卡合成任务: 账号={context.account_login_id}")
            
            # 步骤1: 导航到结界卡界面
            nav_result = await self._navigate_to_card_page(context)
            if not nav_result:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="无法导航到结界卡界面",
                    duration=(datetime.now() - start_time).total_seconds()
                )
            
            # 步骤2: 进入合成页面
            synthesis_page_result = await self._navigate_to_synthesis_page(context)
            if not synthesis_page_result:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="无法进入合成页面",
                    duration=(datetime.now() - start_time).total_seconds()
                )
            
            # 步骤3: 批量合成
            max_synthesis = 20  # 最多合成20次
            
            for i in range(max_synthesis):
                # 检查是否还有可合成的卡片
                can_synthesis = await self._check_synthesis_available(context)
                if not can_synthesis:
                    break
                
                # 执行单次合成
                synthesis_result = await self._execute_single_synthesis(context)
                if synthesis_result:
                    synthesis_count += 1
                    self.logger.info(f"完成第{synthesis_count}次合成")
                else:
                    break
                
                await asyncio.sleep(1)
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return TaskResult(
                status=TaskStatus.SUCCESS,
                message=f"结界卡合成任务完成，合成{synthesis_count}张卡片",
                duration=duration,
                screenshots=screenshots,
                data={"synthesis_count": synthesis_count}
            )
            
        except Exception as e:
            self.logger.error(f"结界卡合成任务异常: {str(e)}")
            duration = (datetime.now() - start_time).total_seconds()
            return TaskResult(
                status=TaskStatus.FAILED,
                message=f"任务异常: {str(e)}",
                duration=duration,
                error=str(e)
            )
    
    async def _navigate_to_card_page(self, context: TaskContext) -> bool:
        """导航到结界卡界面"""
        try:
            screenshot = await context.capture_engine.capture()
            
            card_entrance = await context.vision_engine.match_template(
                screenshot,
                "card_entrance",
                threshold=0.8
            )
            
            if card_entrance.found:
                await context.emulator_adapter.tap(
                    card_entrance.center_x,
                    card_entrance.center_y
                )
                await asyncio.sleep(2)
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"导航到结界卡界面失败: {str(e)}")
            return False
    
    async def _navigate_to_synthesis_page(self, context: TaskContext) -> bool:
        """进入合成页面"""
        try:
            screenshot = await context.capture_engine.capture()
            
            synthesis_tab = await context.vision_engine.match_template(
                screenshot,
                "synthesis_tab",
                threshold=0.8
            )
            
            if synthesis_tab.found:
                await context.emulator_adapter.tap(
                    synthesis_tab.center_x,
                    synthesis_tab.center_y
                )
                await asyncio.sleep(2)
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"进入合成页面失败: {str(e)}")
            return False
    
    async def _check_synthesis_available(self, context: TaskContext) -> bool:
        """检查是否可以合成"""
        try:
            screenshot = await context.capture_engine.capture()
            
            # 检查合成按钮是否可用（非灰色）
            synthesis_button = await context.vision_engine.match_template(
                screenshot,
                "synthesis_button_active",
                threshold=0.8
            )
            
            return synthesis_button.found
            
        except Exception as e:
            self.logger.error(f"检查合成可用性失败: {str(e)}")
            return False
    
    async def _execute_single_synthesis(self, context: TaskContext) -> bool:
        """执行单次合成"""
        try:
            screenshot = await context.capture_engine.capture()
            
            # 点击合成按钮
            synthesis_button = await context.vision_engine.match_template(
                screenshot,
                "synthesis_button_active",
                threshold=0.8
            )
            
            if synthesis_button.found:
                await context.emulator_adapter.tap(
                    synthesis_button.center_x,
                    synthesis_button.center_y
                )
                await asyncio.sleep(1)
                
                # 确认合成
                confirm_synthesis = await context.vision_engine.match_template(
                    screenshot,
                    "confirm_synthesis",
                    threshold=0.8
                )
                
                if confirm_synthesis.found:
                    await context.emulator_adapter.tap(
                        confirm_synthesis.center_x,
                        confirm_synthesis.center_y
                    )
                    await asyncio.sleep(2)
                    
                    # 检查合成结果
                    return await self._check_synthesis_result(context)
            
            return False
            
        except Exception as e:
            self.logger.error(f"执行合成失败: {str(e)}")
            return False
    
    async def _check_synthesis_result(self, context: TaskContext) -> bool:
        """检查合成结果"""
        try:
            screenshot = await context.capture_engine.capture()
            
            # OCR识别合成结果
            result_text = await context.vision_engine.ocr_text(
                screenshot,
                roi=(300, 300, 200, 100)
            )
            
            for text_result in result_text:
                if "合成成功" in text_result.text or "获得" in text_result.text:
                    # 点击确认关闭结果提示
                    await context.emulator_adapter.tap(400, 400)
                    await asyncio.sleep(1)
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"检查合成结果失败: {str(e)}")
            return False
    
    def get_required_templates(self) -> List[str]:
        """获取所需模板"""
        return [
            "card_entrance.png",          # 结界卡入口
            "synthesis_tab.png",          # 合成标签
            "synthesis_button_active.png", # 可用合成按钮
            "confirm_synthesis.png"       # 确认合成按钮
        ]
    
    def get_ocr_regions(self) -> List[Tuple[int, int, int, int]]:
        """获取OCR区域"""
        return [
            (300, 300, 200, 100),  # 合成结果区域
            (500, 50, 100, 50)     # 材料数量区域
        ]