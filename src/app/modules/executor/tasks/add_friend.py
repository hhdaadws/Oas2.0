"""
加好友任务实现
"""
import asyncio
from typing import List, Tuple
from .base_task import BaseTask, TaskContext, TaskResult, TaskStatus
from ....core.logger import logger


class AddFriendTask(BaseTask):
    """加好友任务"""
    
    def __init__(self):
        super().__init__()
        self.name = "加好友任务"
        self.timeout = 120  # 2分钟超时
        self.logger = logger.bind(task="add_friend")
    
    async def execute(self, context: TaskContext) -> TaskResult:
        """
        执行加好友任务
        
        流程：
        1. 导航到好友界面
        2. 进入添加好友页面
        3. 搜索推荐好友
        4. 批量添加好友
        5. 确认添加结果
        """
        start_time = datetime.now()
        screenshots = []
        added_count = 0
        
        try:
            self.logger.info(f"开始执行加好友任务: 账号={context.account_login_id}")
            
            # 步骤1: 导航到好友界面
            nav_result = await self._navigate_to_friend_page(context)
            if not nav_result:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="无法导航到好友界面",
                    duration=(datetime.now() - start_time).total_seconds()
                )
            
            # 步骤2: 进入添加好友页面
            add_page_result = await self._navigate_to_add_friend_page(context)
            if not add_page_result:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="无法打开添加好友页面",
                    duration=(datetime.now() - start_time).total_seconds()
                )
            
            # 步骤3: 批量添加好友
            max_attempts = 10  # 最多尝试添加10个好友
            attempt_count = 0
            
            while attempt_count < max_attempts:
                # 查找可添加的好友
                friend_found = await self._find_available_friend(context)
                if not friend_found:
                    break
                
                # 添加好友
                add_result = await self._add_single_friend(context)
                if add_result:
                    added_count += 1
                    self.logger.info(f"成功添加第{added_count}个好友")
                
                attempt_count += 1
                await asyncio.sleep(1)  # 短暂间隔
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return TaskResult(
                status=TaskStatus.SUCCESS,
                message=f"加好友任务完成，成功添加{added_count}个好友",
                duration=duration,
                screenshots=screenshots,
                data={"added_count": added_count}
            )
            
        except Exception as e:
            self.logger.error(f"加好友任务异常: {str(e)}")
            duration = (datetime.now() - start_time).total_seconds()
            return TaskResult(
                status=TaskStatus.FAILED,
                message=f"任务异常: {str(e)}",
                duration=duration,
                error=str(e)
            )
    
    async def _navigate_to_friend_page(self, context: TaskContext) -> bool:
        """导航到好友界面"""
        try:
            screenshot = await context.capture_engine.capture()
            
            friend_entrance = await context.vision_engine.match_template(
                screenshot,
                "friend_entrance",
                threshold=0.8
            )
            
            if friend_entrance.found:
                await context.emulator_adapter.tap(
                    friend_entrance.center_x,
                    friend_entrance.center_y
                )
                await asyncio.sleep(2)
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"导航到好友界面失败: {str(e)}")
            return False
    
    async def _navigate_to_add_friend_page(self, context: TaskContext) -> bool:
        """进入添加好友页面"""
        try:
            screenshot = await context.capture_engine.capture()
            
            add_friend_button = await context.vision_engine.match_template(
                screenshot,
                "add_friend_button",
                threshold=0.8
            )
            
            if add_friend_button.found:
                await context.emulator_adapter.tap(
                    add_friend_button.center_x,
                    add_friend_button.center_y
                )
                await asyncio.sleep(2)
                
                # 点击推荐好友标签
                recommend_tab = await context.vision_engine.match_template(
                    screenshot,
                    "recommend_tab",
                    threshold=0.8
                )
                
                if recommend_tab.found:
                    await context.emulator_adapter.tap(
                        recommend_tab.center_x,
                        recommend_tab.center_y
                    )
                    await asyncio.sleep(1)
                
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"进入添加好友页面失败: {str(e)}")
            return False
    
    async def _find_available_friend(self, context: TaskContext) -> bool:
        """查找可添加的好友"""
        try:
            screenshot = await context.capture_engine.capture()
            
            # 检查是否有可添加的好友
            friend_available = await context.vision_engine.match_template(
                screenshot,
                "friend_add_button",
                threshold=0.8
            )
            
            return friend_available.found
            
        except Exception as e:
            self.logger.error(f"查找好友失败: {str(e)}")
            return False
    
    async def _add_single_friend(self, context: TaskContext) -> bool:
        """添加单个好友"""
        try:
            screenshot = await context.capture_engine.capture()
            
            # 点击添加按钮
            add_button = await context.vision_engine.match_template(
                screenshot,
                "friend_add_button",
                threshold=0.8
            )
            
            if add_button.found:
                await context.emulator_adapter.tap(
                    add_button.center_x,
                    add_button.center_y
                )
                await asyncio.sleep(1)
                
                # 检查是否添加成功
                success_check = await self._check_add_success(context)
                return success_check
            
            return False
            
        except Exception as e:
            self.logger.error(f"添加好友失败: {str(e)}")
            return False
    
    async def _check_add_success(self, context: TaskContext) -> bool:
        """检查添加是否成功"""
        try:
            await asyncio.sleep(1)
            screenshot = await context.capture_engine.capture()
            
            # OCR识别成功提示
            success_text = await context.vision_engine.ocr_text(
                screenshot,
                roi=(300, 250, 200, 100)
            )
            
            for text_result in success_text:
                if "成功" in text_result.text or "已发送" in text_result.text:
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"检查添加结果失败: {str(e)}")
            return False
    
    def get_required_templates(self) -> List[str]:
        """获取所需模板"""
        return [
            "friend_entrance.png",     # 好友入口
            "add_friend_button.png",   # 添加好友按钮
            "recommend_tab.png",       # 推荐好友标签
            "friend_add_button.png"    # 好友添加按钮
        ]
    
    def get_ocr_regions(self) -> List[Tuple[int, int, int, int]]:
        """获取OCR区域"""
        return [
            (300, 250, 200, 100),  # 成功提示区域
            (100, 100, 300, 400)   # 好友列表区域
        ]