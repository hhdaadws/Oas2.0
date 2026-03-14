"""
组队御魂执行器（占位）
"""
from .base import BaseExecutor


class TeamYuhunExecutor(BaseExecutor):
    """组队御魂任务占位执行器。

    实际的组队御魂逻辑需要协调两个模拟器同时执行，
    当前版本仅作占位，直接标记任务完成。
    """

    async def execute(self):
        role = (self.intent_payload or {}).get("role", "unknown")
        partner_id = (self.intent_payload or {}).get("partner_user_id", "?")
        self.logger.info(
            "组队御魂任务占位执行: role={}, partner_user_id={}", role, partner_id
        )
        # TODO: 实际组队御魂逻辑
