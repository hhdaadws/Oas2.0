"""
探索突破任务实现
"""
import asyncio
from typing import List, Tuple
from .base_task import BaseTask, TaskContext, TaskResult, TaskStatus
from ....core.logger import logger


class ExploreTask(BaseTask):
    """探索突破任务"""
    
    def __init__(self):
        super().__init__()
        self.name = "探索突破任务"
        self.timeout = 300  # 5分钟超时
        self.logger = logger.bind(task="explore")
    
    async def execute(self, context: TaskContext) -> TaskResult:
        """
        执行探索突破任务
        
        流程：
        1. 检查当前体力值
        2. 导航到探索界面
        3. 选择探索副本
        4. 执行探索战斗
        5. 处理突破逻辑
        6. 确认完成并返回
        """
        start_time = datetime.now()
        screenshots = []
        ocr_results = []
        
        try:
            self.logger.info(f"开始执行探索突破任务: 账号={context.account_login_id}")
            
            # 步骤1: 检查体力值
            stamina = await self._check_stamina(context)
            if stamina < 100:  # 体力不足
                return TaskResult(
                    status=TaskStatus.SUCCESS,
                    message=f"体力不足({stamina})，跳过探索",
                    duration=(datetime.now() - start_time).total_seconds()
                )
            
            # 步骤2: 导航到探索界面
            nav_result = await self._navigate_to_explore(context)
            if not nav_result:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="无法导航到探索界面",
                    duration=(datetime.now() - start_time).total_seconds()
                )
            
            # 步骤3: 执行探索
            explore_count = 0
            max_explore = 5  # 最多探索5次
            
            while explore_count < max_explore and await self._check_stamina(context) >= 100:
                # 执行一次探索
                result = await self._execute_single_explore(context)
                if result:
                    explore_count += 1
                    self.logger.info(f"完成第{explore_count}次探索")
                    
                    # 检查是否需要突破
                    if await self._check_breakthrough_available(context):
                        breakthrough_result = await self._execute_breakthrough(context)
                        if breakthrough_result:
                            self.logger.info("执行突破成功")
                else:
                    break
                
                await asyncio.sleep(2)  # 短暂休息
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return TaskResult(
                status=TaskStatus.SUCCESS,
                message=f"探索突破任务完成，执行{explore_count}次探索",
                duration=duration,
                screenshots=screenshots,
                ocr_results=ocr_results,
                data={"explore_count": explore_count}
            )
            
        except Exception as e:
            self.logger.error(f"探索突破任务异常: {str(e)}")
            duration = (datetime.now() - start_time).total_seconds()
            return TaskResult(
                status=TaskStatus.FAILED,
                message=f"任务异常: {str(e)}",
                duration=duration,
                error=str(e)
            )
    
    async def _check_stamina(self, context: TaskContext) -> int:
        """检查当前体力值"""
        try:
            # 截图并OCR识别体力区域
            screenshot = await context.capture_engine.capture_roi((50, 50, 150, 50))
            ocr_result = await context.vision_engine.ocr_text(screenshot)
            
            for text_result in ocr_result:
                # 查找数字
                import re
                numbers = re.findall(r'\d+', text_result.text)
                if numbers:
                    return int(numbers[0])
            
            return 0
            
        except Exception as e:
            self.logger.error(f"检查体力失败: {str(e)}")
            return 0
    
    async def _navigate_to_explore(self, context: TaskContext) -> bool:
        """导航到探索界面"""
        try:
            screenshot = await context.capture_engine.capture()
            
            # 寻找探索入口
            explore_entrance = await context.vision_engine.match_template(
                screenshot,
                "explore_entrance",
                threshold=0.8
            )
            
            if explore_entrance.found:
                await context.emulator_adapter.tap(
                    explore_entrance.center_x,
                    explore_entrance.center_y
                )
                await asyncio.sleep(3)
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"导航到探索界面失败: {str(e)}")
            return False
    
    async def _execute_single_explore(self, context: TaskContext) -> bool:
        """执行单次探索"""
        try:
            # 点击探索按钮
            screenshot = await context.capture_engine.capture()
            
            explore_button = await context.vision_engine.match_template(
                screenshot,
                "explore_button",
                threshold=0.8
            )
            
            if explore_button.found:
                await context.emulator_adapter.tap(
                    explore_button.center_x,
                    explore_button.center_y
                )
                
                # 等待战斗完成（检查战斗结束标识）
                await self._wait_battle_complete(context)
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"执行探索失败: {str(e)}")
            return False
    
    async def _wait_battle_complete(self, context: TaskContext, max_wait: int = 60) -> bool:
        """等待战斗完成"""
        try:
            wait_time = 0
            while wait_time < max_wait:
                screenshot = await context.capture_engine.capture()
                
                # 检查战斗完成标识
                battle_complete = await context.vision_engine.match_template(
                    screenshot,
                    "battle_complete",
                    threshold=0.8
                )
                
                if battle_complete.found:
                    # 点击确认
                    await context.emulator_adapter.tap(
                        battle_complete.center_x,
                        battle_complete.center_y
                    )
                    return True
                
                await asyncio.sleep(3)
                wait_time += 3
            
            return False
            
        except Exception as e:
            self.logger.error(f"等待战斗完成失败: {str(e)}")
            return False
    
    async def _check_breakthrough_available(self, context: TaskContext) -> bool:
        """检查是否可以突破"""
        try:
            screenshot = await context.capture_engine.capture()
            
            breakthrough_available = await context.vision_engine.match_template(
                screenshot,
                "breakthrough_available",
                threshold=0.8
            )
            
            return breakthrough_available.found
            
        except Exception as e:
            self.logger.error(f"检查突破可用性失败: {str(e)}")
            return False
    
    async def _execute_breakthrough(self, context: TaskContext) -> bool:
        """执行突破"""
        try:
            screenshot = await context.capture_engine.capture()
            
            breakthrough_button = await context.vision_engine.match_template(
                screenshot,
                "breakthrough_button",
                threshold=0.8
            )
            
            if breakthrough_button.found:
                await context.emulator_adapter.tap(
                    breakthrough_button.center_x,
                    breakthrough_button.center_y
                )
                
                # 等待突破完成
                await self._wait_battle_complete(context)
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"执行突破失败: {str(e)}")
            return False
    
    def get_required_templates(self) -> List[str]:
        """获取所需模板"""
        return [
            "explore_entrance.png",      # 探索入口
            "explore_button.png",        # 探索按钮
            "battle_complete.png",       # 战斗完成
            "breakthrough_available.png", # 可突破标识
            "breakthrough_button.png",   # 突破按钮
            "confirm_button.png"         # 确认按钮
        ]
    
    def get_ocr_regions(self) -> List[Tuple[int, int, int, int]]:
        """获取OCR区域"""
        return [
            (50, 50, 150, 50),     # 体力显示区域
            (400, 300, 200, 100)   # 提示信息区域
        ]