from types import SimpleNamespace

import pytest

from app.core.constants import TaskStatus, TaskType
from app.modules.executor.base import BaseExecutor
from app.modules.ui.manager import CangbaogeListedException


class _RaiseOnExecuteExecutor(BaseExecutor):
    def __init__(self, *, error: Exception):
        super().__init__(worker_id=1, emulator_id=1)
        self._error = error
        self.cleaned = False

    async def prepare(self, task, account) -> bool:
        return True

    async def execute(self):
        raise self._error

    async def cleanup(self):
        self.cleaned = True


@pytest.mark.asyncio
async def test_run_task_reraises_cangbaoge_exception():
    executor = _RaiseOnExecuteExecutor(
        error=CangbaogeListedException("cangbaoge listed")
    )
    task = SimpleNamespace(type=TaskType.ADD_FRIEND)
    account = SimpleNamespace(login_id="test_login")

    with pytest.raises(CangbaogeListedException):
        await executor.run_task(task, account)

    assert executor.cleaned is True


@pytest.mark.asyncio
async def test_run_task_still_catches_generic_exception():
    executor = _RaiseOnExecuteExecutor(error=RuntimeError("boom"))
    task = SimpleNamespace(type=TaskType.ADD_FRIEND)
    account = SimpleNamespace(login_id="test_login")

    result = await executor.run_task(task, account)

    assert result["status"] == TaskStatus.FAILED
    assert "boom" in result["error"]
    assert executor.cleaned is True
