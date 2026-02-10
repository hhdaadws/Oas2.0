"""
Executor types and data structures
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ...core.constants import TaskType


@dataclass
class TaskIntent:
    account_id: int
    task_type: TaskType
    enqueue_time: datetime = field(default_factory=datetime.utcnow)
    payload: dict = field(default_factory=dict)
    started_at: Optional[datetime] = None
