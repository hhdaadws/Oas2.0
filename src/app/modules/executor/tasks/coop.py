"""
勾协任务实现
"""
import asyncio
from typing import List, Tuple
from .base_task import BaseTask, TaskContext, TaskResult, TaskStatus
from ....core.logger import logger


class CoopTask(BaseTask):
    """勾协任务"""
    
    def __init__(self):
        super().__init__()
        self.name = "勾协任务"
        self.timeout = 180  # 3分钟超时
        self.logger = logger.bind(task="coop")
    
    async def execute(self, context: TaskContext) -> TaskResult:
        """
        执行勾协任务
        
        流程：
        1. 导航到勾协界面
        2. 检查勾协状态
        3. 创建或加入勾协房间
        4. 等待勾协开始
        5. 执行勾协战斗
        6. 确认完成
        """
        start_time = datetime.now()
        screenshots = []
        
        try:
            self.logger.info(f"开始执行勾协任务: 账号={context.account_login_id}")
            
            # 步骤1: 导航到勾协界面
            nav_result = await self._navigate_to_coop_page(context)
            if not nav_result:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="无法导航到勾协界面",
                    duration=(datetime.now() - start_time).total_seconds()
                )
            
            # 步骤2: 检查勾协状态
            coop_status = await self._check_coop_status(context)
            
            if coop_status == "in_room":
                # 已在房间中，等待开始
                result = await self._wait_coop_start(context)
            elif coop_status == "available":
                # 创建或加入房间
                result = await self._create_or_join_coop(context)
                if result:
                    result = await self._wait_coop_start(context)
            else:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="勾协不可用",
                    duration=(datetime.now() - start_time).total_seconds()
                )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if result:
                return TaskResult(
                    status=TaskStatus.SUCCESS,
                    message="勾协任务执行成功",
                    duration=duration,
                    screenshots=screenshots
                )
            else:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="勾协任务执行失败",
                    duration=duration,
                    screenshots=screenshots
                )
            
        except Exception as e:
            self.logger.error(f"勾协任务异常: {str(e)}")
            duration = (datetime.now() - start_time).total_seconds()
            return TaskResult(
                status=TaskStatus.FAILED,
                message=f"任务异常: {str(e)}",
                duration=duration,
                error=str(e)
            )
    
    async def _navigate_to_coop_page(self, context: TaskContext) -> bool:
        """导航到勾协界面"""
        try:
            screenshot = await context.capture_engine.capture()
            
            coop_entrance = await context.vision_engine.match_template(
                screenshot,
                "coop_entrance",
                threshold=0.8
            )
            
            if coop_entrance.found:
                await context.emulator_adapter.tap(
                    coop_entrance.center_x,
                    coop_entrance.center_y
                )
                await asyncio.sleep(3)
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"导航到勾协界面失败: {str(e)}")
            return False
    
    async def _check_coop_status(self, context: TaskContext) -> str:
        """
        检查勾协状态
        
        Returns:
            "unavailable": 不可用
            "available": 可用
            "in_room": 已在房间中
        """
        try:
            screenshot = await context.capture_engine.capture()
            
            # 检查是否已在房间中
            in_room = await context.vision_engine.match_template(
                screenshot,
                "coop_in_room",
                threshold=0.8
            )
            
            if in_room.found:
                return "in_room"
            
            # 检查是否可创建勾协
            available = await context.vision_engine.match_template(
                screenshot,
                "coop_available",
                threshold=0.8
            )
            
            if available.found:
                return "available"
            
            return "unavailable"
            
        except Exception as e:
            self.logger.error(f"检查勾协状态失败: {str(e)}")
            return "unavailable"
    
    async def _create_or_join_coop(self, context: TaskContext) -> bool:
        """创建或加入勾协"""
        try:
            # 先尝试加入现有房间
            if await self._try_join_existing_room(context):
                return True
            
            # 如果没有房间，创建新房间
            return await self._create_new_room(context)
            
        except Exception as e:
            self.logger.error(f"创建或加入勾协失败: {str(e)}")
            return False
    
    async def _try_join_existing_room(self, context: TaskContext) -> bool:
        """尝试加入现有房间"""
        try:
            screenshot = await context.capture_engine.capture()
            
            join_room = await context.vision_engine.match_template(
                screenshot,
                "coop_join_room",
                threshold=0.8
            )
            
            if join_room.found:
                await context.emulator_adapter.tap(
                    join_room.center_x,
                    join_room.center_y
                )
                await asyncio.sleep(2)
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"加入房间失败: {str(e)}")
            return False
    
    async def _create_new_room(self, context: TaskContext) -> bool:
        """创建新房间"""
        try:
            screenshot = await context.capture_engine.capture()
            
            create_room = await context.vision_engine.match_template(
                screenshot,
                "coop_create_room",
                threshold=0.8
            )
            
            if create_room.found:
                await context.emulator_adapter.tap(
                    create_room.center_x,
                    create_room.center_y
                )
                await asyncio.sleep(2)
                
                # 确认创建
                confirm_create = await context.vision_engine.match_template(
                    screenshot,
                    "coop_confirm_create",
                    threshold=0.8
                )
                
                if confirm_create.found:
                    await context.emulator_adapter.tap(
                        confirm_create.center_x,
                        confirm_create.center_y
                    )
                    await asyncio.sleep(3)
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"创建房间失败: {str(e)}")
            return False
    
    async def _wait_coop_start(self, context: TaskContext) -> bool:
        """等待勾协开始"""
        try:
            max_wait = 60  # 最多等待1分钟
            wait_time = 0
            
            while wait_time < max_wait:
                screenshot = await context.capture_engine.capture()
                
                # 检查勾协是否开始
                coop_started = await context.vision_engine.match_template(
                    screenshot,
                    "coop_battle_start",
                    threshold=0.8
                )
                
                if coop_started.found:
                    # 等待战斗完成
                    return await self._wait_coop_battle_complete(context)
                
                await asyncio.sleep(3)
                wait_time += 3
            
            return False
            
        except Exception as e:
            self.logger.error(f"等待勾协开始失败: {str(e)}")
            return False
    
    async def _wait_coop_battle_complete(self, context: TaskContext) -> bool:
        """等待勾协战斗完成"""
        try:
            max_wait = 120  # 最多等待2分钟
            wait_time = 0
            
            while wait_time < max_wait:
                screenshot = await context.capture_engine.capture()
                
                # 检查战斗是否完成
                battle_complete = await context.vision_engine.match_template(
                    screenshot,
                    "coop_battle_complete",
                    threshold=0.8
                )
                
                if battle_complete.found:
                    # 点击确认
                    await context.emulator_adapter.tap(
                        battle_complete.center_x,
                        battle_complete.center_y
                    )
                    await asyncio.sleep(2)
                    return True
                
                await asyncio.sleep(5)
                wait_time += 5
            
            return False
            
        except Exception as e:
            self.logger.error(f"等待勾协战斗完成失败: {str(e)}")
            return False
    
    def get_required_templates(self) -> List[str]:
        """获取所需模板"""
        return [
            "coop_entrance.png",        # 勾协入口
            "coop_available.png",       # 勾协可用
            "coop_in_room.png",         # 已在房间中
            "coop_join_room.png",       # 加入房间
            "coop_create_room.png",     # 创建房间
            "coop_confirm_create.png",  # 确认创建
            "coop_battle_start.png",    # 战斗开始
            "coop_battle_complete.png"  # 战斗完成
        ]
    
    def get_ocr_regions(self) -> List[Tuple[int, int, int, int]]:
        """获取OCR区域"""
        return [
            (400, 200, 200, 50),   # 房间信息区域
            (300, 500, 200, 50)    # 状态提示区域
        ]